from rest_framework.pagination import CursorPagination


class NotificationCursorPagination(CursorPagination):
    page_size = 30
    max_page_size = 100
    page_size_query_param = "page_size"
    ordering = ("-last_event_at", "-id")
