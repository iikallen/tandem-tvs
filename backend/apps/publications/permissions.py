from rest_framework.permissions import BasePermission

EDITORIAL_ROLES = {"author", "editor", "admin", "administrator"}
EDITOR_ROLES = {"editor", "admin", "administrator"}


class IsEditorialRole(BasePermission):
    message = "An editorial role is required."

    def has_permission(self, request, view):
        return bool(EDITORIAL_ROLES.intersection(getattr(request.user, "module_roles", [])))


class IsEditorRole(BasePermission):
    message = "An editor role is required."

    def has_permission(self, request, view):
        return bool(EDITOR_ROLES.intersection(getattr(request.user, "module_roles", [])))
