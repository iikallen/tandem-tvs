import uuid

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.discussions.models import Comment, Reaction
from apps.identity.portal import get_portal_adapter
from apps.identity.services import provision_user
from apps.organization.models import OrgUnit
from apps.publications.models import AudienceRule, Category, Publication

PUBLICATION_ID = uuid.UUID("00000000-0000-0000-0000-000000003001")


class Command(BaseCommand):
    help = "Create deterministic Stage 3 live-E2E data."

    @transaction.atomic
    def handle(self, *args, **options):
        adapter = get_portal_adapter()
        for portal_id in ("employee-1", "author-1", "admin-1"):
            employee = adapter.get_employee(portal_id)
            if employee is None:
                raise RuntimeError(f"Missing demo portal employee: {portal_id}")
            provision_user(adapter, employee)
        author_employee = adapter.get_employee("author-1")
        if author_employee is None:
            raise RuntimeError("Missing demo portal employee: author-1")
        author = provision_user(adapter, author_employee)
        category, _ = Category.objects.update_or_create(
            slug="stage-3", defaults={"name": "Stage 3", "is_active": True}
        )
        publication, _ = Publication.objects.update_or_create(
            pk=PUBLICATION_ID,
            defaults={
                "title": "Обсуждение Stage 3",
                "slug": "stage-3-discussion",
                "summary": "Проверка комментариев, реакций и realtime",
                "body": {
                    "type": "doc",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Живая публикация Stage 3"}],
                        }
                    ],
                },
                "category": category,
                "author": author,
                "status": Publication.Status.PUBLISHED,
                "published_at": timezone.now(),
            },
        )
        Comment.objects.filter(publication=publication).delete()
        Reaction.objects.filter(publication=publication).delete()
        publication.audience_rules.all().delete()
        AudienceRule.objects.create(
            publication=publication,
            kind=AudienceRule.Kind.ORG_UNIT,
            org_unit=OrgUnit.objects.get(external_id="communications"),
        )
        self.stdout.write(self.style.SUCCESS(str(publication.pk)))
