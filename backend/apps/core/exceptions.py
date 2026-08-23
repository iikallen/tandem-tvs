from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.identity.portal import PortalUnavailableError


def api_exception_handler(exc, context):
    if isinstance(exc, PortalUnavailableError):
        return Response(
            {
                "error": {
                    "code": "portal_unavailable",
                    "message": "Portal is temporarily unavailable.",
                }
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    response = exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    if detail is not None:
        response.data = {
            "error": {
                "code": getattr(detail, "code", "api_error"),
                "message": str(detail),
            }
        }
    return response
