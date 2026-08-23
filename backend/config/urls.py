from django.conf import settings
from django.contrib.staticfiles.views import serve as serve_static
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import LiveView, ReadyView, RuntimeMetaView
from apps.discussions.views import (
    CommentDetailView,
    CommentListCreateView,
    ReactionDetailView,
    ReactionSummaryView,
    RealtimeTicketView,
)
from apps.identity.views import MeView
from apps.organization.views import EmployeeSearchView, OrgUnitListView, PositionGroupListView
from apps.publications.views import (
    CategoryListView,
    EditorialCategoryDetailView,
    EditorialCategoryListCreateView,
    EditorialMediaDeleteView,
    EditorialMediaListUploadView,
    EditorialPublicationDetailView,
    EditorialPublicationDuplicateView,
    EditorialPublicationListCreateView,
    EditorialPublicationTransitionView,
    EditorialPublicationVersionDetailView,
    EditorialPublicationVersionListView,
    EditorialReviewListView,
    EditorialTagDetailView,
    EditorialTagListCreateView,
    MediaContentView,
    NewsDetailView,
    NewsListView,
    NewsPinnedListView,
    NewsPinView,
)

urlpatterns = [
    path("api/v1/news", NewsListView.as_view(), name="news-list"),
    path("api/v1/news/pinned", NewsPinnedListView.as_view(), name="news-pinned-list"),
    path("api/v1/news/categories", CategoryListView.as_view(), name="news-category-list"),
    path(
        "api/v1/news/<uuid:publication_id>/pin",
        NewsPinView.as_view(),
        name="news-pin",
    ),
    path("api/v1/news/<str:publication_id>", NewsDetailView.as_view(), name="news-detail"),
    path(
        "api/v1/news/<uuid:publication_id>/comments",
        CommentListCreateView.as_view(),
        name="comment-list",
    ),
    path(
        "api/v1/news/<uuid:publication_id>/comments/<uuid:comment_id>",
        CommentDetailView.as_view(),
        name="comment-detail",
    ),
    path(
        "api/v1/news/<uuid:publication_id>/reactions",
        ReactionSummaryView.as_view(),
        name="reaction-summary",
    ),
    path(
        "api/v1/news/<uuid:publication_id>/reactions/<str:reaction_type>",
        ReactionDetailView.as_view(),
        name="reaction-detail",
    ),
    path("api/v1/realtime/tickets", RealtimeTicketView.as_view(), name="realtime-ticket"),
    path(
        "api/v1/editorial/publications",
        EditorialPublicationListCreateView.as_view(),
        name="editorial-publication-list",
    ),
    path(
        "api/v1/editorial/publications/<uuid:id>",
        EditorialPublicationDetailView.as_view(),
        name="editorial-publication-detail",
    ),
    path(
        "api/v1/editorial/publications/<uuid:publication_id>/publish",
        EditorialPublicationTransitionView.as_view(),
        {"action": "publish"},
        name="editorial-publication-publish",
    ),
    *[
        path(
            f"api/v1/editorial/publications/<uuid:publication_id>/{action}",
            EditorialPublicationTransitionView.as_view(),
            {"action": action},
            name=f"editorial-publication-{action}",
        )
        for action in (
            "submit-review",
            "return-to-draft",
            "schedule",
            "cancel-schedule",
            "unpublish",
            "archive",
        )
    ],
    path(
        "api/v1/editorial/publications/<uuid:publication_id>/duplicate",
        EditorialPublicationDuplicateView.as_view(),
        name="editorial-publication-duplicate",
    ),
    path(
        "api/v1/editorial/publications/<uuid:publication_id>/versions",
        EditorialPublicationVersionListView.as_view(),
        name="editorial-publication-versions",
    ),
    path(
        "api/v1/editorial/publications/<uuid:publication_id>/versions/<int:version_number>",
        EditorialPublicationVersionDetailView.as_view(),
        name="editorial-publication-version-detail",
    ),
    path("api/v1/editorial/review", EditorialReviewListView.as_view(), name="editorial-review"),
    path(
        "api/v1/editorial/media",
        EditorialMediaListUploadView.as_view(),
        name="editorial-media",
    ),
    path(
        "api/v1/editorial/media/<uuid:asset_id>",
        EditorialMediaDeleteView.as_view(),
        name="editorial-media-detail",
    ),
    path(
        "api/v1/media/<uuid:asset_id>/content",
        MediaContentView.as_view(),
        name="media-content",
    ),
    path(
        "api/v1/editorial/categories",
        EditorialCategoryListCreateView.as_view(),
        name="editorial-categories",
    ),
    path(
        "api/v1/editorial/categories/<int:pk>",
        EditorialCategoryDetailView.as_view(),
        name="editorial-category-detail",
    ),
    path(
        "api/v1/editorial/tags",
        EditorialTagListCreateView.as_view(),
        name="editorial-tags",
    ),
    path(
        "api/v1/editorial/tags/<int:pk>",
        EditorialTagDetailView.as_view(),
        name="editorial-tag-detail",
    ),
    path("api/v1/me", MeView.as_view(), name="me"),
    path("api/v1/organization/units", OrgUnitListView.as_view(), name="org-unit-list"),
    path(
        "api/v1/organization/position-groups",
        PositionGroupListView.as_view(),
        name="position-group-list",
    ),
    path(
        "api/v1/organization/employees",
        EmployeeSearchView.as_view(),
        name="employee-search",
    ),
    path("api/v1/runtime/meta", RuntimeMetaView.as_view(), name="runtime-meta"),
    path("api/v1/health/live", LiveView.as_view(), name="health-live"),
    path("api/v1/health/ready", ReadyView.as_view(), name="health-ready"),
]

if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path("static/<path:path>", serve_static, {"insecure": True}),
        path("api/schema", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="api-docs",
        ),
    ]
