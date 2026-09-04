from django.urls import path

from apps.taxonomy.api.views import BusinessCategoryListView

urlpatterns = [
    path("categories/", BusinessCategoryListView.as_view(), name="category-list"),
]
