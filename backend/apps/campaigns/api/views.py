from django.http import Http404
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView
from rest_framework.response import Response

from apps.campaigns.api.serializers import CampaignProgressSerializer, CampaignSerializer
from apps.campaigns.domain import CampaignValidationError
from apps.campaigns.models import DiscoveryCampaign
from apps.campaigns.progress import get_campaign_progress
from apps.campaigns.services import start_campaign
from apps.system.api.exceptions import ApiException


def enqueue_campaign(campaign_id) -> None:
    from apps.discovery.tasks import run_discovery_campaign

    run_discovery_campaign.delay(str(campaign_id))


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


class CampaignStartView(OwnedCampaignQuerysetMixin, RetrieveAPIView):
    serializer_class = CampaignSerializer

    def post(self, request, *args, **kwargs):
        campaign = self.get_object()
        try:
            campaign = start_campaign(
                campaign_id=campaign.id,
                actor=request.user,
                enqueue=enqueue_campaign,
            )
        except CampaignValidationError as error:
            raise ApiException(
                error.code,
                error.detail,
                status_code=status.HTTP_409_CONFLICT,
                fields=error.fields,
            ) from error
        return Response(self.get_serializer(campaign).data, status=status.HTTP_202_ACCEPTED)


class CampaignProgressView(OwnedCampaignQuerysetMixin, RetrieveAPIView):
    serializer_class = CampaignProgressSerializer

    def get(self, request, *args, **kwargs):
        try:
            progress = get_campaign_progress(kwargs["pk"], actor=request.user)
        except DiscoveryCampaign.DoesNotExist as error:
            raise Http404 from error
        return Response(self.get_serializer(progress).data)
