"""Booking business logic.

Lock order used everywhere in the project (to avoid deadlocks):
    Booking row -> Slot row -> Paymentlog row
"""
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.courts.models import Slot, SlotStatus
from apps.payments.api.service import create_payment_log
from apps.payments.models import PaymentStatus
from apps.wallet.models import TypesValue


class BookingError(Exception):
    """A booking rule was broken; the message is safe to show to the player."""


def calculate_advance(price):
    advance = -(-price * settings.ADVANCE_PERCENT // 100)  # ceil
    return min(price, max(advance, settings.MIN_ADVANCE_AMOUNT))


@transaction.atomic
def hold_slot(player, slot_id):
    """Hold a slot for `player`. The Slot row is locked, so two players racing for the
    same slot are serialised: the loser sees status != available and is rejected."""
    try:
        slot = Slot.objects.select_for_update().select_related("court").get(pk=slot_id)
    except Slot.DoesNotExist:
        raise BookingError("Slot not found")

    if not slot.court.is_active:
        raise BookingError("This court is not accepting bookings")
    if slot.status != SlotStatus.AVAILABLE:
        raise BookingError("Slot is not available")
    if slot.start_datetime <= timezone.now():
        raise BookingError("This slot has already started")

    slot.status = SlotStatus.HELD
    slot.save(update_fields=["status"])

    advance = calculate_advance(slot.price)
    try:
        with transaction.atomic():
            booking = Booking.objects.create(
                player=player,
                slot=slot,
                total_price=slot.price,
                advance_amount=advance,
                held_until=timezone.now() + timedelta(seconds=settings.SLOT_HOLD_SECONDS),
            )
    except IntegrityError:  # the partial unique constraint caught a double booking
        raise BookingError("Slot is not available")

    payment_log = create_payment_log(
        user=player,
        amount=advance,
        types=TypesValue.BOOKING_ADVANCE,
        reference=f"booking-{booking.pk}",
        booking=booking,
    )
    return booking, payment_log


@transaction.atomic
def release_booking(booking_id, new_status):
    """Free the slot of an unpaid (pending) booking. Returns True if something was released.
    Does nothing if the booking was paid in the meantime."""
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.status != BookingStatus.PENDING:
        return False
    slot = Slot.objects.select_for_update().get(pk=booking.slot_id)

    booking.status = new_status
    booking.save(update_fields=["status", "modified_at"])
    if slot.status == SlotStatus.HELD:
        slot.status = SlotStatus.AVAILABLE
        slot.save(update_fields=["status"])
    booking.payments.filter(status__in=[PaymentStatus.PENDING, PaymentStatus.INITIAL]).update(
        status=PaymentStatus.FAILED
    )
    return True


def confirm_booking_locked(booking, slot):
    """Confirm `booking` after its advance was verified. Caller must hold the Booking and Slot
    locks. Returns False when the booking can no longer be honoured (=> refund needed)."""
    if booking.status == BookingStatus.CONFIRMED:
        return True
    if booking.status == BookingStatus.PENDING:
        pass
    elif (
        # Paid after the hold expired: still fine if nobody else took the slot meanwhile
        booking.status in (BookingStatus.EXPIRED, BookingStatus.CANCELLED)
        and slot.status == SlotStatus.AVAILABLE
        and slot.start_datetime > timezone.now()
    ):
        pass
    else:
        return False

    booking.status = BookingStatus.CONFIRMED
    booking.save(update_fields=["status", "modified_at"])
    slot.status = SlotStatus.BOOKED
    slot.save(update_fields=["status"])
    return True
