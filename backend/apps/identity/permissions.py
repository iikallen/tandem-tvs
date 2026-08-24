from rest_framework.permissions import BasePermission

from .models import AccessGrant


def access_grants(user):
    cached = getattr(user, "_prefetched_objects_cache", {}).get("access_grants")
    return cached if cached is not None else user.access_grants.all()


def has_role(user, module: str, role: str) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return any(grant.module == module and grant.role == role for grant in access_grants(user))


def has_any_role(user, module: str, roles: set[str]) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return any(grant.module == module and grant.role in roles for grant in access_grants(user))


def has_module_access(user, module: str) -> bool:
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return False
    return any(grant.module == module for grant in access_grants(user))


def legacy_news_roles(user) -> set[str]:
    mapping = {
        AccessGrant.Role.MEMBER: "employee",
        AccessGrant.Role.AUTHOR: "author",
        AccessGrant.Role.EDITOR: "editor",
        AccessGrant.Role.MODERATOR: "moderator",
        AccessGrant.Role.ADMIN: "admin",
    }
    return {
        mapping[grant.role]
        for grant in access_grants(user)
        if grant.module == AccessGrant.Module.NEWS and grant.role in mapping
    }


class HasNewsAccess(BasePermission):
    message = "News access is required."

    def has_permission(self, request, view):
        return has_module_access(request.user, AccessGrant.Module.NEWS)


class IsNewsAuthor(BasePermission):
    message = "A news author role is required."

    def has_permission(self, request, view):
        return has_any_role(
            request.user,
            AccessGrant.Module.NEWS,
            {AccessGrant.Role.AUTHOR, AccessGrant.Role.EDITOR, AccessGrant.Role.ADMIN},
        )


class IsNewsEditor(BasePermission):
    message = "A news editor role is required."

    def has_permission(self, request, view):
        return has_any_role(
            request.user,
            AccessGrant.Module.NEWS,
            {AccessGrant.Role.EDITOR, AccessGrant.Role.ADMIN},
        )


class IsNewsModerator(BasePermission):
    message = "A news moderator role is required."

    def has_permission(self, request, view):
        return has_any_role(
            request.user,
            AccessGrant.Module.NEWS,
            {AccessGrant.Role.MODERATOR, AccessGrant.Role.ADMIN},
        )


class IsNewsAdmin(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, AccessGrant.Module.NEWS, AccessGrant.Role.ADMIN)


class HasMessengerAccess(BasePermission):
    def has_permission(self, request, view):
        return has_module_access(request.user, AccessGrant.Module.MESSENGER)


class IsMessengerAdmin(BasePermission):
    def has_permission(self, request, view):
        return has_role(request.user, AccessGrant.Module.MESSENGER, AccessGrant.Role.ADMIN)


class IsPlatformAdmin(BasePermission):
    message = "Platform administrator access is required."

    def has_permission(self, request, view):
        return has_role(request.user, AccessGrant.Module.PLATFORM, AccessGrant.Role.ADMIN)
