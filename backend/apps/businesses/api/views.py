import json
import re

from django.db.models import (
    BooleanField,
    Count,
    Exists,
    F,
    Func,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.businesses.api.pagination import SourceRecordPagination, StandardPagination
from apps.businesses.api.serializers import (
    BusinessDetailSerializer,
    BusinessListSerializer,
    BusinessQuerySerializer,
    DashboardSummarySerializer,
    DuplicateCandidateSerializer,
    DuplicateDecisionSerializer,
    PaginationQuerySerializer,
    SourceRecordDetailSerializer,
    SourceRecordListSerializer,
    SourceRecordQuerySerializer,
    StrictInputSerializer,
)
from apps.businesses.models import Business, BusinessSourceMembership, DuplicateCandidate
from apps.campaigns.models import DiscoveryCampaign
from apps.deduplication.decisions import confirm_duplicate, reject_duplicate
from apps.deduplication.exceptions import DuplicateCandidateNotPending
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
                "businesses": {
                    "active": Business.active.filter(owner=request.user).count(),
                    "pending_duplicates": _pending_candidates(request.user).count(),
                },
            }
        )
        return Response(serializer.data)


def _pending_candidates(owner):
    return DuplicateCandidate.objects.filter(
        owner=owner,
        status=DuplicateCandidate.Status.PENDING,
        left_business__owner=owner,
        right_business__owner=owner,
        left_business__merged_into__isnull=True,
        right_business__merged_into__isnull=True,
    )


def _businesses(owner, *, detail=False):
    # Correlated aggregates keep provenance and candidate counts independent of
    # list filters and avoid multiplying membership/candidate joins.
    memberships = (
        BusinessSourceMembership.objects.filter(
            business_id=OuterRef("pk"),
            normalized_record__source_record__campaign__created_by=owner,
        )
        .order_by()
        .values("business_id")
    )
    pending = (
        _pending_candidates(owner)
        .filter(Q(left_business_id=OuterRef("pk")) | Q(right_business_id=OuterRef("pk")))
        .order_by()
        .values("owner_id")
        .annotate(total=Count("id", distinct=True))
        .values("total")
    )
    related = ["category", "district"]
    fields = [
        "id",
        "display_name",
        "address_text",
        "location",
        "phones",
        "emails",
        "websites",
        "social_urls",
        "first_seen_at",
        "last_seen_at",
        "category__id",
        "category__name",
        "category__slug",
        "district__id",
        "district__name_ru",
        "district__slug",
    ]
    if detail:
        related.extend(("country", "province", "neighborhood"))
        for relation, code in (("country", "code"), ("province", "code"), ("neighborhood", "slug")):
            fields.extend((f"{relation}__id", f"{relation}__name_ru", f"{relation}__{code}"))
    return (
        Business.active.filter(owner=owner)
        .select_related(*related)
        .only(*fields)
        .annotate(
            source_count=Coalesce(
                Subquery(
                    memberships.annotate(
                        total=Count("normalized_record__source_record__source_id", distinct=True)
                    ).values("total")
                ),
                0,
            ),
            source_record_count=Coalesce(
                Subquery(
                    memberships.annotate(
                        total=Count("normalized_record__source_record_id", distinct=True)
                    ).values("total")
                ),
                0,
            ),
            pending_duplicate_count=Coalesce(Subquery(pending), 0),
        )
    )


class BusinessListView(ListAPIView):
    serializer_class = BusinessListSerializer
    pagination_class = StandardPagination

    def list(self, request, *args, **kwargs):
        page_ids = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        summaries = {
            business.id: business
            for business in _businesses(request.user).filter(id__in=page_ids).order_by()
        }
        # Projection order is independent of the narrow page query's ordering.
        page = [summaries[pk] for pk in page_ids if pk in summaries]
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def get_queryset(self):
        query = BusinessQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        queryset = Business.active.filter(owner=self.request.user)
        membership_filters = {}
        if campaign := params.get("campaign"):
            membership_filters["normalized_record__source_record__campaign_id"] = campaign
        if source := params.get("source"):
            membership_filters["normalized_record__source_record__source__code"] = source
        if membership_filters:
            queryset = queryset.filter(
                Exists(
                    BusinessSourceMembership.objects.filter(
                        business_id=OuterRef("pk"),
                        normalized_record__source_record__campaign__created_by=self.request.user,
                        **membership_filters,
                    )
                )
            )
        if category := params.get("category"):
            queryset = queryset.filter(category__slug=category)
        if search := params.get("search"):
            # Search JSON array values, not serialized JSON punctuation. The path
            # is a bound ORM parameter; regex and JSON quoting preserve literals.
            path = "$[*] ? (@ like_regex " + json.dumps(re.escape(search)) + ' flag "i")'
            contacts = Q(normalized_name__icontains=search)
            for field in ("phones", "emails", "domains"):
                contacts |= Q(
                    Func(
                        F(field),
                        Value(path),
                        function="jsonb_path_exists",
                        output_field=BooleanField(),
                    )
                )
            queryset = queryset.filter(contacts)
        return queryset.order_by(params.get("ordering", "display_name"), "id").values_list(
            "id", flat=True
        )


class BusinessDetailView(RetrieveAPIView):
    serializer_class = BusinessDetailSerializer

    def get_queryset(self):
        query = StrictInputSerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return _businesses(self.request.user, detail=True)

    def get_object(self):
        business = super().get_object()
        memberships = list(
            business.memberships.filter(
                normalized_record__source_record__campaign__created_by=self.request.user,
            )
            .select_related("normalized_record__source_record__source")
            .order_by(
                "-normalized_record__source_record__fetched_at",
                "id",
            )[:101]
        )
        business.api_memberships = memberships[:100]
        business.memberships_truncated = len(memberships) > 100
        return business


class DuplicateCandidateListView(ListAPIView):
    serializer_class = DuplicateCandidateSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        query = PaginationQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        summaries = _businesses(self.request.user)
        return (
            _pending_candidates(self.request.user)
            .prefetch_related(
                Prefetch("left_business", queryset=summaries),
                Prefetch("right_business", queryset=summaries),
            )
            .order_by("-score", "created_at", "id")
        )


class DuplicateDecisionView(APIView):
    decision = None

    def post(self, request, pk):
        query = StrictInputSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        body = StrictInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            candidate = self.decision(candidate_id=pk, actor=request.user)
        except DuplicateCandidate.DoesNotExist as exc:
            raise NotFound from exc
        except DuplicateCandidateNotPending as exc:
            return Response({"code": exc.code}, status=409)
        return Response(DuplicateDecisionSerializer(candidate).data)


class ConfirmDuplicateView(DuplicateDecisionView):
    decision = staticmethod(confirm_duplicate)


class RejectDuplicateView(DuplicateDecisionView):
    decision = staticmethod(reject_duplicate)
