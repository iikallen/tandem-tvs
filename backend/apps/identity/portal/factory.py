from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import PortalAdapter
from .mock import MockPortalAdapter


def get_portal_adapter() -> PortalAdapter:
    if settings.PORTAL_ADAPTER == "mock":
        if not settings.ALLOW_MOCK_PORTAL_ADAPTER:
            raise ImproperlyConfigured("MockPortalAdapter is forbidden in this environment")
        return MockPortalAdapter()

    raise ImproperlyConfigured("No supported portal adapter is configured")
