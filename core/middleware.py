from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from .models import Profile


class TimeZoneChosenMiddleware:
    """Sends a logged-in account to the Profile page until it has chosen a time zone."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.path not in (
            reverse('profile'),
            reverse('logout'),
        ):
            has_timezone = (
                Profile.objects.filter(user=request.user).exclude(timezone='').exists()
            )
            if not has_timezone:
                messages.info(request, 'Choose your time zone to continue.')
                return redirect('profile')
        return self.get_response(request)
