import logging

import requests
from django.conf import settings
from django.db import transaction

from apps.payments.models import Paymentlog, PaymentStatus

logger = logging.getLogger(__name__)

# Statuses after which a Paymentlog must never be processed again
FINAL_STATUSES = (PaymentStatus.COMPLETED, PaymentStatus.REFUND_REQUIRED)


class KhaltiError(Exception):
    """Khalti was unreachable or answered with something that isn't JSON."""


def create_payment_log(user, amount, types, reference=None, booking=None):
    return Paymentlog.objects.create(
        user=user,
        amount=amount,
        types=types,
        reference=reference,
        booking=booking,
    )


def _headers():
    # NB: no trailing space after the key, or Khalti rejects the header
    return {
        "Authorization": f"key {settings.KHALTI_TOKEN}",
        "Content-Type": "application/json",
    }


def _post(path, payload):
    try:
        response = requests.post(
            f"{settings.KHALTI_BASE_URL}{path}",
            json=payload,
            headers=_headers(),
            timeout=settings.KHALTI_TIMEOUT,
        )
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise KhaltiError(str(exc)) from exc


def khalti_payment(**kwargs):
    """Initiate an e-payment. Amount is in rupees; Khalti wants paisa."""
    amount = kwargs.get("amount")
    purchase_order_id = str(kwargs.get("purchase_order_id"))
    purchase_order_name = kwargs.get("purchase_order_name")
    payload = {
        "return_url": settings.KHALTI_RETURN_URL,
        "website_url": settings.KHALTI_WEBSITE_URL,
        "amount": amount * 100,
        "purchase_order_id": purchase_order_id,
        "purchase_order_name": purchase_order_name,
        "customer_info": {
            "name": kwargs.get("customer_name"),
            "email": kwargs.get("customer_email"),
            "phone": str(kwargs.get("customer_phone")),
        },
        "product_details": [
            {
                "identity": purchase_order_id,
                "name": purchase_order_name,
                "total_price": amount * 100,
                "quantity": 1,
                "unit_price": amount * 100,
            }
        ],
    }
    return _post("/epayment/initiate/", payload)


def khalti_lookup(pidx):
    """Ask Khalti for the real status of a payment. Never trust the callback's query string."""
    return _post("/epayment/lookup/", {"pidx": pidx})


def apply_lookup_result(paymentlog_id, lookup):
    """Apply a verified Khalti lookup to a Paymentlog. Idempotent and atomic.

    Returns one of: already_processed, completed, refund_required, pending, failed,
    amount_mismatch.
    """
    # imported here: bookings.api.service imports this module
    from apps.bookings.api.service import confirm_booking_locked
    from apps.bookings.models import Booking
    from apps.courts.models import Slot
    from apps.wallet.tasks import credit_wallet

    with transaction.atomic():
        # Lock order: Booking -> Slot -> Paymentlog (same as the booking service)
        log = Paymentlog.objects.get(pk=paymentlog_id)
        booking = slot = None
        if log.booking_id:
            booking = Booking.objects.select_for_update().get(pk=log.booking_id)
            slot = Slot.objects.select_for_update().get(pk=booking.slot_id)
        log = Paymentlog.objects.select_for_update().get(pk=paymentlog_id)

        if log.status in FINAL_STATUSES:  # a duplicate/replayed callback
            return "already_processed"

        khalti_status = lookup.get("status")

        if khalti_status == "Completed":
            try:
                paid = int(lookup.get("total_amount"))
            except (TypeError, ValueError):
                paid = None
            if paid != log.amount * 100:
                logger.error("Amount mismatch for payment %s: expected %s paisa, Khalti says %s",
                             log.pk, log.amount * 100, lookup.get("total_amount"))
                log.status = PaymentStatus.FAILED
                log.save(update_fields=["status", "modified_at"])
                return "amount_mismatch"

            log.khalti_txn_id = lookup.get("transaction_id")
            if booking and confirm_booking_locked(booking, slot):
                log.status = PaymentStatus.COMPLETED
                log.save(update_fields=["status", "khalti_txn_id", "modified_at"])
                transaction.on_commit(lambda: credit_wallet.delay(log.pk))
                return "completed"

            logger.warning("Payment %s verified but booking can't be confirmed; refund needed", log.pk)
            log.status = PaymentStatus.REFUND_REQUIRED
            log.save(update_fields=["status", "khalti_txn_id", "modified_at"])
            return "refund_required"

        if khalti_status in ("Pending", "Initiated"):
            return "pending"  # not final: Khalti may call back again

        # Expired, User canceled, Refunded, ...
        log.status = PaymentStatus.FAILED
        log.save(update_fields=["status", "modified_at"])
        return "failed"
