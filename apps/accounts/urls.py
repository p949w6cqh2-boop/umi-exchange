from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.UMILoginView.as_view(), name="login"),
    path("login/otp/", views.OTPVerifyView.as_view(), name="login-otp"),
    path("logout/", views.UMILogoutView.as_view(), name="logout"),
    # Human verification (docs/specs/human-verification.md, A+C)
    path("verify/pending/", views.VerifyPendingView.as_view(), name="verify-pending"),
    path("verify/send/", views.VerifySendView.as_view(), name="verify-send"),
    path("verify/<str:token>/", views.VerifyEmailView.as_view(), name="verify-email"),
    # Password change (logged in)
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url="/auth/password/change/done/",
        ),
        name="password_change",
    ),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html",
        ),
        name="password_change_done",
    ),
    # Username recovery (logged out)
    path(
        "username/recover/",
        views.UsernameRecoveryView.as_view(),
        name="username_recovery",
    ),
    path(
        "username/recover/done/",
        views.UsernameRecoveryDoneView.as_view(),
        name="username_recovery_done",
    ),
    # Password reset (logged out)
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="emails/password_reset_email.txt",
            success_url="/auth/password/reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password/reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/auth/password/reset/complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
