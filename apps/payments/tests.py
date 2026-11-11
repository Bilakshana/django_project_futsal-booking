from unittest.mock import Mock, patch

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import Role
from apps.bookings.api.service import hold_slot
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.tasks import release_held_slot
from apps.bookings.testing import make_court, make_slot, make_user
from apps.courts.models import SlotStatus
from apps.payments.api.service import KhaltiError
from apps.payments.models import Paymentlog, PaymentStatus
from apps.wallet.models import Statement
from apps.wallet.tasks import credit_wallet

LOOKUP = "apps.payments.views.khalti_lookup"


class PaymentBase(APITestCase):
    def setUp(self):
        self.owner = make_user(Role.OWNER)
        self.player = make_user()
        self.slot = make_slot(make_court(self.owner), price=1000)
        self.booking, self.log = hold_slot(self.player, self.slot.pk)
        self.log.pidx = "pidx-123"
        self.log.status = PaymentStatus.INITIAL
        self.log.save()

    def lookup_result(self, status="Completed", total_amount=None):
        return {
            "pidx": "pidx-123",
            "status": status,
            "total_amount": self.log.amount * 100 if total_amount is None else total_amount,
            "transaction_id": "KH-TXN-1",
        }

    def callback(self, pidx="pidx-123", **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.get(reverse("callback"), {"pidx": pidx, "status": "Completed", **extra})

    def refresh(self):
        for obj in (self.log, self.booking, self.slot, self.owner):
            obj.refresh_from_db()


class InitiatePaymentTests(PaymentBase):
    url = property(lambda self: f"/api/payment/initiate/{self.log.pk}/")

    def post_with_khalti(self, response_json):
        with patch("apps.payments.api.service.requests.post") as post:
            post.return_value = Mock(json=lambda: response_json)
            response = self.client.post(self.url)
        return response, post

    def test_get_is_not_allowed(self):
        self.client.force_authenticate(self.player)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.post(self.url).status_code, 401)

    def test_cannot_initiate_someone_elses_payment(self):
        self.client.force_authenticate(make_user())
        response, post = self.post_with_khalti({"pidx": "x"})
        self.assertEqual(response.status_code, 404)
        post.assert_not_called()

    def test_initiate_calls_khalti_with_clean_auth_header(self):
        self.client.force_authenticate(self.player)
        response, post = self.post_with_khalti({"pidx": "new-pidx", "payment_url": "https://test-pay.khalti.com/?pidx=new-pidx"})

        self.assertEqual(response.status_code, 200)
        args, kwargs = post.call_args
        self.assertTrue(args[0].endswith("/epayment/initiate/"))
        self.assertEqual(kwargs["headers"]["Authorization"], "key test-token")  # no trailing space
        self.assertEqual(kwargs["json"]["amount"], 300 * 100)  # paisa
        self.log.refresh_from_db()
        self.assertEqual((self.log.pidx, self.log.status), ("new-pidx", PaymentStatus.INITIAL))

    def test_khalti_rejection_is_reported_and_not_saved(self):
        self.client.force_authenticate(self.player)
        self.log.pidx, self.log.status = None, PaymentStatus.PENDING
        self.log.save()

        response, _ = self.post_with_khalti({"detail": "Invalid token.", "status_code": 401})

        self.assertEqual(response.status_code, 502)
        self.log.refresh_from_db()
        self.assertIsNone(self.log.pidx)
        self.assertEqual(self.log.status, PaymentStatus.PENDING)

    def test_cannot_initiate_for_expired_booking(self):
        release_held_slot(self.booking.pk)
        self.client.force_authenticate(self.player)
        response, post = self.post_with_khalti({"pidx": "x"})
        self.assertEqual(response.status_code, 400)
        post.assert_not_called()


class PaymentCallbackTests(PaymentBase):
    def test_verified_payment_confirms_booking_and_credits_owner(self):
        with patch(LOOKUP, return_value=self.lookup_result()) as lookup:
            response = self.callback()

        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with("pidx-123")
        self.refresh()
        self.assertEqual(self.log.status, PaymentStatus.COMPLETED)
        self.assertEqual(self.log.khalti_txn_id, "KH-TXN-1")
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)
        self.assertEqual(self.slot.status, SlotStatus.BOOKED)
        self.assertEqual(self.owner.balance, 300)
        statement = Statement.objects.get()
        self.assertEqual((statement.user, statement.amount), (self.owner, 300))

    def test_callback_is_idempotent(self):
        with patch(LOOKUP, return_value=self.lookup_result()) as lookup:
            self.callback()
            second = self.callback()
            third = self.callback()

        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 200)
        self.assertEqual(lookup.call_count, 1)  # completed payments never hit Khalti again
        self.refresh()
        self.assertEqual(self.owner.balance, 300)
        self.assertEqual(Statement.objects.count(), 1)

    def test_credit_wallet_task_is_idempotent(self):
        with patch(LOOKUP, return_value=self.lookup_result()):
            self.callback()
        credit_wallet(self.log.pk)
        credit_wallet(self.log.pk)
        self.refresh()
        self.assertEqual(self.owner.balance, 300)
        self.assertEqual(Statement.objects.count(), 1)

    def test_forged_status_in_query_string_is_ignored(self):
        """The URL says Completed but Khalti says Pending: nothing may change."""
        with patch(LOOKUP, return_value=self.lookup_result(status="Pending")):
            self.callback()

        self.refresh()
        self.assertEqual(self.log.status, PaymentStatus.INITIAL)
        self.assertEqual(self.booking.status, BookingStatus.PENDING)
        self.assertEqual(self.owner.balance, 0)
        self.assertEqual(Statement.objects.count(), 0)

    def test_wrong_amount_is_not_accepted(self):
        with patch(LOOKUP, return_value=self.lookup_result(total_amount=1000)):
            self.callback()

        self.refresh()
        self.assertEqual(self.log.status, PaymentStatus.FAILED)
        self.assertEqual(self.slot.status, SlotStatus.HELD)
        self.assertEqual(self.owner.balance, 0)

    def test_cancelled_payment_fails_without_confirming(self):
        with patch(LOOKUP, return_value=self.lookup_result(status="User canceled")):
            self.callback()

        self.refresh()
        self.assertEqual(self.log.status, PaymentStatus.FAILED)
        self.assertEqual(self.booking.status, BookingStatus.PENDING)
        self.assertEqual(self.owner.balance, 0)

    def test_khalti_unreachable_changes_nothing_and_can_be_retried(self):
        with patch(LOOKUP, side_effect=KhaltiError("timeout")):
            response = self.callback()
        self.assertEqual(response.status_code, 502)
        self.refresh()
        self.assertEqual(self.log.status, PaymentStatus.INITIAL)

        with patch(LOOKUP, return_value=self.lookup_result()):
            self.callback()
        self.refresh()
        self.assertEqual(self.log.status, PaymentStatus.COMPLETED)

    def test_unknown_pidx_is_404(self):
        with patch(LOOKUP) as lookup:
            response = self.callback(pidx="nope")
        self.assertEqual(response.status_code, 404)
        lookup.assert_not_called()

    def test_missing_pidx_is_400(self):
        self.assertEqual(self.client.get(reverse("callback")).status_code, 400)

    def test_callback_only_accepts_get(self):
        self.assertEqual(self.client.post(reverse("callback"), {"pidx": "pidx-123"}).status_code, 405)

    def test_late_payment_after_hold_expired_still_confirms_if_slot_is_free(self):
        release_held_slot(self.booking.pk)  # hold timed out, slot freed
        with patch(LOOKUP, return_value=self.lookup_result()):
            self.callback()

        self.refresh()
        self.assertEqual(self.log.status, PaymentStatus.COMPLETED)
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)
        self.assertEqual(self.slot.status, SlotStatus.BOOKED)
        self.assertEqual(self.owner.balance, 300)

    def test_late_payment_when_slot_was_taken_requires_refund(self):
        release_held_slot(self.booking.pk)
        other_booking, _ = hold_slot(make_user(), self.slot.pk)  # someone else grabs it

        with patch(LOOKUP, return_value=self.lookup_result()):
            self.callback()

        self.refresh()
        self.assertEqual(self.log.status, PaymentStatus.REFUND_REQUIRED)
        self.assertEqual(self.booking.status, BookingStatus.EXPIRED)
        self.assertEqual(self.slot.status, SlotStatus.HELD)  # the other player's hold is intact
        other_booking.refresh_from_db()
        self.assertEqual(other_booking.status, BookingStatus.PENDING)
        self.assertEqual(self.owner.balance, 0)  # never credited
        self.assertEqual(Statement.objects.count(), 0)
