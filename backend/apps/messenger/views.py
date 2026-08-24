from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.response import Response

from apps.core.views import PrivateResponseMixin
from apps.identity.models import AccessGrant, User
from apps.identity.permissions import HasMessengerAccess

from .models import Conversation, ConversationMembership, Message
from .serializers import (
    ConversationSerializer,
    DirectConversationSerializer,
    GroupConversationSerializer,
    MessageSerializer,
    MessageWriteSerializer,
    PersonSerializer,
    ReadSerializer,
)
from .services import (
    create_direct_conversation,
    create_group_conversation,
    eligible_people,
    mark_read,
    member_conversation,
    send_message,
)


def conversation_queryset():
    memberships = ConversationMembership.objects.select_related("user__org_unit")
    last_message = Message.objects.select_related("author__org_unit", "conversation").order_by(
        "-sequence"
    )[:1]
    return Conversation.objects.prefetch_related(
        Prefetch("memberships", queryset=memberships, to_attr="loaded_memberships"),
        Prefetch("messages", queryset=last_message, to_attr="loaded_last_messages"),
    )


class MessengerAPIView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasMessengerAccess]


class PeopleView(MessengerAPIView):
    serializer_class = PersonSerializer
    throttle_scope = "messenger_people"

    def get(self, request):
        people = User.objects.filter(
            is_active=True,
            access_grants__module=AccessGrant.Module.MESSENGER,
        ).exclude(pk=request.user.pk)
        if search := request.query_params.get("search", "").strip():
            people = people.filter(Q(full_name__icontains=search) | Q(username__icontains=search))
        people = people.select_related("org_unit").distinct().order_by("full_name", "pk")[:50]
        return Response(self.get_serializer(people, many=True).data)


class ConversationListView(MessengerAPIView):
    serializer_class = ConversationSerializer

    def get(self, request):
        conversations = (
            conversation_queryset()
            .filter(memberships__user=request.user)
            .distinct()
            .order_by("-last_message_at", "-created_at")[:50]
        )
        return Response(self.get_serializer(conversations, many=True).data)


class DirectConversationView(MessengerAPIView):
    serializer_class = DirectConversationSerializer
    throttle_scope = "messenger_direct"

    def post(self, request):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user_id = payload.validated_data["user_id"]
        if user_id == request.user.pk:
            raise serializers.ValidationError({"user_id": "A direct chat requires another user."})
        other = get_object_or_404(eligible_people([user_id]), pk=user_id)
        conversation, created = create_direct_conversation(request.user, other)
        conversation = conversation_queryset().get(pk=conversation.pk)
        data = ConversationSerializer(conversation, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class GroupConversationView(MessengerAPIView):
    serializer_class = GroupConversationSerializer
    throttle_scope = "messenger_group"

    def post(self, request):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        member_ids = set(payload.validated_data["member_ids"]) - {request.user.pk}
        if not member_ids:
            raise serializers.ValidationError(
                {"member_ids": "A group requires at least one other member."}
            )
        members = list(eligible_people(member_ids))
        if len(members) != len(member_ids):
            raise serializers.ValidationError(
                {"member_ids": "Every member must be active and have Messenger access."}
            )
        conversation = create_group_conversation(
            request.user, title=payload.validated_data["title"], members=members
        )
        conversation = conversation_queryset().get(pk=conversation.pk)
        return Response(
            ConversationSerializer(conversation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ConversationDetailView(MessengerAPIView):
    serializer_class = ConversationSerializer

    def get(self, request, conversation_id):
        conversation = get_object_or_404(
            conversation_queryset().filter(memberships__user=request.user).distinct(),
            pk=conversation_id,
        )
        return Response(self.get_serializer(conversation).data)


class MessageListCreateView(MessengerAPIView):
    serializer_class = MessageWriteSerializer

    def get_throttles(self):
        self.throttle_scope = "messenger_message" if self.request.method == "POST" else None
        return super().get_throttles()

    def get(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        try:
            page_size = int(request.query_params.get("page_size", "50"))
            before = int(
                request.query_params.get("before_sequence", conversation.last_sequence + 1)
            )
        except ValueError as exc:
            raise serializers.ValidationError("Pagination values must be integers.") from exc
        if not 1 <= page_size <= 50 or before < 1:
            raise serializers.ValidationError(
                "page_size must be 1 to 50 and before_sequence must be positive."
            )
        related = cast(Any, conversation)
        memberships = list(
            related.memberships.select_related("user__org_unit").order_by("joined_at", "id")
        )
        descending = list(
            related.messages.filter(sequence__lt=before)
            .select_related("author__org_unit", "conversation")
            .order_by("-sequence")[: page_size + 1]
        )
        has_more = len(descending) > page_size
        messages = list(reversed(descending[:page_size]))
        return Response(
            {
                "messages": MessageSerializer(
                    messages, many=True, context={"memberships": memberships}
                ).data,
                "has_more": has_more,
                "next_before_sequence": messages[0].sequence if has_more else None,
            }
        )

    def post(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        message, created = send_message(conversation, author=request.user, **payload.validated_data)
        memberships = list(cast(Any, conversation).memberships.select_related("user__org_unit"))
        data = MessageSerializer(message, context={"memberships": memberships}).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ReadView(MessengerAPIView):
    serializer_class = ReadSerializer

    def post(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            membership = mark_read(
                conversation, user=request.user, sequence=payload.validated_data["sequence"]
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return Response(
            {
                "last_read_sequence": membership.last_read_sequence,
                "read_at": membership.read_at,
            }
        )
