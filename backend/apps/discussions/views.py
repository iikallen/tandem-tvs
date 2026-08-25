from datetime import timedelta
from typing import cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, F, Q, Window
from django.db.models.functions import RowNumber
from django.http import Http404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.views import PrivateResponseMixin
from apps.identity.models import AccessGrant, User
from apps.identity.permissions import HasNewsAccess, IsNewsModerator, has_module_access
from apps.publications.engagement import resolve_recipient_users
from apps.publications.media import create_media_asset
from apps.publications.models import AuditEvent
from apps.publications.permissions import IsEditorRole
from apps.publications.serializers import MediaAssetSerializer, UserSummarySerializer
from apps.publications.services import record_audit_event, visible_publication_or_404
from apps.realtime.claims import RealtimeScope
from apps.realtime.tickets import create_ticket as create_realtime_ticket

from .models import (
    Comment,
    CommentReport,
    CommentRestriction,
    EngagementSettings,
    Reaction,
    StopWord,
)
from .pagination import CommentCursorPagination, ReplyCursorPagination
from .serializers import (
    CommentReportSerializer,
    CommentSerializer,
    CommentWriteSerializer,
    EngagementSettingsSerializer,
    ReactionSerializer,
    ReactionSummarySerializer,
    RealtimeTicketSerializer,
    StopWordSerializer,
)
from .services import (
    create_comment,
    delete_comment,
    delete_reaction,
    moderate_comment,
    put_reaction,
    report_comment,
    update_comment,
)
from .tickets import create_ticket


def _comments_queryset():
    return Comment.objects.select_related("author", "reply_to__author").prefetch_related(
        "mentions__mentioned_user", "attachments__asset"
    )


def _serialize_roots(view, page):
    roots = list(page)
    ids = [root.pk for root in roots]
    replies = list(
        _comments_queryset()
        .filter(thread_root_id__in=ids)
        .annotate(
            preview_rank=Window(
                expression=RowNumber(),
                partition_by=[F("thread_root_id")],
                order_by=[F("created_at").asc(), F("id").asc()],
            )
        )
        .filter(preview_rank__lte=2)
        .order_by("thread_root_id", "created_at", "id")
    )
    previews: dict[object, list[Comment]] = {root_id: [] for root_id in ids}
    for reply in replies:
        if reply.thread_root is not None:
            previews[reply.thread_root.pk].append(reply)
    for root in roots:
        root.preview_items = previews[root.pk]
    return view.get_serializer(roots, many=True).data


class CommentListCreateView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]
    serializer_class = CommentSerializer
    pagination_class = CommentCursorPagination

    def get_throttles(self):
        self.throttle_scope = "comment_create" if self.request.method == "POST" else None
        return super().get_throttles()

    def _publication(self):
        return visible_publication_or_404(
            cast(User, self.request.user), self.kwargs["publication_id"]
        )

    def get(self, request, publication_id):
        publication = self._publication()
        sort = request.query_params.get("sort", "recent")
        if sort not in {"recent", "popular"}:
            raise serializers.ValidationError({"sort": "Use recent or popular."})
        queryset = (
            _comments_queryset()
            .filter(publication=publication, thread_root__isnull=True)
            .annotate(
                reply_count=Count("thread_replies", distinct=True),
                reaction_count=Count("reactions", distinct=True),
            )
        )
        queryset = (
            queryset.order_by("-reaction_count", "-reply_count", "-created_at", "-id")
            if sort == "popular"
            else queryset.order_by("-created_at", "-id")
        )
        paginator = cast(CommentCursorPagination, self.paginator)
        paginator.ordering = (
            ("-reaction_count", "-reply_count", "-created_at", "-id")
            if sort == "popular"
            else ("-created_at", "-id")
        )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(_serialize_roots(self, page))

    def post(self, request, publication_id):
        publication = self._publication()
        payload = CommentWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        try:
            comment = create_comment(
                publication=publication,
                author=request.user,
                body=data["body"],
                reply_to_id=data.get("reply_to"),
                mentioned_users=data["mentioned_users"],
                assets=data["attachments"],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        comment = _comments_queryset().get(pk=comment.pk)
        return Response(self.get_serializer(comment).data, status=status.HTTP_201_CREATED)


class CommentRepliesView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]
    serializer_class = CommentSerializer
    pagination_class = ReplyCursorPagination

    def get(self, request, publication_id, root_id):
        publication = visible_publication_or_404(request.user, publication_id)
        root = generics.get_object_or_404(
            Comment, pk=root_id, publication=publication, thread_root__isnull=True
        )
        queryset = (
            _comments_queryset()
            .filter(thread_root=root)
            .annotate(
                reply_count=Count("thread_replies", distinct=True),
                reaction_count=Count("reactions", distinct=True),
            )
            .order_by("created_at", "id")
        )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


class CommentDetailView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]
    serializer_class = CommentSerializer
    throttle_scope = "comment_edit"

    def _publication(self):
        return visible_publication_or_404(
            cast(User, self.request.user), self.kwargs["publication_id"]
        )

    def patch(self, request, publication_id, comment_id):
        publication = self._publication()
        payload = CommentWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        if set(request.data) != {"body"}:
            raise serializers.ValidationError("Only body can be edited.")
        try:
            comment = update_comment(
                publication=publication,
                comment_id=comment_id,
                actor=request.user,
                body=payload.validated_data["body"],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(self.get_serializer(comment).data)

    def delete(self, request, publication_id, comment_id):
        publication = self._publication()
        delete_comment(publication=publication, comment_id=comment_id, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _reaction_summary(queryset, user):
    counts = {
        row["reaction_type"]: row["count"]
        for row in queryset.values("reaction_type").annotate(count=Count("id"))
    }
    mine = list(queryset.filter(user=user).values_list("reaction_type", flat=True))
    actors = {
        reaction_type: UserSummarySerializer(
            [
                reaction.user
                for reaction in queryset.filter(reaction_type=reaction_type).select_related("user")[
                    :20
                ]
            ],
            many=True,
        ).data
        for reaction_type in counts
    }
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "mine": mine,
        "actors": actors,
        "enabled_types": EngagementSettings.load().enabled_reaction_types,
    }


class ReactionSummaryView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]
    serializer_class = ReactionSummarySerializer

    def get(self, request, publication_id):
        publication = visible_publication_or_404(request.user, publication_id)
        return Response(
            self.get_serializer(
                _reaction_summary(Reaction.objects.filter(publication=publication), request.user)
            ).data
        )


class ReactionDetailView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]
    serializer_class = ReactionSerializer
    throttle_scope = "reaction"

    def _context(self, request, publication_id, reaction_type):
        publication = visible_publication_or_404(request.user, publication_id)
        if reaction_type not in Reaction.Type.values:
            raise Http404
        return publication

    def put(self, request, publication_id, reaction_type):
        publication = self._context(request, publication_id, reaction_type)
        try:
            reaction, created = put_reaction(
                publication=publication, user=request.user, reaction_type=reaction_type
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(
            self.get_serializer(reaction).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, publication_id, reaction_type):
        publication = self._context(request, publication_id, reaction_type)
        delete_reaction(publication=publication, user=request.user, reaction_type=reaction_type)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentReactionSummaryView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]
    serializer_class = ReactionSummarySerializer

    def get(self, request, publication_id, comment_id):
        publication = visible_publication_or_404(request.user, publication_id)
        comment = generics.get_object_or_404(Comment, pk=comment_id, publication=publication)
        return Response(
            self.get_serializer(
                _reaction_summary(Reaction.objects.filter(comment=comment), request.user)
            ).data
        )


class CommentReactionDetailView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]
    serializer_class = ReactionSerializer
    throttle_scope = "reaction"

    def _context(self, request, publication_id, comment_id, reaction_type):
        publication = visible_publication_or_404(request.user, publication_id)
        comment = generics.get_object_or_404(Comment, pk=comment_id, publication=publication)
        if reaction_type not in Reaction.Type.values:
            raise Http404
        return publication, comment

    def put(self, request, publication_id, comment_id, reaction_type):
        publication, comment = self._context(request, publication_id, comment_id, reaction_type)
        try:
            reaction, created = put_reaction(
                publication=publication,
                comment=comment,
                user=request.user,
                reaction_type=reaction_type,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(
            self.get_serializer(reaction).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, publication_id, comment_id, reaction_type):
        publication, comment = self._context(request, publication_id, comment_id, reaction_type)
        delete_reaction(
            publication=publication, comment=comment, user=request.user, reaction_type=reaction_type
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MentionCandidateView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]

    def get(self, request, publication_id):
        publication = visible_publication_or_404(request.user, publication_id)
        search = request.query_params.get("search", "").strip().casefold()
        users = resolve_recipient_users(publication)
        if search:
            users = [
                user
                for user in users
                if search in user.full_name.casefold() or search in user.email.casefold()
            ]
        return Response(UserSummarySerializer(users[:20], many=True).data)


class CommentMediaUploadView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "comment_upload"

    def post(self, request, publication_id):
        publication = visible_publication_or_404(request.user, publication_id)
        if not publication.comments_enabled or not publication.category.comment_attachments_enabled:
            raise serializers.ValidationError("Comment attachments are disabled.")
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": "A file is required."})
        try:
            asset = create_media_asset(upload=upload, actor=request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc
        return Response(MediaAssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class CommentReportView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasNewsAccess]
    serializer_class = CommentReportSerializer

    def post(self, request, publication_id, comment_id):
        publication = visible_publication_or_404(request.user, publication_id)
        comment = generics.get_object_or_404(Comment, pk=comment_id, publication=publication)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        report, created = report_comment(
            comment=comment, reporter=request.user, reason=payload.validated_data.get("reason", "")
        )
        return Response(
            self.get_serializer(report).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class EngagementSettingsView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsEditorRole]
    serializer_class = EngagementSettingsSerializer

    def get(self, request):
        return Response(self.get_serializer(EngagementSettings.load()).data)

    def patch(self, request):
        row = EngagementSettings.load()
        previous = self.get_serializer(row).data
        payload = self.get_serializer(row, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        with transaction.atomic():
            row = payload.save()
            record_audit_event(
                actor=request.user,
                event_type=AuditEvent.Type.ENGAGEMENT_UPDATED,
                target_type=AuditEvent.TargetType.SETTINGS,
                target_id="engagement",
                previous_state=previous,
                new_state=self.get_serializer(row).data,
            )
        return Response(self.get_serializer(row).data)


class StopWordListCreateView(PrivateResponseMixin, generics.ListCreateAPIView):
    permission_classes = [IsEditorRole]
    serializer_class = StopWordSerializer
    pagination_class = None
    queryset = StopWord.objects.all()

    def perform_create(self, serializer):
        with transaction.atomic():
            word = serializer.save()
            record_audit_event(
                actor=cast(User, self.request.user),
                event_type=AuditEvent.Type.STOP_WORD_CREATED,
                target_type=AuditEvent.TargetType.SETTINGS,
                target_id=f"stop-word:{word.pk}",
                new_state={"value": word.value, "is_active": word.is_active},
            )


class StopWordDetailView(PrivateResponseMixin, generics.UpdateAPIView):
    permission_classes = [IsEditorRole]
    serializer_class = StopWordSerializer
    queryset = StopWord.objects.all()

    def perform_update(self, serializer):
        word = cast(StopWord, serializer.instance)
        previous = {
            "value": word.value,
            "is_active": word.is_active,
        }
        with transaction.atomic():
            word = serializer.save()
            record_audit_event(
                actor=cast(User, self.request.user),
                event_type=(
                    AuditEvent.Type.STOP_WORD_DISABLED
                    if previous["is_active"] and not word.is_active
                    else AuditEvent.Type.ENGAGEMENT_UPDATED
                ),
                target_type=AuditEvent.TargetType.SETTINGS,
                target_id=f"stop-word:{word.pk}",
                previous_state=previous,
                new_state={"value": word.value, "is_active": word.is_active},
            )


class ModerationQueueView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsNewsModerator]

    def get(self, request):
        reports = CommentReport.objects.filter(status=CommentReport.Status.OPEN).select_related(
            "comment__author", "comment__publication"
        )[:100]
        flags = (
            Comment.objects.filter(flags__is_open=True)
            .select_related("author", "publication")
            .distinct()[:100]
        )
        return Response(
            {
                "reports": [
                    {
                        "id": str(item.pk),
                        "comment": CommentSerializer(
                            item.comment, context={"request": request}
                        ).data,
                        "publication_title": item.comment.publication.title,
                        "created_at": item.created_at,
                    }
                    for item in reports
                ],
                "flags": CommentSerializer(flags, many=True, context={"request": request}).data,
            }
        )


class ModerationCommentActionView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsNewsModerator]

    def post(self, request, comment_id, action):
        comment = generics.get_object_or_404(
            Comment.objects.select_related("publication"), pk=comment_id
        )
        try:
            comment = moderate_comment(comment=comment, actor=request.user, action=action)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(CommentSerializer(comment, context={"request": request}).data)


class ModerationReportResolveView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsNewsModerator]

    def post(self, request, report_id):
        with transaction.atomic():
            report = generics.get_object_or_404(
                CommentReport.objects.select_for_update(), pk=report_id
            )
            if report.status != CommentReport.Status.RESOLVED:
                report.status = CommentReport.Status.RESOLVED
                report.resolved_at = timezone.now()
                report.resolved_by = request.user
                report.save(update_fields=["status", "resolved_at", "resolved_by"])
                record_audit_event(
                    publication=report.comment.publication,
                    actor=request.user,
                    event_type=AuditEvent.Type.REPORT_RESOLVED,
                    target_type=AuditEvent.TargetType.REPORT,
                    target_id=report.pk,
                    previous_state={"status": "OPEN"},
                    new_state={"status": "RESOLVED"},
                )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentRestrictionView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [IsNewsModerator]

    def post(self, request, portal_id):
        user = generics.get_object_or_404(
            User.objects.filter(Q(portal_id=portal_id) | Q(username=portal_id)), is_active=True
        )
        hours = request.data.get("hours", 24)
        if not isinstance(hours, int) or not 1 <= hours <= 8760:
            raise serializers.ValidationError({"hours": "Use an integer from 1 to 8760."})
        with transaction.atomic():
            row = CommentRestriction.objects.create(
                user=user,
                created_by=request.user,
                reason=str(request.data.get("reason", ""))[:500],
                expires_at=timezone.now() + timedelta(hours=hours),
            )
            record_audit_event(
                actor=request.user,
                event_type=AuditEvent.Type.USER_RESTRICTED,
                target_type=AuditEvent.TargetType.USER,
                target_id=user.portal_id or user.username,
                new_state={"restriction_id": row.pk, "expires_at": row.expires_at.isoformat()},
            )
        return Response(
            {"id": row.pk, "expires_at": row.expires_at}, status=status.HTTP_201_CREATED
        )

    def delete(self, request, portal_id):
        user = generics.get_object_or_404(
            User.objects.filter(Q(portal_id=portal_id) | Q(username=portal_id))
        )
        now = timezone.now()
        with transaction.atomic():
            CommentRestriction.objects.filter(user=user, revoked_at__isnull=True).update(
                revoked_at=now
            )
            record_audit_event(
                actor=request.user,
                event_type=AuditEvent.Type.RESTRICTION_REVOKED,
                target_type=AuditEvent.TargetType.USER,
                target_id=user.portal_id or user.username,
                new_state={"revoked_at": now.isoformat()},
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RealtimeTicketView(PrivateResponseMixin, generics.GenericAPIView):
    serializer_class = RealtimeTicketSerializer
    throttle_scope = "realtime_ticket"

    def post(self, request):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        if not request.session.session_key:
            request.session.save()
        if payload.validated_data["scope"] == RealtimeScope.MESSENGER:
            if not has_module_access(request.user, AccessGrant.Module.MESSENGER):
                raise PermissionDenied("Messenger access is required.")
            token, expires_in = create_realtime_ticket(
                user_id=request.user.pk,
                security_epoch=request.user.security_epoch,
                session_key=request.session.session_key,
                scope=RealtimeScope.MESSENGER,
            )
            return Response({"ticket": token, "expires_in": expires_in})
        if payload.validated_data["scope"] == RealtimeScope.NOTIFICATIONS:
            token, expires_in = create_realtime_ticket(
                user_id=request.user.pk,
                security_epoch=request.user.security_epoch,
                session_key=request.session.session_key,
                scope=RealtimeScope.NOTIFICATIONS,
            )
            return Response({"ticket": token, "expires_in": expires_in})
        if not has_module_access(request.user, AccessGrant.Module.NEWS):
            raise PermissionDenied("News access is required.")
        publication = visible_publication_or_404(
            request.user, payload.validated_data["publication_id"]
        )
        token, expires_in = create_ticket(
            user_id=request.user.pk,
            publication_id=publication.pk,
            session_key=request.session.session_key,
        )
        return Response({"ticket": token, "expires_in": expires_in})
