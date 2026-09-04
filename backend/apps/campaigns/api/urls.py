from django.urls import path

from apps.campaigns.api.views import CampaignDetailView, CampaignListCreateView

urlpatterns = [
    path("", CampaignListCreateView.as_view(), name="campaign-list"),
    path("<uuid:pk>/", CampaignDetailView.as_view(), name="campaign-detail"),
]
