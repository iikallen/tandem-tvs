from rest_framework import serializers


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()


class RuntimeMetaSerializer(serializers.Serializer):
    application = serializers.CharField()
    version = serializers.CharField()
    revision = serializers.CharField()
    default_locale = serializers.CharField()
    supported_locales = serializers.ListField(child=serializers.CharField())
    planned_locales = serializers.ListField(child=serializers.CharField())
