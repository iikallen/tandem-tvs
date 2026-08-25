import hashlib
import io
import uuid
import zipfile
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import models, transaction
from PIL import Image, UnidentifiedImageError

from apps.identity.models import User

from .models import AuditEvent, MediaAsset, MediaUsage
from .services import is_editor, record_audit_event

DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED = {
    ".png": (MediaAsset.Kind.IMAGE, "image/png"),
    ".jpg": (MediaAsset.Kind.IMAGE, "image/jpeg"),
    ".jpeg": (MediaAsset.Kind.IMAGE, "image/jpeg"),
    ".gif": (MediaAsset.Kind.IMAGE, "image/gif"),
    ".webp": (MediaAsset.Kind.IMAGE, "image/webp"),
    ".mp4": (MediaAsset.Kind.VIDEO, "video/mp4"),
    ".pdf": (MediaAsset.Kind.DOCUMENT, "application/pdf"),
    ".docx": (
        MediaAsset.Kind.DOCUMENT,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".xlsx": (
        MediaAsset.Kind.DOCUMENT,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
}


def _detected_mime(data: bytes, extension: str) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04") and extension in {".docx", ".xlsx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return None
        if extension == ".docx" and "word/document.xml" in names:
            return ALLOWED[extension][1]
        if extension == ".xlsx" and "xl/workbook.xml" in names:
            return ALLOWED[extension][1]
    return None


def _image_dimensions(data: bytes) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 100_000_000:
                raise ValidationError("Image dimensions are unsafe.")
            return width, height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError("Image content is invalid.") from exc


def create_media_asset(
    *, upload: UploadedFile, actor: User, messenger_only: bool = False
) -> MediaAsset:
    from apps.discussions.models import EngagementSettings

    policy = EngagementSettings.load()
    hard_limit = int(getattr(settings, "MEDIA_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES))
    max_bytes = min(hard_limit, policy.max_comment_attachment_bytes)
    upload_size = upload.size or 0
    if upload_size <= 0 or upload_size > max_bytes:
        raise ValidationError(f"File must be between 1 and {max_bytes} bytes.")
    original_name = PurePosixPath((upload.name or "").replace("\\", "/")).name
    extension = PurePosixPath(original_name).suffix.casefold()
    expected = ALLOWED.get(extension) if extension in policy.allowed_media_extensions else None
    if expected is None or extension == ".svg":
        raise ValidationError("File extension is not allowed.")
    data = upload.read(max_bytes + 1)
    upload.seek(0)
    if len(data) != upload_size or len(data) > max_bytes:
        raise ValidationError("File size does not match the upload metadata.")
    detected = _detected_mime(data, extension)
    if detected != expected[1]:
        raise ValidationError("File content does not match its extension.")
    declared = (upload.content_type or "").casefold().split(";", 1)[0]
    if declared and declared not in {detected, "application/octet-stream"}:
        raise ValidationError("Declared MIME type does not match file content.")
    width = height = None
    if expected[0] == MediaAsset.Kind.IMAGE:
        width, height = _image_dimensions(data)
    storage_key = f"assets/{uuid.uuid4().hex}{extension}"
    asset = MediaAsset(
        original_name=original_name[:255],
        storage_key=storage_key,
        mime_type=detected,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        kind=expected[0],
        uploader=actor,
        width=width,
        height=height,
        is_messenger_only=messenger_only,
    )
    asset.file.save(storage_key, upload, save=False)
    try:
        with transaction.atomic():
            asset.full_clean()
            asset.save()
            record_audit_event(
                actor=actor,
                event_type=AuditEvent.Type.MEDIA_UPLOADED,
                target_type=AuditEvent.TargetType.MEDIA,
                target_id=asset.pk,
                new_state=_media_state(asset),
            )
    except Exception:
        asset.file.storage.delete(asset.file.name)
        raise
    return asset


def can_read_media(user: User, asset: MediaAsset) -> bool:
    from apps.messenger.models import ConversationMembership, MessageAttachment

    active_conversations = ConversationMembership.objects.filter(
        user=user, left_at__isnull=True
    ).values("conversation_id")
    messenger_attachments = MessageAttachment.objects.filter(asset=asset)
    if messenger_attachments.filter(
        models.Q(message__conversation__memberships__left_sequence__isnull=True)
        | models.Q(
            message__sequence__lte=models.F("message__conversation__memberships__left_sequence")
        ),
        message__deleted_at__isnull=True,
        message__conversation_id__in=active_conversations,
        message__conversation__memberships__user=user,
        message__sequence__gt=models.F("message__conversation__memberships__joined_sequence"),
    ).exists():
        return True
    publication_ids = MediaUsage.objects.filter(asset=asset).values("publication_id")
    if (
        is_editor(user)
        and not asset.is_messenger_only
        and (publication_ids.exists() or not messenger_attachments.exists())
    ):
        return True
    if Publication.objects.visible_to(user).filter(pk__in=publication_ids).exists():
        return True
    from apps.discussions.models import CommentAttachment

    comment_publications = CommentAttachment.objects.filter(
        asset=asset, comment__status="ACTIVE"
    ).values("comment__publication_id")
    if Publication.objects.visible_to(user).filter(pk__in=comment_publications).exists():
        return True
    return False


@transaction.atomic
def delete_media_asset(asset: MediaAsset, *, actor: User) -> None:
    if not is_editor(actor):
        raise ValidationError("An editor role is required.")
    asset = MediaAsset.objects.select_for_update().get(pk=asset.pk)
    from apps.discussions.models import CommentAttachment
    from apps.messenger.models import MessageAttachment

    if (
        MediaUsage.objects.filter(asset=asset).exists()
        or CommentAttachment.objects.filter(asset=asset).exists()
        or MessageAttachment.objects.filter(asset=asset).exists()
    ):
        raise ValidationError("Media used by a publication cannot be deleted.")
    previous = _media_state(asset)
    storage = asset.file.storage
    storage_name = asset.file.name
    record_audit_event(
        actor=actor,
        event_type=AuditEvent.Type.MEDIA_DELETED,
        target_type=AuditEvent.TargetType.MEDIA,
        target_id=asset.pk,
        previous_state=previous,
    )
    asset.delete()
    transaction.on_commit(lambda: storage.delete(storage_name), robust=True)


def _media_state(asset: MediaAsset) -> dict[str, object]:
    return {
        "original_name": asset.original_name,
        "storage_key": asset.storage_key,
        "mime_type": asset.mime_type,
        "size": asset.size,
        "sha256": asset.sha256,
        "kind": asset.kind,
        "status": asset.status,
        "is_messenger_only": asset.is_messenger_only,
    }


# Imported late to keep model loading acyclic.
from .models import Publication  # noqa: E402
