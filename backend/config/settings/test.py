from .base import *  # noqa: F403

SECRET_KEY = "test-only-secret"
PORTAL_ADAPTER = "mock"
ALLOW_MOCK_PORTAL_ADAPTER = True
API_DOCS_ENABLED = True
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
