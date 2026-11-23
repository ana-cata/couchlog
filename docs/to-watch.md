# To Watch lists

## What it does

- **Two lists, one per section.** The header has **Movies** and **Series**. **Movies** opens on its **To Watch** tab, and **Series** opens on **Watching** (its first tab), so Series → To Watch is one click further. **Movies → To Watch** (`/movies/`) lists only films and **Series → To Watch** (`/series/`) lists only series. Each shows tiles (poster, name, year, movie or series), newest added first. **A tile has no button:** open the title to take it off the list (see "Remove"). An empty list says what it is for ("Keep the movies you want to see here." / "Keep the series you want to see here.") and links to Search.
- **Tabs.** Under the section's name there is a small tab bar with the current tab underlined. Movies has **To Watch** and **History** (see [History](history.md)). Series has **Watching**, **To Watch**, **Finished** and **Dropped**, in that order (see [Series](series.md)).
- **Series → To Watch only lists series you have not started.** Once you mark an episode of a series, it moves to Series → Watching (its entry on this list stays, so un-marking every episode brings it back here). A series you dropped is not listed here either: it is under Series → Dropped, and bringing it back returns it, with its entry untouched. A series taken off all lists with **Remove from all lists** (see [Series](series.md)) is listed under **Recently removed** here for 10 seconds, with an Undo that brings back its history too.
- **The old addresses still work.** `/to-watch/` sends you to `/movies/` and `/history/` to `/movies/history/`, so an old bookmark is not lost.
- **Every tile is the same size.** A name is always given two lines, and a longer one is cut with "..." (hover to see the whole name). The year line is one line, so the grid looks even. (No tile has a button except on the Search page.)
- **Your stars on the tiles.** A title you gave stars shows them under the year, small and light pink, like on its page (★★★★☆). A title without stars shows nothing there, and so does one with only a note. Only your own stars show. This is the same on History and the Series tabs; Search and Home tiles never show stars.
- **Filter and sort** (card #120). Above every list on Movies (To Watch, History) and Series (all four tabs) is a small bar: **Genre** (only the genres found in that list), **My rating** (Any rating, 5 stars, 4 stars or more ... 1 star or more, Not rated), **My tag** (your own tags; left out when you have none) and **Sort** (List order, the default; Year, newest first; Year, oldest first). One genre at a time. Choosing something updates the list right away. **Clear filters** above the list shows the whole list again; when nothing matches it says "No titles match these filters." with the same link.
  - A note without stars counts as **Not rated**. Only your own stars and tags count, never another account's.
  - Sorting by year keeps the list's own order among titles of the same year, and a title with no year goes last in both sorts.
  - The choices are in the page's address (like `/movies/?genre=18&rating=4&tag=&sort=newest`), so Back and a bookmark keep them.
  - On a phone the bar starts folded under **Filter and sort**: tap it to open. It opens by itself when a filter is on. On a computer it is always open.
  - An empty list has no bar, just its usual message. A title saved before genres were kept has no genres until the nightly refresh fills them in, so until then it never matches a genre.
  - Filters only change what you see, never your data, so there is nothing to undo.
- **Add:** every search result and suggestion has a small round **+** in its poster's corner, and each movie or series page has a small "Add to To Watch" button with words under the poster. Press it and it turns into a **✓** on a tile (or "Remove from To Watch" on a title page) right away, without the page reloading. While the server works the button is grayed out and its (hidden) words say **Adding…** (or **Removing…**), so it cannot be pressed twice. A series goes on the list in about a second, however many seasons it has: its episodes and Calendar dates are collected a few seconds later (see below). The title is still on the screen after you reload, log out and back in, or restart the app.
- **Remove:** press the **✓** on a tile on the Search page (a result or a suggestion), or open the title from a To Watch list (or anywhere) and press "Remove from To Watch" under its poster. The title leaves the list. The To Watch lists themselves have no button on their tiles, so a title is never removed by accident while scrolling.
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
| `/to-watch/collect/` | Collect the episodes and dates of a series just added (sent by the page right after the add, POST only; answers 204 and nothing is shown) | Yes |
| `/to-watch/remove/` | Remove a title (button, POST only) | Yes |
| `/to-watch/undo/` | Put a removed title back (button, POST only) | Yes |

The buttons serve both sections, so they keep their addresses. Each sends `kind` (`movie` or `series`), `tmdb_id` and `next` (the page to come back to). Anything else is refused with a 400, and `next` is only followed if it is a page of this site. With no usable `next`, the browser goes back to the section of the title's kind (`SECTION_OF_KIND` in `core/views.py`).

**The two sections** (`movies` and `series` in `core/views.py`)
- Both are the same screen (`to_watch.html`) filtered by the title's kind: `ToWatchItem` entries of this account, with an empty `removed_at`, whose `title.kind` is `movie` (or `series`), newest `added_at` first. For series, entries whose series you have marked an episode of are left out (`started_series` in `core/episodes.py`), and so are those you dropped (`dropped_series`). No table changed for this.
- The tab bar is one small partial (`_section_tabs.html`) used by the To Watch screen and by History. Pico's `aria-current="page"` marks the current tab, and `couchlog.css` underlines it.
- "Recently removed" is built per kind (`_recently_removed(request, kind)`), and its undo buttons come back to that section.

**Filters** (card #120, the same on History and the Series tabs)
- `_filtered(request, rows, title_of)` in `core/views.py` takes a list already built in its own order (after `_with_my_rating`, so `my_rating` is set) and reads `genre` (a TMDB genre id), `rating` (`1` to `5` for "at least", or `none`), `tag` (a tag id) and `sort` (`newest` or `oldest`) from the address. A value that is not one of the choices (another account's tag, a genre not in the list, anything made up) is ignored. Filtering is done in Python on the list: the lists are small, and the Series tabs are worked out in Python anyway. No table changed.
- `_list_filters.html` is the bar: a `<details>` with a plain GET form. Without JavaScript a **Show** button (in `<noscript>`) sends it. With htmx a change sends it by itself (`hx-get`, `hx-trigger="change"`), swaps only `<div id="list">` (`hx-select`, `hx-target`) and puts the choices in the address (`hx-push-url`). `hx-history="false"` keeps htmx from saving a copy of the page, so Back asks Couchlog again and the list always matches the choices. `_filters_note.html` (inside `#list`) is the "Clear filters" line, a plain link to the page's own address.
- Folded on a phone: `couchlog.css` hides the summary line and shows the inside of the closed `<details>` (`::details-content`) from 576 px wide. A browser without `::details-content` keeps the summary line, so the filters can always be reached.

**Tables** (see [data model](data-model.md))
- `core_title`: the TMDB details saved when a title is first added: kind, TMDB id, name, year, poster address, description. One row per title, shared by every account, so later features (watches, episodes, calendar) can point to it. Unique on kind + TMDB id (a movie and a series can have the same number).
- `core_towatchitem`: one row per account and title: `user`, `title`, `added_at`, `removed_at`, `removed_by_watch`. Unique on user + title. `removed_at` is empty while the title is on the list. `removed_by_watch` is only filled in when the title left because it was marked as watched; entries like that are skipped by "Recently removed" and by the Undo here.

**Add** (`to_watch_add` in `core/views.py`)
- If the title is already in `core_title`, TMDB is not asked at all. Otherwise one TMDB call (`GET /movie/<id>` or `/tv/<id>`) fetches the details and they are saved (design rule 6). The list is then shown from our own table.
- First time: a new `core_towatchitem` row. Already on the list: nothing changes. Removed earlier: `removed_at` is cleared and `added_at` becomes now.
- **Dates for the [Calendar](calendar.md).** When the title is put on the list (first time, or added again after a removal), `_collect_dates` asks TMDB for them: for a movie its cinema and streaming dates (`GET /movie/<id>?append_to_response=release_dates`, which also gives its banner), for a series its episodes, status and genres (as the series page does), unless they were saved less than a day ago, and then its upcoming episodes from TVmaze (always, because opening the series page does not collect them). If TMDB or TVmaze does not answer, the title is still added and nothing is half saved; the next `refresh_calendar` run collects the dates. Pressing Add on a title already on the list asks TMDB nothing more.
- **When the dates are collected.**
  - A **movie** is collected during the add itself: its dates are one call.
  - A **series** needs a call for its seasons as well (up to 20 seasons per call since card #115, see [Series](series.md); it used to be one call per season, which took about 3 seconds for Grey's Anatomy's 24 seasons). With htmx, the add only saves the series and puts it on the list. The answer carries a hidden form (`hx-trigger="load"`) that sends a second request, `to_watch_collect`, as soon as the new button is on the page; that request runs `_collect_dates`. So the series is on the list at once and its episodes and Calendar dates are there a few seconds later (reload the Calendar to see them).
  - **Without htmx** (no JavaScript) nothing could send the second request, so the add collects everything itself, as before: slow for a long series, but complete.
  - `to_watch_collect` only works for a series that is on this account's list. If it was removed in the meantime (or was never added), nothing is collected, so the address cannot be used to ask TMDB about any title. Removing while it collects works: the episodes belong to the series, not to the list, and Undo puts the entry back as it was.
  - The series page does not wait for this. If its episodes are still missing it collects them itself (see [Series](series.md)); the worst case is that both ask TMDB at once, which is harmless because episodes are matched by TMDB's id and none is saved twice.

**Remove and undo**
- Remove only fills in `removed_at`. Undo clears it again and does not touch `added_at`, so the entry comes back exactly as it was (design rule 5; the test `test_undo_puts_everything_back_as_it_was` checks this).
- The undo window is one setting, `UNDO_WINDOW` (10 seconds) in `core/views.py`; the number shown on the screen comes from it. A To Watch list lists entries with an empty `removed_at`, newest `added_at` first, and offers Undo for entries whose `removed_at` is inside the window. The server checks the window again when Undo is pressed, so an old removal can never be undone.
- **The list empties by itself.** The "Recently removed" block (`_recently_removed.html`) carries an htmx timer (`hx-trigger="load delay:Ns"`): N is the seconds left for the oldest removal plus one. When it fires, the block asks `/to-watch/removed/?kind=...` (its own kind) for itself again, gets back only what is still undoable (nothing, once time is up), and replaces itself. The time is always worked out by the server, never by the browser's clock. While something is still undoable the new block sets the next timer; when nothing is left it has no timer. The answer is never cached.
- After the window nothing is erased: the row stays with its `removed_at`, and adding the title again clears `removed_at` and sets `added_at` to now.

**Live buttons on the search page and the title pages**
- The buttons on search results, the Search suggestions and title pages use htmx (a tile's form also sends `corner=1`, which `_answer` in `core/views.py` reads, so the answer is the round button again and a title page's answer is the one with words): the page asks the server and swaps in only the button's new state (`_to_watch_button.html`). The page does not reload and TMDB is not searched again. On a Search suggestion the tile is then replaced by the next spare suggestion (see [Search](search.md)); the add and the second request for a series work exactly as above.
- **"Adding…"** (`_to_watch_button.html`, `couchlog.css`). The button holds both wordings (on a tile's round button they are in a `visually-hidden` span: screen readers read them and the hover hint repeats them, but nobody sees them), for example `<span class="idle">Add to To Watch</span><span class="busy">Adding…</span>`. `hx-disabled-elt="find button"` makes htmx disable the button while the request runs, and htmx puts the class `htmx-request` on the form for that time: a rule in `couchlog.css` then hides `.idle` and shows `.busy`. When the answer is swapped in, the button is replaced by the new one. The ✓ on the To Watch lists are plain forms that reload the page, so they never show it.
- Without htmx the same buttons are normal forms: the server answers with a redirect back to the page and shows a message.
- Search and the title pages check your own list to know which button to show, so the right one shows after a reload. A title page whose TMDB request failed shows the error and no button.

**Same-size tiles** (`core/static/core/couchlog.css`)
- The stars line (`small.tile-stars` in `_tile_link.html`) is only there for a title with stars. The list's page gives each title its `my_rating` (`_with_my_rating` in `core/views.py`, one query for the whole list, ratings with stars only). The stars are `aria-hidden`, and screen readers hear "Your rating: 4 of 5" instead. The line does not wrap, so a rated tile is one short line taller and a phone keeps two tiles side by side (`test_the_stars_fit_on_the_tiles_of_a_list_on_a_phone`).
- A tile is a column that fills its grid cell, so a button under it (History) sits at the bottom. The name is clamped to two lines with a fixed height, the year line does not wrap, and the round button is placed on the poster, so it takes no room.
- The smallest tile width is in `rem`, not pixels, because the text grows on a big screen (Pico scales the page font with the screen width). With pixels the year line was cut off on wide screens. A browser test (`test_every_tile_is_the_same_size_whatever_the_title`) checks that all tiles are the same size and that nothing is cut.

**Known limits**
- A series added from a page with htmx is on the Calendar only after the second request has finished, a few seconds later. If the tab is closed or the network drops in those seconds, or TMDB or TVmaze does not answer, the series stays on the list and its dates wait for the next `refresh_calendar` run (or, for the episodes, for the series page to be opened).
- A title's saved details are not refreshed yet. Changes on TMDB (a new poster, a fixed year) do not reach titles already saved. Refreshing comes with later cards.
- After the 10 seconds there is no undo, only adding the title again, which resets its date added.
- Without JavaScript the block cannot empty itself. It still goes away when the page is reloaded, and Undo is refused by the server after the 10 seconds.
- A removal made on the Search page or on a title's own page (which is where every removal is made now) is only offered for undo here if you open that title's list (Movies or Series) within the 10 seconds. On those pages the ✓ (or the button with words) turns back into the + (or "Add to To Watch"), which is the same as undoing it except that the date added is reset.
- The date added is stored but not shown on screen.
