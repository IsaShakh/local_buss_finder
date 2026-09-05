from rest_framework.generics import ListAPIView

from apps.taxonomy.api.serializers import BusinessCategorySerializer
from apps.taxonomy.models import BusinessCategory


class BusinessCategoryListView(ListAPIView):
    serializer_class = BusinessCategorySerializer
    queryset = BusinessCategory.objects.filter(
        is_active=True,
        parent__isnull=True,
    ).order_by("name", "id")
