"""Ratings on lists, and a nudge to rate (card #118).

My stars show on the tiles of my lists (Movies → To Watch and History, the four Series tabs), and nothing shows for a
title without stars. Right after a movie is marked as watched, or the last aired episode of a series, the page offers
the rating form ("How was it?") with "Not now". A title that already has stars is never asked, and "Not now" saves
nothing. The offer itself changes no data: only its Save does, which is the rating box's own Save."""

import datetime
import re

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import (
    DroppedSeries,
    Episode,
    Profile,
    Rating,
    Title,
    ToWatchItem,
    Watch,
)

MOVIE_PAGE = '/movie/603/'
SERIES_PAGE = '/series/1399/'
HTMX = {'HTTP_HX_REQUEST': 'true'}

# The fixed "now" for every test here: 1 November 2026 in the evening, so "today" is 1 November in Lisbon.
NOW = datetime.datetime(2026, 11, 1, 20, 0, tzinfo=datetime.UTC)
AIRED = datetime.date(2026, 10, 1)
NOT_AIRED = datetime.date(2026, 12, 1)


@pytest.fixture(autouse=True)
def tmdb_key(settings):
    settings.TMDB_API_KEY = 'made-up-secret-key'


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False):
        yield


def make_client(name):
    """A browser logged in as a new account (with a time zone chosen, so no redirect to Profile)."""
    user = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client()
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def me(db):
    return make_client('made-up-user')


@pytest.fixture
def movie(db):
    """A movie already saved with its length and genres, so its page never asks TMDB (the tests never call it)."""
    return Title.objects.create(
        kind='movie', tmdb_id=603, title='Made-up Movie', year='1999', runtime=136, genres=[{'id': 18, 'name': 'Drama'}]
    )


@pytest.fixture
def series(db):
    """A series already saved with fresh episodes: two aired in season 1, one still to come, and an aired special."""
    show = Title.objects.create(
        kind='series', tmdb_id=1399, title='Made-up Series', status='Ended', episodes_refreshed_at=NOW
    )
    for tmdb_id, season, number, air_date in (
        (7001, 1, 1, AIRED),
        (7002, 1, 2, AIRED),
        (7003, 1, 3, NOT_AIRED),
        (7000, 0, 1, AIRED),
    ):
        Episode.objects.create(
            title=show, tmdb_id=tmdb_id, season_number=season, episode_number=number, air_date=air_date
        )
    return show


def episode(tmdb_id):
    return Episode.objects.get(tmdb_id=tmdb_id)


def rate(user, title, stars=None, note=''):
    return Rating.objects.create(user=user, title=title, stars=stars, note=note)


def watch(user, title, tmdb_episode=None):
    return Watch.objects.create(
        user=user, title=title, episode=episode(tmdb_episode) if tmdb_episode else None, watched_on=AIRED
    )


def tile_stars(html):
    """The stars line of each tile on a list page, in order."""
    return re.findall(r'<small class="tile-stars"><span aria-hidden="true">([★☆]+)</span>', html)


def mark_movie(client, **extra):
    return client.post(
        '/watched/add/',
        {'kind': 'movie', 'tmdb_id': 603, 'watched_on': '2026-11-01', 'next': MOVIE_PAGE, **extra},
        follow=True,
    )


def mark_episode(client, tmdb_id, headers=HTMX, **extra):
    data = {'episode_id': episode(tmdb_id).id, 'next': f'{SERIES_PAGE}?season=1', **extra}
    return client.post('/watched/episode/add/', data, **headers)


def offered(html):
    return 'How was it?' in html and 'class="rate-offer"' in html


def snapshot():
    """Everything the offer could touch, to check that showing it or pressing "Not now" saves nothing."""
    return (
        list(Rating.objects.values_list('user', 'title', 'stars', 'note')),
        list(Watch.objects.values_list('id', flat=True)),
        list(ToWatchItem.objects.values_list('id', 'removed_at')),
    )


# Stars on the tiles of my lists.


def test_a_rated_movie_shows_its_stars_on_the_to_watch_list_and_an_unrated_one_shows_nothing(me, movie):
    other = Title.objects.create(kind='movie', tmdb_id=604, title='Unrated Movie')
    ToWatchItem.objects.create(user=me.user, title=movie)
    ToWatchItem.objects.create(user=me.user, title=other)
    rate(me.user, movie, stars=4)

    html = me.get('/movies/').content.decode()

    assert html.count('class="tile"') == 2
    assert tile_stars(html) == ['★★★★☆']
    # Screen readers hear the score in words, as on the title's page.
    assert 'Your rating: 4 of 5' in html


def test_a_rated_movie_shows_its_stars_in_history(me, movie):
    watch(me.user, movie)
    rate(me.user, movie, stars=2)

    assert tile_stars(me.get('/movies/history/').content.decode()) == ['★★☆☆☆']


def test_an_unrated_movie_in_history_shows_no_stars(me, movie):
    watch(me.user, movie)

    html = me.get('/movies/history/').content.decode()
    assert 'Made-up Movie' in html
    assert tile_stars(html) == []


def test_a_rated_series_shows_its_stars_on_the_series_to_watch_list(me, series):
    ToWatchItem.objects.create(user=me.user, title=series)
    rate(me.user, series, stars=5)

    assert tile_stars(me.get('/series/').content.decode()) == ['★★★★★']


def test_a_rated_series_shows_its_stars_under_watching(me, series):
    watch(me.user, series, 7001)
    rate(me.user, series, stars=3)

    assert tile_stars(me.get('/series/watching/').content.decode()) == ['★★★☆☆']


def test_a_rated_series_shows_its_stars_under_finished(me, series):
    watch(me.user, series, 7001)
    watch(me.user, series, 7002)
    rate(me.user, series, stars=1)

    assert tile_stars(me.get('/series/finished/').content.decode()) == ['★☆☆☆☆']


def test_a_rated_series_shows_its_stars_under_dropped(me, series):
    watch(me.user, series, 7001)
    DroppedSeries.objects.create(user=me.user, title=series)
    rate(me.user, series, stars=2)

    assert tile_stars(me.get('/series/dropped/').content.decode()) == ['★★☆☆☆']


def test_a_note_without_stars_shows_nothing_on_the_tile(me, movie):
    ToWatchItem.objects.create(user=me.user, title=movie)
    rate(me.user, movie, note='Made-up note.')

    html = me.get('/movies/').content.decode()
    assert tile_stars(html) == []
    assert 'Made-up note.' not in html


def test_another_accounts_stars_never_show_on_my_tiles(me, movie):
    ToWatchItem.objects.create(user=me.user, title=movie)
    rate(make_client('someone-else').user, movie, stars=5)

    assert tile_stars(me.get('/movies/').content.decode()) == []


# The offer after marking a movie as watched.


def test_marking_an_unrated_movie_offers_to_rate_it_under_the_button(me, movie):
    html = mark_movie(me).content.decode()

    assert offered(html)
    # Under the button: after "Mark as watched"'s form, before the list of watches.
    assert html.index('class="watched-form"') < html.index('class="rate-offer"') < html.index('class="watch-list"')
    # It is the rating form (it saves through the rating box's own Save), and "Not now" leads back to the page.
    offer = html[html.index('class="rate-offer"') :]
    assert 'action="/rating/save/"' in offer
    assert f'href="{MOVIE_PAGE}"' in offer and 'Not now' in offer


def test_the_offer_shows_once_only(me, movie):
    mark_movie(me)

    assert not offered(me.get(MOVIE_PAGE).content.decode())


def test_not_now_saves_nothing(me, movie):
    mark_movie(me)
    before = snapshot()

    # "Not now" is a link to the page itself (with JavaScript it only takes the offer off the page).
    html = me.get(MOVIE_PAGE).content.decode()

    assert not offered(html)
    assert snapshot() == before
    assert not Rating.objects.exists()


def test_saving_from_the_offer_saves_the_stars_and_the_tile_shows_them(me, movie):
    mark_movie(me)

    me.post('/rating/save/', {'kind': 'movie', 'tmdb_id': 603, 'stars': '4', 'note': '', 'next': MOVIE_PAGE})

    assert Rating.objects.get(user=me.user, title=movie).stars == 4
    assert tile_stars(me.get('/movies/history/').content.decode()) == ['★★★★☆']


def test_a_movie_that_already_has_stars_is_not_asked_neither_on_marking_nor_on_watch_again(me, movie):
    rate(me.user, movie, stars=3)

    assert not offered(mark_movie(me).content.decode())
    assert not offered(mark_movie(me).content.decode())


def test_watching_again_an_unrated_movie_offers_again(me, movie):
    mark_movie(me)
    me.get(MOVIE_PAGE)  # "Not now"

    assert offered(mark_movie(me).content.decode())


def test_a_movie_with_only_a_note_is_offered_with_its_note_filled_in(me, movie):
    rate(me.user, movie, note='Made-up note.')

    html = mark_movie(me).content.decode()

    assert offered(html)
    offer = html[html.index('class="rate-offer"') :]
    assert 'Made-up note.</textarea>' in offer


def test_the_offer_for_one_movie_never_shows_on_another_title(me, movie):
    Title.objects.create(kind='movie', tmdb_id=604, title='Other Movie', runtime=90, genres=[{'id': 18, 'name': 'Drama'}])
    me.post('/watched/add/', {'kind': 'movie', 'tmdb_id': 603, 'watched_on': '2026-11-01', 'next': '/movies/history/'})

    assert not offered(me.get('/movie/604/').content.decode())


# The offer after the last aired episode of a series.


def test_marking_an_episode_that_leaves_others_unwatched_offers_nothing(me, series):
    html = mark_episode(me, 7001).content.decode()

    assert 'Mark episode 1 as not watched' in html
    assert 'rate-offer' not in html


def test_marking_the_last_aired_episode_offers_to_rate_the_series_in_a_pop_up(me, series):
    mark_episode(me, 7001)

    html = mark_episode(me, 7002).content.decode()

    # The row comes back as usual, and the pop-up is put in its place on the page (htmx's out-of-band swap).
    assert 'Mark episode 2 as not watched' in html
    assert '<div id="rate-offer" hx-swap-oob="true">' in html
    assert '<dialog open class="rate-offer"' in html and 'How was it?' in html
    assert "You've watched every episode of Made-up Series so far." in html
    # Its Save comes back to the season, still open.
    assert f'value="{SERIES_PAGE}?season=1"' in html
    # The episode still to come and the special do not have to be watched for it.


def test_marking_a_whole_season_that_finishes_the_series_offers_to_rate_it(me, series):
    response = me.post('/watched/season/add/', {'tmdb_id': 1399, 'season': 1}, **HTMX)

    assert offered(response.content.decode())


def test_yes_on_the_earlier_episodes_question_that_finishes_the_series_offers_to_rate_it(me, series):
    response = me.post('/watched/up-to/add/', {'episode_id': episode(7002).id}, **HTMX)

    assert Watch.objects.filter(user=me.user).count() == 2
    assert offered(response.content.decode())


def test_a_series_that_already_has_stars_is_not_asked(me, series):
    rate(me.user, series, stars=4)
    mark_episode(me, 7001)

    assert 'rate-offer' not in mark_episode(me, 7002).content.decode()


def test_watching_an_episode_again_on_a_finished_series_offers_nothing(me, series):
    watch(me.user, series, 7001)
    watch(me.user, series, 7002)

    html = mark_episode(me, 7002).content.decode()

    assert Watch.objects.filter(user=me.user, episode=episode(7002)).count() == 2
    assert 'rate-offer' not in html


def test_marking_a_special_after_the_seasons_are_watched_offers_nothing(me, series):
    watch(me.user, series, 7001)
    watch(me.user, series, 7002)

    assert 'rate-offer' not in mark_episode(me, 7000).content.decode()


def test_the_check_on_home_never_offers(me, series):
    watch(me.user, series, 7001)

    response = mark_episode(me, 7002, up_next='1')

    assert Watch.objects.filter(user=me.user, episode=episode(7002)).exists()
    assert 'rate-offer' not in response.content.decode()
    assert not offered(me.get(SERIES_PAGE).content.decode())


def test_without_javascript_the_series_page_shows_the_offer_once_after_the_redirect(me, series):
    watch(me.user, series, 7001)

    response = mark_episode(me, 7002, headers={})
    assert response.status_code == 302

    first = me.get(response.url).content.decode()
    assert '<dialog open class="rate-offer"' in first
    assert not offered(me.get(SERIES_PAGE).content.decode())


def test_not_now_on_a_series_saves_nothing(me, series):
    watch(me.user, series, 7001)
    mark_episode(me, 7002, headers={})
    before = snapshot()

    me.get(SERIES_PAGE)  # "Not now" without JavaScript; with it, nothing is even asked from the server

    assert snapshot() == before
    assert not Rating.objects.exists()


def test_taking_back_the_last_episode_and_marking_it_again_offers_again(me, series):
    watch(me.user, series, 7001)
    mark_episode(me, 7002)
    last = Watch.objects.get(user=me.user, episode=episode(7002))

    me.post('/watched/remove/', {'watch_id': last.id, 'episode_id': episode(7002).id}, **HTMX)
    assert not Watch.objects.filter(id=last.id).exists()

    assert offered(mark_episode(me, 7002).content.decode())
