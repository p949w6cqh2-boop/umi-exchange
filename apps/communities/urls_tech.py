from django.urls import path

from .views import TechnologyView

urlpatterns = [path("", TechnologyView.as_view(), name="technology")]
