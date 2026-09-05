from django.urls import path

from apps.businesses.api.views import (
    DashboardSummaryView,
    SourceRecordDetailView,
    SourceRecordListView,
)

urlpatterns = [
    path("source-records/", SourceRecordListView.as_view(), name="source-record-list"),
    path(
        "source-records/<uuid:pk>/",
        SourceRecordDetailView.as_view(),
        name="source-record-detail",
    ),
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
]
