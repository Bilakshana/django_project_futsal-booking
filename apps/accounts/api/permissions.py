from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class _HasRole(BasePermission):
    roles = ()

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in self.roles)


class IsPlayer(_HasRole):
    roles = (Role.PLAYER,)


class IsOwner(_HasRole):
    roles = (Role.OWNER,)


class IsAdmin(_HasRole):
    roles = (Role.ADMIN,)


class IsOwnerOrAdmin(_HasRole):
    roles = (Role.OWNER, Role.ADMIN)
