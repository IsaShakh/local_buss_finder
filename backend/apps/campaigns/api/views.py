from rest_framework.generics import ListCreateAPIView, RetrieveAPIView

from apps.campaigns.api.serializers import CampaignSerializer
from apps.campaigns.models import DiscoveryCampaign


class OwnedCampaignQuerysetMixin:
    def get_queryset(self):
        return (
            DiscoveryCampaign.objects.filter(created_by=self.request.user)
            .select_related("search_area")
            .prefetch_related("sources", "categories")
        )


class CampaignListCreateView(OwnedCampaignQuerysetMixin, ListCreateAPIView):
    serializer_class = CampaignSerializer


class CampaignDetailView(OwnedCampaignQuerysetMixin, RetrieveAPIView):
    serializer_class = CampaignSerializer
