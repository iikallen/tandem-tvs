import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasOpsToken(BasePermission):
    def has_permission(self, request, view) -> bool:
        expected = settings.OPS_MONITORING_TOKEN
        authorization = request.headers.get("Authorization", "")
        supplied = (
            authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        )
        return bool(expected and supplied and secrets.compare_digest(supplied, expected))
