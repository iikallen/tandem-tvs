import unicodedata

from django.db import migrations


def forwards(apps, schema_editor):
    User = apps.get_model("identity", "User")
    AccessGrant = apps.get_model("identity", "AccessGrant")
    rows = list(User.objects.order_by("id"))
    normalized = [
        unicodedata.normalize("NFKC", (user.portal_id or "")).strip().casefold() for user in rows
    ]
    collisions = sorted({value for value in normalized if value and normalized.count(value) > 1})
    missing = [user.pk for user, value in zip(rows, normalized, strict=True) if not value]
    if collisions or missing:
        raise RuntimeError(
            "Stage 6 username remediation required before migration: "
            f"collisions={collisions}, missing_user_ids={missing}"
        )

    for user, username in zip(rows, normalized, strict=True):
        User.objects.filter(pk=user.pk).update(username=username)
        roles = {
            role.strip().casefold()
            for role in (user.module_roles if isinstance(user.module_roles, list) else [])
            if isinstance(role, str)
        }
        grants = {("NEWS", "MEMBER")}
        if "author" in roles:
            grants.add(("NEWS", "AUTHOR"))
        if "editor" in roles:
            grants.add(("NEWS", "EDITOR"))
        if "moderator" in roles:
            grants.add(("NEWS", "MODERATOR"))
        if roles.intersection({"admin", "administrator"}):
            grants.update({("PLATFORM", "ADMIN"), ("NEWS", "ADMIN")})
        if user.is_active:
            grants.add(("MESSENGER", "MEMBER"))
        AccessGrant.objects.bulk_create(
            [AccessGrant(user_id=user.pk, module=module, role=role) for module, role in grants]
        )


class Migration(migrations.Migration):
    dependencies = [("identity", "0003_local_identity_schema")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
