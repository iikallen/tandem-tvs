import os

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost").split(",")
    if origin.strip()
]
PORTAL_ADAPTER = os.getenv("PORTAL_ADAPTER", "mock")
ALLOW_MOCK_PORTAL_ADAPTER = True
