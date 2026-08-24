from rest_framework import serializers

from apps.identity.models import User


class OrgUnitSerializer(serializers.Serializer):
    external_id = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    parent_external_id = serializers.CharField(source="parent.external_id", allow_null=True)
    is_active = serializers.BooleanField()


class EmployeeSerializer(serializers.ModelSerializer):
    org_unit_external_id = serializers.CharField(source="org_unit.external_id", allow_null=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        fields = ["id", "portal_id", "full_name", "job_title", "org_unit_external_id"]


class PositionGroupSerializer(serializers.Serializer):
    external_id = serializers.CharField()
    name = serializers.CharField()
