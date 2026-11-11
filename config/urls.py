from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.payments.views import payment_callback

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.api.urls")),
    path("api/courts/", include("apps.courts.api.urls")),
    path("api/bookings/", include("apps.bookings.api.urls")),
    path("api/payment/", include("apps.payments.api.urls")),
    path("api/wallet/", include("apps.wallet.api.urls")),
    path("api/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Khalti redirects the player's browser here after payment
    path("payment/callback/", payment_callback, name="callback"),
    # api documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
