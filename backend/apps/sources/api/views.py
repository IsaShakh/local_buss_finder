from rest_framework.generics import ListAPIView

from apps.sources.api.serializers import SourceSerializer
from apps.sources.models import Source


class SourceListView(ListAPIView):
    queryset = Source.objects.order_by("code")
    serializer_class = SourceSerializer
