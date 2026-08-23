from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.portal import get_portal_adapter

from .serializers import HealthSerializer, ReadinessSerializer, RuntimeMetaSerializer


class PublicAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class LiveView(PublicAPIView):
    @extend_schema(responses=HealthSerializer)
    def get(self, request):
        return Response({"status": "ok"})


class ReadyView(PublicAPIView):
    @extend_schema(responses=ReadinessSerializer)
    def get(self, request):
        components: dict[str, str] = {}

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            components["database"] = "ok"
        except Exception:
            components["database"] = "unavailable"

        try:
            cache.set("readiness", "ok", timeout=5)
            components["cache"] = "ok" if cache.get("readiness") == "ok" else "unavailable"
        except Exception:
            components["cache"] = "unavailable"

        try:
            portal_health = get_portal_adapter().healthcheck()
            components["portal"] = "ok" if portal_health.available else "unavailable"
        except Exception:
            components["portal"] = "unavailable"

        is_ready = all(value == "ok" for value in components.values())
        return Response(
            {"status": "ok" if is_ready else "unavailable", "components": components},
            status=200 if is_ready else 503,
        )


class RuntimeMetaView(PublicAPIView):
    @extend_schema(responses=RuntimeMetaSerializer)
    def get(self, request):
        return Response(
            {
                "application": "Tandem Portal",
                "version": "1.0.0",
                "default_locale": "ru",
                "supported_locales": ["ru"],
                "planned_locales": ["kk"],
            }
        )
