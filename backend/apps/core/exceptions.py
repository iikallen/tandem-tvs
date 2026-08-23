from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
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
