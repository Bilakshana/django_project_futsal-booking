from datetime import date as date_cls

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.accounts.api.permissions import IsOwnerOrAdmin
from apps.accounts.models import Role
from apps.courts.api.permissions import IsCourtOwnerOrReadOnly
from apps.courts.api.serializers import CourtSerializer, SlotSerializer
from apps.courts.models import Court, Slot


def courts_for(user):
    if user.role == Role.ADMIN:
        return Court.objects.all()
    if user.role == Role.OWNER:
        return Court.objects.filter(owner=user)
    return Court.objects.filter(is_active=True)  # players browse active courts


class CourtListCreateView(generics.ListCreateAPIView):
    serializer_class = CourtSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsOwnerOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return courts_for(self.request.user).order_by("id")


class CourtDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CourtSerializer
    permission_classes = [IsAuthenticated, IsCourtOwnerOrReadOnly]

    def get_queryset(self):
        return Court.objects.all() if self.request.method == "GET" else courts_for(self.request.user)


class CourtSlotListView(generics.ListAPIView):
    """Slots of one court. Filter with ?date=YYYY-MM-DD and/or ?status=available."""

    serializer_class = SlotSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        court = get_object_or_404(Court, pk=self.kwargs["pk"])
        qs = Slot.objects.filter(court=court)
        day = self.request.query_params.get("date")
        if day:
            try:
                qs = qs.filter(date=date_cls.fromisoformat(day))
            except ValueError:
                raise ValidationError({"date": "Use YYYY-MM-DD"})
        slot_status = self.request.query_params.get("status")
        if slot_status:
            qs = qs.filter(status=slot_status)
        return qs
