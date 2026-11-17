from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class RegisterThrottle(AnonRateThrottle):
    scope = "register"


class HoldThrottle(UserRateThrottle):
    scope = "hold"


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Login with a strict per-IP limit to slow down password guessing."""

    throttle_classes = [LoginThrottle]
