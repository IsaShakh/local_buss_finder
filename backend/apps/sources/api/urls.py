from django.urls import path

from apps.sources.api.views import SourceListView

urlpatterns = [
    path("", SourceListView.as_view(), name="source-list"),
]
