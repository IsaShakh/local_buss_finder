from django.urls import include, path

urlpatterns = [
    path("", include("apps.system.api.urls")),
]
