from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Role(models.TextChoices):
    ADMIN = "admin"
    PLAYER = "player"
    OWNER = "owner"


class CustomManager(UserManager):

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    phone_number = models.PositiveBigIntegerField(unique=True)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.PLAYER)
    email = models.EmailField(unique=True)
    # Wallet balance in rupees. Court owners are credited when a player's advance clears.
    balance = models.PositiveIntegerField(default=0)

    objects = CustomManager()
    REQUIRED_FIELDS = ["email", "phone_number"]
