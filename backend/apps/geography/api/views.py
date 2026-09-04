from rest_framework.generics import ListAPIView

from apps.geography.models import SearchArea

from .serializers import SearchAreaSerializer


class SearchAreaListView(ListAPIView):
    serializer_class = SearchAreaSerializer
    queryset = SearchArea.objects.filter(is_active=True).select_related(
        "country",
        "province",
        "district",
        "neighborhood",
    )
