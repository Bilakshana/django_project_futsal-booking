from django.contrib import admin

from apps.bookings.models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "player", "slot", "status", "advance_amount", "held_until", "reminder_sent")
    list_filter = ("status",)
