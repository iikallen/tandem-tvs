from django.db.models import Q
from rest_framework import serializers
from rest_framework.response import Response

from apps.core.views import PrivateAPIView
from apps.identity.models import User

from .models import OrgUnit
from .serializers import EmployeeSerializer, OrgUnitSerializer, PositionGroupSerializer

EMPLOYEE_SEARCH_LIMIT = 20


class EmployeeSearchQuerySerializer(serializers.Serializer):
    search = serializers.CharField(trim_whitespace=True, min_length=2, max_length=100)


class OrgUnitListView(PrivateAPIView):
    serializer_class = OrgUnitSerializer

    def get(self, request):
        units = OrgUnit.objects.select_related("parent").filter(is_active=True)
        return Response(self.serializer_class(units, many=True).data)


class EmployeeSearchView(PrivateAPIView):
    serializer_class = EmployeeSerializer

    def get(self, request):
        raw_query = request.query_params.get("search", "").strip()
        if len(raw_query) < 2:
            return Response([])

        query_serializer = EmployeeSearchQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            raise serializers.ValidationError(query_serializer.errors)

        query = query_serializer.validated_data["search"]
        employees = (
            User.objects.filter(is_active=True)
            .filter(Q(full_name__icontains=query) | Q(username__icontains=query))
            .select_related("org_unit")[:EMPLOYEE_SEARCH_LIMIT]
        )
        return Response(self.serializer_class(employees, many=True).data)


class PositionGroupListView(PrivateAPIView):
    serializer_class = PositionGroupSerializer

    def get(self, request):
        groups = list(
            {
                row["position_group_external_id"]: {
                    "external_id": row["position_group_external_id"],
                    "name": row["position_group_name"],
                }
                for row in User.objects.filter(is_active=True)
                .exclude(position_group_external_id="")
                .exclude(position_group_name="")
                .order_by("position_group_name", "pk")
                .values("position_group_external_id", "position_group_name")
            }.values()
        )
        return Response(self.serializer_class(groups, many=True).data)
