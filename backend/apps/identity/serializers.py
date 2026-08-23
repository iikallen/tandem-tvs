from rest_framework import serializers


class UserOrgUnitSerializer(serializers.Serializer):
    external_id = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    parent_external_id = serializers.CharField(source="parent.external_id", allow_null=True)


class MeSerializer(serializers.Serializer):
    portal_id = serializers.CharField()
    full_name = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    job_title = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    avatar_url = serializers.URLField(allow_blank=True)
    org_unit = UserOrgUnitSerializer(allow_null=True)
    module_roles = serializers.ListField(child=serializers.CharField())
