from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers

from .cloudflare_access import (
    TOKEN_HEADER,
    SignInRefused,
    account_for,
    on_cloudflare_address,
    verified_email,
)
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


class CloudflareSignInMiddleware:
    """On the Cloudflare address, the person is whoever Cloudflare's token says, on every request.

    Couchlog keeps no login of its own there, so a shared browser cannot stay in the wrong account. Any other address
    is left alone and the token header is not even read there, so a made-up header at home does nothing.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not on_cloudflare_address(request):
            return self.get_response(request)

        try:
            if request.path.startswith(reverse('admin:index')):
                raise SignInRefused('The admin page only opens from the home address.')
            request.user = account_for(verified_email(request.headers.get(TOKEN_HEADER, '')))
        except SignInRefused as refused:
            return render(request, 'core/sign_in_refused.html', {'message': refused.message}, status=refused.status)

        # The username and password form is not used here, and someone with a token is already in.
        if request.path == reverse('login'):
            return redirect('home')
        return self.get_response(request)


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
