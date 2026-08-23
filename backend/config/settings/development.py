import os

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
PORTAL_ADAPTER = os.getenv("PORTAL_ADAPTER", "mock")
ALLOW_MOCK_PORTAL_ADAPTER = True
