import uuid
from datetime import UTC, datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.identity.portal.mock import EMPLOYEES, MockPortalAdapter
from apps.identity.services import provision_user

from ...models import Category, Publication, PublicationView
from ...services import replace_audience_rules


def rich_body(text: str) -> dict[str, object]:
    return {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": text}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Подключайтесь безопасно по инструкции."}],
            },
        ],
    }


class Command(BaseCommand):
    help = "Create deterministic Stage 2 acceptance data."

    @transaction.atomic
    def handle(self, *args, **options):
        adapter = MockPortalAdapter()
        users = {employee.portal_id: provision_user(adapter, employee) for employee in EMPLOYEES}
        category, _ = Category.objects.update_or_create(
            slug="regulations",
            defaults={"name": "Регламенты", "sort_order": 10, "is_active": True},
        )
        publication, _ = Publication.objects.update_or_create(
            id=uuid.UUID("b7a9e052-b4e6-4f58-8bbf-fc64257261e9"),
            defaults={
                "slug": "reglament-vpn",
                "title": "Регламент VPN",
                "summary": "Правила безопасного удалённого подключения",
                "body": rich_body("Регламент VPN"),
                "category": category,
                "author": users["editor-1"],
                "status": Publication.Status.PUBLISHED,
                "published_at": datetime(2026, 8, 23, 9, 0, tzinfo=UTC),
            },
        )
        engineering = users["admin-1"].org_unit
        assert engineering is not None
        replace_audience_rules(publication, org_units=[engineering])
        PublicationView.objects.filter(publication=publication).delete()
        self.stdout.write(self.style.SUCCESS(f"Seeded publication {publication.id}"))
