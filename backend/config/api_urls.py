from django.urls import include, path

urlpatterns = [
    path("geography/", include("apps.geography.api.urls")),
    path("", include("apps.system.api.urls")),
]
