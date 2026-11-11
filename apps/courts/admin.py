from django.contrib import admin

from apps.courts.models import Court, Slot


@admin.register(Court)
class CourtAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "price_per_slot", "opening_time", "closing_time", "is_active")


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ("court", "date", "start_time", "end_time", "price", "status")
    list_filter = ("status", "court", "date")
