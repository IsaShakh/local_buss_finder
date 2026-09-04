from django.urls import path

from .views import SearchAreaListView

urlpatterns = [
    path("search-areas/", SearchAreaListView.as_view(), name="search-area-list"),
]
