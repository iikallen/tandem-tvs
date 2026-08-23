from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from apps.core.views import LiveView, ReadyView, RuntimeMetaView
from apps.identity.views import MeView
from apps.organization.views import EmployeeSearchView, OrgUnitListView

urlpatterns = [
    path("api/v1/me", MeView.as_view(), name="me"),
    path("api/v1/organization/units", OrgUnitListView.as_view(), name="org-unit-list"),
    path(
        "api/v1/organization/employees",
        EmployeeSearchView.as_view(),
        name="employee-search",
    ),
    path("api/v1/runtime/meta", RuntimeMetaView.as_view(), name="runtime-meta"),
    path("api/v1/health/live", LiveView.as_view(), name="health-live"),
    path("api/v1/health/ready", ReadyView.as_view(), name="health-ready"),
    path(
        "api/schema",
        SpectacularAPIView.as_view(
            authentication_classes=[],
            permission_classes=[AllowAny],
        ),
        name="schema",
    ),
    path(
        "api/docs",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            authentication_classes=[],
            permission_classes=[AllowAny],
        ),
        name="api-docs",
    ),
]
