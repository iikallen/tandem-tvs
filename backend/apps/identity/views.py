from rest_framework.response import Response

from apps.core.views import PrivateAPIView

from .serializers import MeSerializer


class MeView(PrivateAPIView):
    serializer_class = MeSerializer

    def get(self, request):
        return Response(self.serializer_class(request.user).data)
