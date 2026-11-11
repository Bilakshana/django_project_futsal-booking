from rest_framework import serializers

from apps.wallet.models import Statement


class StatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Statement
        fields = ["id", "amount", "types", "reference", "created_at"]
        read_only_fields = fields
