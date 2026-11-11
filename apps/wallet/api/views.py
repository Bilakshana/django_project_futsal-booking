from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from apps.wallet.api.serializers import StatementSerializer
from apps.wallet.models import Statement


class StatementListView(ListAPIView):
    """The caller's own ledger."""

    serializer_class = StatementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Statement.objects.filter(user=self.request.user).order_by("-id")
