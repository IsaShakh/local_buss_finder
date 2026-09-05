from django.urls import path

from apps.businesses.api.views import (
    BusinessDetailView,
    BusinessListView,
    ConfirmDuplicateView,
    DashboardSummaryView,
    DuplicateCandidateListView,
    RejectDuplicateView,
    SourceRecordDetailView,
    SourceRecordListView,
)

urlpatterns = [
    path("businesses/", BusinessListView.as_view(), name="business-list"),
    path("businesses/<uuid:pk>/", BusinessDetailView.as_view(), name="business-detail"),
    path(
        "duplicate-candidates/",
        DuplicateCandidateListView.as_view(),
        name="duplicate-candidate-list",
    ),
    path(
        "duplicate-candidates/<uuid:pk>/confirm/",
        ConfirmDuplicateView.as_view(),
        name="duplicate-candidate-confirm",
    ),
    path(
        "duplicate-candidates/<uuid:pk>/reject/",
        RejectDuplicateView.as_view(),
        name="duplicate-candidate-reject",
    ),
    path("source-records/", SourceRecordListView.as_view(), name="source-record-list"),
    path(
        "source-records/<uuid:pk>/",
        SourceRecordDetailView.as_view(),
        name="source-record-detail",
    ),
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
]
