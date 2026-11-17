import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.bookings.models import BookingStatus
from apps.payments.api.service import FINAL_STATUSES, KhaltiError, khalti_payment
from apps.payments.models import Paymentlog, PaymentStatus, PaymentType

logger = logging.getLogger(__name__)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment(request, id):
    """Step 2: start the Khalti payment for one of *your own* payment logs.
    Returns Khalti's payment_url: send the player there.

    Calling it again returns the same payment_url instead of creating a second Khalti payment,
    so a paid pidx can never be orphaned."""
    # The row stays locked while we talk to Khalti, so two clicks can't create two payments
    with transaction.atomic():
        data = get_object_or_404(
            Paymentlog.objects.select_for_update().select_related("booking", "user"),
            id=id, user=request.user,
        )

        if data.status in FINAL_STATUSES:
            return Response({"error": "payment already completed"}, status.HTTP_400_BAD_REQUEST)
        if data.booking and data.booking.status != BookingStatus.PENDING:
            return Response({"error": "this booking is no longer awaiting payment"}, status.HTTP_400_BAD_REQUEST)

        if data.status == PaymentStatus.INITIAL and data.pidx and data.payment_url:
            return Response({"pidx": data.pidx, "payment_url": data.payment_url})

        try:
            response = khalti_payment(
                amount=data.amount,
                purchase_order_id=data.id,
                purchase_order_name=f"{data.types}-{data.id}",
                customer_name=f"{data.user.first_name} {data.user.last_name}".strip() or data.user.username,
                customer_email=data.user.email,
                customer_phone=data.user.phone_number,
            )
        except KhaltiError as exc:
            logger.error("Khalti initiate failed for payment %s: %s", data.pk, exc)
            return Response({"error": "Could not reach Khalti, try again"}, status.HTTP_502_BAD_GATEWAY)

        if not response.get("pidx"):  # Khalti rejected the request (bad key, bad amount, ...)
            logger.error("Khalti rejected payment %s: %s", data.pk, response)  # details stay in the log
            return Response({"error": "Khalti rejected the payment request"}, status.HTTP_502_BAD_GATEWAY)

        data.pidx = response["pidx"]
        data.payment_url = response.get("payment_url")
        data.payment_type = PaymentType.KHALTI
        data.status = PaymentStatus.INITIAL
        data.save(update_fields=["pidx", "payment_url", "payment_type", "status", "modified_at"])
        return Response(response)
