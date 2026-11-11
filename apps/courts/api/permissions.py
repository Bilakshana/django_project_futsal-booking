from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import Role


class IsCourtOwnerOrReadOnly(BasePermission):
    """Anyone authenticated can read; only the court's owner (or an admin) can change it."""

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == Role.ADMIN or obj.owner_id == request.user.id
