from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import Role, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone_number", "role", "balance"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    # Self-registration can only create players or owners; admins are made via createsuperuser.
    role = serializers.ChoiceField(choices=[Role.PLAYER, Role.OWNER], default=Role.PLAYER)

    class Meta:
        model = User
        fields = [
            "username", "password", "confirm_password", "first_name", "last_name",
            "email", "phone_number", "role",
        ]

    def validate_phone_number(self, phone_number):
        if len(str(phone_number)) != 10:
            raise serializers.ValidationError("Length of phone number should be 10")
        return phone_number

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("Password and confirm password do not match")
        validate_password(attrs["password"], user=User(**{
            k: v for k, v in attrs.items() if k not in ("password", "confirm_password")
        }))
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        return User.objects.create_user(**validated_data)  # hashes the password
