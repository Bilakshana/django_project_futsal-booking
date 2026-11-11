from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from apps.bookings.api.service import release_booking
from apps.bookings.models import Booking, BookingStatus


@shared_task
def release_held_slot(booking_id):
    """Queued with countdown=600 when a slot is held: free it if the advance wasn't paid."""
    released = release_booking(booking_id, BookingStatus.EXPIRED)
    return f"booking {booking_id}: {'released' if released else 'nothing to release'}"


@shared_task
def send_booking_reminder():
    """Beat (every 5 min): remind players whose confirmed booking starts within the hour."""
    now = timezone.now()
    horizon = now + timedelta(minutes=settings.REMINDER_LEAD_MINUTES)
    today = timezone.localdate(now)

    candidates = (
        Booking.objects.filter(
            status=BookingStatus.CONFIRMED,
            reminder_sent=False,
            slot__date__in=[today, timezone.localdate(horizon)],
        )
        .select_related("player", "slot__court")
    )
    sent = 0
    for booking in candidates:
        if not (now <= booking.slot.start_datetime <= horizon):
            continue
        # Claim the booking atomically so two overlapping runs can't both email
        if not Booking.objects.filter(pk=booking.pk, reminder_sent=False).update(reminder_sent=True):
            continue
        slot = booking.slot
        send_mail(
            subject=f"Reminder: {slot.court.name} at {slot.start_time:%H:%M}",
            message=(
                f"Hi {booking.player.first_name or booking.player.username}, your futsal game at "
                f"{slot.court.name} ({slot.court.location}) starts at {slot.start_time:%H:%M} "
                f"on {slot.date}."
            ),
            from_email=None,
            recipient_list=[booking.player.email],
        )
        sent += 1
    return f"sent {sent} reminders"


@shared_task
def mark_completed_bookings():
    """Beat (every 10 min): confirmed bookings whose slot has ended become completed."""
    now = timezone.localtime()
    ended = Q(slot__date__lt=now.date()) | Q(slot__date=now.date(), slot__end_time__lte=now.time())
    updated = Booking.objects.filter(ended, status=BookingStatus.CONFIRMED).update(
        status=BookingStatus.COMPLETED
    )
    return f"completed {updated} bookings"
