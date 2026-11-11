from django.urls import path

from apps.courts.api.views import CourtDetailView, CourtListCreateView, CourtSlotListView

urlpatterns = [
    path("", CourtListCreateView.as_view()),
    path("<int:pk>/", CourtDetailView.as_view()),
    path("<int:pk>/slots/", CourtSlotListView.as_view()),
]
