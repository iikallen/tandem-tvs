from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.identity.models import User

from .models import AudienceRule, Category, Publication
from .services import create_publication, update_publication


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        fields = ["portal_id", "full_name", "job_title"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Category
        fields = ["id", "slug", "name", "sort_order"]


class AudienceSerializer(serializers.Serializer):
    everyone = serializers.BooleanField(default=False)
    org_units = serializers.ListField(
        child=serializers.CharField(max_length=128),
        required=False,
        default=list,
        max_length=100,
    )
    employees = serializers.ListField(
        child=serializers.CharField(max_length=128),
        required=False,
        default=list,
        max_length=100,
    )
    module_roles = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        default=list,
        max_length=20,
    )

    def validate(self, attrs):
        has_narrow = any(attrs[key] for key in ("org_units", "employees", "module_roles"))
        if attrs["everyone"] and has_narrow:
            raise serializers.ValidationError("Entire company cannot be combined with targets.")
        return attrs


def audience_representation(publication: Publication) -> dict[str, object]:
    rules = publication.audience_rules.all()
    return {
        "everyone": any(rule.kind == AudienceRule.Kind.ALL for rule in rules),
        "org_units": [
            rule.org_unit.external_id
            for rule in rules
            if rule.kind == AudienceRule.Kind.ORG_UNIT and rule.org_unit is not None
        ],
        "employees": [
            rule.employee.portal_id
            for rule in rules
            if rule.kind == AudienceRule.Kind.EMPLOYEE and rule.employee is not None
        ],
        "module_roles": [
            rule.module_role for rule in rules if rule.kind == AudienceRule.Kind.MODULE_ROLE
        ],
    }


class EditorialPublicationSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(
        slug_field="slug", queryset=Category.objects.filter(is_active=True)
    )
    author = UserSummarySerializer(read_only=True)
    audience = AudienceSerializer(write_only=True, required=False)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Publication
        fields = [
            "id",
            "slug",
            "title",
            "summary",
            "body",
            "category",
            "author",
            "status",
            "published_at",
            "audience",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "author",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        if "author" in self.initial_data:
            raise serializers.ValidationError({"author": "Author is assigned by the server."})
        return attrs

    def create(self, validated_data):
        if "audience" not in validated_data:
            validated_data["audience"] = {
                "everyone": False,
                "org_units": [],
                "employees": [],
                "module_roles": [],
            }
        try:
            return create_publication(actor=self.context["request"].user, data=validated_data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def update(self, instance, validated_data):
        try:
            return update_publication(
                instance,
                actor=self.context["request"].user,
                data=validated_data,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["audience"] = audience_representation(instance)
        return data


class NewsPublicationSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    author = UserSummarySerializer(read_only=True)
    cover = serializers.CharField(read_only=True, allow_null=True, default=None)
    view_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    reaction_count = serializers.IntegerField(read_only=True)
    is_read = serializers.BooleanField(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Publication
        fields = [
            "id",
            "slug",
            "title",
            "summary",
            "category",
            "author",
            "published_at",
            "cover",
            "view_count",
            "comment_count",
            "reaction_count",
            "is_read",
        ]


class NewsPublicationDetailSerializer(NewsPublicationSerializer):
    class Meta(NewsPublicationSerializer.Meta):
        fields = [*NewsPublicationSerializer.Meta.fields, "body"]


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
