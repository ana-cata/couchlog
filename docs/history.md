# History and "Mark as watched"

## What it does

- **Mark a movie as watched.** On a movie's page (not a series' page) there is a **Watched on** date box and a **Mark as watched** button. The box starts on today, in your own time zone (the one on your Profile page), and you can pick an earlier day. Tick **Date unknown** for an old watch you cannot place; the box is then ignored.
- **A day in the future is refused**, with a message, and nothing is saved. Whether a day is "in the future" follows your time zone: late in the evening in Lisbon it is already tomorrow in Auckland.
- **After marking,** the page shows "Watched on 5 Mar 2026" (or "Watched (date unknown)") and a **Mark as not watched** button instead of the form. Pressing Mark as watched on a movie that is already marked changes nothing and says so. Watching a movie again is a later feature (Rewatch).
- **History screen** (`/movies/history/`, the **History** tab of the Movies section; the old `/history/` sends you there). Every movie you marked, as tiles with the date under each: newest watched day first, "Date unknown" at the bottom (among those, the one saved last first). Empty: "Nothing in your history yet".
- **It leaves To Watch.** If the movie was on your To Watch list it is taken off it. It does not show under "Recently removed", because you did not remove it.
- **Undo: Mark as not watched**, on the movie page and under each tile in History. It works right after marking and any time later (no time limit, unlike the 10 seconds for To Watch removals). The watch is erased, and if marking it took the movie off To Watch, the movie goes back on the list exactly as it was, with its old date added. A movie that was not on the list stays off it. After an undo you can mark the movie again.
- **Your own history:** each account sees only its own watches and can only undo its own.
- **If something goes wrong** you see a message, not a crash: TMDB cannot be reached the first time you mark a movie (nothing is saved, try again later); a day that makes no sense or is missing; a watch that is not in your history. A movie TMDB does not have gives the normal "page not found" screen.

## How it works

**Pages and buttons**

| Address | What | Needs login |
|---|---|---|
| `/movies/history/` | The History screen (a tab of Movies) | Yes |
| `/history/` | Old address: redirects to `/movies/history/` | Yes |
| `/watched/add/` | Mark a movie as watched (button, POST only) | Yes |
| `/watched/remove/` | Mark as not watched, the undo (button, POST only) | Yes |

The buttons are normal forms, not htmx: the server saves, then sends the browser back to the page (the `next` field, only if it is a page of this site; History otherwise) with a message. Mark sends `kind` (only `movie`; a series is refused with a 400), `tmdb_id`, `watched_on` and `date_unknown`. Un-mark sends `watch_id`.

**Tables** (see [data model](data-model.md))
- `core_watch`: one row per watch: `user`, `title` (links to `core_title`), `watched_on` (a day; empty means date unknown) and `created_at`. There is deliberately no "one per title" limit: a rewatch will be another row (design rule 1), and episodes use this table too, with a link to the episode (see [Series](series.md)); a movie's watch has no episode.
- `core_towatchitem` gets one column, `removed_by_watch` (links to the watch). It is filled in only when marking a movie as watched took it off To Watch.

**Mark** (`watched_add` in `core/views.py`)
1. The date is checked first (`WatchedForm` in `core/forms.py`): a real day, not after today in your time zone, or "unknown".
2. The title is saved from TMDB if our own table does not have it yet (the same `_saved_title` that adding to To Watch uses, design rule 6), otherwise TMDB is not asked.
3. If you already have a watch for the movie, nothing changes.
4. In one database step: the `core_watch` row is created and, if the movie is on your To Watch list, it gets `removed_at` = now and `removed_by_watch` = this watch.
- "Today" comes from `_today()`: the current time converted to the time zone on your Profile.

**Undo** (`watched_remove`)
- Only your own watch can be found; anything else gets "not in your history".
- In one database step: any To Watch entry pointing at this watch gets `removed_at` and `removed_by_watch` cleared (its `added_at` was never touched), then the watch row is deleted. The tests `test_undo_puts_everything_back_as_it_was` and the cases around it check that everything is back as before.
- If you added the movie to To Watch again after watching it, the entry is already back on the list and undo leaves it alone.
- "Recently removed" and the To Watch Undo ignore entries with `removed_by_watch` set, so a watched movie can only come back through Mark as not watched. Adding it to To Watch again from Search or its page works as usual (and clears the mark).

**Screens**: `title.html` (the form or the "Watched" line, movies only), `history.html`, and `_tile_link.html` (the clickable poster, name and year, shared by To Watch, search and History).

**Known limits**
- Only movies are marked here; episodes are marked on the series page ([Series](series.md)). History belongs to the Movies section and lists films only (`history` in `core/views.py` filters on the title's kind), so episode watches do not show here.
- One watch per movie in the screens. Pressing Mark twice at the very same moment (a double click) could still save two; Mark as not watched then removes one at a time.
- The title page still reads TMDB every time it is opened, so it shows an error if TMDB is down (History does not need TMDB).
- History has no search, filter or paging yet.
