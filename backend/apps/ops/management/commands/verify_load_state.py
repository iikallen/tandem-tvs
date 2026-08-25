import json
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, Max

from apps.identity.models import User
from apps.messenger.models import Conversation, Message
from apps.notifications.models import NotificationFanoutEvent
from apps.realtime.models import RealtimeOutboxEvent

from ...health import dependency_status


class Command(BaseCommand):
    help = "Verify postconditions after a Stage 10 load or WebSocket capacity run."

    def add_arguments(self, parser):
        parser.add_argument("--minimum-load-users", type=int, default=1_000)
        parser.add_argument("--minimum-messages", type=int, default=20_000)
        parser.add_argument("--require-k6-writes", action="store_true")
        parser.add_argument("--wait-seconds", type=int, default=90)

    def handle(self, *args, **options):
        failures: list[str] = []
        load_users = User.objects.filter(username__startswith="load-", is_active=True).count()
        message_count = Message.objects.count()
        if load_users < options["minimum_load_users"]:
            failures.append(f"only {load_users} active load users")
        if message_count < options["minimum_messages"]:
            failures.append(f"only {message_count} committed messages")
        if (
            options["require_k6_writes"]
            and not Message.objects.filter(body__startswith="k6 ").exists()
        ):
            failures.append("no committed k6 message was found")

        counters = {
            row["conversation_id"]: row["maximum"] or 0
            for row in Message.objects.values("conversation_id").annotate(maximum=Max("sequence"))
        }
        stale = [
            str(row.pk)
            for row in Conversation.objects.only("pk", "last_sequence")
            if row.last_sequence != counters.get(row.pk, 0)
        ]
        if stale:
            failures.append(f"conversation counters differ from committed history: {stale[:5]}")
        duplicate_sequences = (
            Message.objects.values("conversation_id", "sequence")
            .annotate(rows=Count("pk"))
            .filter(rows__gt=1)
            .exists()
        )
        if duplicate_sequences:
            failures.append("duplicate conversation sequence detected")
        deadline = time.monotonic() + options["wait_seconds"]
        while time.monotonic() < deadline:
            if (
                not RealtimeOutboxEvent.objects.filter(delivered_at__isnull=True).exists()
                and not NotificationFanoutEvent.objects.filter(processed_at__isnull=True).exists()
            ):
                break
            time.sleep(1)
        if RealtimeOutboxEvent.objects.filter(delivered_at__isnull=True).exists():
            failures.append("realtime outbox has pending rows")
        if NotificationFanoutEvent.objects.filter(processed_at__isnull=True).exists():
            failures.append("notification fanout has pending rows")

        with connection.cursor() as cursor:
            cursor.execute("SHOW max_connections")
            maximum_connections = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT count(*) FILTER (WHERE state = 'idle in transaction'), count(*) "
                "FROM pg_stat_activity WHERE datname = current_database()"
            )
            idle_in_transaction, active_connections = map(int, cursor.fetchone())
        if idle_in_transaction:
            failures.append(f"{idle_in_transaction} DB sessions idle in transaction")
        if active_connections >= maximum_connections:
            failures.append("database connection pool is exhausted")

        dependencies = dependency_status()
        if any(value != "ok" for value in dependencies.values()):
            failures.append(f"dependencies are not healthy: {dependencies}")
        if failures:
            raise CommandError("; ".join(failures))
        self.stdout.write(
            json.dumps(
                {
                    "status": "PASS",
                    "load_users": load_users,
                    "messages": message_count,
                    "active_db_connections": active_connections,
                    "max_connections": maximum_connections,
                    "dependencies": dependencies,
                },
                sort_keys=True,
            )
        )
