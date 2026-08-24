from django.urls import re_path

from apps.messenger.consumers import MessengerConsumer

from .consumers import PublicationConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/v1/publications/(?P<publication_id>[0-9a-fA-F-]{36})$",
        PublicationConsumer.as_asgi(),  # type: ignore[arg-type]
    ),
    re_path(r"^ws/v1/messenger$", MessengerConsumer.as_asgi()),  # type: ignore[arg-type]
]
