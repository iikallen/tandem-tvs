from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import PortalAdapter
from .mock import MockPortalAdapter
from .unavailable import UnavailablePortalAdapter


def get_portal_adapter() -> PortalAdapter:
    if settings.PORTAL_ADAPTER == "mock":
        if not settings.ALLOW_MOCK_PORTAL_ADAPTER:
            raise ImproperlyConfigured("MockPortalAdapter is forbidden in this environment")
        return MockPortalAdapter()

    if settings.PORTAL_ADAPTER == "unavailable":
        return UnavailablePortalAdapter()

    raise ImproperlyConfigured("No supported portal adapter is configured")
