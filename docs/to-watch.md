# To Watch lists

## What it does

- **Two lists, one per section.** The header has **Movies** and **Series**. **Movies** opens on its **To Watch** tab, and **Series** opens on **Watching** (its first tab), so Series → To Watch is one click further. **Movies → To Watch** (`/movies/`) lists only films and **Series → To Watch** (`/series/`) lists only series. Each shows tiles (poster, name, year, movie or series), newest added first. An empty list says so ("No movies on your To Watch list yet" / "No series on your To Watch list yet") and links to Search.
- **Tabs.** Under the section's name there is a small tab bar with the current tab underlined. Movies has **To Watch** and **History** (see [History](history.md)). Series has **Watching**, **To Watch**, **Finished** and **Dropped**, in that order (see [Series](series.md)).
- **Series → To Watch only lists series you have not started.** Once you mark an episode of a series, it moves to Series → Watching (its entry on this list stays, so un-marking every episode brings it back here). A series you dropped is not listed here either: it is under Series → Dropped, and bringing it back returns it, with its entry untouched.
- **The old addresses still work.** `/to-watch/` sends you to `/movies/` and `/history/` to `/movies/history/`, so an old bookmark is not lost.
- **Every tile is the same size.** A name is always given two lines, and a longer one is cut with "..." (hover to see the whole name). The year line is one line, and the button is always at the bottom of the tile, so the grid looks even.
- **Add:** every search result has an "Add to To Watch" button under its tile, and so does each movie or series page, under the poster. Press it and the button turns into "Remove from To Watch" right away, without the page reloading. The title is still on the screen after you reload, log out and back in, or restart the app.
- **Remove:** the same button on a search result or a title page, or "Remove from To Watch" under a tile on a To Watch list. The title leaves the list.
- **Undo, for 10 seconds:** a title you removed appears under **Recently removed** at the top of its own list (a film in Movies, a series in Series), with an Undo button. Each list only shows removals of its own kind. Undo puts it back in its old place in the list (the date it was added is kept). A removal can only be undone during those 10 seconds. When the time is up the title **disappears from Recently removed by itself**, even if you leave the page open and do nothing. It is then gone from the To Watch list for good, and the only way back is to search for it and add it again from Search (or its page). That puts it back as newly added (at the top of the list).
- **No "Removed ..." notice.** Removing a title shows no message at the top. The title leaving the list and appearing under Recently removed is the feedback, and that block says how long Undo lasts ("You can undo a removal for 10 seconds.").
- **A movie you mark as watched leaves the list** by itself (see [History](history.md)). It is not under "Recently removed": its undo is "Mark as not watched", which puts it back here exactly as it was.
- **The same title twice:** pressing Add on something already on the list does nothing but say so. There is never a second entry.
- **Your own list:** each account has its own list. Nobody else sees yours or can change it.
- **If something goes wrong** you see a message, not a crash:
  - TMDB cannot be reached when you add a title: a message next to the button, and nothing is saved. Try again later.
  - A title TMDB does not have: the normal "page not found" screen.
  - You press Undo after the 10 seconds are over (for example the page has no JavaScript and could not update itself): "It is too late to undo ... You can add it again from Search." and nothing changes.

## How it works

**Pages and buttons**

| Address | What | Needs login |
|---|---|---|
| `/movies/` | Movies → To Watch: the films on your list | Yes |
| `/series/` | Series → To Watch: the series on your list | Yes |
| `/to-watch/` | Old address: redirects to `/movies/` | Yes |
| `/to-watch/removed/?kind=movie` (or `series`) | Only the "Recently removed" block of one section, which its screen asks for when time runs out (GET). Without a real `kind` it is refused with a 400 | Yes |
| `/to-watch/add/` | Add a title (button, POST only) | Yes |
| `/to-watch/remove/` | Remove a title (button, POST only) | Yes |
| `/to-watch/undo/` | Put a removed title back (button, POST only) | Yes |

The three buttons serve both sections, so they keep their addresses. Each sends `kind` (`movie` or `series`), `tmdb_id` and `next` (the page to come back to). Anything else is refused with a 400, and `next` is only followed if it is a page of this site. With no usable `next`, the browser goes back to the section of the title's kind (`SECTION_OF_KIND` in `core/views.py`).

**The two sections** (`movies` and `series` in `core/views.py`)
- Both are the same screen (`to_watch.html`) filtered by the title's kind: `ToWatchItem` entries of this account, with an empty `removed_at`, whose `title.kind` is `movie` (or `series`), newest `added_at` first. For series, entries whose series you have marked an episode of are left out (`started_series` in `core/episodes.py`), and so are those you dropped (`dropped_series`). No table changed for this.
- The tab bar is one small partial (`_section_tabs.html`) used by the To Watch screen and by History. Pico's `aria-current="page"` marks the current tab, and `couchlog.css` underlines it.
- "Recently removed" is built per kind (`_recently_removed(request, kind)`), and its undo buttons come back to that section.

**Tables** (see [data model](data-model.md))
- `core_title`: the TMDB details saved when a title is first added: kind, TMDB id, name, year, poster address, description. One row per title, shared by every account, so later features (watches, episodes, calendar) can point to it. Unique on kind + TMDB id (a movie and a series can have the same number).
- `core_towatchitem`: one row per account and title: `user`, `title`, `added_at`, `removed_at`, `removed_by_watch`. Unique on user + title. `removed_at` is empty while the title is on the list. `removed_by_watch` is only filled in when the title left because it was marked as watched; entries like that are skipped by "Recently removed" and by the Undo here.

**Add** (`to_watch_add` in `core/views.py`)
- If the title is already in `core_title`, TMDB is not asked at all. Otherwise one TMDB call (`GET /movie/<id>` or `/tv/<id>`) fetches the details and they are saved (design rule 6). The list is then shown from our own table.
- First time: a new `core_towatchitem` row. Already on the list: nothing changes. Removed earlier: `removed_at` is cleared and `added_at` becomes now.
- **Dates for the [Calendar](calendar.md).** When the title is put on the list (first time, or added again after a removal), `_collect_dates` asks TMDB for them right away, so the Calendar is right at once: for a movie its cinema and streaming dates (`GET /movie/<id>?append_to_response=release_dates`, which also gives its banner), for a series its episodes (as the series page does), unless they were saved less than a day ago, and then its upcoming episodes from TVmaze (always, because opening the series page does not collect them). A long series makes the button take a few seconds the first time. If TMDB or TVmaze does not answer, the title is still added and nothing is half saved; the next `refresh_calendar` run collects the dates. Pressing Add on a title already on the list asks TMDB nothing more.

**Remove and undo**
- Remove only fills in `removed_at`. Undo clears it again and does not touch `added_at`, so the entry comes back exactly as it was (design rule 5; the test `test_undo_puts_everything_back_as_it_was` checks this).
- The undo window is one setting, `UNDO_WINDOW` (10 seconds) in `core/views.py`; the number shown on the screen comes from it. A To Watch list lists entries with an empty `removed_at`, newest `added_at` first, and offers Undo for entries whose `removed_at` is inside the window. The server checks the window again when Undo is pressed, so an old removal can never be undone.
- **The list empties by itself.** The "Recently removed" block (`_recently_removed.html`) carries an htmx timer (`hx-trigger="load delay:Ns"`): N is the seconds left for the oldest removal plus one. When it fires, the block asks `/to-watch/removed/?kind=...` (its own kind) for itself again, gets back only what is still undoable (nothing, once time is up), and replaces itself. The time is always worked out by the server, never by the browser's clock. While something is still undoable the new block sets the next timer; when nothing is left it has no timer. The answer is never cached.
- After the window nothing is erased: the row stays with its `removed_at`, and adding the title again clears `removed_at` and sets `added_at` to now.

**Live buttons on the search page and the title pages**
- The buttons on search results and on title pages use htmx: the page asks the server and swaps in only the button's new state (`_to_watch_button.html`). The page does not reload and TMDB is not searched again.
- Without htmx the same buttons are normal forms: the server answers with a redirect back to the page and shows a message.
- Search and the title pages check your own list to know which button to show, so the right one shows after a reload. A title page whose TMDB request failed shows the error and no button.

**Same-size tiles** (`core/static/core/couchlog.css`)
- A tile is a column that fills its grid cell, so the button sits at the bottom. The name is clamped to two lines with a fixed height, the year line does not wrap, and the button has a fixed height under a tile.
- The smallest tile width is in `rem`, not pixels, because the text grows on a big screen (Pico scales the page font with the screen width). With pixels the year line was cut off on wide screens. A browser test (`test_every_tile_is_the_same_size_whatever_the_title`) checks that all tiles are the same size and that nothing is cut.

**Known limits**
- A title's saved details are not refreshed yet. Changes on TMDB (a new poster, a fixed year) do not reach titles already saved. Refreshing comes with later cards.
- After the 10 seconds there is no undo, only adding the title again, which resets its date added.
- Without JavaScript the block cannot empty itself. It still goes away when the page is reloaded, and Undo is refused by the server after the 10 seconds.
- A removal made on a search or title page (not on a To Watch list) is only offered for undo here if you open that title's list (Movies or Series) within the 10 seconds. On those pages the button turns back into "Add to To Watch", which is the same as undoing it except that the date added is reset.
- The date added is stored but not shown on screen.
