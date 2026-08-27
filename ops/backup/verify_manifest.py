#!/usr/bin/env python3
import argparse
import hashlib
import tarfile
from pathlib import Path, PurePosixPath

BACKUP_FILES = ("database.dump", "media.tar", "source-evidence.txt")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def create(directory: Path) -> None:
    lines = [f"{digest(directory / name)}  {name}" for name in BACKUP_FILES]
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")


def verify(directory: Path) -> None:
    manifest = directory / "SHA256SUMS"
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="ascii").splitlines():
        checksum, separator, name = line.partition("  ")
        if not separator or name not in BACKUP_FILES or len(checksum) != 64:
            raise SystemExit("Invalid backup manifest")
        entries[name] = checksum
    if set(entries) != set(BACKUP_FILES):
        raise SystemExit("Backup manifest is incomplete")
    for name, expected in entries.items():
        if digest(directory / name) != expected:
            raise SystemExit(f"Checksum mismatch: {name}")

    try:
        evidence = dict(
            line.split("=", 1)
            for line in (directory / "source-evidence.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    except ValueError as exc:
        raise SystemExit("Backup source evidence is invalid") from exc
    required = {
        "database_identity",
        "postgres_data_root",
        "postgres_data_device",
        "media_root",
        "media_device",
        "backup_root",
        "backup_device",
    }
    if set(evidence) != required or not all(evidence.values()):
        raise SystemExit("Backup source evidence is incomplete")
    if evidence["backup_device"] in {
        evidence["postgres_data_device"],
        evidence["media_device"],
    }:
        raise SystemExit("Backup source evidence has a shared failure domain")


def verify_archive(directory: Path) -> None:
    with tarfile.open(directory / "media.tar", "r:") as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit("Unsafe media archive path")
            if member.issym() or member.islnk() or member.isdev():
                raise SystemExit("Unsafe media archive member")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("directory", type=Path)
    arguments = parser.parse_args()
    directory = arguments.directory.resolve()
    if arguments.action == "create":
        create(directory)
    else:
        verify(directory)
        verify_archive(directory)
        print("Backup manifest: PASS")


if __name__ == "__main__":
    main()
