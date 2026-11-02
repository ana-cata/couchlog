import math
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core import serializers
from django.core.exceptions import BadRequest
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from . import releases, tmdb, tvmaze
from .episodes import (
    dropped_series,
    dropped_tab,
    mark_episodes,
    refresh_episodes,
    rewatch_episodes,
    series_tabs,
    skipped_episodes,
    started_series,
    take_back_rewatch,
    unmark_episodes,
    up_next,
)
from .forms import NOTE_MAX_LENGTH, STAR_CHOICES, RatingForm, TimeZoneForm, WatchedForm
from .models import (
    DroppedSeries,
    Episode,
    Profile,
    Rating,
    RemovedSeries,
    Title,
    ToWatchItem,
    Watch,
)
from .releases import news, refresh_movie, refresh_upcoming, upcoming
from .suggestions import suggest
from .time_spent import describe, minutes_watched
from .title_line import title_line

# How old our saved episodes may get before opening a series page asks TMDB again.
EPISODES_REFRESH_AFTER = timedelta(days=1)

# How long after removing a title from To Watch it can still be undone. The screen says the
# number of seconds, which comes from here. After that, the way back is adding the title again.
UNDO_WINDOW = timedelta(seconds=10)

# The section of the app each kind of title lives in. It is also the name of that section's
# To Watch address, so a button with no page to come back to returns to the right one.
SECTION_OF_KIND = {'movie': 'movies', 'series': 'series'}


def home(request):
    """Home: News (what comes out in the next days) above Up Next. Both are worked out from what is saved."""
    zone = _zone(request)
    today = timezone.now().astimezone(zone).date()
    context = {
        'news': news(request.user, today, zone),
        'news_days': releases.NEWS_DAYS,
        'entries': up_next(request.user, today),
    }
    return render(request, 'core/home.html', context)


def calendar(request):
    """The upcoming releases of the series being watched and of the To Watch list, from what is saved. TMDB is not asked."""
    zone = _zone(request)
    today = timezone.now().astimezone(zone).date()
    return render(request, 'core/calendar.html', {'days': upcoming(request.user, today, zone)})


# The same address answers with a whole page or, for the live results, only the list.
# Telling caches the answer depends on this header stops the browser mixing them up.
@vary_on_headers('HX-Request')
def search(request):
    query = request.GET.get('q', '').strip()
    results, error = [], ''
    if query:
        try:
            results = tmdb.search(query)
        except tmdb.TmdbError as problem:
            error = str(problem)

    # Each result knows whether it is already on this account's To Watch list.
    on_list = {
        (item.title.kind, item.title.tmdb_id)
        for item in ToWatchItem.objects.filter(user=request.user, removed_at=None).select_related('title')
    }
    # A series I dropped says so instead of offering the To Watch button.
    dropped = set(DroppedSeries.objects.filter(user=request.user).values_list('title__tmdb_id', flat=True))
    # A series I started is under Watching or Finished: no To Watch button for it either.
    started = set(started_series(request.user).values_list('title__tmdb_id', flat=True))
    for result in results:
        result['on_list'] = (result['kind'], result['tmdb_id']) in on_list
        result['dropped'] = result['kind'] == 'series' and result['tmdb_id'] in dropped
        result['started'] = result['kind'] == 'series' and result['tmdb_id'] in started

    # htmx also asks for the whole page when it restores a page from its history.
    live_update = request.headers.get('HX-Request') and not request.headers.get('HX-History-Restore-Request')
    template = 'core/_search_results.html' if live_update else 'core/search.html'
    context = {'query': query, 'results': results, 'error': error, 'next': request.get_full_path()}
    return render(request, template, context)


# Not cached, so the list is picked again each time (a title just added to To Watch is then left out).
@never_cache
def search_suggestions(request):
    """The suggested movies and series under an empty search box (htmx loads this after the page, so a slow TMDB never
    holds up the box). Movies and series are asked separately: if TMDB fails for one, the other still shows."""
    blocks = []
    for kind, heading in (('movie', 'Suggested movies'), ('series', 'Suggested series')):
        block = {'heading': heading, 'tiles': [], 'spares': [], 'error': ''}
        try:
            block['tiles'], block['spares'] = suggest(request.user, kind)
        except tmdb.TmdbError as problem:
            block['error'] = str(problem)
        blocks.append(block)
    # `next` is where a button without htmx would come back to. The tiles are only ever on this page with htmx.
    return render(request, 'core/_suggestions.html', {'blocks': blocks, 'next': reverse('search')})


def title(request, kind, tmdb_id):
    if kind == 'series':
        return _series_page(request, tmdb_id)
    try:
        item = tmdb.get_title(kind, tmdb_id)
    except tmdb.TmdbNotFound:
        raise Http404 from None
    except tmdb.TmdbError as problem:
        return render(request, 'core/title.html', {'error': str(problem)})
    on_list = _my_item(request, kind, tmdb_id).filter(removed_at=None).exists()
    context = {
        'item': item,
        'line': title_line(kind, item['year'], '', item['runtime'], item['genres']),
        'on_list': on_list,
        'next': request.get_full_path(),
        **_rating_box(request, kind, tmdb_id),
    }
    if kind == 'movie':
        # Series are marked episode by episode, so only movies get this section. Every watch of the film is
        # listed, newest day first like History.
        context['watches'] = list(
            Watch.objects.filter(user=request.user, title__kind=kind, title__tmdb_id=tmdb_id).order_by(
                F('watched_on').desc(nulls_last=True), '-created_at', '-id'
            )
        )
        context['today'] = _today(request)
    return render(request, 'core/title.html', context)


def _series_page(request, tmdb_id):
    """A series with its seasons and episodes, from our own saved copy (design rule 6)."""
    try:
        series = _saved_title('series', tmdb_id)
    except tmdb.TmdbNotFound:
        raise Http404 from None
    except tmdb.TmdbError as problem:
        return render(request, 'core/title.html', {'error': str(problem)})

    # Saved episodes are refreshed when they are over a day old. If TMDB does not answer, the page
    # still shows what was saved earlier, with a note.
    notice = ''
    saved_at = series.episodes_refreshed_at
    if saved_at is None or saved_at < timezone.now() - EPISODES_REFRESH_AFTER:
        try:
            refresh_episodes(series)
        except tmdb.TmdbError as problem:
            notice = f'{problem} Showing the episodes saved earlier.' if saved_at else str(problem)

    today = _today(request)
    watches = _watches_by_episode(request.user, title=series, episode__isnull=False)
    by_season = {}
    for episode in series.episodes.order_by('season_number', 'episode_number', 'id'):
        episode.watch, episode.watch_count = watches.get(episode.id, (None, 0))
        episode.aired = _has_aired(episode, today)
        by_season.setdefault(episode.season_number, []).append(episode)
    # Specials (season 0) last.
    numbers = sorted(by_season, key=lambda number: (number == 0, number))
    seasons = [_season_info(number, by_season[number]) for number in numbers]
    try:
        open_season = int(request.GET['season'])
    except (KeyError, ValueError):
        open_season = numbers[0] if numbers else None

    on_list = _my_item(request, 'series', tmdb_id).filter(removed_at=None).exists()
    dropped = DroppedSeries.objects.filter(user=request.user, title=series).exists()
    asked = series.episodes.filter(id=request.session.pop('ask_earlier', 0)).first()
    context = {
        'item': series,
        'line': title_line('series', series.year, series.status, series.runtime, series.genres),
        'on_list': on_list,
        'dropped': dropped,
        # "Stop watching" is offered for a series that is in one of my tabs: started or on my To Watch list.
        'can_drop': not dropped and (on_list or bool(watches)),
        # A series I started is under Watching or Finished: there it has no To Watch button. "Remove from all lists"
        # (in the corner) is only for a dropped series: Watching -> Dropped -> Remove from all lists.
        'started': bool(watches),
        'can_remove_all': dropped,
        'watch_total': sum(count for _, count in watches.values()),
        'undo_seconds': _undo_seconds(),
        'next': request.get_full_path(),
        **_rating_box(request, 'series', tmdb_id),
        'notice': notice,
        'seasons': seasons,
        'open_season': open_season,
        'progress': _series_progress(request, series),
        # Without htmx, the question after a mark that skips episodes ("did you watch the earlier episodes too?")
        # comes back here and is shown once. It is worked out again here, so a page that is out of date asks nothing.
        'ask': _question(request, asked, today) if asked else None,
    }
    return render(request, 'core/title.html', context)


def _zone(request):
    """The account's own time zone."""
    name = Profile.objects.filter(user=request.user).values_list('timezone', flat=True).first()
    return ZoneInfo(name or 'UTC')


def _today(request):
    """Today's date in the account's own time zone. The server's time zone does not matter."""
    return timezone.now().astimezone(_zone(request)).date()


def _saved_title(kind, tmdb_id):
    """Our own saved copy of a title. The first time anyone needs it, TMDB is asked and it is saved."""
    title = Title.objects.filter(kind=kind, tmdb_id=tmdb_id).first()
    if title is None:
        details = tmdb.get_title(kind, tmdb_id)
        keys = ('title', 'year', 'poster_url', 'backdrop_url', 'overview', 'runtime', 'genres')
        saved = {key: details[key] for key in keys}
        title, _ = Title.objects.get_or_create(kind=kind, tmdb_id=tmdb_id, defaults=saved)
    return title


def _undo_seconds():
    return int(UNDO_WINDOW.total_seconds())


def _recently_removed(request, kind):
    """What the "Recently removed" block of one section shows: only titles of that kind still inside the undo window.

    A title that left because it was marked as watched is not here: its undo is "Mark as not watched". A series
    taken off all lists is here too, with the undo that puts its history back.
    """
    removed = list(
        ToWatchItem.objects.filter(
            user=request.user,
            title__kind=kind,
            removed_at__gte=timezone.now() - UNDO_WINDOW,
            removed_by_watch=None,
        )
        .select_related('title')
        .order_by('-removed_at')
    )
    if kind == 'series':
        _forget_expired_removals(request.user)
        removed += RemovedSeries.objects.filter(user=request.user).select_related('title')
        removed.sort(key=lambda item: item.removed_at, reverse=True)
    context = {
        'removed': removed,
        'kind': kind,
        'undo_seconds': _undo_seconds(),
        'next': reverse(SECTION_OF_KIND[kind]),
    }
    if removed:
        # The oldest one runs out of time first. The block asks the server again just after
        # that, so a page that stays open empties the list by itself.
        runs_out = min(item.removed_at for item in removed) + UNDO_WINDOW
        context['recheck_seconds'] = max(1, math.ceil((runs_out - timezone.now()).total_seconds()) + 1)
    return context


def _to_watch_screen(request, kind):
    items = (
        ToWatchItem.objects.filter(user=request.user, title__kind=kind, removed_at=None)
        .select_related('title')
        .order_by('-added_at')
    )
    if kind == 'series':
        # A series with an episode marked is being watched: it is under Watching now, not here.
        # Its entry on the list is untouched, so un-marking the episode brings it back here.
        # A dropped series is under Dropped only, and bringing it back returns it to the list the same way.
        items = items.exclude(title__in=started_series(request.user)).exclude(title__in=dropped_series(request.user))
    context = {'items': items, 'section': SECTION_OF_KIND[kind], **_recently_removed(request, kind)}
    return render(request, 'core/to_watch.html', context)


def movies(request):
    return _to_watch_screen(request, 'movie')


def series(request):
    return _to_watch_screen(request, 'series')


def _series_tab(request, tab):
    if tab == 'dropped':
        titles = dropped_tab(request.user)
    else:
        watching, finished = series_tabs(request.user, _today(request))
        titles = watching if tab == 'watching' else finished
    return render(request, 'core/series_tab.html', {'titles': titles, 'section': 'series', 'tab': tab})


def series_watching(request):
    return _series_tab(request, 'watching')


def series_finished(request):
    return _series_tab(request, 'finished')


def series_dropped(request):
    return _series_tab(request, 'dropped')


def _posted_series(request):
    """The saved series a button on its page was pressed for."""
    kind, tmdb_id = _posted_title(request)
    if kind != 'series':
        raise BadRequest
    return get_object_or_404(Title, kind='series', tmdb_id=tmdb_id)


@require_POST
def series_drop(request):
    """Stop watching: move the series to Dropped. Nothing else is touched, so bringing it back is the undo."""
    series = _posted_series(request)
    _, created = DroppedSeries.objects.get_or_create(user=request.user, title=series)
    if created:
        text = f'“{series.title}” is under Series → Dropped now. Bring it back any time.'
    else:
        text = f'“{series.title}” is already in your Dropped list.'
    return _redirect_back(request, text, True, 'series_dropped')


@require_POST
def series_bring_back(request):
    """Bring a dropped series back, any time later. It returns to the tab its watches and TMDB's status give it."""
    series = _posted_series(request)
    deleted, _ = DroppedSeries.objects.filter(user=request.user, title=series).delete()
    if not deleted:
        return _redirect_back(request, f'“{series.title}” is not in your Dropped list.', False, 'series')
    return _redirect_back(request, f'Brought “{series.title}” back. It is in its own tab again.', True, 'series')


# What "Remove from all lists" deletes, in the order Undo writes it back (a To Watch entry points at a watch).
REMOVED_WITH_A_SERIES = (Watch, ToWatchItem, DroppedSeries, Rating)


def _series_rows(user, series):
    """Every row this account has for the series that "Remove from all lists" deletes, as one list."""
    return [row for model in REMOVED_WITH_A_SERIES for row in model.objects.filter(user=user, title=series)]


def _forget_expired_removals(user):
    """Delete the copies whose Undo window is over: from then on the history is gone for good."""
    RemovedSeries.objects.filter(user=user, removed_at__lt=timezone.now() - UNDO_WINDOW).delete()


@require_POST
def series_remove_all(request):
    """Take a series off every list (To Watch, Watching, Finished, Dropped) and delete its history, rating and note.

    The deleted rows are kept in a copy for the Undo (10 seconds). The button asks for confirmation in the browser.
    """
    series = _posted_series(request)
    _forget_expired_removals(request.user)
    rows = _series_rows(request.user, series)
    if not rows:
        return _redirect_back(request, f'“{series.title}” is not on any of your lists.', False, 'series')
    with transaction.atomic():
        RemovedSeries.objects.update_or_create(
            user=request.user,
            title=series,
            defaults={'rows': serializers.serialize('json', rows), 'removed_at': timezone.now()},
        )
        for model in reversed(REMOVED_WITH_A_SERIES):
            model.objects.filter(user=request.user, title=series).delete()
    text = f'Removed “{series.title}” from all your lists, with its history.'
    return _redirect_back(request, text, True, 'series')


@require_POST
def series_remove_all_undo(request):
    """Put back what "Remove from all lists" deleted, if it was a moment ago and the series is still untouched."""
    series = _posted_series(request)
    copy = RemovedSeries.objects.filter(user=request.user, title=series).first()
    if copy is None:
        return _redirect_back(request, 'There is nothing to undo for that series.', False, 'series')
    if copy.removed_at < timezone.now() - UNDO_WINDOW:
        copy.delete()
        text = f'It is too late to undo removing “{series.title}”. You can add it again from Search.'
        return _redirect_back(request, text, False, 'series')
    if _series_rows(request.user, series):
        # Putting the old rows back on top of new ones would overwrite what happened since.
        text = f'“{series.title}” was changed since it was removed, so it was not put back.'
        return _redirect_back(request, text, False, 'series')
    with transaction.atomic():
        for row in serializers.deserialize('json', copy.rows):
            row.save()
        copy.delete()
    return _redirect_back(request, f'Put “{series.title}” back on all your lists, with its history.', True, 'series')


# Only the "Recently removed" block of one section, which its To Watch screen asks for when time runs out.
@never_cache
def to_watch_removed(request):
    kind = request.GET.get('kind')
    if kind not in SECTION_OF_KIND:
        raise BadRequest
    return render(request, 'core/_recently_removed.html', _recently_removed(request, kind))


def _posted_title(request):
    """The kind and TMDB id of the title a button was pressed for."""
    kind = request.POST.get('kind')
    try:
        tmdb_id = int(request.POST.get('tmdb_id', ''))
    except ValueError:
        raise BadRequest from None
    if kind not in ('movie', 'series') or tmdb_id < 1:
        raise BadRequest
    return kind, tmdb_id


def _my_item(request, kind, tmdb_id):
    """This account's To Watch entry for a title, whether or not it was removed."""
    return ToWatchItem.objects.select_related('title').filter(
        user=request.user, title__kind=kind, title__tmdb_id=tmdb_id
    )


def _answer(request, kind, tmdb_id, on_list, text, ok=True, collect=False):
    """Reply to a button press.

    The search page uses htmx, which swaps in just the button in its new state. Without
    htmx the reply is a redirect back to the page the button was on, with a message (unless
    `text` is empty: then there is nothing to say). With `collect`, the button also asks the
    server to collect the title's dates as soon as it is on the page (`to_watch_collect`).
    """
    if request.headers.get('HX-Request'):
        tile = {'kind': kind, 'tmdb_id': tmdb_id}
        context = {'tile': tile, 'on_list': on_list, 'next': request.POST.get('next', ''), 'live': True}
        # A tile's button sends `corner`, so the answer is the small round button again, not the one with words.
        if request.POST.get('corner'):
            context['corner'] = True
        if collect:
            context['collect'] = True
        if not ok:
            context['error'] = text
        return render(request, 'core/_to_watch_button.html', context)

    return _redirect_back(request, text, ok, SECTION_OF_KIND[kind])


def _redirect_back(request, text, ok, fallback):
    """Go back to the page a button was on, with a message (unless `text` is empty)."""
    if text:
        (messages.success if ok else messages.error)(request, text)
    next_url = request.POST.get('next', '')
    # Only come back to a page of this site, never to an address someone slipped into the form.
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse(fallback)
    return redirect(next_url)


def _collect_dates(title):
    """Collect the dates the Calendar shows for a title that was just put on a To Watch list.

    A movie's cinema and streaming dates, or a series' episodes (when they were never saved, or are over a day
    old) and then its upcoming episodes from TVmaze. If TMDB or TVmaze does not answer, the title is still on the
    list and the next `refresh_calendar` run collects them.
    """
    try:
        if title.kind == 'movie':
            refresh_movie(title)
        else:
            if title.episodes_refreshed_at is None or title.episodes_refreshed_at < timezone.now() - EPISODES_REFRESH_AFTER:
                refresh_episodes(title)
            refresh_upcoming(title)
    except (tmdb.TmdbError, tvmaze.TvmazeError):
        pass


@require_POST
def to_watch_add(request):
    kind, tmdb_id = _posted_title(request)

    # The details come from TMDB the first time anyone adds a title, then from our own table.
    try:
        title = _saved_title(kind, tmdb_id)
    except tmdb.TmdbNotFound:
        raise Http404 from None
    except tmdb.TmdbError as problem:
        return _answer(request, kind, tmdb_id, False, str(problem), ok=False)

    item, created = ToWatchItem.objects.get_or_create(user=request.user, title=title)
    if item.removed_at:
        # Adding a title again after removing it puts it back as newly added.
        item.removed_at, item.added_at, item.removed_by_watch = None, timezone.now(), None
        item.save(update_fields=['removed_at', 'added_at', 'removed_by_watch'])
    elif not created:
        return _answer(request, kind, tmdb_id, True, f'“{title.title}” is already on your To Watch list.')

    # A movie's dates are one quick call, so they are collected now. A series needs a call per season, which can take
    # seconds: with htmx the series is on the list at once and the button asks for the rest right after
    # (`to_watch_collect`). Without htmx nothing could ask, so the series is collected now, as before.
    later = title.kind == 'series' and bool(request.headers.get('HX-Request'))
    if not later:
        _collect_dates(title)
    return _answer(request, kind, tmdb_id, True, f'Added “{title.title}” to your To Watch list.', collect=later)


@require_POST
def to_watch_collect(request):
    """Collect the dates of a title that was just put on this account's list: what the button asks for right after a
    series is added. Nothing is shown (204: htmx changes nothing).

    A title that is not on the account's list (it was removed in the meantime, or never added) is left alone, so this
    cannot be used to ask TMDB about any title. If TMDB or TVmaze does not answer, `_collect_dates` leaves the title
    on the list and the next `refresh_calendar` run catches up.
    """
    kind, tmdb_id = _posted_title(request)
    item = _my_item(request, kind, tmdb_id).filter(removed_at=None).first()
    if item is not None:
        _collect_dates(item.title)
    return HttpResponse(status=204)


@require_POST
def to_watch_remove(request):
    kind, tmdb_id = _posted_title(request)
    item = _my_item(request, kind, tmdb_id).filter(removed_at=None).first()
    if item is None:
        return _answer(request, kind, tmdb_id, False, 'That title is not on your To Watch list.', ok=False)
    # Only marked as removed, not erased, so Undo can bring it back as it was.
    item.removed_at = timezone.now()
    item.save(update_fields=['removed_at'])
    # No message: the title leaving the list and showing up under "Recently removed" says it.
    return _answer(request, kind, tmdb_id, False, '')


@require_POST
def to_watch_undo(request):
    kind, tmdb_id = _posted_title(request)
    # A title that left because it was watched is brought back by "Mark as not watched", not here.
    item = _my_item(request, kind, tmdb_id).exclude(removed_at=None).filter(removed_by_watch=None).first()
    if item is None:
        return _answer(request, kind, tmdb_id, False, 'There is nothing to undo for that title.', ok=False)
    if item.removed_at < timezone.now() - UNDO_WINDOW:
        text = f'It is too late to undo removing “{item.title.title}”. You can add it again from Search.'
        return _answer(request, kind, tmdb_id, False, text, ok=False)
    # The date added was never touched, so the title returns to its old place in the list.
    item.removed_at = None
    item.save(update_fields=['removed_at'])
    return _answer(request, kind, tmdb_id, True, f'Put “{item.title.title}” back on your To Watch list.')


def _my_rating(request, kind, tmdb_id):
    """This account's rating and note for a title, or None when nothing is saved for it."""
    return Rating.objects.filter(user=request.user, title__kind=kind, title__tmdb_id=tmdb_id).first()


def _rating_box(request, kind, tmdb_id):
    """What the rating box on a title's page shows: this account's saved stars and note."""
    return {'rating': _my_rating(request, kind, tmdb_id), 'star_choices': STAR_CHOICES, 'note_max': NOTE_MAX_LENGTH}


@require_POST
def rating_save(request):
    """Save, change or remove the stars and the note of a title, all in one Save.

    "No rating" removes the stars and an empty note removes the note, each without touching the other; with both
    gone nothing is kept. Saving what is already saved changes nothing. The title does not need to be watched, and if
    it is not saved yet it is saved from TMDB first. There is no Undo button: the page's form is always there to
    put the stars and the note back.
    """
    kind, tmdb_id = _posted_title(request)
    form = RatingForm(request.POST)
    if not form.is_valid():
        problem = ' '.join(error for errors in form.errors.values() for error in errors)
        return _redirect_back(request, problem, False, 'search')
    stars, note = form.cleaned_data['stars'], form.cleaned_data['note']

    rating = _my_rating(request, kind, tmdb_id)
    if (stars, note) == ((rating.stars, rating.note) if rating else (None, '')):
        return _redirect_back(request, 'Nothing changed, so nothing was saved.', True, 'search')

    try:
        title = _saved_title(kind, tmdb_id)
    except tmdb.TmdbNotFound:
        raise Http404 from None
    except tmdb.TmdbError as problem:
        return _redirect_back(request, str(problem), False, 'search')

    said = []
    with transaction.atomic():
        rating, _ = Rating.objects.get_or_create(user=request.user, title=title)
        if stars != rating.stars:
            said.append('rating saved' if stars else 'rating removed')
        if note != rating.note:
            said.append('note saved' if note else 'note removed')
        if stars or note:
            rating.stars, rating.note = stars, note
            rating.save()
        else:
            rating.delete()
    if not said:
        return _redirect_back(request, 'Nothing changed, so nothing was saved.', True, 'search')
    return _redirect_back(request, ' and '.join(said).capitalize() + '.', True, 'search')


def history(request):
    # Newest watch first. Watches with an unknown date go last, newest saved first among themselves.
    # History is the Movies section's tab, so it lists films only.
    watches = (
        Watch.objects.filter(user=request.user, title__kind='movie')
        .select_related('title')
        .order_by(F('watched_on').desc(nulls_last=True), '-created_at', '-id')
    )
    # A film watched again is still one tile, with the date of its latest watch (the first one in that order). All
    # its watches are listed on its own page. The button under the tile takes back the watch the tile shows only,
    # so it says so when the film has others (`times` is how many watches it has).
    shown = {}
    for watch in watches:
        if watch.title_id in shown:
            shown[watch.title_id].times += 1
        else:
            watch.times = 1
            shown[watch.title_id] = watch
    return render(
        request, 'core/history.html', {'watches': list(shown.values()), 'section': 'movies', 'next': reverse('history')}
    )


@require_POST
def watched_add(request):
    kind, tmdb_id = _posted_title(request)
    if kind != 'movie':
        raise BadRequest  # series are marked episode by episode, in a later card

    form = WatchedForm(request.POST, today=_today(request))
    if not form.is_valid():
        problem = ' '.join(error for errors in form.errors.values() for error in errors)
        return _redirect_back(request, problem, False, 'history')

    try:
        title = _saved_title(kind, tmdb_id)
    except tmdb.TmdbNotFound:
        raise Http404 from None
    except tmdb.TmdbError as problem:
        return _redirect_back(request, str(problem), False, 'history')

    # Pressing it for a movie that is already watched is "Watch again": one more watch with its own date.
    again = Watch.objects.filter(user=request.user, title=title).exists()

    with transaction.atomic():
        watch = Watch.objects.create(user=request.user, title=title, watched_on=form.cleaned_data['watched_on'])
        # A watched movie leaves the To Watch list. The watch is remembered on the entry, so
        # un-marking it can put the entry back exactly as it was.
        ToWatchItem.objects.filter(user=request.user, title=title, removed_at=None).update(
            removed_at=timezone.now(), removed_by_watch=watch
        )
    text = f'Added another watch of “{title.title}”.' if again else f'Marked “{title.title}” as watched.'
    return _redirect_back(request, text, True, 'history')


def _posted_episode(request):
    """The episode a button was pressed for."""
    try:
        episode_id = int(request.POST.get('episode_id', ''))
    except ValueError:
        raise BadRequest from None
    return get_object_or_404(Episode.objects.select_related('title'), id=episode_id)


def _has_aired(episode, today):
    return episode.air_date is not None and episode.air_date <= today


def _watches_by_episode(user, **where):
    """This account's watches of episodes, as {episode id: (its latest watch, how many times it was watched)}.

    `where` says which watches to look at. An episode watched again has several; the latest is the one the "−"
    button takes back."""
    found = {}
    for watch in Watch.objects.filter(user=user, **where).order_by('created_at', 'id'):
        _, count = found.get(watch.episode_id, (None, 0))
        found[watch.episode_id] = (watch, count + 1)
    return found


def _with_state(request, episodes):
    """Give each episode what its row needs: this account's latest watch for it and how many it has, and whether
    it has aired."""
    today = _today(request)
    watches = _watches_by_episode(request.user, episode__in=episodes)
    for episode in episodes:
        episode.watch, episode.watch_count = watches.get(episode.id, (None, 0))
        episode.aired = _has_aired(episode, today)
    return episodes


def _series_progress(request, series):
    """The series' bar on its page: how many of its episodes this account has watched, out of every episode we know
    of, aired or not (so a season of 10 with 2 still to come reads "3 of 10"). Specials (season 0) are left out, like
    in the seasons' bars, so the seasons' counts add up to this one. Home and the tabs count only episodes that have
    aired (`progress_by_series` in core/episodes.py) and are not touched."""
    regular = series.episodes.filter(season_number__gt=0)
    watched = Watch.objects.filter(user=request.user, episode__in=regular).values('episode').distinct().count()
    return {'watched': watched, 'total': regular.count()}


def _season_info(number, episodes):
    """What a season needs on the page, from its episodes (each with its watch and `aired` already set)."""
    aired = [episode for episode in episodes if episode.aired]
    # The season's count is the episodes watched out of all the season has, aired or not. Specials (season 0) are
    # left out of progress: they have no count, only their number of episodes.
    counted = [] if number == 0 else episodes
    return {
        'number': number,
        'name': 'Specials' if number == 0 else f'Season {number}',
        'episodes': episodes,
        'progress_id': f'progress-season-{number}',
        'watched_count': sum(1 for episode in counted if episode.watch),
        'total_count': len(counted),
        # A season none of whose episodes has aired has nothing to mark, so it gets no button.
        'has_aired': bool(aired),
        # Once every episode that has aired is marked, the button un-marks the season instead, and the season
        # can be watched again.
        'all_marked': bool(aired) and all(episode.watch for episode in aired),
        # The "−" next to "Watch Season N again" is there while some episode has been watched more than once.
        'can_take_back': any(episode.watch_count > 1 for episode in episodes),
    }


def _season_infos(request, series, episodes):
    """The seasons that `episodes` are in, as they are now, for the buttons htmx puts in place after a change."""
    numbers = {episode.season_number for episode in episodes}
    in_those = series.episodes.filter(season_number__in=numbers).order_by('season_number', 'episode_number', 'id')
    by_season = {}
    for episode in _with_state(request, list(in_those)):
        by_season.setdefault(episode.season_number, []).append(episode)
    return [_season_info(number, by_season[number]) for number in sorted(by_season)]


def _episode_row(request, episode):
    """One episode's row in its current state, which htmx swaps in place so the page does not move.
    Its season's button comes with it, because this episode may have just completed (or broken) the season."""
    _with_state(request, [episode])
    context = {
        'episode': episode,
        'item': episode.title,
        'seasons': _season_infos(request, episode.title, [episode]),
        'progress': _series_progress(request, episode.title),
    }
    return render(request, 'core/_episode_answer.html', context)


def _short_name(episode):
    return f'S{episode.season_number}E{episode.episode_number}'


def _question(request, episode, today):
    """What to ask when marking `episode` skips episodes ("did you watch the earlier episodes too?"), or None
    when there is nothing to ask."""
    last_marked, skipped = skipped_episodes(request.user, episode, today)
    if not skipped:
        return None
    return {
        'item': episode.title,
        'episode': episode,
        'name': _short_name(episode),
        # The nearest episode marked before it, or empty when nothing before it is marked.
        'after': _short_name(last_marked) if last_marked else '',
        'first': _short_name(skipped[0]),
        'count': len(skipped) + 1,  # what "Yes" marks: the skipped ones and this one
    }


def _up_next_card(request, series):
    """One series' card on the Home page as it is now, which htmx swaps in place of the card the button was in.
    When the series has nothing left to watch (or is not in Watching), there is no card: the answer is empty."""
    entry = next((entry for entry in up_next(request.user, _today(request)) if entry['series'].id == series.id), None)
    return render(request, 'core/_up_next_card.html', {'entry': entry} if entry else {})


def _answer_episode(request, episode, text='', ok=True):
    """Reply to an episode button. With htmx: just the row, as it is now (the colour says what happened).
    Without htmx: a redirect back to the page the button was on, with a message (unless `text` is empty).

    On the Home page (`up_next` is posted) the button is a card's check, so with htmx the answer is that
    series' card as it is now: the next episode, or nothing.

    When the button was "No, only this one" on the question, the question is on the page and has to go away
    too, so the answer is the one `_answer_changed` gives (the changed row, and the question taken off)."""
    if request.headers.get('HX-Request'):
        if request.POST.get('up_next'):
            return _up_next_card(request, episode.title)
        if request.POST.get('only_this'):
            return _answer_changed(request, episode.title, [episode])
        return _episode_row(request, episode)
    return _redirect_back(request, text, ok, 'series')


def _ask_earlier(request, question):
    """Answer a first mark with the question instead of marking. Nothing is saved until it is answered.

    With htmx the question goes into the page where it is (`#ask`). Without htmx it is kept for the series
    page to show, once, after the redirect.
    """
    if request.headers.get('HX-Request'):
        response = render(request, 'core/_ask_earlier.html', {'ask': question, 'next': request.POST.get('next', '')})
        response['HX-Retarget'] = '#ask'
        response['HX-Reswap'] = 'innerHTML'
        return response
    request.session['ask_earlier'] = question['episode'].id
    return _redirect_back(request, '', True, 'series')


@require_POST
def episode_watched_add(request):
    """Mark one episode as watched, on the day the button is pressed (in the account's time zone).

    An episode that skips unmarked episodes before it asks first whether those were watched too. The question's
    "No, only this one" sends `only_this` to skip it. An episode that is already watched gets one more watch each
    time its circle is pressed (the "−" button, `watched_remove`, takes the latest back), and asks nothing.
    """
    episode = _posted_episode(request)
    name = f'“{episode.title.title}” S{episode.season_number}E{episode.episode_number}'
    today = _today(request)

    if episode.air_date is None:
        return _answer_episode(request, episode, f'{name} has no air date yet, so it cannot be marked.', False)
    if episode.air_date > today:
        return _answer_episode(request, episode, f'{name} has not aired yet, so it cannot be marked.', False)
    watched_before = Watch.objects.filter(user=request.user, episode=episode).exists()
    if watched_before and (request.POST.get('up_next') or request.POST.get('only_this')):
        # Pressing the circle of an episode that is already watched counts as another time watched. But Home's
        # check and the question's "No, only this one" are about marking it for the first time, so on one of them
        # that is out of date (the episode was marked in another tab) nothing is added.
        return _answer_episode(request, episode, f'{name} is already marked as watched.')
    if not watched_before and not request.POST.get('only_this'):
        question = _question(request, episode, today)
        if question and request.POST.get('up_next'):
            # Home has no place for the question, and its cards only offer the first episode left to watch,
            # which skips nothing. So this is a page that is out of date: nothing is marked, and the card
            # comes back as it is now.
            return _answer_episode(request, episode)
        if question:
            return _ask_earlier(request, question)

    Watch.objects.create(user=request.user, title=episode.title, episode=episode, watched_on=today)
    # On the Home page the card changing to the next episode is feedback for the browser with htmx.
    # Without htmx the page reloads, so it says what happened.
    return _answer_episode(request, episode, f'Marked {name} as watched.' if request.POST.get('up_next') else '')


@require_POST
def watched_remove(request):
    """Undo a watch, right after marking it or any time later."""
    try:
        watch_id = int(request.POST.get('watch_id', ''))
    except ValueError:
        raise BadRequest from None
    watch = Watch.objects.select_related('title', 'episode').filter(user=request.user, id=watch_id).first()
    if watch is None:
        if request.headers.get('HX-Request') and 'episode_id' in request.POST:
            # An episode button on a page that is out of date (undone in another tab): show the row as it is now.
            return _episode_row(request, _posted_episode(request))
        return _redirect_back(request, 'That watch is not in your history.', False, 'history')

    with transaction.atomic():
        # A film can be watched more than once, and this takes back only this watch. If it took the title off To
        # Watch, it goes back as it was (the date added is untouched) when this is the newest watch of the film,
        # which is the undo of the latest press, and so when it is the only one ("Mark as not watched"). Taking
        # back an older watch while newer ones remain leaves the film off the list: the entry now points at the
        # earliest watch that is left, so taking those back one by one ends with the film back on the list.
        others = Watch.objects.none()
        newer = False
        if watch.episode_id is None:
            others = Watch.objects.filter(user=request.user, title_id=watch.title_id, episode=None).exclude(id=watch.id)
            newer = others.filter(
                Q(created_at__gt=watch.created_at) | Q(created_at=watch.created_at, id__gt=watch.id)
            ).exists()
        back_on_list = 0
        if newer:
            ToWatchItem.objects.filter(removed_by_watch=watch).update(
                removed_by_watch=others.order_by('created_at', 'id').first()
            )
        else:
            back_on_list = ToWatchItem.objects.filter(removed_by_watch=watch).update(
                removed_at=None, removed_by_watch=None
            )
        watch.delete()
    if watch.episode_id:
        # No message: the button turning gray (or the count going down) says it.
        return _answer_episode(request, watch.episode)
    if others.exists():
        text = f'Removed one watch of “{watch.title.title}”.'
    else:
        text = f'Marked “{watch.title.title}” as not watched.'
    if back_on_list:
        text += ' It is back on your To Watch list.'
    return _redirect_back(request, text, True, 'history')


def _answer_changed(request, series, episodes, text='', ok=True):
    """Reply to the season buttons and to the question's "Yes" and "No". `episodes` are the ones that changed.

    With htmx: just those rows and the buttons of their seasons, which htmx puts where they are on the page
    (the form says `hx-swap="none"`, so nothing else is touched), and the question taken off the page if it
    was open. The page does not move and the open seasons stay open.
    Without htmx: a redirect back to the series page, with `text` as a message (unless it is empty).
    """
    if request.headers.get('HX-Request'):
        context = {
            'item': series,
            'episodes': _with_state(request, episodes),
            'seasons': _season_infos(request, series, episodes),
            'progress': _series_progress(request, series),
        }
        return render(request, 'core/_bulk_result.html', context)
    return _redirect_back(request, text, ok, 'series')


def _posted_season(request):
    """The series, the season number and the season's episodes a season button was pressed for."""
    try:
        tmdb_id, number = int(request.POST.get('tmdb_id', '')), int(request.POST.get('season', ''))
    except ValueError:
        raise BadRequest from None
    if tmdb_id < 1 or number < 0:
        raise BadRequest
    series = get_object_or_404(Title, kind='series', tmdb_id=tmdb_id)
    episodes = list(series.episodes.filter(season_number=number).order_by('episode_number', 'id'))
    if not episodes:
        raise Http404
    return series, number, episodes


@require_POST
def season_watched_add(request):
    """Mark every episode of a season that has aired and is not marked yet, in one step.

    When there is nothing new to mark, nothing happens and nothing is said (the page only offers this button
    while something is left to mark).
    """
    series, _, episodes = _posted_season(request)
    marked = mark_episodes(request.user, episodes, _today(request))
    return _answer_changed(request, series, marked)


@require_POST
def season_watched_remove(request):
    """Mark a whole season as not watched in one step: the season button, pressed again.

    Every watch of this account for the season goes, so it is the undo of marking the whole season. When
    nothing in the season is marked, nothing happens.
    """
    series, _, episodes = _posted_season(request)
    unmarked = unmark_episodes(request.user, episodes)
    return _answer_changed(request, series, unmarked)


@require_POST
def season_watched_again(request):
    """Watch a season again: one more watch, dated today, for every episode of it that has aired, in one step.

    Only a season that is watched through can be watched again (the page only offers the button then). When it
    is not, nothing happens and nothing is said.
    """
    series, _, episodes = _posted_season(request)
    again = rewatch_episodes(request.user, episodes, _today(request))
    return _answer_changed(request, series, again)


@require_POST
def season_watched_again_remove(request):
    """Take back one season rewatch, the "−" next to "Watch Season N again": the latest watch of every episode of
    the season that has more than one goes. It is the undo of `season_watched_again`. When no episode has more
    than one watch, nothing happens."""
    series, _, episodes = _posted_season(request)
    taken_back = take_back_rewatch(request.user, episodes)
    return _answer_changed(request, series, taken_back)


@require_POST
def episodes_watched_up_to(request):
    """The "Yes" of the question: mark the chosen episode and the episodes it skips (the ones that have aired and
    are not marked, between the nearest episode marked before it and it), in one step."""
    episode = _posted_episode(request)
    if episode.season_number == 0:
        raise BadRequest  # specials are not in that order, and the page offers no question for them
    name = _short_name(episode)
    if episode.air_date is None:
        text = f'{name} has no air date yet, so nothing can be marked up to it.'
        return _answer_changed(request, episode.title, [], text, ok=False)
    if episode.air_date > _today(request):
        text = f'{name} has not aired yet, so nothing can be marked up to it.'
        return _answer_changed(request, episode.title, [], text, ok=False)
    _, skipped = skipped_episodes(request.user, episode, _today(request))
    marked = mark_episodes(request.user, [*skipped, episode], _today(request))
    return _answer_changed(request, episode.title, marked)


# Nothing private on this page, and the TMDB credit should be visible to everyone.
@login_not_required
def about(request):
    return render(request, 'core/about.html')


def profile(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = TimeZoneForm(request.POST)
        if form.is_valid():
            profile.timezone = form.cleaned_data['timezone']
            profile.save()
            messages.success(request, 'Time zone saved.')
            return redirect('profile')
    else:
        form = TimeZoneForm(initial={'timezone': profile.timezone})
    movies, series = minutes_watched(request.user)
    time_spent = {'movies': describe(movies), 'series': describe(series), 'total': describe(movies + series)}
    return render(request, 'core/profile.html', {'form': form, 'profile': profile, 'time_spent': time_spent})
