from typing import TypedDict

from django.contrib.auth.models import AbstractUser
from rest_framework import serializers


class UserResponse(TypedDict):
    id: int
    username: str
    display_name: str


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(trim_whitespace=True)
    password = serializers.CharField(trim_whitespace=False, write_only=True)


def serialize_user(user: AbstractUser) -> UserResponse:
    display_name = user.get_full_name().strip() or user.get_username()
    return {
        "id": int(user.pk),
        "username": user.get_username(),
        "display_name": display_name,
    }
