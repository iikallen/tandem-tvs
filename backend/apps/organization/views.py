from rest_framework import serializers
from rest_framework.response import Response

from apps.core.views import PrivateAPIView
from apps.identity.portal import get_portal_adapter

from .models import OrgUnit
from .serializers import EmployeeSerializer, OrgUnitSerializer

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
