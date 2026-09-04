from django.urls import include, path

urlpatterns = [
    path("geography/", include("apps.geography.api.urls")),
    path("sources/", include("apps.sources.api.urls")),
    path("", include("apps.system.api.urls")),
]
