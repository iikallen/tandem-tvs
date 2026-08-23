from rest_framework.pagination import CursorPagination, LimitOffsetPagination


class NewsCursorPagination(CursorPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50
    ordering: tuple[str, ...] = ("-published_at", "-id")  # pyright: ignore[reportIncompatibleVariableOverride]

    def get_ordering(self, request, queryset, view) -> tuple[str, ...]:
        if request.query_params.get("q", "").strip():
            return ("-search_cursor",)
        return self.ordering


class EditorialPagination(LimitOffsetPagination):
    default_limit = 20
    max_limit = 50
