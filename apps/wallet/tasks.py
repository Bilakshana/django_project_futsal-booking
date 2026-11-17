from celery import shared_task
from django.db import transaction

from apps.accounts.models import User
from apps.payments.models import Paymentlog, PaymentStatus
from apps.wallet.models import Statement, TypesValue


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def credit_wallet(paymentlog_id):
    """After a verified Khalti payment: credit the court owner and write a Statement.
    Idempotent: re-running (retries, duplicate callbacks) never credits twice."""
    with transaction.atomic():
        log = Paymentlog.objects.select_related("booking__slot__court").get(pk=paymentlog_id)
        if log.status != PaymentStatus.COMPLETED or log.booking is None:
            return f"payment {paymentlog_id}: not creditable"

        reference = f"payment-{log.pk}"
        if Statement.objects.filter(types=TypesValue.BOOKING_ADVANCE, reference=reference).exists():
            return f"payment {paymentlog_id}: already credited"

        owner = User.objects.select_for_update().get(pk=log.booking.slot.court.owner_id)
        owner.balance += log.amount
        owner.save(update_fields=["balance"])
        Statement.objects.create(
            user=owner,
            amount=log.amount,
            types=TypesValue.BOOKING_ADVANCE,
            reference=reference,
        )
    return f"payment {paymentlog_id}: credited {log.amount}"


@shared_task
def credit_missing_wallets():
    """Beat backstop: credit COMPLETED payments whose credit_wallet message was lost.
    Safe to re-run: credit_wallet is idempotent."""
    credited = {
        r for r in Statement.objects.filter(types=TypesValue.BOOKING_ADVANCE).values_list("reference", flat=True)
    }
    todo = [
        pk for pk in Paymentlog.objects.filter(status=PaymentStatus.COMPLETED, booking__isnull=False)
        .values_list("pk", flat=True) if f"payment-{pk}" not in credited
    ]
    for pk in todo:
        credit_wallet(pk)
    return f"credited {len(todo)} missing payments"
