from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import User


@admin.register(User)
class CustomUser(UserAdmin):
    list_display = ("username", "email", "role", "phone_number", "balance", "is_staff")
    list_filter = UserAdmin.list_filter + ("role",)
    fieldsets = UserAdmin.fieldsets + (("Futsal", {"fields": ("role", "phone_number", "balance")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Futsal", {"fields": ("email", "role", "phone_number")}),
    )
