from django.conf import settings
from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.bookings.api.service import BookingError, hold_slot
from apps.bookings.models import Booking
from apps.bookings.tasks import release_held_slot
from apps.courts.api.serializers import SlotSerializer
from apps.courts.models import Slot


class BookingSerializer(serializers.ModelSerializer):
    slot = SlotSerializer(read_only=True)
    payment_id = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id", "player", "slot", "status", "total_price", "advance_amount",
            "held_until", "payment_id", "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.INT)
    def get_payment_id(self, booking):
        # POST /api/payment/initiate/<payment_id>/ starts the Khalti payment
        payment = booking.payments.order_by("-id").first()
        return payment.id if payment else None


class HoldSlotSerializer(serializers.Serializer):
    slot = serializers.PrimaryKeyRelatedField(queryset=Slot.objects.all())

    def create(self, validated_data):
        player = self.context["request"].user
        try:
            with transaction.atomic():
                booking, _ = hold_slot(player, validated_data["slot"].pk)
                # Free the slot again if the advance isn't paid within the hold window
                transaction.on_commit(
                    lambda: release_held_slot.apply_async(
                        args=[booking.pk], countdown=settings.SLOT_HOLD_SECONDS
                    )
                )
        except BookingError as exc:
            raise serializers.ValidationError({"slot": str(exc)})
        return booking
