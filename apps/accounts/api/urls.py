from django.urls import path

from apps.accounts.api.views import me, register, user_list

urlpatterns = [
    path("list/", user_list),
    path("register/", register),
    path("me/", me),
]
