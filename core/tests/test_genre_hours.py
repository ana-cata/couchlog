"""Hours watched per genre on Profile (card #126): counted like Time spent, a watch counts fully in each genre of its
title, movies and series apart, most first, the top 8 and then Other (which also holds titles with no genre).

Nothing is stored for the charts, so there is nothing to undo on them: taking a watch back takes its hours off."""

import datetime
import os
import re

import pytest
import time_machine
from django.contrib.auth.models import User
from django.test import Client

from core.models import Episode, Profile, Title, Watch
from core.time_spent import genre_chart, minutes_by_genre, short

# The fixed "now" for every test here: 8 pm UTC on 23 Nov 2026.
NOW = datetime.datetime(2026, 11, 23, 20, 0, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def clock():
    with time_machine.travel(NOW, tick=False) as traveller:
        yield traveller


def make_client(name):
    user = User.objects.create_user(username=name, password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    client = Client()
    client.force_login(user)
    client.user = user
    return client


@pytest.fixture
def me(db):
    return make_client('made-up-user')


_next_id = iter(range(1000, 100000))


def genres(*names):
    return [{'id': index, 'name': name} for index, name in enumerate(names)]


def movie(runtime, *names):
    return Title.objects.create(
        kind='movie', tmdb_id=next(_next_id), title=f'Made-up movie {runtime}', runtime=runtime, genres=genres(*names)
    )


def series(typical_runtime, *names):
    return Title.objects.create(
        kind='series',
        tmdb_id=next(_next_id),
        title='Made-up series',
        runtime=typical_runtime,
        genres=genres(*names),
    )


def episode(show, runtime, number=1):
    return Episode.objects.create(
        title=show, tmdb_id=next(_next_id), season_number=1, episode_number=number, runtime=runtime
    )


def watch(user, title, an_episode=None):
    return Watch.objects.create(user=user, title=title, episode=an_episode, watched_on=datetime.date(2026, 11, 1))


def movies_of(user):
    return dict(minutes_by_genre(user)[0])


def series_of(user):
    return dict(minutes_by_genre(user)[1])


def profile_html(client):
    return client.get('/profile/').content.decode()


def chart_rows(html, heading):
    """The (genre, time) rows of the chart under this heading on the Profile page."""
    section = re.search(rf'<h3>{heading}</h3>(.*?)</section>', html, re.DOTALL).group(1)
    names = re.findall(r'<span class="genre-name">(.*?)</span>', section)
    times = re.findall(r'<span class="genre-time">(.*?)</span>', section)
    return list(zip(names, times, strict=True))


# --- counting ----------------------------------------------------------------------------------


def test_a_watch_counts_fully_in_each_genre_of_its_title(me):
    watch(me.user, movie(120, 'Crime', 'Drama'))

    assert movies_of(me.user) == {'Crime': 120, 'Drama': 120}


def test_a_rewatch_counts_twice(me):
    film = movie(100, 'Drama')
    watch(me.user, film)
    watch(me.user, film)

    assert movies_of(me.user) == {'Drama': 200}


def test_an_episode_with_no_runtime_uses_the_typical_runtime(me):
    show = series(45, 'Comedy')
    watch(me.user, show, episode(show, 30, 1))
    watch(me.user, show, episode(show, None, 2))

    assert series_of(me.user) == {'Comedy': 75}


def test_the_genres_are_sorted_from_most_to_least(me):
    watch(me.user, movie(60, 'Horror'))
    watch(me.user, movie(180, 'Drama'))
    watch(me.user, movie(90, 'Crime'))
    watch(me.user, movie(90, 'Action'))  # a tie goes in the order of the alphabet

    assert [name for name, _ in minutes_by_genre(me.user)[0]] == ['Drama', 'Action', 'Crime', 'Horror']


def test_movies_and_series_are_counted_apart(me):
    watch(me.user, movie(100, 'Drama'))
    show = series(40, 'Comedy')
    watch(me.user, show, episode(show, 50))

    movies, shows = minutes_by_genre(me.user)
    assert movies == [('Drama', 100)]
    assert shows == [('Comedy', 50)]


def test_another_accounts_watches_never_count(me):
    friend = make_client('made-up-friend')
    watch(friend.user, movie(100, 'Drama'))
    show = series(40, 'Comedy')
    watch(friend.user, show, episode(show, 50))

    assert minutes_by_genre(me.user) == ([], [])


def test_after_the_top_8_the_rest_goes_to_other(me):
    for minutes, name in enumerate('ABCDEFGHIJ', start=1):
        watch(me.user, movie(minutes * 10, f'Genre {name}'))

    ranked = minutes_by_genre(me.user)[0]
    # J (100) down to C (30) are shown; A (10) and B (20) are added up as Other, which comes last.
    assert [name for name, _ in ranked] == [f'Genre {name}' for name in 'JIHGFEDC'] + ['Other']
    assert ranked[-1] == ('Other', 30)


def test_a_title_with_no_genres_counts_in_other(me):
    watch(me.user, movie(100, 'Drama'))
    watch(me.user, movie(80))
    show = series(40)
    watch(me.user, show, episode(show, 50))

    assert minutes_by_genre(me.user) == ([('Drama', 100), ('Other', 80)], [('Other', 50)])


def test_a_watch_with_no_runtime_at_all_is_left_out(me):
    watch(me.user, movie(None, 'Drama'))
    show = series(None, 'Comedy')
    watch(me.user, show, episode(show, None))

    assert minutes_by_genre(me.user) == ([], [])


def test_taking_a_watch_back_takes_its_hours_off(me):
    film = movie(100, 'Drama')
    watch(me.user, film)
    before = minutes_by_genre(me.user)
    me.post('/watched/add/', {'kind': 'movie', 'tmdb_id': film.tmdb_id, 'watched_on': '2026-11-20'})
    assert movies_of(me.user) == {'Drama': 200}

    second = Watch.objects.filter(user=me.user).order_by('id').last()
    me.post('/watched/remove/', {'watch_id': second.id})

    assert minutes_by_genre(me.user) == before


# --- the words and the bars ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ('minutes', 'words'),
    [(45, '45 min'), (59, '59 min'), (60, '1 h'), (89, '1 h'), (90, '2 h'), (2520, '42 h')],
)
def test_hours_are_written_short(minutes, words):
    assert short(minutes) == words


def test_the_longest_bar_is_full_and_the_others_are_a_share_of_it():
    rows = genre_chart([('Drama', 600), ('Crime', 300), ('Other', 1)])

    assert [row['percent'] for row in rows] == [100, 50, 1]  # a tiny one still shows a sliver
    assert [row['time'] for row in rows] == ['10 h', '5 h', '1 min']


# --- the Profile page ----------------------------------------------------------------------------


def test_profile_shows_both_charts_under_time_spent(me):
    watch(me.user, movie(120, 'Crime', 'Drama'))
    watch(me.user, movie(45, 'Drama'))
    show = series(40, 'Comedy')
    watch(me.user, show, episode(show, 30))

    html = profile_html(me)

    assert html.index('Time spent watching') < html.index('Movies by genre') < html.index('Series by genre')
    assert html.index('Series by genre') < html.index('My tags')
    assert chart_rows(html, 'Movies by genre') == [('Drama', '3 h'), ('Crime', '2 h')]
    assert chart_rows(html, 'Series by genre') == [('Comedy', '30 min')]
    assert 'the bars add up to more than the time above' in html


def test_empty_charts_say_what_to_do(me):
    html = profile_html(me)

    assert 'Watch a movie to see your genres here.' in html
    assert 'Watch a series to see your genres here.' in html
    assert chart_rows(html, 'Movies by genre') == []


def test_the_charts_do_not_disturb_the_time_spent_list(me):
    """The Time spent list is the only <dd> on the page; the charts use their own list."""
    watch(me.user, movie(100, 'Drama'))

    html = profile_html(me)

    assert len(re.findall(r'<dd>', html)) == 3


# --- on a phone, in a real browser -----------------------------------------------------------------

# The browser's driver runs inside an event loop, and Django refuses database calls from there unless told it is fine.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')


def test_the_charts_fit_a_phone_screen(live_server, browser):
    user = User.objects.create_user(username='made-up-phone', password='made-up-password')
    Profile.objects.create(user=user, timezone='Europe/Lisbon')
    watch(user, movie(6000, 'Action & Adventure', 'Science Fiction', 'Documentary'))
    watch(user, movie(45, 'Drama'))
    show = series(40, 'Sci-Fi & Fantasy')
    watch(user, show, episode(show, 50))
    context = browser.new_context(viewport={'width': 360, 'height': 800}, has_touch=True, is_mobile=True)
    page = context.new_page()
    page.goto(live_server.url)
    page.get_by_label('Username').fill('made-up-phone')
    page.get_by_label('Password').fill('made-up-password')
    page.get_by_role('button', name='Log in').click()
    page.wait_for_url(live_server.url + '/')

    page.goto(live_server.url + '/profile/')

    bars = page.locator('.genre-chart').first.locator('.genre-bar span')
    widths = [bars.nth(index).bounding_box()['width'] for index in range(bars.count())]
    assert widths[0] > 30  # the longest bar is really there on a narrow screen
    assert widths[-1] < widths[0]  # Drama's 45 minutes are far shorter than 100 hours
    starts = {round(box['x']) for box in (bars.nth(i).bounding_box() for i in range(bars.count()))}
    assert len(starts) == 1  # every bar starts at the same place
    assert page.locator('.genre-time').first.inner_text() == '100 h'
    # Nothing goes off the screen sideways.
    assert page.evaluate('document.documentElement.scrollWidth') <= 360
    context.close()
