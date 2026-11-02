from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.cache import add_never_cache_headers

from .models import Profile


class NeverCacheMiddleware:
    """Tells the browser not to keep a copy of any page.

    The buttons on a title's page change it in place, so the list I opened it from is out of date by the time I press
    Back. With a copy kept, the browser shows that old list; without one it asks again and shows what is true now.
    The CSS, logo and htmx are served by WhiteNoise before this runs, so they stay cacheable.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        add_never_cache_headers(response)
        return response


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
