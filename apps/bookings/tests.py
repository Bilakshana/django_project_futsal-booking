from datetime import time, timedelta
from unittest.mock import patch

from django.core import mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Role
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.tasks import mark_completed_bookings, release_held_slot, send_booking_reminder
from apps.bookings.testing import make_court, make_slot, make_user
from apps.courts.models import Slot, SlotStatus
from apps.courts.tasks import generate_daily_slots
from apps.payments.models import Paymentlog, PaymentStatus


class DoubleBookingTests(APITestCase):
    def setUp(self):
        self.owner = make_user(Role.OWNER)
        self.alice = make_user()
        self.bob = make_user()
        self.court = make_court(self.owner)
        self.slot = make_slot(self.court)

    def hold(self, user, slot=None):
        self.client.force_authenticate(user)
        return self.client.post("/api/bookings/hold/", {"slot": (slot or self.slot).pk}, format="json")

    def test_hold_creates_pending_booking_payment_log_and_schedules_release(self):
        with patch.object(release_held_slot, "apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.hold(self.alice)

        self.assertEqual(response.status_code, 201, response.data)
        booking = Booking.objects.get()
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.assertEqual(booking.advance_amount, 300)  # 30% of 1000
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, SlotStatus.HELD)
        log = Paymentlog.objects.get()
        self.assertEqual((log.user, log.booking, log.amount), (self.alice, booking, 300))
        self.assertEqual(response.data["data"]["payment_id"], log.pk)
        apply_async.assert_called_once_with(args=[booking.pk], countdown=600)

    def test_second_player_cannot_hold_a_held_slot(self):
        self.assertEqual(self.hold(self.alice).status_code, 201)
        response = self.hold(self.bob)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Booking.objects.get().player, self.alice)

    def test_cannot_hold_a_booked_slot(self):
        self.slot.status = SlotStatus.BOOKED
        self.slot.save()
        self.assertEqual(self.hold(self.alice).status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_cannot_hold_a_slot_that_already_started(self):
        past = make_slot(self.court, start_in=timedelta(hours=-3))
        self.assertEqual(self.hold(self.alice, past).status_code, 400)

    def test_only_players_can_hold(self):
        self.assertEqual(self.hold(self.owner).status_code, 403)

    def test_database_rejects_duplicate_slot(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Slot.objects.create(
                court=self.court, date=self.slot.date, start_time=self.slot.start_time,
                end_time=self.slot.end_time, price=1,
            )

    def test_database_rejects_two_live_bookings_for_one_slot(self):
        def book(player):
            return Booking.objects.create(
                player=player, slot=self.slot, total_price=1000, advance_amount=300,
                held_until=timezone.now(),
            )

        book(self.alice)
        with self.assertRaises(IntegrityError), transaction.atomic():
            book(self.bob)

    def test_expired_booking_does_not_block_a_new_one(self):
        self.hold(self.alice)
        release_held_slot(Booking.objects.get().pk)
        self.assertEqual(self.hold(self.bob).status_code, 201)
        self.assertEqual(Booking.objects.count(), 2)


class ReleaseHeldSlotTests(APITestCase):
    def setUp(self):
        self.owner = make_user(Role.OWNER)
        self.player = make_user()
        self.slot = make_slot(make_court(self.owner))
        self.client.force_authenticate(self.player)
        self.client.post("/api/bookings/hold/", {"slot": self.slot.pk}, format="json")
        self.booking = Booking.objects.get()

    def test_unpaid_hold_is_released(self):
        release_held_slot(self.booking.pk)

        self.booking.refresh_from_db()
        self.slot.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.EXPIRED)
        self.assertEqual(self.slot.status, SlotStatus.AVAILABLE)
        self.assertEqual(Paymentlog.objects.get().status, PaymentStatus.FAILED)

    def test_paid_booking_is_left_alone(self):
        self.booking.status = BookingStatus.CONFIRMED
        self.booking.save()
        self.slot.status = SlotStatus.BOOKED
        self.slot.save()

        release_held_slot(self.booking.pk)

        self.booking.refresh_from_db()
        self.slot.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)
        self.assertEqual(self.slot.status, SlotStatus.BOOKED)

    def test_player_can_cancel_unpaid_booking(self):
        response = self.client.post(f"/api/bookings/{self.booking.pk}/cancel/")
        self.assertEqual(response.status_code, 200)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, SlotStatus.AVAILABLE)

    def test_other_player_cannot_cancel(self):
        self.client.force_authenticate(make_user())
        self.assertEqual(self.client.post(f"/api/bookings/{self.booking.pk}/cancel/").status_code, 404)


class ScheduledTaskTests(APITestCase):
    def setUp(self):
        self.owner = make_user(Role.OWNER)
        self.player = make_user()
        self.court = make_court(self.owner, opening_time=time(6, 0), closing_time=time(9, 0))

    def confirmed_booking(self, slot):
        slot.status = SlotStatus.BOOKED
        slot.save()
        return Booking.objects.create(
            player=self.player, slot=slot, status=BookingStatus.CONFIRMED,
            total_price=slot.price, advance_amount=300, held_until=timezone.now(),
        )

    def test_generate_daily_slots_creates_seven_days_and_is_idempotent(self):
        generate_daily_slots()
        self.assertEqual(Slot.objects.count(), 3 * 7)  # 06-07, 07-08, 08-09 for 7 days
        dates = set(Slot.objects.values_list("date", flat=True))
        self.assertEqual(len(dates), 7)
        self.assertEqual(min(dates), timezone.localdate())

        generate_daily_slots()
        self.assertEqual(Slot.objects.count(), 3 * 7)

    def test_creating_a_court_via_api_generates_its_slots(self):
        self.client.force_authenticate(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/courts/",
                {"name": "New", "location": "Patan", "price_per_slot": 800,
                 "opening_time": "06:00", "closing_time": "08:00"},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Slot.objects.filter(court_id=response.data["id"]).count(), 2 * 7)

    def test_reminder_sent_once_for_booking_starting_within_the_hour(self):
        soon = self.confirmed_booking(make_slot(self.court, start_in=timedelta(minutes=30)))
        self.confirmed_booking(make_slot(self.court, start_in=timedelta(hours=5)))

        send_booking_reminder()
        send_booking_reminder()  # second run must not email again

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.player.email])
        soon.refresh_from_db()
        self.assertTrue(soon.reminder_sent)

    def test_unconfirmed_booking_gets_no_reminder(self):
        slot = make_slot(self.court, start_in=timedelta(minutes=30))
        Booking.objects.create(player=self.player, slot=slot, total_price=1000, advance_amount=300,
                               held_until=timezone.now())
        send_booking_reminder()
        self.assertEqual(len(mail.outbox), 0)

    def test_mark_completed_bookings(self):
        past = self.confirmed_booking(make_slot(self.court, start_in=timedelta(hours=-3)))
        future = self.confirmed_booking(make_slot(self.court, start_in=timedelta(hours=5)))

        mark_completed_bookings()

        past.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(past.status, BookingStatus.COMPLETED)
        self.assertEqual(future.status, BookingStatus.CONFIRMED)
