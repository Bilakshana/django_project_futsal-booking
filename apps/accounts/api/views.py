from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.api.permissions import IsAdmin
from apps.accounts.api.serializers import RegisterSerializer, UserSerializer
from apps.accounts.models import User


@extend_schema(responses=UserSerializer(many=True))
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdmin])
def user_list(request):
    serializer = UserSerializer(User.objects.all().order_by("id"), many=True)
    return Response(serializer.data)


@extend_schema(responses=UserSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@extend_schema(request=RegisterSerializer, responses={201: None})
@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "User registered successfully"}, status.HTTP_201_CREATED)
    return Response(serializer.errors, status.HTTP_400_BAD_REQUEST)
