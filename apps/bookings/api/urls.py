from django.urls import path

from apps.bookings.api.views import BookingListView, CancelBookingView, HoldSlotView

urlpatterns = [
    path("", BookingListView.as_view()),
    path("hold/", HoldSlotView.as_view()),
    path("<int:pk>/cancel/", CancelBookingView.as_view()),
]
