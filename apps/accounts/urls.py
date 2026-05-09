from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.UMILoginView.as_view(), name="login"),
    path("logout/", views.UMILogoutView.as_view(), name="logout"),
]
