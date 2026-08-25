import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.discussions.models import Comment, Reaction
from apps.identity.models import AccessGrant, User
from apps.messenger.models import (
    Conversation,
    ConversationMembership,
    DirectConversationPair,
    Message,
)
from apps.notifications.models import Notification
from apps.organization.models import OrgUnit
from apps.publications.models import (
    AudienceRule,
    Category,
    MediaAsset,
    MediaUsage,
    Publication,
    PublicationRecipient,
    PublicationView,
)

NAMESPACE = uuid.UUID("ad516c98-12d0-40e7-bad2-9e4fb6a1478b")
REFERENCE_TIME = datetime(2026, 1, 1, 9, tzinfo=UTC)


def stable_uuid(kind: str, number: int) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{number}")


def rich_body(text: str) -> dict[str, object]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def bounded(options: dict[str, Any], name: str, maximum: int, minimum: int = 1) -> int:
    value = int(options[name])
    if not minimum <= value <= maximum:
        raise CommandError(f"--{name.replace('_', '-')} must be between {minimum} and {maximum}.")
    return value


class Command(BaseCommand):
    help = "Seed an idempotent, deterministic Stage 10 load-test profile."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=1_000)
        parser.add_argument("--publications", type=int, default=120)
        parser.add_argument("--messages", type=int, default=20_000)
        parser.add_argument("--notifications", type=int, default=20_000)
        parser.add_argument("--confirm-load-environment", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["confirm_load_environment"]:
            raise CommandError("Pass --confirm-load-environment for the isolated load environment.")
        password = os.environ.get("TANDEM_LOAD_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("TANDEM_LOAD_PASSWORD must contain at least 12 characters.")
        user_count = bounded(options, "users", 1_000, minimum=2)
        publication_count = bounded(options, "publications", 120)
        message_count = bounded(options, "messages", 20_000)
        notification_count = bounded(options, "notifications", 20_000)

        now = REFERENCE_TIME
        units = self._units()
        users = self._users(user_count, units, password, now)
        publications = self._publications(publication_count, users, now)
        self._engagement(publications, users)
        self._analytics(publications, users, now)
        conversations = self._conversations(users, now)
        messages = self._messages(message_count, conversations, users, now)
        self._notifications(notification_count, users, messages, publications, now)
        self._small_media(users[0], publications)
        self.stdout.write(
            self.style.SUCCESS(
                "Load profile: "
                f"{len(users)} users, {len(publications)} publications, "
                f"{len(conversations)} conversations, {message_count} messages, "
                f"{notification_count} notifications"
            )
        )

    def _units(self) -> list[OrgUnit]:
        root, _ = OrgUnit.objects.update_or_create(
            external_id="load-root",
            defaults={"name": "Тандем ТВС", "kind": "COMPANY", "is_active": True},
        )
        units = []
        names = (
            "Производство",
            "Инженерлік қызмет",
            "Финансы",
            "Ақпараттық технологиялар",
            "Безопасность",
            "Адам ресурстары",
            "Логистика",
            "Коммуникации",
            "Снабжение",
            "Заң қызметі",
        )
        for index, name in enumerate(names, 1):
            unit, _ = OrgUnit.objects.update_or_create(
                external_id=f"load-department-{index:02d}",
                defaults={"name": name, "kind": "DEPARTMENT", "parent": root, "is_active": True},
            )
            units.append(unit)
        return units

    def _users(self, count: int, units: list[OrgUnit], password: str, now) -> list[User]:
        usernames = [f"load-{index:04d}" for index in range(1, count + 1)]
        existing = User.objects.in_bulk(usernames, field_name="username")
        encoded_password = make_password(
            password,
            salt="tandem-load-profile-2026",
            hasher="pbkdf2_sha256",
        )
        missing = []
        for index, username in enumerate(usernames, 1):
            if username not in existing:
                missing.append(
                    User(
                        username=username,
                        email=f"{username}@load.invalid",
                        full_name=(
                            f"Сотрудник нагрузки {index:04d}"
                            if index % 2
                            else f"Жүктеме қызметкері {index:04d}"
                        ),
                        job_title="Инженер" if index % 2 else "Жетекші маман",
                        org_unit=units[(index - 1) % len(units)],
                        position_group_external_id=f"load-position-{(index - 1) % 8 + 1:02d}",
                        position_group_name=f"Группа должностей {(index - 1) % 8 + 1}",
                        is_active=True,
                        password=encoded_password,
                        activated_at=now,
                        password_changed_at=now,
                    )
                )
        User.objects.bulk_create(missing, batch_size=500)
        users = list(
            User.objects.filter(username__in=usernames)
            .select_related("org_unit")
            .order_by("username")
        )
        for user in users:
            user.password = encoded_password
            user.is_active = True
            user.activated_at = now
            user.password_changed_at = now
        User.objects.bulk_update(
            users,
            ["password", "is_active", "activated_at", "password_changed_at"],
            batch_size=500,
        )
        AccessGrant.objects.bulk_create(
            [
                AccessGrant(user=user, module=module, role=AccessGrant.Role.MEMBER)
                for user in users
                for module in (AccessGrant.Module.NEWS, AccessGrant.Module.MESSENGER)
            ],
            ignore_conflicts=True,
            batch_size=1_000,
        )
        editorial_roles = (
            AccessGrant.Role.AUTHOR,
            AccessGrant.Role.EDITOR,
            AccessGrant.Role.MODERATOR,
            AccessGrant.Role.ADMIN,
        )
        AccessGrant.objects.bulk_create(
            [
                AccessGrant(
                    user=user, module=AccessGrant.Module.NEWS, role=editorial_roles[index % 4]
                )
                for index, user in enumerate(users[: min(40, len(users))])
            ],
            ignore_conflicts=True,
            batch_size=100,
        )
        privileged = [
            AccessGrant(
                user=users[0],
                module=AccessGrant.Module.PLATFORM,
                role=AccessGrant.Role.ADMIN,
            ),
            AccessGrant(
                user=users[0],
                module=AccessGrant.Module.MESSENGER,
                role=AccessGrant.Role.ADMIN,
            ),
        ]
        if len(users) > 1:
            privileged.append(
                AccessGrant(
                    user=users[1],
                    module=AccessGrant.Module.MESSENGER,
                    role=AccessGrant.Role.MODERATOR,
                )
            )
        AccessGrant.objects.bulk_create(privileged, ignore_conflicts=True)
        return users

    def _publications(self, count: int, users: list[User], now) -> list[Publication]:
        category, _ = Category.objects.update_or_create(
            slug="load-news",
            defaults={"name": "Новости нагрузки", "sort_order": 900, "is_active": True},
        )
        rows = []
        for index in range(1, count + 1):
            kazakh = index % 2 == 0
            text = (
                f"Өндірістік қауіпсіздік және әріптестерге арналған хабарлама {index}"
                if kazakh
                else f"Производственная безопасность и сообщение для коллег {index}"
            )
            publication, _ = Publication.objects.update_or_create(
                pk=stable_uuid("publication", index),
                defaults={
                    "slug": f"load-news-{index:03d}",
                    "title": text,
                    "summary": text,
                    "body": rich_body(text),
                    "category": category,
                    "author": users[(index - 1) % len(users)],
                    "status": Publication.Status.PUBLISHED,
                    "published_at": now - timedelta(minutes=index),
                    "acknowledgement_required": index % 10 == 0,
                },
            )
            AudienceRule.objects.filter(publication=publication).delete()
            audience_kind = index % 5
            if audience_kind == 0 or index <= 20:
                AudienceRule.objects.create(publication=publication, kind=AudienceRule.Kind.ALL)
            elif audience_kind == 1:
                AudienceRule.objects.create(
                    publication=publication,
                    kind=AudienceRule.Kind.ORG_UNIT,
                    org_unit=users[index % len(users)].org_unit,
                    include_descendants=True,
                )
            elif audience_kind == 2:
                AudienceRule.objects.create(
                    publication=publication,
                    kind=AudienceRule.Kind.EMPLOYEE,
                    employee=users[index % len(users)],
                )
            elif audience_kind == 3:
                AudienceRule.objects.create(
                    publication=publication,
                    kind=AudienceRule.Kind.MODULE_ROLE,
                    module_role="author",
                )
            else:
                target = users[index % len(users)]
                AudienceRule.objects.create(
                    publication=publication,
                    kind=AudienceRule.Kind.POSITION_GROUP,
                    position_group_external_id=target.position_group_external_id,
                    position_group_name=target.position_group_name,
                )
            rows.append(publication)
        return rows

    def _engagement(self, publications: list[Publication], users: list[User]) -> None:
        comments = []
        reactions = []
        for publication_index, publication in enumerate(publications, 1):
            for offset in range(3):
                user = users[(publication_index * 3 + offset) % len(users)]
                comments.append(
                    Comment(
                        id=stable_uuid("comment", publication_index * 10 + offset),
                        publication=publication,
                        author=user,
                        body=(
                            f"Полезное разъяснение по теме {publication_index}."
                            if offset % 2
                            else f"{publication_index} тақырыбы бойынша пайдалы түсініктеме."
                        ),
                    )
                )
                reactions.append(
                    Reaction(
                        id=stable_uuid("reaction", publication_index * 10 + offset),
                        publication=publication,
                        user=user,
                        reaction_type=Reaction.Type.LIKE,
                    )
                )
        Comment.objects.bulk_create(comments, ignore_conflicts=True, batch_size=1_000)
        Reaction.objects.bulk_create(reactions, ignore_conflicts=True, batch_size=1_000)

    def _analytics(self, publications: list[Publication], users: list[User], now) -> None:
        recipients = []
        views = []
        for publication in publications:
            rule = publication.audience_rules.select_related("org_unit", "employee").get()
            if rule.kind == AudienceRule.Kind.ALL:
                selected = users[:100]
            elif rule.kind == AudienceRule.Kind.ORG_UNIT:
                selected = [user for user in users if user.org_unit == rule.org_unit][:100]
            elif rule.kind == AudienceRule.Kind.EMPLOYEE:
                selected = [rule.employee] if rule.employee is not None else []
            elif rule.kind == AudienceRule.Kind.MODULE_ROLE:
                selected = users[:40:4]
            else:
                selected = [
                    user
                    for user in users
                    if user.position_group_external_id == rule.position_group_external_id
                ][:100]
            for index, user in enumerate(selected):
                recipients.append(
                    PublicationRecipient(
                        publication=publication,
                        user=user,
                        full_name=user.full_name,
                        email=user.email,
                        org_unit_external_id=user.org_unit.external_id if user.org_unit else "",
                        org_unit_name=user.org_unit.name if user.org_unit else "",
                    )
                )
                if index % 2 == 0:
                    views.append(
                        PublicationView(
                            publication=publication,
                            user=user,
                            first_viewed_at=now,
                            last_viewed_at=now,
                        )
                    )
        PublicationRecipient.objects.bulk_create(
            recipients, ignore_conflicts=True, batch_size=1_000
        )
        PublicationView.objects.bulk_create(views, ignore_conflicts=True, batch_size=1_000)

    def _conversations(self, users: list[User], now) -> list[Conversation]:
        count = min(30, max(3, len(users) // 10))
        rows = []
        for index in range(1, count + 1):
            if index <= max(1, count // 3):
                conversation_type = Conversation.Type.DIRECT
                title = ""
            elif index <= max(2, count * 2 // 3):
                conversation_type = Conversation.Type.GROUP
                title = f"Рабочая группа {index:02d}"
            else:
                conversation_type = Conversation.Type.CHANNEL
                title = f"Ақпараттық арна {index:02d}"
            conversation, _ = Conversation.objects.update_or_create(
                pk=stable_uuid("conversation", index),
                defaults={
                    "type": conversation_type,
                    "title": title,
                    "discussion_enabled": conversation_type == Conversation.Type.CHANNEL,
                    "created_by": users[(index - 1) % len(users)],
                    "activity_at": now,
                },
            )
            rows.append(conversation)

        memberships = []
        shared_indexes = [
            index for index, row in enumerate(rows) if row.type != Conversation.Type.DIRECT
        ]
        for user_index, user in enumerate(users):
            group_indexes = {
                shared_indexes[user_index % len(shared_indexes)],
                shared_indexes[(user_index + len(shared_indexes) // 2) % len(shared_indexes)],
            }
            for conversation_index in sorted(group_indexes):
                conversation = rows[conversation_index]
                role = (
                    ConversationMembership.Role.ADMIN
                    if conversation.created_by.pk == user.pk
                    else (
                        ConversationMembership.Role.WRITER
                        if conversation.type == Conversation.Type.CHANNEL and user_index % 5 == 0
                        else ConversationMembership.Role.MEMBER
                    )
                )
                memberships.append(
                    ConversationMembership(conversation=conversation, user=user, role=role)
                )

        direct_rows = []
        direct_conversations = [row for row in rows if row.type == Conversation.Type.DIRECT]
        for index, conversation in enumerate(direct_conversations):
            low, high = sorted((conversation.created_by.pk, users[(index + 1) % len(users)].pk))
            memberships.extend(
                [
                    ConversationMembership(conversation=conversation, user_id=low),
                    ConversationMembership(conversation=conversation, user_id=high),
                ]
            )
            direct_rows.append(
                DirectConversationPair(
                    conversation=conversation, user_low_id=low, user_high_id=high
                )
            )
        ConversationMembership.objects.bulk_create(
            memberships, ignore_conflicts=True, batch_size=1_000
        )
        DirectConversationPair.objects.bulk_create(
            direct_rows, ignore_conflicts=True, batch_size=100
        )
        return rows

    def _messages(
        self,
        count: int,
        conversations: list[Conversation],
        users: list[User],
        now,
    ) -> list[Message]:
        messages = []
        last_sequences = [0] * len(conversations)
        members = {
            conversation.pk: list(
                ConversationMembership.objects.filter(
                    conversation=conversation, left_at__isnull=True
                ).values_list("user_id", "role")
            )
            for conversation in conversations
        }
        users_by_id = {user.pk: user for user in users}
        for index in range(1, count + 1):
            conversation_index = (index - 1) % len(conversations)
            conversation = conversations[conversation_index]
            last_sequences[conversation_index] += 1
            sequence = last_sequences[conversation_index]
            candidates = members[conversation.pk]
            if conversation.type == Conversation.Type.CHANNEL:
                candidates = [
                    row
                    for row in candidates
                    if row[1]
                    in {ConversationMembership.Role.WRITER, ConversationMembership.Role.ADMIN}
                ]
            author = users_by_id[candidates[(sequence - 1) % len(candidates)][0]]
            body = (
                f"Хабарлама {index}: өндірістік қауіпсіздік және күнделікті жұмыс."
                if index % 2 == 0
                else f"Сообщение {index}: производственная безопасность и текущая работа."
            )
            messages.append(
                Message(
                    id=stable_uuid("message", index),
                    conversation=conversation,
                    sequence=sequence,
                    client_message_id=stable_uuid("client-message", index),
                    author=author,
                    body=body,
                    kind=(
                        Message.Kind.CHANNEL_POST
                        if conversation.type == Conversation.Type.CHANNEL
                        else Message.Kind.CHAT
                    ),
                    request_fingerprint=hashlib.sha256(body.encode()).hexdigest(),
                    created_at=now - timedelta(seconds=count - index),
                )
            )
        Message.objects.bulk_create(messages, ignore_conflicts=True, batch_size=1_000)
        for index, conversation in enumerate(conversations):
            conversation.last_sequence = last_sequences[index]
            conversation.last_message_at = now
            conversation.activity_at = now
        Conversation.objects.bulk_update(
            conversations,
            ["last_sequence", "last_message_at", "activity_at", "updated_at"],
            batch_size=100,
        )
        return messages

    def _notifications(
        self,
        count: int,
        users: list[User],
        messages: list[Message],
        publications: list[Publication],
        now,
    ) -> None:
        rows = []
        for index in range(1, count + 1):
            recipient = users[(index - 1) % len(users)]
            if index % 2 and messages:
                source = messages[(index - 1) % len(messages)]
                notification_type = Notification.Type.NEW_MESSAGE
                source_type = "MESSAGE"
                publication_id = None
                conversation_id = source.conversation.pk
            else:
                source = publications[(index - 1) % len(publications)]
                notification_type = Notification.Type.NEW_PUBLICATION
                source_type = "PUBLICATION"
                publication_id = source.pk
                conversation_id = None
            rows.append(
                Notification(
                    id=stable_uuid("notification", index),
                    recipient=recipient,
                    actor=users[index % len(users)],
                    notification_type=notification_type,
                    source_type=source_type,
                    source_id=source.pk,
                    publication_id=publication_id,
                    conversation_id=conversation_id,
                    dedupe_key=f"load:{index}",
                    payload={"load_profile": True},
                    last_event_at=now - timedelta(seconds=count - index),
                )
            )
        Notification.objects.bulk_create(rows, ignore_conflicts=True, batch_size=1_000)

    def _small_media(self, uploader: User, publications: list[Publication]) -> None:
        content = "Тестовый документ. Сынақ құжаты.\n".encode()
        storage_key = "load-profile/ru-kz-sample.txt"
        if default_storage.exists(storage_key):
            with default_storage.open(storage_key, "rb") as existing:
                if existing.read() != content:
                    raise CommandError(f"Refusing to replace existing load media: {storage_key}")
        elif default_storage.save(storage_key, ContentFile(content)) != storage_key:
            raise CommandError(f"Storage changed the deterministic key: {storage_key}")
        asset, _ = MediaAsset.objects.update_or_create(
            pk=stable_uuid("media", 1),
            defaults={
                "original_name": "ru-kz-sample.txt",
                "storage_key": storage_key,
                "file": storage_key,
                "mime_type": "text/plain",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "kind": MediaAsset.Kind.DOCUMENT,
                "uploader": uploader,
                "status": MediaAsset.Status.READY,
            },
        )
        MediaUsage.objects.bulk_create(
            [
                MediaUsage(
                    asset=asset, publication=publication, purpose=MediaUsage.Purpose.ATTACHMENT
                )
                for publication in publications[:10]
            ],
            ignore_conflicts=True,
        )
