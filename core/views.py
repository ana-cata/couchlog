import math
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import BadRequest
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_headers

from . import tmdb
from .forms import TimeZoneForm
from .models import Profile, Title, ToWatchItem

# How long after removing a title from To Watch it can still be undone. The screen says the
# number of seconds, which comes from here. After that, the way back is adding the title again.
UNDO_WINDOW = timedelta(seconds=10)


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
    try:
        item = tmdb.get_title(kind, tmdb_id)
    except tmdb.TmdbNotFound:
        raise Http404 from None
    except tmdb.TmdbError as problem:
        return render(request, 'core/title.html', {'error': str(problem)})
    on_list = _my_item(request, kind, tmdb_id).filter(removed_at=None).exists()
    return render(request, 'core/title.html', {'item': item, 'on_list': on_list, 'next': request.get_full_path()})


def _undo_seconds():
    return int(UNDO_WINDOW.total_seconds())


def _recently_removed(request):
    """What the "Recently removed" block shows: only titles still inside the undo window."""
    removed = list(
        ToWatchItem.objects.filter(user=request.user, removed_at__gte=timezone.now() - UNDO_WINDOW)
        .select_related('title')
        .order_by('-removed_at')
    )
    context = {'removed': removed, 'undo_seconds': _undo_seconds(), 'next': reverse('to_watch')}
    if removed:
        # The oldest one runs out of time first. The block asks the server again just after
        # that, so a page that stays open empties the list by itself.
        runs_out = min(item.removed_at for item in removed) + UNDO_WINDOW
        context['recheck_seconds'] = max(1, math.ceil((runs_out - timezone.now()).total_seconds()) + 1)
    return context


def to_watch(request):
    items = (
        ToWatchItem.objects.filter(user=request.user, removed_at=None)
        .select_related('title')
        .order_by('-added_at')
    )
    return render(request, 'core/to_watch.html', {'items': items, **_recently_removed(request)})


# Only the "Recently removed" block, which the To Watch screen asks for when time runs out.
@never_cache
def to_watch_removed(request):
    return render(request, 'core/_recently_removed.html', _recently_removed(request))


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

    if text:
        (messages.success if ok else messages.error)(request, text)
    next_url = request.POST.get('next', '')
    # Only come back to a page of this site, never to an address someone slipped into the form.
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('to_watch')
    return redirect(next_url)


@require_POST
def to_watch_add(request):
    kind, tmdb_id = _posted_title(request)

    # The details come from TMDB the first time anyone adds a title, then from our own table.
    title = Title.objects.filter(kind=kind, tmdb_id=tmdb_id).first()
    if title is None:
        try:
            details = tmdb.get_title(kind, tmdb_id)
        except tmdb.TmdbNotFound:
            raise Http404 from None
        except tmdb.TmdbError as problem:
            return _answer(request, kind, tmdb_id, False, str(problem), ok=False)
        saved = {key: details[key] for key in ('title', 'year', 'poster_url', 'overview')}
        title, _ = Title.objects.get_or_create(kind=kind, tmdb_id=tmdb_id, defaults=saved)

    item, created = ToWatchItem.objects.get_or_create(user=request.user, title=title)
    if item.removed_at:
        # Adding a title again after removing it puts it back as newly added.
        item.removed_at, item.added_at = None, timezone.now()
        item.save(update_fields=['removed_at', 'added_at'])
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
    item = _my_item(request, kind, tmdb_id).exclude(removed_at=None).first()
    if item is None:
        return _answer(request, kind, tmdb_id, False, 'There is nothing to undo for that title.', ok=False)
    if item.removed_at < timezone.now() - UNDO_WINDOW:
        text = f'It is too late to undo removing “{item.title.title}”. You can add it again from Search.'
        return _answer(request, kind, tmdb_id, False, text, ok=False)
    # The date added was never touched, so the title returns to its old place in the list.
    item.removed_at = None
    item.save(update_fields=['removed_at'])
    return _answer(request, kind, tmdb_id, True, f'Put “{item.title.title}” back on your To Watch list.')


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
