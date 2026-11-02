# History and "Mark as watched"

## What it does

- **Mark a movie as watched.** On a movie's page (not a series' page) there is a **Watched on** date box with a small **Mark as watched** button at its right (light pink, hot pink when the mouse is over it), and **Date unknown** under them. The box starts on today, in your own time zone (the one on your Profile page), and you can pick an earlier day. Tick **Date unknown** for an old watch you cannot place; the box is then ignored.
- **A day in the future is refused**, with a message, and nothing is saved. Whether a day is "in the future" follows your time zone: late in the evening in Lisbon it is already tomorrow in Auckland.
- **After marking,** the page shows "Watched" with "on 5 Mar 2026" (or "(date unknown)") and a **Mark as not watched** button, and under it the same date box with a small **Watch again** button beside it.
- **Watch again.** Each press of **Watch again** saves one more watch of the movie with its own date: the box works like the first mark (starts on today, an earlier day can be picked, **Date unknown** ticked ignores it, a day in the future is refused). So a rewatch from last year can be entered too. Pressing it 3 times adds 3 watches. The page then says "Watched 4 times" and lists every watch, newest day first, each with its own **Remove this watch** button. A rewatch does not change anything else: not the To Watch list, not Home. Every watch adds the movie's runtime to the **Time spent watching** on [Profile](profile.md), and taking a watch back takes it off again.
- **History screen** (`/movies/history/`, the **History** tab of the Movies section; the old `/history/` sends you there). Every movie you watched, once, as tiles with the date under each. A movie you watched 3 times is still one tile, with the date of its latest watch (all its watches are listed on the movie's own page). Newest watched day first, "Date unknown" at the bottom (among those, the one saved last first); a movie with a dated watch and an undated one shows the dated one. Empty: "Nothing in your history yet".
- **It leaves To Watch.** If the movie was on your To Watch list it is taken off it. It does not show under "Recently removed", because you did not remove it.
- **Undo: Mark as not watched** (when the movie has one watch) or **Remove this watch** (when it has several), on the movie page and under each tile in History. It works right after marking and any time later (no time limit, unlike the 10 seconds for To Watch removals). Only that one watch is erased. Under a History tile it is the watch the tile shows (the latest); the next one shows after that.
  - Taking back the **last** watch is "Mark as not watched": if marking it took the movie off To Watch, the movie goes back on the list exactly as it was, with its old date added. A movie that was not on the list stays off it. After that you can mark the movie again.
  - Taking back one of several watches leaves the movie off To Watch (it is still watched). Taking them back one by one ends with the movie back on the list. The one exception is the newest watch of a movie you had put back on To Watch to see it again: taking that one back puts it back on the list.
- **Your own history:** each account sees only its own watches and can only undo its own. Another account's watches of the same movie never count as yours.
- **If something goes wrong** you see a message, not a crash: TMDB cannot be reached the first time you mark a movie (nothing is saved, try again later); a day that makes no sense or is missing; a watch that is not in your history. A movie TMDB does not have gives the normal "page not found" screen.

## How it works

**Pages and buttons**

| Address | What | Needs login |
|---|---|---|
| `/movies/history/` | The History screen (a tab of Movies) | Yes |
| `/history/` | Old address: redirects to `/movies/history/` | Yes |
| `/watched/add/` | Mark a movie as watched (button, POST only) | Yes |
| `/watched/remove/` | Mark as not watched, the undo (button, POST only) | Yes |

The buttons are normal forms, not htmx: the server saves, then sends the browser back to the page (the `next` field, only if it is a page of this site; History otherwise) with a message. Mark and Watch again are the same form and the same address: they send `kind` (only `movie`; a series is refused with a 400), `tmdb_id`, `watched_on` and `date_unknown`. Un-mark sends `watch_id`.

**Tables** (see [data model](data-model.md))
- `core_watch`: one row per watch: `user`, `title` (links to `core_title`), `watched_on` (a day; empty means date unknown) and `created_at`. There is deliberately no "one per title" limit (design rule 1): a rewatch is another row, so no table changed for Watch again. Episodes use this table too, with a link to the episode (see [Series](series.md)); a movie's watch has no episode.
- `core_towatchitem` gets one column, `removed_by_watch` (links to the watch). It is filled in only when marking a movie as watched took it off To Watch.

**Mark and Watch again** (`watched_add` in `core/views.py`)
1. The date is checked first (`WatchedForm` in `core/forms.py`): a real day, not after today in your time zone, or "unknown".
2. The title is saved from TMDB if our own table does not have it yet (the same `_saved_title` that adding to To Watch uses, design rule 6), otherwise TMDB is not asked. The movie's runtime is saved with it (`core_title.runtime`), for the time spent on [Profile](profile.md).
3. In one database step: the `core_watch` row is created and, if the movie is on your To Watch list, it gets `removed_at` = now and `removed_by_watch` = this watch. The message says "Marked … as watched." for the first watch and "Added another watch of …." for the others.
- "Today" comes from `_today()`: the current time converted to the time zone on your Profile.

**Undo** (`watched_remove`)
- Only your own watch can be found; anything else gets "not in your history".
- In one database step, any To Watch entry pointing at this watch is dealt with, then the watch row is deleted:
  - if no newer watch of yours of this movie exists, the entry gets `removed_at` and `removed_by_watch` cleared (its `added_at` was never touched), so the movie is back on the list as it was;
  - if a newer watch exists, the entry is pointed at the earliest watch that is left and stays off the list, so taking the watches back one by one ends with the movie back on the list.
- The tests `test_undo_puts_everything_back_as_it_was`, `test_taking_the_watches_back_one_by_one_puts_everything_back_as_it_was` and the cases around them check that everything is back as before.
- If you added the movie to To Watch again after watching it, the entry is already back on the list and undoing the watch that took it off earlier leaves it alone.
- "Recently removed" and the To Watch Undo ignore entries with `removed_by_watch` set, so a watched movie can only come back through taking its watches back. Adding it to To Watch again from Search or its page works as usual (and clears the mark).

**Screens**: `title.html` (the list of watches and the date box, movies only; the date form has the class `watched-form`, which `couchlog.css` lays out as the box and the button on one row, with "Date unknown" on the row under), `history.html` (one tile for each movie: `history` in `core/views.py` keeps the first watch of each movie in the list order, which is the latest, and counts the rest in `watch.times`; the button says "Remove this watch" when the movie has several watches), and `_tile_link.html` (the clickable poster, name and year, shared by To Watch, search and History).

**Known limits**
- Only movies are marked here; episodes are marked on the series page ([Series](series.md)). History belongs to the Movies section and lists films only (`history` in `core/views.py` filters on the title's kind), so episode watches do not show here.
- Pressing Mark twice at the very same moment (a double click) saves two watches, as a double click on Watch again does; Remove this watch takes them back one at a time.
- The title page still reads TMDB every time it is opened, so it shows an error if TMDB is down (History does not need TMDB).
- History has no search, filter or paging yet.
