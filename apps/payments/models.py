import uuid

from django.db import models

from apps.accounts.models import User
from apps.wallet.models import TypesValue


class PaymentType(models.TextChoices):
    KHALTI = "Khalti"


class PaymentStatus(models.TextChoices):
    PENDING = "pending"
    INITIAL = "initial"
    COMPLETED = "completed"
    FAILED = "failed"
    # Khalti took the money but the booking could no longer be honoured: refund manually
    REFUND_REQUIRED = "refund_required"


class Paymentlog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # string reference avoids a circular import with apps.bookings
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="payments")
    amount = models.PositiveIntegerField()  # rupees
    types = models.CharField(max_length=20, choices=TypesValue.choices)
    reference = models.CharField(max_length=50, null=True, blank=True)
    pidx = models.CharField(max_length=40, null=True, blank=True, unique=True)
    txn_id = models.UUIDField(default=uuid.uuid4)
    khalti_txn_id = models.CharField(max_length=70, null=True, blank=True)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices, null=True, blank=True)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "paymentlog"

    def __str__(self):
        return f"{self.user.username} {self.amount} ({self.status})"
