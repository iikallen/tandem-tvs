import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, F

from apps.identity.models import User
from apps.messenger.models import ConversationMembership, Message
from apps.messenger.services import membership_message_filter
from apps.messenger.views import conversation_summary_queryset
from apps.notifications.models import Notification
from apps.publications.models import Publication, PublicationRecipient
from apps.search.services import authorized_sections


class Command(BaseCommand):
    help = "Print PostgreSQL EXPLAIN ANALYZE BUFFERS plans for Stage 10 critical queries."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="load-0001")
        parser.add_argument("--query", default="безопасность қауіпсіздік")
        parser.add_argument("--summary", action="store_true")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("Database profiling requires PostgreSQL.")
        user = (
            User.objects.filter(username=options["username"], is_active=True)
            .prefetch_related("access_grants")
            .first()
        )
        if user is None:
            raise CommandError(f"Active user {options['username']!r} was not found.")
        publication = Publication.objects.visible_to(user).first()
        membership = (
            ConversationMembership.objects.filter(user=user, left_at__isnull=True)
            .select_related("conversation")
            .first()
        )
        if publication is None or membership is None:
            raise CommandError("Seed visible publications and conversations before profiling.")

        self.summary = bool(options["summary"])
        self.summaries: list[dict[str, object]] = []
        self._plan(
            "feed", Publication.objects.visible_to(user).select_related("category", "author")
        )
        self._plan(
            "publication-detail",
            Publication.objects.visible_to(user)
            .filter(pk=publication.pk)
            .select_related("category", "author"),
        )
        for scope, queryset in authorized_sections(user, options["query"]).items():
            self._plan(f"global-search/{scope}", queryset)
        self._plan("messenger-inbox", conversation_summary_queryset(user))
        self._plan(
            "message-history",
            Message.objects.filter(
                membership_message_filter(user, membership.conversation),
                conversation=membership.conversation,
            ).order_by("-sequence"),
        )
        self._plan(
            "unread",
            ConversationMembership.objects.filter(user=user, left_at__isnull=True).annotate(
                unread=F("conversation__last_sequence") - F("last_read_sequence")
            ),
        )
        self._plan(
            "notification-inbox",
            Notification.objects.filter(recipient=user, in_app_visible=True).order_by(
                "-last_event_at", "-id"
            ),
        )
        self._plan(
            "analytics",
            PublicationRecipient.objects.filter(is_current=True)
            .values("publication_id")
            .annotate(
                recipients=Count("id"), unique_views=Count("publication__views", distinct=True)
            ),
        )
        with connection.cursor() as cursor:
            cursor.execute("SHOW autovacuum")
            autovacuum = cursor.fetchone()[0]
        if self.summary:
            self.stdout.write(
                json.dumps(
                    {"autovacuum": autovacuum, "plans": self.summaries},
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        else:
            self.stdout.write(f"\n=== autovacuum ===\n{autovacuum}")
        if autovacuum != "on":
            raise CommandError("PostgreSQL autovacuum is disabled.")

    def _plan(self, label: str, queryset: Any) -> None:
        if self.summary:
            result = json.loads(
                queryset.explain(analyze=True, buffers=True, verbose=True, format="json")
            )[0]
            plan = result["Plan"]
            self.summaries.append(
                {
                    "execution_ms": result["Execution Time"],
                    "label": label,
                    "node": plan["Node Type"],
                    "planning_ms": result["Planning Time"],
                    "rows": plan["Actual Rows"],
                    "shared_hit_blocks": plan.get("Shared Hit Blocks", 0),
                    "shared_read_blocks": plan.get("Shared Read Blocks", 0),
                }
            )
            return
        self.stdout.write(f"\n=== {label} ===")
        self.stdout.write(queryset.explain(analyze=True, buffers=True, verbose=True))
