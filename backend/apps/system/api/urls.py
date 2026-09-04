from django.urls import path

from .views import LiveHealthView, ReadyHealthView

urlpatterns = [
    path("health/live/", LiveHealthView.as_view(), name="health-live"),
    path("health/ready/", ReadyHealthView.as_view(), name="health-ready"),
]
