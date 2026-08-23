from rest_framework import serializers
from rest_framework.response import Response

from apps.core.views import PrivateAPIView
from apps.identity.portal import get_portal_adapter

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
        employees = [
            employee
            for employee in get_portal_adapter().search_employees(
                query,
                limit=EMPLOYEE_SEARCH_LIMIT,
            )
            if employee.is_active
        ][:EMPLOYEE_SEARCH_LIMIT]
        return Response(self.serializer_class(employees, many=True).data)


class PositionGroupListView(PrivateAPIView):
    serializer_class = PositionGroupSerializer

    def get(self, request):
        groups = {
            employee.position_group_external_id: employee.position_group_name
            for employee in get_portal_adapter().search_employees("", limit=1_000)
            if employee.is_active
            and employee.position_group_external_id
            and employee.position_group_name
        }
        if not groups:
            from apps.identity.models import User

            groups = dict(
                User.objects.filter(is_active=True)
                .exclude(position_group_external_id="")
                .values_list("position_group_external_id", "position_group_name")
            )
        payload = [
            {"external_id": external_id, "name": name}
            for external_id, name in sorted(groups.items(), key=lambda item: item[1])
        ]
        return Response(self.serializer_class(payload, many=True).data)
