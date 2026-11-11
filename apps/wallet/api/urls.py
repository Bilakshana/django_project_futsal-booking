from django.urls import path

from apps.wallet.api.views import StatementListView

urlpatterns = [
    path("statements/", StatementListView.as_view()),
]
