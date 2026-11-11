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


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment(request, id):
    """Step 2: start the Khalti payment for one of *your own* payment logs.
    Returns Khalti's payment_url: send the player there."""
    data = get_object_or_404(Paymentlog.objects.select_related("booking", "user"), id=id, user=request.user)

    if data.status in FINAL_STATUSES:
        return Response({"error": "payment already completed"}, status.HTTP_400_BAD_REQUEST)
    if data.booking and data.booking.status != BookingStatus.PENDING:
        return Response({"error": "this booking is no longer awaiting payment"}, status.HTTP_400_BAD_REQUEST)

    try:
        response = khalti_payment(
            amount=data.amount,
            purchase_order_id=data.id,
            purchase_order_name=f"{data.types}-{data.id}",
            customer_name=f"{data.user.first_name} {data.user.last_name}".strip() or data.user.username,
            customer_email=data.user.email,
            customer_phone=data.user.phone_number,
        )
    except KhaltiError:
        return Response({"error": "Could not reach Khalti, try again"}, status.HTTP_502_BAD_GATEWAY)

    if not response.get("pidx"):  # Khalti rejected the request (bad key, bad amount, ...)
        return Response({"error": "Khalti rejected the payment request", "detail": response},
                        status.HTTP_502_BAD_GATEWAY)

    data.pidx = response["pidx"]
    data.payment_type = PaymentType.KHALTI
    data.status = PaymentStatus.INITIAL
    data.save(update_fields=["pidx", "payment_type", "status", "modified_at"])
    return Response(response)
