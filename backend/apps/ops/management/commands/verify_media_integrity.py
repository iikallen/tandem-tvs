import hashlib
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

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

        for asset in MediaAsset.objects.filter(status=MediaAsset.Status.READY).iterator(
            chunk_size=500
        ):
            path = (root / asset.storage_key).resolve()
            if not path.is_relative_to(root):
                failures += 1
                self.stderr.write(f"Unsafe asset path: {asset.pk}")
                continue
            referenced.add(path)
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
            path for path in root.rglob("*") if path.is_file() and path not in referenced
        )
        for path in orphans:
            failures += 1
            self.stderr.write(f"Orphan media file: {path.relative_to(root)}")

        try:
            cache.set("tandem:ops:media-integrity-failures", failures, timeout=None)
        except Exception:
            pass

        if failures:
            raise CommandError(f"{failures} media integrity failures")
        self.stdout.write("Media integrity: PASS")
