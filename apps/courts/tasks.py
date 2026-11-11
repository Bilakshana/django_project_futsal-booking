from datetime import time, timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.courts.models import Court, Slot


def slot_windows(court):
    """Yield (start_time, end_time) pairs that fit between opening and closing."""
    t = court.opening_time.hour * 60 + court.opening_time.minute
    end = court.closing_time.hour * 60 + court.closing_time.minute
    step = court.slot_duration_minutes
    while t + step <= end:
        yield time(t // 60, t % 60), time((t + step) // 60, (t + step) % 60)
        t += step


@shared_task
def generate_daily_slots(court_id=None, days=None):
    """Create slots for the next `days` days (default 7). Safe to run repeatedly:
    existing slots are skipped, and the unique constraint backs that up."""
    days = days or settings.SLOT_GENERATION_DAYS
    courts = Court.objects.filter(is_active=True)
    if court_id is not None:
        courts = courts.filter(pk=court_id)

    today = timezone.localdate()
    dates = [today + timedelta(days=i) for i in range(days)]
    created = 0
    for court in courts:
        existing = set(
            Slot.objects.filter(court=court, date__in=dates).values_list("date", "start_time")
        )
        new_slots = [
            Slot(court=court, date=d, start_time=start, end_time=end, price=court.price_per_slot)
            for d in dates
            for start, end in slot_windows(court)
            if (d, start) not in existing
        ]
        Slot.objects.bulk_create(new_slots, ignore_conflicts=True)
        created += len(new_slots)
    return f"created {created} slots"
