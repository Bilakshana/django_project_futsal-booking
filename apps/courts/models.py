from datetime import datetime, time

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.accounts.models import User


class Court(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courts")
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # Used by the nightly generate_daily_slots task
    price_per_slot = models.PositiveIntegerField(validators=[MinValueValidator(10)])
    opening_time = models.TimeField(default=time(6, 0))
    closing_time = models.TimeField(default=time(21, 0))
    slot_duration_minutes = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(30)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "court"

    def __str__(self):
        return self.name


class SlotStatus(models.TextChoices):
    AVAILABLE = "available"
    HELD = "held"
    BOOKED = "booked"


class Slot(models.Model):
    court = models.ForeignKey(Court, on_delete=models.CASCADE, related_name="slots")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    price = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=SlotStatus.choices, default=SlotStatus.AVAILABLE)

    class Meta:
        db_table = "slot"
        ordering = ["date", "start_time"]
        constraints = [
            # Last line of defence against double booking, whatever the application code does
            models.UniqueConstraint(fields=["court", "date", "start_time"], name="unique_slot_per_court_time"),
        ]
        indexes = [models.Index(fields=["court", "date", "status"])]

    def __str__(self):
        return f"{self.court} {self.date} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

    @property
    def start_datetime(self):
        return timezone.make_aware(datetime.combine(self.date, self.start_time))

    @property
    def end_datetime(self):
        return timezone.make_aware(datetime.combine(self.date, self.end_time))
