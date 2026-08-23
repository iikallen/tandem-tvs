from rest_framework import serializers

from apps.identity.portal.types import PortalEmployee


class OrgUnitSerializer(serializers.Serializer):
    external_id = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    parent_external_id = serializers.CharField(source="parent.external_id", allow_null=True)
    is_active = serializers.BooleanField()


class EmployeeSerializer(serializers.Serializer):
    portal_id = serializers.CharField()
    full_name = serializers.CharField()
    job_title = serializers.CharField(allow_blank=True)
    org_unit_external_id = serializers.CharField(allow_null=True)

    def to_representation(self, instance: PortalEmployee):
        return super().to_representation(instance)


class PositionGroupSerializer(serializers.Serializer):
    external_id = serializers.CharField()
    name = serializers.CharField()
