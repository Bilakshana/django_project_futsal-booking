"""Small factories shared by the test modules."""
from datetime import time, timedelta

from django.utils import timezone

from apps.accounts.models import Role, User
from apps.courts.models import Court, Slot

_counter = {"n": 0}


def make_user(role=Role.PLAYER, **kwargs):
    _counter["n"] += 1
    n = _counter["n"]
    return User.objects.create_user(
        username=kwargs.pop("username", f"user{n}"),
        email=kwargs.pop("email", f"user{n}@example.com"),
        password="pass12345!x",
        phone_number=kwargs.pop("phone_number", 9800000000 + n),
        role=role,
        **kwargs,
    )


def make_court(owner, **kwargs):
    defaults = dict(name="Arena", location="Kathmandu", price_per_slot=1000)
    defaults.update(kwargs)
    return Court.objects.create(owner=owner, **defaults)


def make_slot(court, start_in=timedelta(days=1), price=1000, **kwargs):
    """A one-hour slot starting `start_in` from now (local time)."""
    start = (timezone.localtime() + start_in).replace(second=0, microsecond=0)
    end = start + timedelta(hours=1)
    # real slots never cross midnight; clamp so a late-evening start doesn't wrap to 00:xx
    end_time = end.time() if end.date() == start.date() else time(23, 59)
    return Slot.objects.create(
        court=court,
        date=start.date(),
        start_time=start.time(),
        end_time=end_time,
        price=price,
        **kwargs,
    )
