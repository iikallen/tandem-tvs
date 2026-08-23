from rest_framework.pagination import CursorPagination


class CommentCursorPagination(CursorPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100
    # The first page is the live window: a newly created comment must be
    # present when realtime invalidates only the pages currently in cache.
    ordering = ("-created_at", "-id")
