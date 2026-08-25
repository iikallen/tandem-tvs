from typing import Any, cast

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.response import Response

from apps.core.views import PrivateResponseMixin
from apps.identity.models import User

from .models import Notification, NotificationPreference, NotificationSettings, PushSubscription
from .pagination import NotificationCursorPagination
from .serializers import (
    NotificationSerializer,
    NotificationSettingsWriteSerializer,
    PushSubscriptionSerializer,
    settings_payload,
)
from .services import emit_notification_hint, unread_count


class NotificationListView(PrivateResponseMixin, generics.ListAPIView):
    serializer_class = NotificationSerializer
    pagination_class = NotificationCursorPagination

    def get_queryset(self):
        rows = Notification.objects.filter(
            recipient=self.request.user, in_app_visible=True
        ).select_related("actor")
        if self.request.query_params.get("unread") == "true":
            rows = rows.filter(read_at__isnull=True)
        return rows


class NotificationUnreadCountView(PrivateResponseMixin, generics.GenericAPIView):
    def get(self, request):
        return Response({"unread_count": unread_count(request.user.pk)})


class NotificationReadView(PrivateResponseMixin, generics.GenericAPIView):
    def post(self, request, notification_id):
        with transaction.atomic():
            notification = generics.get_object_or_404(
                Notification.objects.select_for_update(),
                pk=notification_id,
                recipient=request.user,
                in_app_visible=True,
            )
            if notification.read_at is None:
                notification.read_at = timezone.now()
                notification.save(update_fields=["read_at"])
                emit_notification_hint(request.user.pk, "notification.read", notification.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationReadAllView(PrivateResponseMixin, generics.GenericAPIView):
    def post(self, request):
        updated = Notification.objects.filter(
            recipient=request.user, in_app_visible=True, read_at__isnull=True
        ).update(read_at=timezone.now())
        if updated:
            emit_notification_hint(request.user.pk, "notification.read_all")
        return Response({"updated": updated})


class NotificationSettingsView(PrivateResponseMixin, generics.GenericAPIView):
    serializer_class = NotificationSettingsWriteSerializer

    def get(self, request):
        return Response(settings_payload(request.user))

    def patch(self, request):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with transaction.atomic():
            if "enabled" in payload.validated_data:
                NotificationSettings.objects.update_or_create(
                    user=request.user,
                    defaults={"enabled": payload.validated_data["enabled"]},
                )
            for preference in payload.validated_data.get("preferences", []):
                kind = preference.pop("notification_type")
                NotificationPreference.objects.update_or_create(
                    user=request.user,
                    notification_type=kind,
                    defaults=preference,
                )
        request.user.refresh_from_db()
        return Response(settings_payload(request.user))


class PushConfigView(PrivateResponseMixin, generics.GenericAPIView):
    def get(self, request):
        return Response(
            {
                "enabled": settings.WEB_PUSH_ENABLED,
                "vapid_public_key": settings.VAPID_PUBLIC_KEY if settings.WEB_PUSH_ENABLED else "",
            }
        )


class PushSubscriptionView(PrivateResponseMixin, generics.GenericAPIView):
    serializer_class = PushSubscriptionSerializer
    throttle_scope = "push_subscription"

    def post(self, request):
        if not settings.WEB_PUSH_ENABLED:
            raise serializers.ValidationError("Web Push is disabled.")
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        with transaction.atomic():
            User.objects.select_for_update().only("pk").get(pk=request.user.pk)
            existing = (
                PushSubscription.objects.select_for_update()
                .filter(endpoint=payload.validated_data["endpoint"])
                .first()
            )
            if existing is not None and cast(Any, existing).user_id != request.user.pk:
                raise serializers.ValidationError("This push subscription is already registered.")
            if (
                existing is None
                and PushSubscription.objects.filter(user=request.user, enabled=True).count()
                >= settings.WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER
            ):
                raise serializers.ValidationError("Too many active push subscriptions.")
            PushSubscription.objects.update_or_create(
                endpoint=payload.validated_data["endpoint"],
                defaults={**payload.validated_data, "user": request.user, "enabled": True},
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request, subscription_id):
        subscription = generics.get_object_or_404(
            PushSubscription, pk=subscription_id, user=request.user
        )
        subscription.enabled = False
        subscription.save(update_fields=["enabled", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
