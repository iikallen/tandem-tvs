from typing import cast
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Exists, IntegerField, OuterRef, Prefetch, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from django.utils.http import content_disposition_header
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.views import PrivateResponseMixin
from apps.discussions.models import Comment, Reaction
from apps.identity.models import User

from .media import can_read_media, create_media_asset, delete_media_asset
from .models import (
    AudienceRule,
    AuditEvent,
    Category,
    MediaAsset,
    Publication,
    PublicationVersion,
    PublicationView,
    Tag,
)
from .pagination import EditorialPagination, NewsCursorPagination
from .permissions import IsEditorialRole
from .serializers import (
    CategorySerializer,
    EditorialPublicationSerializer,
    MediaAssetSerializer,
    NewsPublicationDetailSerializer,
    NewsPublicationSerializer,
    NewsQuerySerializer,
    PinSerializer,
    PublicationVersionSerializer,
    TagSerializer,
    TransitionSerializer,
)
from .services import (
    duplicate_publication,
    is_editor,
    pin_publication,
    record_audit_event,
    record_publication_view,
    transition_publication,
    unpin_publication,
)


def editorial_queryset():
    return Publication.objects.select_related(
        "category", "author", "cover", "pin"
    ).prefetch_related(
        "tags",
        "media_usages__asset",
        Prefetch(
            "audience_rules",
            queryset=AudienceRule.objects.select_related("org_unit", "employee"),
        ),
    )


def _editorial_for(user: object):
    queryset = editorial_queryset()
    return queryset if is_editor(user) else queryset.filter(author=user)


def _taxonomy_state(instance: Category | Tag) -> dict[str, object]:
    fields = ["slug", "name", "is_active"]
    if isinstance(instance, Category):
        fields.append("sort_order")
    return {field: getattr(instance, field) for field in fields}


class EditorialPublicationListCreateView(PrivateResponseMixin, generics.ListCreateAPIView):
    serializer_class = EditorialPublicationSerializer
    permission_classes = [IsEditorialRole]
    pagination_class = EditorialPagination

    def get_queryset(self):
        queryset = _editorial_for(self.request.user)
        if publication_status := self.request.query_params.get("status"):
            if publication_status not in Publication.Status.values:
                raise serializers.ValidationError({"status": "Unknown publication status."})
            queryset = queryset.filter(status=publication_status)
        return queryset


class EditorialReviewListView(EditorialPublicationListCreateView):
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return _editorial_for(self.request.user).filter(status=Publication.Status.IN_REVIEW)


class EditorialPublicationDetailView(PrivateResponseMixin, generics.RetrieveUpdateAPIView):
    serializer_class = EditorialPublicationSerializer
    permission_classes = [IsEditorialRole]
    lookup_field = "id"

    def get_queryset(self):
        return _editorial_for(self.request.user)


class EditorialPublicationTransitionView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsEditorialRole]
    serializer_class = TransitionSerializer

    def post(self, request, publication_id, action):
        publication = generics.get_object_or_404(_editorial_for(request.user), pk=publication_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            publication = transition_publication(
                publication,
                actor=request.user,
                action=action,
                **payload.validated_data,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        publication = editorial_queryset().get(pk=publication.pk)
        return Response(EditorialPublicationSerializer(publication).data)


class EditorialPublicationDuplicateView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsEditorialRole]

    def post(self, request, publication_id):
        publication = generics.get_object_or_404(_editorial_for(request.user), pk=publication_id)
        try:
            clone = duplicate_publication(publication, actor=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        clone = editorial_queryset().get(pk=clone.pk)
        return Response(EditorialPublicationSerializer(clone).data, status=status.HTTP_201_CREATED)


class EditorialPublicationVersionListView(PrivateResponseMixin, generics.ListAPIView):
    permission_classes = [IsEditorialRole]
    serializer_class = PublicationVersionSerializer
    pagination_class = None

    def get_queryset(self):
        publication = generics.get_object_or_404(
            _editorial_for(self.request.user), pk=self.kwargs["publication_id"]
        )
        return PublicationVersion.objects.filter(publication=publication).select_related("actor")


class EditorialPublicationVersionDetailView(PrivateResponseMixin, generics.RetrieveAPIView):
    permission_classes = [IsEditorialRole]
    serializer_class = PublicationVersionSerializer
    lookup_field = "version_number"
    lookup_url_kwarg = "version_number"

    def get_queryset(self):
        publication = generics.get_object_or_404(
            _editorial_for(self.request.user), pk=self.kwargs["publication_id"]
        )
        return PublicationVersion.objects.filter(publication=publication).select_related("actor")


class CategoryListView(PrivateResponseMixin, generics.ListAPIView):
    serializer_class = CategorySerializer
    pagination_class = None
    queryset = Category.objects.filter(is_active=True)


class EditorialCategoryListCreateView(PrivateResponseMixin, generics.ListCreateAPIView):
    permission_classes = [IsEditorialRole]
    serializer_class = CategorySerializer
    pagination_class = None
    queryset = Category.objects.all()

    def perform_create(self, serializer):
        if not is_editor(self.request.user):
            raise serializers.ValidationError("An editor role is required.")
        with transaction.atomic():
            category = serializer.save()
            record_audit_event(
                actor=cast(User, self.request.user),
                event_type=AuditEvent.Type.CATEGORY_CREATED,
                target_type=AuditEvent.TargetType.CATEGORY,
                target_id=category.pk,
                new_state=_taxonomy_state(category),
            )


class EditorialCategoryDetailView(PrivateResponseMixin, generics.UpdateAPIView):
    permission_classes = [IsEditorialRole]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def perform_update(self, serializer):
        if not is_editor(self.request.user):
            raise serializers.ValidationError("An editor role is required.")
        previous = _taxonomy_state(cast(Category, serializer.instance))
        with transaction.atomic():
            category = serializer.save()
            record_audit_event(
                actor=cast(User, self.request.user),
                event_type=AuditEvent.Type.CATEGORY_UPDATED,
                target_type=AuditEvent.TargetType.CATEGORY,
                target_id=category.pk,
                previous_state=previous,
                new_state=_taxonomy_state(category),
            )


class EditorialTagListCreateView(PrivateResponseMixin, generics.ListCreateAPIView):
    permission_classes = [IsEditorialRole]
    serializer_class = TagSerializer
    pagination_class = None
    queryset = Tag.objects.all()

    def perform_create(self, serializer):
        if not is_editor(self.request.user):
            raise serializers.ValidationError("An editor role is required.")
        with transaction.atomic():
            tag = serializer.save()
            record_audit_event(
                actor=cast(User, self.request.user),
                event_type=AuditEvent.Type.TAG_CREATED,
                target_type=AuditEvent.TargetType.TAG,
                target_id=tag.pk,
                new_state=_taxonomy_state(tag),
            )


class EditorialTagDetailView(PrivateResponseMixin, generics.UpdateAPIView):
    permission_classes = [IsEditorialRole]
    serializer_class = TagSerializer
    queryset = Tag.objects.all()

    def perform_update(self, serializer):
        if not is_editor(self.request.user):
            raise serializers.ValidationError("An editor role is required.")
        previous = _taxonomy_state(cast(Tag, serializer.instance))
        with transaction.atomic():
            tag = serializer.save()
            record_audit_event(
                actor=cast(User, self.request.user),
                event_type=AuditEvent.Type.TAG_UPDATED,
                target_type=AuditEvent.TargetType.TAG,
                target_id=tag.pk,
                previous_state=previous,
                new_state=_taxonomy_state(tag),
            )


class EditorialMediaListUploadView(PrivateResponseMixin, generics.ListCreateAPIView):
    permission_classes = [IsEditorialRole]
    serializer_class = MediaAssetSerializer
    pagination_class = EditorialPagination
    parser_classes = [MultiPartParser, FormParser]
    queryset = MediaAsset.objects.select_related("uploader")

    def create(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": "A file is required."})
        try:
            asset = create_media_asset(upload=upload, actor=cast(User, request.user))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc
        return Response(MediaAssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class EditorialMediaDeleteView(PrivateResponseMixin, generics.DestroyAPIView):
    permission_classes = [IsEditorialRole]
    queryset = MediaAsset.objects.all()
    lookup_url_kwarg = "asset_id"

    def perform_destroy(self, instance):
        try:
            delete_media_asset(instance, actor=cast(User, self.request.user))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc


class MediaContentView(PrivateResponseMixin, generics.GenericAPIView):
    def get(self, request, asset_id):
        asset = generics.get_object_or_404(MediaAsset, pk=asset_id, status=MediaAsset.Status.READY)
        if not can_read_media(request.user, asset):
            raise Http404
        response = HttpResponse(status=200, content_type=asset.mime_type)
        response["X-Accel-Redirect"] = f"/_protected_media/{asset.storage_key}"
        response["Content-Length"] = str(asset.size)
        disposition = content_disposition_header(
            asset.kind == MediaAsset.Kind.DOCUMENT, asset.original_name
        )
        if disposition:
            response["Content-Disposition"] = disposition
        response["Cache-Control"] = "private, no-store"
        return response


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
        .select_related("category", "author", "cover", "pin")
        .prefetch_related("tags", "media_usages__asset")
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
        queryset = employee_news_queryset(self.request.user).filter(pin__isnull=True)
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


class NewsPinnedListView(PrivateResponseMixin, generics.ListAPIView):
    serializer_class = NewsPublicationSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            employee_news_queryset(self.request.user)
            .filter(pin__isnull=False)
            .order_by("pin__slot")
        )


class NewsPinView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsEditorialRole]

    def put(self, request, publication_id):
        payload = PinSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        publication = generics.get_object_or_404(Publication, pk=publication_id)
        try:
            pin = pin_publication(
                publication, actor=request.user, slot=payload.validated_data["slot"]
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response({"publication_id": str(publication.pk), "slot": pin.slot})

    def delete(self, request, publication_id):
        publication = generics.get_object_or_404(Publication, pk=publication_id)
        unpin_publication(publication, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
