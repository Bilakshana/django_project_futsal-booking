from django.db import models

from apps.accounts.models import User


class TypesValue(models.TextChoices):
    BOOKING_ADVANCE = "booking_advance"


class Statement(models.Model):
    """Ledger line. A booking advance credits the court owner's balance."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.PositiveIntegerField()
    types = models.CharField(max_length=20, choices=TypesValue.choices)
    reference = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "statement"
        constraints = [
            # One ledger line per (type, reference): a payment can never be credited twice
            models.UniqueConstraint(fields=["types", "reference"], name="unique_statement_type_reference"),
        ]

    def __str__(self):
        return f"{self.user.username} +{self.amount}"
