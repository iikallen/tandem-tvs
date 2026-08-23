from typing import cast
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Exists, IntegerField, OuterRef, Prefetch, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework import generics, serializers
from rest_framework.response import Response

from apps.core.views import PrivateResponseMixin
from apps.discussions.models import Comment, Reaction
from apps.identity.models import User

from .models import AudienceRule, Category, Publication, PublicationView
from .pagination import EditorialPagination, NewsCursorPagination
from .permissions import IsEditorialRole
from .serializers import (
    CategorySerializer,
    EditorialPublicationSerializer,
    NewsPublicationDetailSerializer,
    NewsPublicationSerializer,
    NewsQuerySerializer,
)
from .services import publish_publication, record_publication_view


def editorial_queryset():
    return Publication.objects.select_related("category", "author").prefetch_related(
        Prefetch(
            "audience_rules",
            queryset=AudienceRule.objects.select_related("org_unit", "employee"),
        )
    )


class EditorialPublicationListCreateView(PrivateResponseMixin, generics.ListCreateAPIView):
    serializer_class = EditorialPublicationSerializer
    permission_classes = [IsEditorialRole]
    pagination_class = EditorialPagination

    def get_queryset(self):
        return editorial_queryset()


class EditorialPublicationDetailView(PrivateResponseMixin, generics.RetrieveUpdateAPIView):
    serializer_class = EditorialPublicationSerializer
    permission_classes = [IsEditorialRole]
    lookup_field = "id"

    def get_queryset(self):
        return editorial_queryset()


class EditorialPublicationPublishView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsEditorialRole]
    serializer_class = EditorialPublicationSerializer

    def post(self, request, publication_id):
        publication = generics.get_object_or_404(Publication, pk=publication_id)
        try:
            publication = publish_publication(publication, actor=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        publication = editorial_queryset().get(pk=publication.pk)
        return Response(self.get_serializer(publication).data)


class CategoryListView(PrivateResponseMixin, generics.ListAPIView):
    serializer_class = CategorySerializer
    pagination_class = None
    queryset = Category.objects.filter(is_active=True)


def employee_news_queryset(user):
    viewed = PublicationView.objects.filter(publication=OuterRef("pk"), user=user)
    view_count = (
        PublicationView.objects.filter(publication=OuterRef("pk"))
        .values("publication")
        .annotate(total=Count("pk"))
        .values("total")
    )
    comment_count = (
        Comment.objects.filter(publication=OuterRef("pk"), status=Comment.Status.ACTIVE)
        .values("publication")
        .annotate(total=Count("pk"))
        .values("total")
    )
    reaction_count = (
        Reaction.objects.filter(publication=OuterRef("pk"))
        .values("publication")
        .annotate(total=Count("pk"))
        .values("total")
    )
    return (
        Publication.objects.visible_to(user)
        .select_related("category", "author")
        .annotate(
            view_count=Coalesce(Subquery(view_count, output_field=IntegerField()), Value(0)),
            comment_count=Coalesce(Subquery(comment_count, output_field=IntegerField()), Value(0)),
            reaction_count=Coalesce(
                Subquery(reaction_count, output_field=IntegerField()), Value(0)
            ),
            is_read=Exists(viewed),
            search_rank=Value(0.0),
        )
    )


class NewsListView(PrivateResponseMixin, generics.ListAPIView):
    serializer_class = NewsPublicationSerializer
    pagination_class = NewsCursorPagination

    def get_queryset(self):
        params = NewsQuerySerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        queryset = employee_news_queryset(self.request.user)
        if category := data.get("category"):
            queryset = queryset.filter(category__slug=category)
        if author := data.get("author"):
            queryset = queryset.filter(author__portal_id=author)
        if date_from := data.get("date_from"):
            queryset = queryset.filter(published_at__date__gte=date_from)
        if date_to := data.get("date_to"):
            queryset = queryset.filter(published_at__date__lte=date_to)
        if data.get("unread") is True:
            queryset = queryset.filter(is_read=False)
        if query := data.get("q"):
            queryset = queryset.search(query)
        return queryset


class NewsDetailView(PrivateResponseMixin, generics.RetrieveAPIView):
    serializer_class = NewsPublicationDetailSerializer

    def get_object(self):
        lookup = self.kwargs["publication_id"]
        query = {"id": UUID(lookup)} if _is_uuid(lookup) else {"slug": lookup}
        publication = generics.get_object_or_404(employee_news_queryset(self.request.user), **query)
        record_publication_view(publication, cast(User, self.request.user))
        publication.is_read = True
        publication.view_count = publication.views.count()
        return publication


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True
