import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator
from django.conf import settings
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

django_asgi_application = get_asgi_application()

from apps.discussions.middleware import TicketAuthMiddleware  # noqa: E402
from apps.discussions.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": OriginValidator(
            TicketAuthMiddleware(URLRouter(websocket_urlpatterns)),
            settings.REALTIME_ALLOWED_ORIGINS,
        ),
    }
)
