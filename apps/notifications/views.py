from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.views import View
from django.views.generic import ListView

from .models import Notification


class NotificationListView(LoginRequiredMixin, ListView):
    template_name = "notifications/list.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)


class MarkAllReadView(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        # HTMX requests: return empty 204 (no content swap needed)
        if getattr(request, "htmx", False):
            return HttpResponse(status=204)
        # Regular form POST: redirect back to the notification list
        messages.success(request, "All notifications marked as read.")
        return redirect("notification-list")


class UnreadCountView(LoginRequiredMixin, View):
    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return JsonResponse({"count": count})


class RecentNotificationsView(LoginRequiredMixin, View):
    """Return an HTML partial of the 5 most recent notifications for the
    HTMX-powered dropdown in the header."""

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user)[:5]
        html = render_to_string(
            "notifications/_recent_list.html",
            {"notifications": notifications},
            request=request,
        )
        return HttpResponse(html)
