from rest_framework import serializers


class GlobalSearchSerializer(serializers.Serializer):
    q = serializers.CharField(min_length=1, max_length=200, trim_whitespace=True)
    scope = serializers.ChoiceField(
        choices=["all", "publications", "comments", "messages", "files", "employees"],
        required=False,
        default="all",
    )
    cursor = serializers.CharField(required=False, max_length=32)

    def validate(self, attrs):
        if attrs["scope"] == "all" and "cursor" in attrs:
            raise serializers.ValidationError({"cursor": "Use a scoped search for pagination."})
        return attrs
