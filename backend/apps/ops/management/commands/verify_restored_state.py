from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.identity.models import User
from apps.messenger.models import Conversation, Message
from apps.notifications.models import Notification
from apps.publications.models import MediaAsset, Publication


class Command(BaseCommand):
    help = "Verify that a restore contains the core application state and protected media."

    def handle(self, *args, **options):
        checks = {
            "active users": User.objects.filter(is_active=True).exists(),
            "publications": Publication.objects.exists(),
            "conversations": Conversation.objects.exists(),
            "messages": Message.objects.exists(),
            "notifications": Notification.objects.exists(),
            "ready media": MediaAsset.objects.filter(status=MediaAsset.Status.READY).exists(),
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise CommandError("Restored state is incomplete: " + ", ".join(failed))
        call_command("verify_media_integrity")
        self.stdout.write("Restored application state: PASS")
