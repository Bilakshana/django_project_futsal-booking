from django.db import transaction
from rest_framework import serializers

from apps.courts.models import Court, Slot
from apps.courts.tasks import generate_daily_slots


class CourtSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Court
        fields = [
            "id", "owner", "name", "location", "description", "price_per_slot",
            "opening_time", "closing_time", "slot_duration_minutes", "is_active",
        ]

    def validate(self, attrs):
        opening = attrs.get("opening_time", getattr(self.instance, "opening_time", None))
        closing = attrs.get("closing_time", getattr(self.instance, "closing_time", None))
        if opening and closing and opening >= closing:
            raise serializers.ValidationError("opening_time must be before closing_time")
        return attrs

    def create(self, validated_data):
        validated_data["owner"] = self.context["request"].user
        with transaction.atomic():
            court = super().create(validated_data)
            # Give the new court its first 7 days of slots straight away
            transaction.on_commit(lambda: generate_daily_slots.delay(court_id=court.pk))
        return court


class SlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slot
        fields = ["id", "court", "date", "start_time", "end_time", "price", "status"]
        read_only_fields = fields
