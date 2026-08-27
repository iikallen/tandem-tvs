from rest_framework import serializers

from apps.organization.models import OrgUnit

from .auth_services import access_payload, validate_local_password
from .managers import UserManager
from .models import AccessGrant, User
from .permissions import access_grants


class UserOrgUnitSerializer(serializers.Serializer):
    external_id = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    parent_external_id = serializers.CharField(source="parent.external_id", allow_null=True)


class AccountSerializer(serializers.ModelSerializer):
    access = serializers.SerializerMethodField()
    module_roles = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        fields = [
            "id",
            "username",
            "portal_id",
            "full_name",
            "email",
            "job_title",
            "phone",
            "avatar_url",
            "org_unit",
            "is_active",
            "activated_at",
            "access",
            "module_roles",
        ]

    def get_access(self, user):
        return access_payload(user)

    def get_module_roles(self, user):
        mapping = {
            AccessGrant.Role.MEMBER: "employee",
            AccessGrant.Role.AUTHOR: "author",
            AccessGrant.Role.EDITOR: "editor",
            AccessGrant.Role.MODERATOR: "moderator",
            AccessGrant.Role.ADMIN: "admin",
        }
        return [
            mapping[grant.role]
            for grant in sorted(access_grants(user), key=lambda item: item.role)
            if grant.module == AccessGrant.Module.NEWS and grant.role in mapping
        ]


class MeSerializer(AccountSerializer):
    org_unit = UserOrgUnitSerializer(allow_null=True)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate_username(self, value):
        return UserManager.normalize_username(value)


class PasswordPairSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128, trim_whitespace=True)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    password_confirm = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    new_password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def validate_new_password(self, value):
        validate_local_password(value, self.context["request"].user)
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class GrantInputSerializer(serializers.Serializer):
    module = serializers.ChoiceField(choices=AccessGrant.Module.choices)
    role = serializers.ChoiceField(choices=AccessGrant.Role.choices)

    def validate(self, attrs):
        allowed = {
            AccessGrant.Module.PLATFORM: {AccessGrant.Role.ADMIN},
            AccessGrant.Module.NEWS: set(AccessGrant.Role.values),
            AccessGrant.Module.MESSENGER: {
                AccessGrant.Role.MEMBER,
                AccessGrant.Role.MODERATOR,
                AccessGrant.Role.ADMIN,
            },
        }
        if attrs["role"] not in allowed[attrs["module"]]:
            raise serializers.ValidationError("Role is not valid for this module.")
        return attrs


class PlatformUserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=255)
    job_title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    portal_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    org_unit = serializers.PrimaryKeyRelatedField(
        queryset=OrgUnit.objects.filter(is_active=True), required=False, allow_null=True
    )
    grants = GrantInputSerializer(many=True, required=False)

    def validate_username(self, value):
        value = UserManager.normalize_username(value)
        if not value:
            raise serializers.ValidationError("Username is required.")
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Username is already in use.")
        return value

    def validate_email(self, value):
        value = value.strip().casefold()
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email is already in use.")
        return value

    def validate_portal_id(self, value):
        return value or None


class PlatformUserUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=255, required=False)
    job_title = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    org_unit = serializers.PrimaryKeyRelatedField(
        queryset=OrgUnit.objects.filter(is_active=True), required=False, allow_null=True
    )
    is_active = serializers.BooleanField(required=False)

    def validate_email(self, value):
        value = value.strip().casefold()
        queryset = User.objects.filter(email__iexact=value)
        user_id = self.context.get("user_id")
        if user_id is not None:
            queryset = queryset.exclude(pk=user_id)
        if value and queryset.exists():
            raise serializers.ValidationError("Email is already in use.")
        return value
