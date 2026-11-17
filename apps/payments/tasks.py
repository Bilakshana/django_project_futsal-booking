import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.payments.api.service import FINAL_STATUSES, KhaltiError, apply_lookup_result, khalti_lookup
from apps.payments.models import Paymentlog, PaymentStatus

logger = logging.getLogger(__name__)

MIN_AGE = timedelta(minutes=2)  # give the player's own redirect a chance to arrive first
MAX_AGE = timedelta(hours=2)  # Khalti payment links expire after about an hour


@shared_task
def reconcile_payments():
    """Beat (every 5 min): ask Khalti about payments whose player never came back to the callback
    (closed tab, lost connection), so money is never taken without the booking being confirmed."""
    now = timezone.now()
    logs = Paymentlog.objects.filter(
        pidx__isnull=False,
        status__in=[PaymentStatus.INITIAL, PaymentStatus.FAILED],  # FAILED: hold expired before payment
        created_at__gte=now - MAX_AGE,
        modified_at__lte=now - MIN_AGE,
    ).exclude(status__in=FINAL_STATUSES)

    checked = 0
    for log in logs:
        try:
            lookup = khalti_lookup(log.pidx)
        except KhaltiError as exc:
            logger.warning("Reconcile: Khalti unavailable for payment %s: %s", log.pk, exc)
            continue
        apply_lookup_result(log.pk, lookup)
        checked += 1
    return f"reconciled {checked} payments"
