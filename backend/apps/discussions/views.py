from typing import cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from django.http import Http404
from rest_framework import generics, serializers, status
from rest_framework.response import Response

from apps.core.views import PrivateResponseMixin
from apps.identity.models import User
from apps.publications.services import visible_publication_or_404

from .models import Comment, Reaction
from .pagination import CommentCursorPagination
from .serializers import (
    CommentSerializer,
    CommentWriteSerializer,
    ReactionSerializer,
    ReactionSummarySerializer,
    RealtimeTicketSerializer,
)
from .services import create_comment, delete_comment, delete_reaction, put_reaction, update_comment
from .tickets import create_ticket


class CommentListCreateView(PrivateResponseMixin, generics.GenericAPIView):
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
        queryset = Comment.objects.filter(publication=publication).select_related("author")
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def post(self, request, publication_id):
        publication = self._publication()
        payload = CommentWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        comment = create_comment(
            publication=publication,
            author=request.user,
            body=payload.validated_data["body"],
        )
        return Response(self.get_serializer(comment).data, status=status.HTTP_201_CREATED)


class CommentDetailView(PrivateResponseMixin, generics.GenericAPIView):
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


class ReactionSummaryView(PrivateResponseMixin, generics.GenericAPIView):
    serializer_class = ReactionSummarySerializer

    def get(self, request, publication_id):
        publication = visible_publication_or_404(request.user, publication_id)
        counts = {
            row["reaction_type"]: row["count"]
            for row in Reaction.objects.filter(publication=publication)
            .values("reaction_type")
            .annotate(count=Count("id"))
        }
        mine = list(
            Reaction.objects.filter(publication=publication, user=request.user).values_list(
                "reaction_type", flat=True
            )
        )
        payload = {"total": sum(counts.values()), "counts": counts, "mine": mine}
        return Response(self.get_serializer(payload).data)


class ReactionDetailView(PrivateResponseMixin, generics.GenericAPIView):
    serializer_class = ReactionSerializer
    throttle_scope = "reaction"

    def _context(self, request, publication_id, reaction_type):
        publication = visible_publication_or_404(request.user, publication_id)
        if reaction_type not in Reaction.Type.values:
            raise Http404
        return publication

    def put(self, request, publication_id, reaction_type):
        publication = self._context(request, publication_id, reaction_type)
        reaction, created = put_reaction(
            publication=publication, user=request.user, reaction_type=reaction_type
        )
        return Response(
            self.get_serializer(reaction).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, publication_id, reaction_type):
        publication = self._context(request, publication_id, reaction_type)
        delete_reaction(publication=publication, user=request.user, reaction_type=reaction_type)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RealtimeTicketView(PrivateResponseMixin, generics.GenericAPIView):
    serializer_class = RealtimeTicketSerializer
    throttle_scope = "realtime_ticket"

    def post(self, request):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        publication = visible_publication_or_404(
            request.user, payload.validated_data["publication_id"]
        )
        token, expires_in = create_ticket(user_id=request.user.pk, publication_id=publication.pk)
        return Response({"ticket": token, "expires_in": expires_in})
