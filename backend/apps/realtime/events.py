from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .groups import user_control_group


def invalidate_user_after_commit(user_id: int) -> None:
    def send() -> None:
        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(
                user_control_group(user_id), {"type": "auth.invalidate"}
            )

    transaction.on_commit(send, robust=True)
