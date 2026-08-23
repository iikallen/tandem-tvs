from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.portal import get_portal_adapter

from .models import OrgUnit
from .serializers import EmployeeSerializer, OrgUnitSerializer


class OrgUnitListView(APIView):
    serializer_class = OrgUnitSerializer

    def get(self, request):
        units = OrgUnit.objects.select_related("parent").filter(is_active=True)
        return Response(self.serializer_class(units, many=True).data)


class EmployeeSearchView(APIView):
    serializer_class = EmployeeSerializer

    def get(self, request):
        query = request.query_params.get("search", "")
        employees = [
            employee
            for employee in get_portal_adapter().search_employees(query)
            if employee.is_active
        ]
        return Response(self.serializer_class(employees, many=True).data)
