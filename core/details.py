"""Keeping every saved title within TMDB's terms, which allow keeping what TMDB says for at most 6 months.

`refresh_calendar` only follows the titles someone is still waiting for or watching. The rest (a movie in History, a
title taken off a list) are asked about here once their details are older than `MAX_AGE`, so nothing saved from TMDB
gets older than 6 months.
"""

import datetime

from django.db.models import Q
from django.utils import timezone

from . import tmdb
from .models import Title

# A month of margin under TMDB's 6 months, so a few days of TMDB not answering do not matter.
MAX_AGE = datetime.timedelta(days=150)


def stale_titles():
    """The saved titles whose details were last asked from TMDB more than `MAX_AGE` ago, or never."""
    too_old = timezone.now() - MAX_AGE
    return Title.objects.filter(Q(details_refreshed_at=None) | Q(details_refreshed_at__lt=too_old)).order_by('title')


def refresh_details(title):
    """Ask TMDB for the title's name, year, poster, summary, banner and genres (and a movie's runtime), save them and
    note when.

    A series' runtime is not asked here: it is the typical runtime of its episodes (`core/episodes.py`). TMDB is asked
    first, so when it fails (it raises `tmdb.TmdbError`, or `tmdb.TmdbNotFound` when it no longer has the title)
    nothing is saved.
    """
    details = tmdb.get_title(title.kind, title.tmdb_id)
    fields = ['title', 'year', 'poster_url', 'backdrop_url', 'overview', 'genres']
    if title.kind == 'movie':
        fields.append('runtime')
    for field in fields:
        setattr(title, field, details[field])
    title.details_refreshed_at = timezone.now()
    title.save(update_fields=[*fields, 'details_refreshed_at'])
