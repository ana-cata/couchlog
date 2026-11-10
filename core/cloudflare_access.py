"""Sign-in by email code on the Cloudflare address.

Cloudflare asks for the email and the one-time code. On each request it then attaches a signed token (a tamper-proof
note) saying which email it checked. This file checks the note and finds the account with that email. The middleware
that uses it is CloudflareSignInMiddleware in core/middleware.py.
"""

from functools import lru_cache

import jwt
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.http.request import split_domain_port

TOKEN_HEADER = 'Cf-Access-Jwt-Assertion'
LOGOUT_ADDRESS = '/cdn-cgi/access/logout'

NOT_VERIFIED = 'Couchlog could not confirm who you are. Close this page and sign in again with your email.'
KEYS_UNREACHABLE = 'Couchlog cannot confirm who you are right now. Try again in a few minutes.'
NO_EMAIL = 'Cloudflare did not say which email you signed in with, so Couchlog cannot open an account.'
TWO_ACCOUNTS = 'More than one Couchlog account uses this email, so nobody is signed in. Ask the owner to fix it.'
NAME_TAKEN = 'Another Couchlog account already uses this email as its username. Ask the owner to fix it.'
DEACTIVATED = 'This Couchlog account has been deactivated.'


class SignInRefused(Exception):
    """Why a person cannot come in, in words they can read, and the HTTP status of the page that says so."""

    def __init__(self, message, status=403):
        super().__init__(message)
        self.message = message
        self.status = status


def on_cloudflare_address(request):
    """Whether this request came to the Cloudflare address. Always False while the setting is empty.

    The port and any final dot are left out of the comparison, so `couchlog.example.com:8443` still counts.
    """
    address = settings.CLOUDFLARE_ACCESS_ADDRESS
    return bool(address) and split_domain_port(request.get_host())[0] == address


@lru_cache
def keys_from(team_domain):
    """The reader of Cloudflare's public keys. It keeps them for a few minutes and asks again for a key it has not seen.

    It has a name of its own because Cloudflare can refuse Python's default name for a program.
    """
    return jwt.PyJWKClient(
        f'https://{team_domain}/cdn-cgi/access/certs',
        headers={'User-Agent': 'couchlog'},
        timeout=5,
    )


def verified_email(token):
    """The email inside Cloudflare's token, or SignInRefused if anything about the token is wrong."""
    team_domain = settings.CLOUDFLARE_ACCESS_TEAM_DOMAIN
    try:
        signing_key = keys_from(team_domain).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            # Only the kind of signature Cloudflare uses, so a token cannot choose a weaker one.
            algorithms=['RS256'],
            audience=settings.CLOUDFLARE_ACCESS_AUD,
            issuer=f'https://{team_domain}',
            options={'require': ['exp', 'aud', 'iss']},
            # A token is made a moment before it arrives, so a Pi clock a little behind Cloudflare's must not refuse it.
            leeway=30,
        )
    except jwt.PyJWKClientConnectionError as error:
        raise SignInRefused(KEYS_UNREACHABLE, status=503) from error
    except jwt.PyJWTError as error:
        raise SignInRefused(NOT_VERIFIED) from error

    email = claims.get('email')
    return email.strip().lower() if isinstance(email, str) else ''


def _only_account_with(email):
    """The account with this email, None if there is none. Deactivated accounts count, so they are never replaced."""
    accounts = list(User.objects.filter(email__iexact=email)[:2])
    if len(accounts) > 1:
        raise SignInRefused(TWO_ACCOUNTS)
    return accounts[0] if accounts else None


def account_for(email):
    """The active account with this email, created the first time. Never guesses: anything unclear is refused."""
    if not email:
        raise SignInRefused(NO_EMAIL)

    user = _only_account_with(email)
    if user is None:
        try:
            with transaction.atomic():
                # No password given, so the account has no usable password.
                user = User.objects.create_user(username=email, email=email)
        except IntegrityError:
            # Either another page of the same first visit created it just now, or a different account has this
            # username. Only the first case finds an account with this email.
            user = _only_account_with(email)
            if user is None:
                raise SignInRefused(NAME_TAKEN) from None

    if not user.is_active:
        raise SignInRefused(DEACTIVATED)
    return user
