from django.contrib import admin

from apps.payments.models import Paymentlog


@admin.register(Paymentlog)
class PaymentlogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "amount", "status", "pidx", "booking", "created_at")
    list_filter = ("status",)
