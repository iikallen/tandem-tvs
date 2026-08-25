from typing import Any, cast

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.cache import caches
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, UserRateThrottle

from apps.core.views import PrivateResponseMixin
from apps.identity.models import AccessGrant, User
from apps.identity.permissions import HasMessengerAccess, IsMessengerAdmin
from apps.publications.media import create_media_asset
from apps.publications.serializers import MediaAssetSerializer

from .models import (
    Conversation,
    ConversationMembership,
    Message,
    MessageAttachment,
    MessageReaction,
    PinnedMessage,
)
from .pagination import ConversationCursorPagination, MembershipPagination
from .serializers import (
    ChannelConversationSerializer,
    ChannelSettingsSerializer,
    ConversationDetailSerializer,
    ConversationStateSerializer,
    ConversationSummarySerializer,
    DirectConversationSerializer,
    GroupConversationSerializer,
    MemberInputSerializer,
    MemberRoleSerializer,
    MembershipSerializer,
    MessageEditSerializer,
    MessageReactionWriteSerializer,
    MessageSearchSerializer,
    MessageSerializer,
    MessageWriteSerializer,
    PersonSerializer,
    ReadSerializer,
)
from .services import (
    add_group_member,
    change_group_role,
    create_channel,
    create_direct_conversation,
    create_group_conversation,
    delete_message,
    delete_message_reaction,
    edit_message,
    eligible_people,
    leave_group,
    mark_delivered,
    mark_read,
    member_conversation,
    membership_message_filter,
    pin_message,
    put_message_reaction,
    remove_group_member,
    send_message,
    unpin_message,
    update_channel_settings,
    update_conversation_state,
    visible_message,
)


def _message_queryset():
    return Message.objects.select_related(
        "author__org_unit", "conversation", "reply_to__author__org_unit"
    ).prefetch_related(
        Prefetch(
            "attachments",
            queryset=MessageAttachment.objects.select_related("asset"),
            to_attr="loaded_attachments",
        ),
        Prefetch(
            "reactions",
            queryset=MessageReaction.objects.select_related("user"),
            to_attr="loaded_reactions",
        ),
    )


def conversation_summary_queryset(user: User):
    active = ConversationMembership.objects.filter(left_at__isnull=True).select_related(
        "user__org_unit"
    )
    return (
        Conversation.objects.filter(memberships__user=user, memberships__left_at__isnull=True)
        .annotate(
            is_pinned=Exists(
                ConversationMembership.objects.filter(
                    conversation=OuterRef("pk"),
                    user=user,
                    left_at__isnull=True,
                    pinned_at__isnull=False,
                )
            ),
            member_count=Count(
                "memberships", filter=Q(memberships__left_at__isnull=True), distinct=True
            ),
        )
        .prefetch_related(
            Prefetch(
                "memberships",
                queryset=active.filter(user=user),
                to_attr="loaded_current_membership",
            ),
            Prefetch(
                "memberships",
                queryset=active.filter(conversation__type=Conversation.Type.DIRECT),
                to_attr="loaded_direct_memberships",
            ),
            Prefetch(
                "messages",
                queryset=_message_queryset().order_by("-sequence")[:1],
                to_attr="loaded_last_messages",
            ),
        )
        .distinct()
    )


def conversation_detail_queryset(user: User):
    pins = PinnedMessage.objects.select_related("message__author__org_unit")[:20]
    return (
        Conversation.objects.filter(memberships__user=user, memberships__left_at__isnull=True)
        .prefetch_related(
            Prefetch("pinned_messages", queryset=pins, to_attr="loaded_pinned_messages"),
        )
        .distinct()
    )


def _memberships(conversation: Conversation) -> list[ConversationMembership]:
    return list(
        cast(Any, conversation)
        .memberships.select_related("user__org_unit")
        .order_by("joined_at", "id")
    )


def _visible_intervals(user: User, conversation: Conversation) -> list[tuple[int, int | None]]:
    return list(
        cast(Any, conversation)
        .memberships.filter(user=user)
        .values_list("joined_sequence", "left_sequence")
    )


def _message_context(request, conversation: Conversation) -> dict[str, object]:
    return {
        "request": request,
        "memberships": _memberships(conversation),
        "visible_intervals": _visible_intervals(request.user, conversation),
    }


def _message_data(message: Message, request) -> dict[str, Any]:
    message = _message_queryset().get(pk=message.pk)
    return cast(
        dict[str, Any],
        MessageSerializer(
            message,
            context=_message_context(request, message.conversation),
        ).data,
    )


def _validation_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        raise serializers.ValidationError(detail) from exc


class MessengerAPIView(PrivateResponseMixin, generics.GenericAPIView):
    permission_classes = [HasMessengerAccess]


class MessengerMessageThrottle(UserRateThrottle):
    scope = "messenger_message"
    cache = caches["throttles"]


class MessengerMentionAllThrottle(UserRateThrottle):
    scope = "messenger_mention_all"
    cache = caches["throttles"]


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
    serializer_class = ConversationSummarySerializer
    pagination_class = ConversationCursorPagination

    def get(self, request):
        queryset = conversation_summary_queryset(request.user).order_by(
            "-is_pinned", "-activity_at", "-id"
        )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)


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
        conversation = conversation_summary_queryset(request.user).get(pk=conversation.pk)
        return Response(
            ConversationSummarySerializer(conversation, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


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
        conversation = conversation_summary_queryset(request.user).get(pk=conversation.pk)
        return Response(
            ConversationSummarySerializer(conversation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ChannelConversationView(MessengerAPIView):
    serializer_class = ChannelConversationSerializer
    permission_classes = [HasMessengerAccess, IsMessengerAdmin]
    throttle_scope = "messenger_group"

    def post(self, request):
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        member_ids = set(payload.validated_data["member_ids"]) - {request.user.pk}
        members = list(eligible_people(member_ids))
        if len(members) != len(member_ids):
            raise serializers.ValidationError(
                {"member_ids": "Every member must be active and have Messenger access."}
            )
        writer_ids = set(payload.validated_data.get("writer_ids", [])) - {request.user.pk}
        conversation = create_channel(
            request.user,
            title=payload.validated_data["title"],
            members=members,
            writer_ids=writer_ids,
            discussion_enabled=payload.validated_data["discussion_enabled"],
        )
        conversation = conversation_summary_queryset(request.user).get(pk=conversation.pk)
        return Response(
            ConversationSummarySerializer(conversation, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ConversationDetailView(MessengerAPIView):
    serializer_class = ConversationDetailSerializer

    def get(self, request, conversation_id):
        conversation = get_object_or_404(
            conversation_detail_queryset(request.user), pk=conversation_id
        )
        return Response(
            self.get_serializer(
                conversation,
                context={
                    "request": request,
                    "visible_intervals": _visible_intervals(request.user, conversation),
                },
            ).data
        )

    def patch(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = ChannelSettingsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        _validation_call(
            update_channel_settings,
            conversation,
            actor=request.user,
            discussion_enabled=payload.validated_data["discussion_enabled"],
        )
        conversation = get_object_or_404(
            conversation_detail_queryset(request.user), pk=conversation_id
        )
        return Response(
            self.get_serializer(
                conversation,
                context={
                    "request": request,
                    "visible_intervals": _visible_intervals(request.user, conversation),
                },
            ).data
        )


class ConversationMemberListView(MessengerAPIView):
    serializer_class = MembershipSerializer
    pagination_class = MembershipPagination

    def get(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        queryset = (
            cast(Any, conversation)
            .memberships.filter(left_at__isnull=True)
            .select_related("user__org_unit")
        )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def post(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = MemberInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = get_object_or_404(eligible_people([payload.validated_data["user_id"]]))
        membership = _validation_call(add_group_member, conversation, actor=request.user, user=user)
        membership = ConversationMembership.objects.select_related("user__org_unit").get(
            pk=membership.pk
        )
        return Response(self.get_serializer(membership).data, status=status.HTTP_201_CREATED)


class ConversationMemberDetailView(MessengerAPIView):
    serializer_class = MemberRoleSerializer

    def patch(self, request, conversation_id, user_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        user = get_object_or_404(User, pk=user_id)
        membership = _validation_call(
            change_group_role,
            conversation,
            actor=request.user,
            user=user,
            role=payload.validated_data["role"],
        )
        return Response(MembershipSerializer(membership).data)

    def delete(self, request, conversation_id, user_id):
        conversation = member_conversation(request.user, conversation_id)
        user = get_object_or_404(User, pk=user_id)
        _validation_call(remove_group_member, conversation, actor=request.user, user=user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConversationLeaveView(MessengerAPIView):
    def post(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        _validation_call(leave_group, conversation, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageListCreateView(MessengerAPIView):
    serializer_class = MessageWriteSerializer
    throttle_classes = [MessengerMessageThrottle]

    def get_throttles(self) -> list[BaseThrottle]:
        if self.request.method != "POST":
            return []
        throttles: list[BaseThrottle] = [MessengerMessageThrottle()]
        try:
            mention_all = serializers.BooleanField().to_internal_value(
                self.request.data.get("mention_all", False)
            )
        except serializers.ValidationError:
            mention_all = False
        if mention_all:
            throttles.append(MessengerMentionAllThrottle())
        return throttles

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
        descending = list(
            _message_queryset()
            .filter(
                membership_message_filter(request.user, conversation), conversation=conversation
            )
            .filter(sequence__lt=before)
            .order_by("-sequence")[: page_size + 1]
        )
        has_more = len(descending) > page_size
        messages = list(reversed(descending[:page_size]))
        return Response(
            {
                "messages": MessageSerializer(
                    messages,
                    many=True,
                    context=_message_context(request, conversation),
                ).data,
                "has_more": has_more,
                "next_before_sequence": messages[0].sequence if has_more else None,
            }
        )

    def post(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        message, created = _validation_call(
            send_message, conversation, author=request.user, **payload.validated_data
        )
        return Response(
            _message_data(message, request),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MessageDetailView(MessengerAPIView):
    serializer_class = MessageEditSerializer

    def patch(self, request, message_id):
        message = visible_message(request.user, message_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        message = _validation_call(
            edit_message, message, actor=request.user, body=payload.validated_data["body"]
        )
        return Response(_message_data(message, request))

    def delete(self, request, message_id):
        message = visible_message(request.user, message_id)
        message = _validation_call(delete_message, message, actor=request.user)
        return Response(_message_data(message, request))


class MessageReactionView(MessengerAPIView):
    serializer_class = MessageReactionWriteSerializer

    def put(self, request, message_id):
        message = visible_message(request.user, message_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        _validation_call(
            put_message_reaction,
            message,
            user=request.user,
            reaction_type=payload.validated_data["reaction_type"],
        )
        return Response(_message_data(message, request))

    def delete(self, request, message_id):
        message = visible_message(request.user, message_id)
        _validation_call(delete_message_reaction, message, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessagePinView(MessengerAPIView):
    def put(self, request, message_id):
        message = visible_message(request.user, message_id)
        _validation_call(pin_message, message, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request, message_id):
        message = visible_message(request.user, message_id)
        _validation_call(unpin_message, message, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReadView(MessengerAPIView):
    serializer_class = ReadSerializer

    def post(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        membership = _validation_call(
            mark_read,
            conversation,
            user=request.user,
            sequence=payload.validated_data["sequence"],
        )
        return Response(
            {"last_read_sequence": membership.last_read_sequence, "read_at": membership.read_at}
        )


class DeliveredView(MessengerAPIView):
    serializer_class = ReadSerializer

    def post(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        membership = _validation_call(
            mark_delivered,
            conversation,
            user=request.user,
            sequence=payload.validated_data["sequence"],
        )
        return Response(
            {
                "last_delivered_sequence": membership.last_delivered_sequence,
                "delivered_at": membership.delivered_at,
            }
        )


class ConversationStateView(MessengerAPIView):
    serializer_class = ConversationStateSerializer

    def patch(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        membership = _validation_call(
            update_conversation_state,
            conversation,
            user=request.user,
            **payload.validated_data,
        )
        return Response(MembershipSerializer(membership).data)


class ConversationAttachmentUploadView(MessengerAPIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, conversation_id):
        member_conversation(request.user, conversation_id)
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": "A file is required."})
        try:
            asset = create_media_asset(
                upload=upload,
                actor=cast(User, request.user),
                messenger_only=True,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": exc.messages}) from exc
        return Response(MediaAssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class ConversationSearchView(MessengerAPIView):
    serializer_class = MessageSearchSerializer

    def get(self, request, conversation_id):
        conversation = member_conversation(request.user, conversation_id)
        payload = self.get_serializer(data=request.query_params)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        messages = (
            _message_queryset()
            .filter(
                membership_message_filter(request.user, conversation), conversation=conversation
            )
            .filter(deleted_at__isnull=True)
        )
        if author_id := data.get("author_id"):
            messages = messages.filter(author_id=author_id)
        if date_from := data.get("date_from"):
            messages = messages.filter(created_at__gte=date_from)
        if date_to := data.get("date_to"):
            messages = messages.filter(created_at__lte=date_to)
        if data.get("has_attachments") is True:
            messages = messages.filter(attachments__isnull=False).distinct()
        elif data.get("has_attachments") is False:
            messages = messages.filter(attachments__isnull=True)
        if query_text := data.get("q"):
            query_ru = SearchQuery(query_text, config="russian", search_type="websearch")
            query_kk = SearchQuery(query_text, config="tandem_kazakh", search_type="websearch")
            messages = (
                messages.annotate(
                    rank=SearchRank(SearchVector("body", config="russian"), query_ru)
                    + SearchRank(SearchVector("body", config="tandem_kazakh"), query_kk)
                )
                .filter(rank__gt=0)
                .order_by("-rank", "-sequence")
            )
        else:
            messages = messages.order_by("-sequence")
        rows = list(messages[: data["page_size"]])
        return Response(
            {
                "results": MessageSerializer(
                    rows,
                    many=True,
                    context=_message_context(request, conversation),
                ).data
            }
        )


class MessageContextView(MessengerAPIView):
    def get(self, request, conversation_id, message_id):
        conversation = member_conversation(request.user, conversation_id)
        visible = membership_message_filter(request.user, conversation)
        target = get_object_or_404(
            _message_queryset().filter(visible, conversation=conversation), pk=message_id
        )
        before = list(
            reversed(
                list(
                    _message_queryset()
                    .filter(visible, conversation=conversation, sequence__lt=target.sequence)
                    .order_by("-sequence")[:10]
                )
            )
        )
        after = list(
            _message_queryset()
            .filter(visible, conversation=conversation, sequence__gt=target.sequence)
            .order_by("sequence")[:10]
        )
        context = _message_context(request, conversation)
        return Response(
            {
                "before": MessageSerializer(before, many=True, context=context).data,
                "target": MessageSerializer(target, context=context).data,
                "after": MessageSerializer(after, many=True, context=context).data,
            }
        )
