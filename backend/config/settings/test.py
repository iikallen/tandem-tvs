import os

from .base import *  # noqa: F403

SECRET_KEY = "test-only-secret"  # nosec B105
PORTAL_ADAPTER = "mock"
ALLOW_MOCK_PORTAL_ADAPTER = True
API_DOCS_ENABLED = True
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
REALTIME_REDIS_URL = os.getenv("TEST_REALTIME_REDIS_URL", "redis://127.0.0.1:6379/15")
REALTIME_ALLOWED_ORIGINS = ["http://localhost", "http://127.0.0.1:8080"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
