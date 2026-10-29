import math
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import BadRequest
from django.db import transaction
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from . import tmdb
from .episodes import (
    earlier_to_ask_about,
    episodes_up_to,
    mark_episodes,
    refresh_episodes,
    series_tabs,
    started_series,
    undo_batch,
)
from .forms import TimeZoneForm, WatchedForm
from .models import Episode, Profile, Title, ToWatchItem, Watch

# How old our saved episodes may get before opening a series page asks TMDB again.
EPISODES_REFRESH_AFTER = timedelta(days=1)

# How long after removing a title from To Watch it can still be undone. The screen says the
# number of seconds, which comes from here. After that, the way back is adding the title again.
UNDO_WINDOW = timedelta(seconds=10)

# The section of the app each kind of title lives in. It is also the name of that section's
# To Watch address, so a button with no page to come back to returns to the right one.
SECTION_OF_KIND = {'movie': 'movies', 'series': 'series'}


def home(request):
    return render(request, 'core/home.html')


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
    for result in results:
        result['on_list'] = (result['kind'], result['tmdb_id']) in on_list

    # htmx also asks for the whole page when it restores a page from its history.
    live_update = request.headers.get('HX-Request') and not request.headers.get('HX-History-Restore-Request')
    template = 'core/_search_results.html' if live_update else 'core/search.html'
    context = {'query': query, 'results': results, 'error': error, 'next': request.get_full_path()}
    return render(request, template, context)


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
    context = {'item': item, 'on_list': on_list, 'next': request.get_full_path()}
    if kind == 'movie':
        # Series are marked episode by episode (a later card), so only movies get this section.
        context['watch'] = (
            Watch.objects.filter(user=request.user, title__kind=kind, title__tmdb_id=tmdb_id)
            .order_by('-created_at', '-id')
            .first()
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
    # Watches are listed oldest first, so with rewatches (later) the latest one wins.
    watches = {
        watch.episode_id: watch
        for watch in Watch.objects.filter(user=request.user, title=series, episode__isnull=False).order_by(
            'created_at', 'id'
        )
    }
    by_season = {}
    for episode in series.episodes.order_by('season_number', 'episode_number', 'id'):
        episode.watch = watches.get(episode.id)
        episode.aired = _has_aired(episode, today)
        by_season.setdefault(episode.season_number, []).append(episode)
    # Specials (season 0) last.
    numbers = sorted(by_season, key=lambda number: (number == 0, number))
    seasons = [
        {
            'number': number,
            'name': 'Specials' if number == 0 else f'Season {number}',
            'episodes': by_season[number],
            # A season none of whose episodes has aired has nothing to mark, so it gets no button.
            'has_aired': any(episode.aired for episode in by_season[number]),
        }
        for number in numbers
    ]
    try:
        open_season = int(request.GET['season'])
    except (KeyError, ValueError):
        open_season = numbers[0] if numbers else None

    on_list = _my_item(request, 'series', tmdb_id).filter(removed_at=None).exists()
    asked = series.episodes.filter(id=request.session.pop('ask_earlier', 0)).first()
    context = {
        'item': series,
        'on_list': on_list,
        'next': request.get_full_path(),
        'notice': notice,
        'seasons': seasons,
        'open_season': open_season,
        # Without htmx, a season or "Yes" press comes back here and leaves its notice (with Undo) to show once.
        'bulk': request.session.pop('bulk_notice', {}),
        # Likewise the question after a first mark ("did you watch the earlier episodes too?"). It is worked out
        # again here, so a page that is out of date asks nothing.
        'ask': _question(request, asked, today) if asked else None,
    }
    return render(request, 'core/title.html', context)


def _today(request):
    """Today's date in the account's own time zone. The server's time zone does not matter."""
    name = Profile.objects.filter(user=request.user).values_list('timezone', flat=True).first()
    return timezone.now().astimezone(ZoneInfo(name or 'UTC')).date()


def _saved_title(kind, tmdb_id):
    """Our own saved copy of a title. The first time anyone needs it, TMDB is asked and it is saved."""
    title = Title.objects.filter(kind=kind, tmdb_id=tmdb_id).first()
    if title is None:
        details = tmdb.get_title(kind, tmdb_id)
        saved = {key: details[key] for key in ('title', 'year', 'poster_url', 'overview')}
        title, _ = Title.objects.get_or_create(kind=kind, tmdb_id=tmdb_id, defaults=saved)
    return title


def _undo_seconds():
    return int(UNDO_WINDOW.total_seconds())


def _recently_removed(request, kind):
    """What the "Recently removed" block of one section shows: only titles of that kind still inside the undo window.

    A title that left because it was marked as watched is not here: its undo is "Mark as not watched".
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
        items = items.exclude(title__in=started_series(request.user))
    context = {'items': items, 'section': SECTION_OF_KIND[kind], **_recently_removed(request, kind)}
    return render(request, 'core/to_watch.html', context)


def movies(request):
    return _to_watch_screen(request, 'movie')


def series(request):
    return _to_watch_screen(request, 'series')


def _series_tab(request, tab):
    watching, finished = series_tabs(request.user, _today(request))
    context = {'titles': watching if tab == 'watching' else finished, 'section': 'series', 'tab': tab}
    return render(request, 'core/series_tab.html', context)


def series_watching(request):
    return _series_tab(request, 'watching')


def series_finished(request):
    return _series_tab(request, 'finished')


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


def _answer(request, kind, tmdb_id, on_list, text, ok=True):
    """Reply to a button press.

    The search page uses htmx, which swaps in just the button in its new state. Without
    htmx the reply is a redirect back to the page the button was on, with a message (unless
    `text` is empty: then there is nothing to say).
    """
    if request.headers.get('HX-Request'):
        tile = {'kind': kind, 'tmdb_id': tmdb_id}
        context = {'tile': tile, 'on_list': on_list, 'next': request.POST.get('next', ''), 'live': True}
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
    return _answer(request, kind, tmdb_id, True, f'Added “{title.title}” to your To Watch list.')


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


def history(request):
    # Newest watch first. Watches with an unknown date go last, newest saved first among themselves.
    # History is the Movies section's tab, so it lists films only.
    watches = (
        Watch.objects.filter(user=request.user, title__kind='movie')
        .select_related('title')
        .order_by(F('watched_on').desc(nulls_last=True), '-created_at', '-id')
    )
    return render(request, 'core/history.html', {'watches': watches, 'section': 'movies', 'next': reverse('history')})


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

    # Watching it again is a later feature (Rewatch). For now a second press changes nothing.
    if Watch.objects.filter(user=request.user, title=title).exists():
        return _redirect_back(request, f'“{title.title}” is already marked as watched.', True, 'history')

    with transaction.atomic():
        watch = Watch.objects.create(user=request.user, title=title, watched_on=form.cleaned_data['watched_on'])
        # A watched movie leaves the To Watch list. The watch is remembered on the entry, so
        # un-marking it can put the entry back exactly as it was.
        ToWatchItem.objects.filter(user=request.user, title=title, removed_at=None).update(
            removed_at=timezone.now(), removed_by_watch=watch
        )
    return _redirect_back(request, f'Marked “{title.title}” as watched.', True, 'history')


def _posted_episode(request):
    """The episode a button was pressed for."""
    try:
        episode_id = int(request.POST.get('episode_id', ''))
    except ValueError:
        raise BadRequest from None
    return get_object_or_404(Episode.objects.select_related('title'), id=episode_id)


def _has_aired(episode, today):
    return episode.air_date is not None and episode.air_date <= today


def _with_state(request, episodes):
    """Give each episode what its row needs: this account's watch for it, and whether it has aired."""
    today = _today(request)
    # Watches are listed oldest first, so with rewatches (later) the latest one wins.
    watches = {
        watch.episode_id: watch
        for watch in Watch.objects.filter(user=request.user, episode__in=episodes).order_by('created_at', 'id')
    }
    for episode in episodes:
        episode.watch = watches.get(episode.id)
        episode.aired = _has_aired(episode, today)
    return episodes


def _episode_row(request, episode):
    """One episode's row in its current state, which htmx swaps in place so the page does not move."""
    _with_state(request, [episode])
    return render(request, 'core/_episode_row.html', {'episode': episode, 'item': episode.title})


def _short_name(episode):
    return f'S{episode.season_number}E{episode.episode_number}'


def _question(request, episode, today):
    """What to ask when `episode` is the first one marked in its series ("did you watch the earlier episodes
    too?"), or None when there is nothing to ask."""
    earlier = earlier_to_ask_about(request.user, episode, today)
    if not earlier:
        return None
    return {
        'item': episode.title,
        'episode': episode,
        'name': _short_name(episode),
        'first': _short_name(earlier[0]),
        'count': len(earlier) + 1,  # what "Yes" marks: the earlier ones and this one
    }


def _answer_episode(request, episode, text='', ok=True):
    """Reply to an episode button. With htmx: just the row, as it is now (the colour says what happened).
    Without htmx: a redirect back to the series page, with a message (unless `text` is empty).

    When the button was "No, only this one" on the question, the question is on the page and has to go away
    too, so the answer is the one `_answer_bulk` gives (the changed row, and the question taken off)."""
    if request.headers.get('HX-Request'):
        if request.POST.get('only_this'):
            return _answer_bulk(request, episode.title, [episode], '')
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

    The first episode marked in a series asks first whether the earlier ones were watched too. The question's
    "No, only this one" sends `only_this` to skip it.
    """
    episode = _posted_episode(request)
    name = f'“{episode.title.title}” S{episode.season_number}E{episode.episode_number}'
    today = _today(request)

    if episode.air_date is None:
        return _answer_episode(request, episode, f'{name} has no air date yet, so it cannot be marked.', False)
    if episode.air_date > today:
        return _answer_episode(request, episode, f'{name} has not aired yet, so it cannot be marked.', False)
    # Watching it again is a later feature (Rewatch). For now a second press changes nothing.
    if Watch.objects.filter(user=request.user, episode=episode).exists():
        return _answer_episode(request, episode, f'{name} is already marked as watched.')
    if not request.POST.get('only_this'):
        question = _question(request, episode, today)
        if question:
            return _ask_earlier(request, question)

    Watch.objects.create(user=request.user, title=episode.title, episode=episode, watched_on=today)
    return _answer_episode(request, episode)


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
        # If this watch took the title off To Watch, it goes back as it was (the date added is untouched).
        back_on_list = ToWatchItem.objects.filter(removed_by_watch=watch).update(
            removed_at=None, removed_by_watch=None
        )
        watch.delete()
    if watch.episode_id:
        # No message: the button turning gray says it.
        return _answer_episode(request, watch.episode)
    text = f'Marked “{watch.title.title}” as not watched.'
    if back_on_list:
        text += ' It is back on your To Watch list.'
    return _redirect_back(request, text, True, 'history')


def _count_episodes(count):
    return f'{count} episode{"" if count == 1 else "s"}'


def _answer_bulk(request, series, episodes, text, batch=None, ok=True):
    """Reply to the season, question ("Yes" and "No") and Undo buttons. `episodes` are the ones whose rows changed.

    With htmx: the notice (with an Undo button when there is a `batch` to undo) and only the changed
    rows, which htmx swaps in where they are, so the page does not move and the open seasons stay open.
    Without htmx: a redirect back to the series page. A notice with Undo is kept for that page to show
    once; a message with nothing to undo is an ordinary message.
    """
    if request.headers.get('HX-Request'):
        context = {
            'item': series,
            'episodes': _with_state(request, episodes),
            'text': text,
            'batch': batch,
            'next': request.POST.get('next', ''),
        }
        return render(request, 'core/_bulk_result.html', context)
    if batch:
        request.session['bulk_notice'] = {'text': text, 'batch': str(batch)}
        text = ''
    return _redirect_back(request, text, ok, 'series')


def _mark_many(request, series, episodes, where):
    """Mark the aired, unmarked ones among `episodes` as one batch and say what happened ("in Season 2")."""
    marked, batch = mark_episodes(request.user, episodes, _today(request))
    if not marked:
        text = f'Nothing new to mark {where}. Episodes already marked, not aired yet or without an air date are left alone.'
        return _answer_bulk(request, series, [], text)
    return _answer_bulk(request, series, marked, f'Marked {_count_episodes(len(marked))} {where} as watched.', batch)


@require_POST
def season_watched_add(request):
    """Mark every episode of a season that has aired and is not marked yet, in one step."""
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
    return _mark_many(request, series, episodes, 'in the Specials' if number == 0 else f'in Season {number}')


@require_POST
def episodes_watched_up_to(request):
    """Watched up to here, the "Yes" of the question on a first mark: mark every episode that has aired and is
    not marked yet, from season 1 episode 1 up to the chosen one, in one step."""
    episode = _posted_episode(request)
    if episode.season_number == 0:
        raise BadRequest  # specials are not in that order, and the page offers no button for them
    name = _short_name(episode)
    if episode.air_date is None:
        text = f'{name} has no air date yet, so nothing can be marked up to it.'
        return _answer_bulk(request, episode.title, [], text, ok=False)
    if episode.air_date > _today(request):
        text = f'{name} has not aired yet, so nothing can be marked up to it.'
        return _answer_bulk(request, episode.title, [], text, ok=False)
    return _mark_many(request, episode.title, episodes_up_to(episode), f'up to {name}')


@require_POST
def watched_batch_remove(request):
    """Undo a season or "Yes" press in one step, right after it or any time later."""
    try:
        batch = uuid.UUID(request.POST.get('batch', ''))
    except ValueError:
        raise BadRequest from None
    episodes = undo_batch(request.user, batch)
    if not episodes:
        text = 'Nothing to undo: those episodes are no longer marked as watched.'
        return _answer_bulk(request, None, [], text, ok=False)
    text = f'Undone: {_count_episodes(len(episodes))} marked as not watched.'
    return _answer_bulk(request, episodes[0].title, episodes, text)


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
    return render(request, 'core/profile.html', {'form': form, 'profile': profile})
