from rest_framework.pagination import CursorPagination, PageNumberPagination


class ConversationCursorPagination(CursorPagination):
    page_size = 30
    max_page_size = 50
    page_size_query_param = "page_size"
    ordering = ("-is_pinned", "-activity_at", "-id")


class MembershipPagination(PageNumberPagination):
    page_size = 50
    max_page_size = 100
    page_size_query_param = "page_size"
