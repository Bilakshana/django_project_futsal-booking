from django.urls import path

from apps.payments.api.views import payment

urlpatterns = [
    path("initiate/<int:id>/", payment, name="initiate-payment"),
]
