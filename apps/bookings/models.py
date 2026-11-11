from django.db import models
from django.db.models import Q

from apps.accounts.models import User
from apps.courts.models import Slot


class BookingStatus(models.TextChoices):
    PENDING = "pending"        # slot held, advance not paid yet
    CONFIRMED = "confirmed"    # advance paid
    CANCELLED = "cancelled"
    EXPIRED = "expired"        # hold timed out unpaid
    COMPLETED = "completed"    # match time has passed


ACTIVE_STATUSES = [BookingStatus.PENDING, BookingStatus.CONFIRMED]


class Booking(models.Model):
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name="bookings")
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    total_price = models.PositiveIntegerField()
    advance_amount = models.PositiveIntegerField()
    held_until = models.DateTimeField()
    reminder_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "booking"
        ordering = ["-created_at"]
        constraints = [
            # A slot can have many historic bookings (expired/cancelled) but only one live one.
            models.UniqueConstraint(
                fields=["slot"],
                condition=Q(status__in=["pending", "confirmed", "completed"]),
                name="one_live_booking_per_slot",
            ),
        ]

    def __str__(self):
        return f"Booking {self.pk} ({self.status})"
