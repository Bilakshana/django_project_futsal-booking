from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.api.permissions import IsPlayer
from apps.accounts.models import Role
from apps.bookings.api.serializers import BookingSerializer, HoldSlotSerializer
from apps.bookings.api.service import release_booking
from apps.bookings.models import Booking, BookingStatus


class HoldSlotView(GenericAPIView):
    """Step 1: hold a slot (10 min). The response has the payment_id to pay the advance."""

    serializer_class = HoldSlotSerializer
    permission_classes = [IsAuthenticated, IsPlayer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()
        return Response(
            {
                "message": "Slot held. Pay the advance to confirm the booking.",
                "data": BookingSerializer(booking).data,
            },
            status.HTTP_201_CREATED,
        )


class BookingListView(ListAPIView):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Booking.objects.select_related("slot__court").prefetch_related("payments")
        if user.role == Role.ADMIN:
            return qs
        if user.role == Role.OWNER:
            return qs.filter(slot__court__owner=user)
        return qs.filter(player=user)


class CancelBookingView(GenericAPIView):
    """Cancel an unpaid booking and free its slot."""

    permission_classes = [IsAuthenticated, IsPlayer]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, player=request.user)
        if not release_booking(booking.pk, BookingStatus.CANCELLED):
            return Response(
                {"error": "Only bookings awaiting payment can be cancelled"},
                status.HTTP_400_BAD_REQUEST,
            )
        return Response({"message": "Booking cancelled"})
