from django.urls import path

from apps.campaigns.api.views import (
    CampaignDetailView,
    CampaignListCreateView,
    CampaignProgressView,
    CampaignStartView,
)

urlpatterns = [
    path("", CampaignListCreateView.as_view(), name="campaign-list"),
    path("<uuid:pk>/", CampaignDetailView.as_view(), name="campaign-detail"),
    path("<uuid:pk>/start/", CampaignStartView.as_view(), name="campaign-start"),
    path("<uuid:pk>/progress/", CampaignProgressView.as_view(), name="campaign-progress"),
]
