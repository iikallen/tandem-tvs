from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import MeSerializer


class MeView(APIView):
    serializer_class = MeSerializer

    def get(self, request):
        return Response(self.serializer_class(request.user).data)
