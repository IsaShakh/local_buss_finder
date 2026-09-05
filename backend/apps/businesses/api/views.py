from django.db.models import Count, Q
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.businesses.api.pagination import SourceRecordPagination
from apps.businesses.api.serializers import (
    DashboardSummarySerializer,
    SourceRecordDetailSerializer,
    SourceRecordListSerializer,
    SourceRecordQuerySerializer,
)
from apps.campaigns.models import DiscoveryCampaign
from apps.sources.models import NormalizedSourceRecord, SourceRecord


class SourceRecordListView(ListAPIView):
    serializer_class = SourceRecordListSerializer
    pagination_class = SourceRecordPagination

    def get_queryset(self):
        query = SourceRecordQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        queryset = NormalizedSourceRecord.objects.filter(
            source_record__campaign__created_by=self.request.user,
            source_record__normalization_status=SourceRecord.NormalizationStatus.NORMALIZED,
        ).select_related(
            "source_record__source",
            "category",
            "district",
        )
        if campaign_id := params.get("campaign"):
            queryset = queryset.filter(source_record__campaign_id=campaign_id)
        if source_code := params.get("source"):
            queryset = queryset.filter(source_record__source__code=source_code)
        if category_slug := params.get("category"):
            queryset = queryset.filter(category__slug=category_slug)
        if search := params.get("search"):
            queryset = queryset.filter(normalized_name__icontains=search)

        ordering = params.get("ordering", "-fetched_at")
        ordering_map = {
            "display_name": "display_name",
            "fetched_at": "source_record__fetched_at",
            "-fetched_at": "-source_record__fetched_at",
        }
        return queryset.order_by(ordering_map[ordering], "id")


class SourceRecordDetailView(RetrieveAPIView):
    serializer_class = SourceRecordDetailSerializer

    def get_queryset(self):
        return SourceRecord.objects.filter(campaign__created_by=self.request.user).select_related(
            "source",
            "normalized_record__category",
            "normalized_record__country",
            "normalized_record__province",
            "normalized_record__district",
            "normalized_record__neighborhood",
        )


class DashboardSummaryView(APIView):
    def get(self, request):
        records = SourceRecord.objects.filter(campaign__created_by=request.user).aggregate(
            raw=Count("id"),
            normalized=Count(
                "id",
                filter=Q(normalization_status=SourceRecord.NormalizationStatus.NORMALIZED),
            ),
            rejected=Count(
                "id",
                filter=Q(normalization_status=SourceRecord.NormalizationStatus.REJECTED),
            ),
            failed=Count(
                "id",
                filter=Q(normalization_status=SourceRecord.NormalizationStatus.FAILED),
            ),
        )
        campaigns_queryset = DiscoveryCampaign.objects.filter(created_by=request.user)
        campaigns = campaigns_queryset.aggregate(
            total=Count("id"),
            running=Count(
                "id",
                filter=Q(
                    status__in=(DiscoveryCampaign.Status.QUEUED, DiscoveryCampaign.Status.RUNNING)
                ),
            ),
            with_errors=Count(
                "id",
                filter=Q(
                    status__in=(
                        DiscoveryCampaign.Status.COMPLETED_WITH_ERRORS,
                        DiscoveryCampaign.Status.FAILED,
                    )
                ),
            ),
        )
        recent_campaigns = [
            {
                "id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "normalized": campaign.normalized_records,
                "updated_at": campaign.updated_at,
            }
            for campaign in campaigns_queryset.order_by("-updated_at", "-id")[:5]
        ]
        serializer = DashboardSummarySerializer(
            {
                "records": records,
                "campaigns": campaigns,
                "recent_campaigns": recent_campaigns,
            }
        )
        return Response(serializer.data)
