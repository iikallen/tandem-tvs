from rest_framework import generics, serializers
from rest_framework.response import Response

from apps.core.views import PrivateResponseMixin

from .serializers import GlobalSearchSerializer
from .services import (
    authorized_sections,
    decode_cursor,
    encode_cursor,
    serialize_result,
)


class GlobalSearchView(PrivateResponseMixin, generics.GenericAPIView):
    serializer_class = GlobalSearchSerializer

    def get(self, request):
        payload = self.get_serializer(data=request.query_params)
        payload.is_valid(raise_exception=True)
        query = payload.validated_data["q"]
        scope = payload.validated_data["scope"]
        sections = authorized_sections(request.user, query)
        if scope == "all":
            return Response(
                {
                    name: [serialize_result(name, row) for row in rows[:5]]
                    for name, rows in sections.items()
                }
            )
        try:
            offset = decode_cursor(payload.validated_data.get("cursor"))
        except ValueError as exc:
            raise serializers.ValidationError({"cursor": str(exc)}) from exc
        rows = list(sections[scope][offset : offset + 21])
        has_more = len(rows) > 20
        return Response(
            {
                "results": [serialize_result(scope, row) for row in rows[:20]],
                "next_cursor": encode_cursor(offset + 20) if has_more else None,
            }
        )
