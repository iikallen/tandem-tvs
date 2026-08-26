from django.conf import settings
from django.http import JsonResponse
from django.utils.cache import patch_cache_control
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ops.health import dependency_status

from .serializers import HealthSerializer, RuntimeMetaSerializer


def bad_request(request, exception=None):
    response = JsonResponse(
        {"error": {"code": "bad_request", "message": "Bad request."}},
        status=400,
    )
    patch_cache_control(response, no_store=True, max_age=0)
    return response


class PublicAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class PrivateResponseMixin:
    """Authenticated API base that prevents user-specific responses being cached."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
            request, response, *args, **kwargs
        )
        patch_cache_control(response, private=True, no_store=True, max_age=0)
        return response


class PrivateAPIView(PrivateResponseMixin, APIView):
    pass


class LiveView(PublicAPIView):
    @extend_schema(responses=HealthSerializer)
    def get(self, request):
        return Response({"status": "ok"})


class ReadyView(PublicAPIView):
    @extend_schema(responses=HealthSerializer)
    def get(self, request):
        components = dependency_status()
        is_ready = components["postgres"] == "ok" and components["media"] == "ok"
        response_status = (
            "ok" if is_ready and all(value == "ok" for value in components.values()) else "degraded"
        )
        return Response(
            {"status": response_status if is_ready else "unavailable"},
            status=200 if is_ready else 503,
        )


class RuntimeMetaView(PublicAPIView):
    @extend_schema(responses=RuntimeMetaSerializer)
    def get(self, request):
        return Response(
            {
                "application": "Tandem Portal",
                "version": settings.APP_VERSION,
                "revision": settings.APP_GIT_SHA,
                "default_locale": "ru",
                "supported_locales": ["ru"],
                "planned_locales": ["kk"],
            }
        )
