from getpass import getpass

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.identity.auth_services import validate_local_password
from apps.identity.models import AccessGrant, User


class Command(BaseCommand):
    help = "Interactively create the first local Tandem platform administrator."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.ALLOW_BOOTSTRAP_LOCAL_ADMIN:
            raise CommandError("Local administrator bootstrap is disabled.")
        if AccessGrant.objects.filter(
            module=AccessGrant.Module.PLATFORM, role=AccessGrant.Role.ADMIN
        ).exists():
            raise CommandError("A platform administrator already exists.")

        username = input("Username: ").strip()
        email = input("Email: ").strip()
        full_name = input("Full name: ").strip()
        password = getpass("Password: ")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise CommandError("Passwords do not match.")

        user = User(username=username, email=email, full_name=full_name, is_active=True)
        validate_local_password(password, user)
        user.set_password(password)
        user.activated_at = timezone.now()
        user.password_changed_at = user.activated_at
        user.save()
        AccessGrant.objects.bulk_create(
            [
                AccessGrant(
                    user=user, module=AccessGrant.Module.PLATFORM, role=AccessGrant.Role.ADMIN
                ),
                AccessGrant(user=user, module=AccessGrant.Module.NEWS, role=AccessGrant.Role.ADMIN),
                AccessGrant(
                    user=user, module=AccessGrant.Module.MESSENGER, role=AccessGrant.Role.ADMIN
                ),
            ]
        )
        self.stdout.write(self.style.SUCCESS(f"Created local administrator {user.username}"))
