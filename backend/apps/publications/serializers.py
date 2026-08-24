from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.identity.models import User
from apps.identity.portal import get_portal_adapter

from .models import (
    Acknowledgement,
    Category,
    MediaAsset,
    Publication,
    PublicationPin,
    PublicationVersion,
    Tag,
)
from .rich_text import rich_text_asset_references
from .services import audience_payload, create_publication, update_publication


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        fields = ["id", "username", "portal_id", "full_name", "job_title"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Category
        fields = ["id", "slug", "name", "sort_order", "is_active", "comment_attachments_enabled"]
        read_only_fields = ["id"]


class TagSerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Tag
        fields = ["id", "slug", "name", "is_active"]
        read_only_fields = ["id"]


class PositionGroupSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=128)
    name = serializers.CharField(max_length=255)


class AudienceSerializer(serializers.Serializer):
    everyone = serializers.BooleanField(default=False)
    org_units = serializers.ListField(
        child=serializers.CharField(max_length=128), required=False, default=list, max_length=100
    )
    org_unit_subtrees = serializers.ListField(
        child=serializers.CharField(max_length=128), required=False, default=list, max_length=100
    )
    employees = serializers.ListField(
        child=serializers.CharField(max_length=128), required=False, default=list, max_length=100
    )
    module_roles = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, default=list, max_length=20
    )
    position_groups = PositionGroupSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        narrow_keys = (
            "org_units",
            "org_unit_subtrees",
            "employees",
            "module_roles",
            "position_groups",
        )
        has_narrow = any(attrs[key] for key in narrow_keys)
        if attrs["everyone"] and has_narrow:
            raise serializers.ValidationError("Entire company cannot be combined with targets.")
        exact = set(attrs["org_units"])
        subtree = set(attrs["org_unit_subtrees"])
        if exact & subtree:
            raise serializers.ValidationError("A unit cannot be exact and subtree at once.")
        group_ids = [group["external_id"] for group in attrs["position_groups"]]
        if len(group_ids) != len(set(group_ids)):
            raise serializers.ValidationError("Position groups must be unique.")
        if group_ids:
            active_groups = {
                group.external_id: group.name
                for group in get_portal_adapter().list_position_groups()
                if group.is_active
            }
            unknown = set(group_ids) - active_groups.keys()
            if unknown:
                raise serializers.ValidationError("Position group is unknown or inactive.")
            attrs["position_groups"] = [
                {"external_id": group_id, "name": active_groups[group_id]} for group_id in group_ids
            ]
        return attrs


class MediaAssetSerializer(serializers.ModelSerializer):
    content_url = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = MediaAsset
        fields = [
            "id",
            "original_name",
            "mime_type",
            "size",
            "sha256",
            "kind",
            "width",
            "height",
            "status",
            "created_at",
            "content_url",
        ]

    def get_content_url(self, obj):
        return f"/api/v1/media/{obj.pk}/content"


class EditorialPublicationSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(
        slug_field="slug", queryset=Category.objects.filter(is_active=True)
    )
    tags = serializers.SlugRelatedField(
        slug_field="slug", queryset=Tag.objects.filter(is_active=True), many=True, required=False
    )
    cover = serializers.PrimaryKeyRelatedField(
        queryset=MediaAsset.objects.filter(status=MediaAsset.Status.READY),
        allow_null=True,
        required=False,
    )
    attachments = serializers.PrimaryKeyRelatedField(
        queryset=MediaAsset.objects.filter(status=MediaAsset.Status.READY),
        many=True,
        required=False,
        write_only=True,
    )
    author = UserSummarySerializer(read_only=True)
    audience = AudienceSerializer(write_only=True, required=False)
    expected_revision = serializers.IntegerField(min_value=0, write_only=True, required=False)
    autosave = serializers.BooleanField(write_only=True, required=False, default=False)
    media = serializers.SerializerMethodField()
    pin_slot = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Publication
        fields = [
            "id",
            "slug",
            "title",
            "summary",
            "body",
            "category",
            "tags",
            "cover",
            "comments_enabled",
            "reactions_enabled",
            "acknowledgement_required",
            "attachments",
            "author",
            "status",
            "published_at",
            "scheduled_for",
            "expires_at",
            "unpublished_at",
            "archived_at",
            "edit_revision",
            "last_autosaved_at",
            "audience",
            "media",
            "pin_slot",
            "expected_revision",
            "autosave",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "author",
            "status",
            "published_at",
            "scheduled_for",
            "unpublished_at",
            "archived_at",
            "edit_revision",
            "last_autosaved_at",
            "media",
            "pin_slot",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        if "author" in self.initial_data:
            raise serializers.ValidationError({"author": "Author is assigned by the server."})
        if self.instance is not None and "expected_revision" not in attrs:
            raise serializers.ValidationError(
                {"expected_revision": "Current edit revision is required."}
            )
        body = attrs.get("body", getattr(self.instance, "body", None))
        try:
            body_references = rich_text_asset_references(body)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"body": exc.messages}) from exc
        body_ids = set(body_references)
        assets = list(MediaAsset.objects.filter(pk__in=body_ids, status=MediaAsset.Status.READY))
        if {asset.pk for asset in assets} != body_ids:
            raise serializers.ValidationError({"body": "Rich text references unknown media."})
        expected_kinds = {
            "assetImage": MediaAsset.Kind.IMAGE,
            "internalVideo": MediaAsset.Kind.VIDEO,
        }
        for asset in assets:
            for node_type in body_references[asset.pk]:
                expected = expected_kinds.get(node_type)
                if expected is not None and asset.kind != expected:
                    raise serializers.ValidationError(
                        {"body": f"{node_type} references incompatible media."}
                    )
        attrs["body_assets"] = assets
        return attrs

    def create(self, validated_data):
        validated_data.pop("expected_revision", None)
        validated_data.pop("autosave", None)
        if "audience" not in validated_data:
            validated_data["audience"] = {
                "everyone": False,
                "org_units": [],
                "org_unit_subtrees": [],
                "employees": [],
                "module_roles": [],
                "position_groups": [],
            }
        try:
            return create_publication(actor=self.context["request"].user, data=validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def update(self, instance, validated_data):
        expected_revision = validated_data.pop("expected_revision")
        autosave = validated_data.pop("autosave", False)
        try:
            return update_publication(
                instance,
                actor=self.context["request"].user,
                data=validated_data,
                expected_revision=expected_revision,
                autosave=autosave,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def get_media(self, instance):
        return [
            {
                "asset": MediaAssetSerializer(usage.asset).data,
                "purpose": usage.purpose,
            }
            for usage in instance.media_usages.select_related("asset").all()
        ]

    def get_pin_slot(self, instance):
        try:
            return instance.pin.slot
        except PublicationPin.DoesNotExist:
            return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["audience"] = audience_payload(instance)
        return data


class PublicationVersionSerializer(serializers.ModelSerializer):
    actor = UserSummarySerializer(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = PublicationVersion
        fields = [
            "version_number",
            "actor",
            "reason",
            "snapshot",
            "changed_fields",
            "content_hash",
            "created_at",
        ]


class NewsPublicationSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(read_only=True, many=True)
    author = UserSummarySerializer(read_only=True)
    cover = MediaAssetSerializer(read_only=True, allow_null=True)
    view_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    reaction_count = serializers.IntegerField(read_only=True)
    is_read = serializers.BooleanField(read_only=True)
    pin_slot = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Publication
        fields = [
            "id",
            "slug",
            "title",
            "summary",
            "category",
            "tags",
            "author",
            "published_at",
            "expires_at",
            "cover",
            "pin_slot",
            "comments_enabled",
            "reactions_enabled",
            "acknowledgement_required",
            "view_count",
            "comment_count",
            "reaction_count",
            "is_read",
        ]

    def get_pin_slot(self, instance):
        try:
            return instance.pin.slot
        except PublicationPin.DoesNotExist:
            return None


class NewsPublicationDetailSerializer(NewsPublicationSerializer):
    media = serializers.SerializerMethodField()
    is_acknowledged = serializers.SerializerMethodField()

    class Meta(NewsPublicationSerializer.Meta):
        fields = [
            *NewsPublicationSerializer.Meta.fields,
            "body",
            "media",
            "is_acknowledged",
        ]

    def get_media(self, instance):
        return [
            {
                "asset": MediaAssetSerializer(usage.asset).data,
                "purpose": usage.purpose,
            }
            for usage in instance.media_usages.select_related("asset").all()
        ]

    def get_is_acknowledged(self, instance):
        request = self.context.get("request")
        return bool(
            request
            and Acknowledgement.objects.filter(publication=instance, user=request.user).exists()
        )


class NewsQuerySerializer(serializers.Serializer):
    category = serializers.SlugField(required=False)
    author = serializers.CharField(required=False, max_length=128)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    unread = serializers.BooleanField(required=False)
    q = serializers.CharField(
        required=False, allow_blank=True, max_length=200, trim_whitespace=True
    )
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=50)
    cursor = serializers.CharField(required=False, max_length=2_000)


class TransitionSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=0, required=False)
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class PinSerializer(serializers.Serializer):
    slot = serializers.IntegerField(min_value=1, max_value=5)
