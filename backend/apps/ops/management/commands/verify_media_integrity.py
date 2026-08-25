import hashlib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ops.health import MEDIA_INTEGRITY_STATE_FILE, record_media_integrity_result
from apps.publications.models import MediaAsset


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Verify READY media files and report unreferenced files without deleting them."

    def handle(self, *args, **options):
        root = Path(settings.MEDIA_ROOT).resolve()
        failures = 0
        referenced: set[Path] = set()

        if not root.is_dir():
            raise CommandError("MEDIA_ROOT is not an accessible directory")

        for asset in MediaAsset.objects.all().iterator(chunk_size=500):
            path = (root / asset.storage_key).resolve()
            if not path.is_relative_to(root):
                if asset.status == MediaAsset.Status.READY:
                    failures += 1
                    self.stderr.write(f"Unsafe asset path: {asset.pk}")
                continue
            referenced.add(path)
            if asset.status != MediaAsset.Status.READY:
                continue
            if not path.is_file():
                failures += 1
                self.stderr.write(f"Missing asset: {asset.pk}")
                continue
            if path.stat().st_size != asset.size:
                failures += 1
                self.stderr.write(f"Size mismatch: {asset.pk}")
                continue
            if sha256(path) != asset.sha256:
                failures += 1
                self.stderr.write(f"SHA-256 mismatch: {asset.pk}")

        orphans = sorted(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path not in referenced
            and not path.name.startswith(MEDIA_INTEGRITY_STATE_FILE)
        )
        for path in orphans:
            failures += 1
            self.stderr.write(f"Orphan media file: {path.relative_to(root)}")

        record_media_integrity_result(failures)

        if failures:
            raise CommandError(f"{failures} media integrity failures")
        self.stdout.write("Media integrity: PASS")
