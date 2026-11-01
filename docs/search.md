# Search and title pages

## What it does

- **Search page** (`/search/`, linked as "Search" in the header). Type a title and matching movies and series appear below the box as you type, a moment after you stop typing. Pressing Enter also works.
- Results are shown as **tiles** in a grid: the poster on top, the name below, then the year and whether it is a movie or a series. The whole tile is a link, and when the mouse is over a tile (or you tab to it) its title and year are underlined so the choice is easy to see. The grid fits the screen (about two tiles across on a phone, more on a wide screen), and every tile is the same size: a long name is cut with "..." (hover to see it all). People (actors, directors) that TMDB also finds are left out.
- **Add to your list:** under each tile is an "Add to To Watch" button (or "Remove from To Watch" when the title is already on your list). See [To Watch](to-watch.md).
- **A series you dropped** shows "In your Dropped list" (a link to Series → Dropped) in place of the button, in the results and on its page. Open it to press **Bring back** (see [Series](series.md)).
- **Open one:** click a result to open its title page: poster, title, year, and TMDB's description, with the same To Watch button under the poster. A movie's page also has the date box and the **Mark as watched** button (see [History](history.md)). A series page also lists its seasons and episodes, each with a round check button (see [Series](series.md)).
- **← Back** (top of a title's page) takes you back to the page you opened the title from: Search, Movies (To Watch or History), Series, Home, Calendar. Coming back to Search, the box still has what you typed and the results are still there. One press is always one page back, also after you marked a film as watched, pressed "Watch again", saved a rating or pressed "Stop watching" or "Bring back" on the page. A title opened directly (a bookmark, a typed address, a new tab) has no page to go back to, so ← Back goes to Search.
- **Your rating and note** (movies and series). Under the description, a title's page shows your own stars (like "★★★★☆ 4 of 5") and your note, when you saved them. Below that, "Rate it or add a note" (or, once something is saved, an **edit icon**: a pencil over a square) opens a small form with what is saved filled in: **Stars** (1 to 5 whole stars, or "No rating") and a **Note** box (up to 500 characters), with one **Save** button.
  - **Change:** click the edit icon, pick other stars or edit the note and press Save. Saving what is already saved does nothing.
  - **Remove:** pick "No rating" to remove the stars, or empty the note box to remove the note, then Save. Each can be removed without touching the other, and "No rating" is not the same as 1 star.
  - **Any title:** you do not have to have watched it, or have it on a list. Only your own account sees and changes your rating and note.
  - **Undo:** there is no Undo button and no time limit. The edit icon is always there, so a rating or note can be changed or put back at any time by editing it again (a removed note has to be typed again).
  - Ratings are not shown on tiles or lists, and episodes and seasons cannot be rated (later, if wanted).
- **Searching saves nothing.** Search results and movie pages are read from TMDB each time. Only a title you add to your To Watch list (or rate) is saved, and a series is also saved the first time you open its page (with its episodes, see [Series](series.md)).
- **If something goes wrong** you see a message instead of a crash:
  - TMDB cannot be reached, or does not accept the key: a short message under the box.
  - Nothing matches: "No movies or series match ...".
  - A title that TMDB does not have: the normal "page not found" screen.
- A result with no poster shows "No poster", and one with no date shows "Year unknown".
- **Undo:** not needed for search itself, because search changes none of your data. For a rating and note, editing again is the way back (see above).

## How it works

**Pages**

| Address | What | Needs login |
|---|---|---|
| `/search/?q=text` | Search box and results. Whole page, or only the results list when htmx asks | Yes |
| `/movie/<TMDB id>/` | Title page of a movie | Yes |
| `/series/<TMDB id>/` | Title page of a series | Yes |

**Live results**
- The box (`core/templates/core/search.html`) uses htmx. A request goes out 0.4 seconds after typing stops (`hx-trigger="input changed delay:400ms, search"`), so TMDB is not asked on every key. A newer request cancels an older one still running (`hx-sync`), so a slow old answer never replaces a newer one.
- The address bar is updated with the search text (`hx-replace-url`), so reloading the page keeps the results.
- The `/search/` view (`core/views.py`) answers a normal request with the whole page (`search.html`) and an htmx request with only the list (`_search_results.html`). The answer is marked `Vary: HX-Request` so the browser never shows the list-only version as a page.
- Each tile (`_tile.html`, with the link part in `_tile_link.html`) is a link to the title page with the To Watch button under it (`_to_watch_button.html`, which is outside the link so a click on the button never opens the page). The view checks your To Watch list to know which button to show.
- Without JavaScript, Enter sends the form and the whole page loads with the results.
- An empty or blank search shows no results and does not call TMDB.

**TMDB calls** (`core/tmdb.py`, server side only; the key never reaches the browser)
- `GET /search/multi?query=...` for search. Only `movie` and `tv` results are kept (`tv` is called "series" in Couchlog). Only the first page (up to 20 results) is shown.
- `GET /movie/<id>` for a movie page, and `GET /tv/<id>` the first time a series is saved. A series page's episodes are described in [Series](series.md).
- TMDB's 404 becomes a "not found"; other problems become a message that is fine to show to the user.
- The year is the first four characters of TMDB's date, used as given (no time zone conversion).
- Posters are loaded by the browser straight from TMDB's picture server (`https://image.tmdb.org/t/p/w342`), the same size in the tiles and on the title page. No key is involved, but it needs an internet connection.

**Back link** (`title.html`, `core/static/core/back.js`)
- The link is `<a href="/search/" data-back>`. `back.js` (loaded on every page) listens for clicks on any link marked `data-back`. If this tab has an earlier page (`history.length > 1`) and the page before this one is on Couchlog (`document.referrer` starts with the site's own address), it calls `history.back()`, the browser's own Back. Otherwise it lets the link go to Search. With JavaScript off the link always goes to Search. A click with Ctrl, Shift, Alt or Cmd is left alone, so it still opens Search in a new tab.
- Going back to Search works because the search box already keeps the text in the page address (`hx-replace-url`, above), so the browser reloads `/search/?q=...`.
- Why one press is one page: the forms that used to reload the title page (Mark as watched, Watch again, Remove this watch, Save rating, Stop watching, Bring back) each added a history entry, so Back only returned to the same page. They now carry `hx-boost="true" hx-push-url="false"`: htmx sends the form in the background, the server answers as before (a redirect to the same page with a message), and htmx swaps the new page in place without adding a history entry. The To Watch button, episode and season buttons were already in place. Without JavaScript the forms still work, by reloading the page.
- Tests: `core/tests/test_back.py` (a real browser): Back from Search, from Movies → To Watch and from History, after each of those buttons, and for a title opened directly or in a new tab.

**Rating and note** (`core/templates/core/_rating.html`; the table is `core_rating`, see [Data model](data-model.md))
- The form posts to `/rating/save/` (`rating_save` in `core/views.py`) with the title's kind and TMDB id, `stars` (empty, or 1 to 5) and `note`. `RatingForm` (`core/forms.py`) checks them: stars outside 1 to 5 and a note over 500 characters are refused with a message and nothing is saved (a line break counts as one character, like in the box).
- If the title is not saved yet (a movie page is read from TMDB each time), it is saved from TMDB first, the way "Mark as watched" does (design rule 6). If TMDB does not answer, a friendly message is shown and nothing is saved. When there is nothing to change, TMDB is not asked at all.
- One row per account and title. Saving changes that row. Removing both the stars and the note deletes it, so a row only exists while something is saved.
- The form is inside a `<details>` element, so it folds away without JavaScript. Once something is saved, the part you click is only an icon, an inline SVG pencil (`summary.rating-edit` in `couchlog.css`). It has no visible words: the text "Change or remove your rating and note" is its tooltip and its name for screen readers (`aria-label`).
- There is no Undo button, so nothing counts down and nothing asks the server again. The old 10-second Undo (and its `previous_*` and `changed_at` columns) was dropped on review of the card (migration `0013_rating_without_undo`).
- Everything is looked up by the logged-in account, so one account never sees or changes another's rating. No JavaScript is needed to save, change or remove.

**Known limits**
- Only the first 20 results; there is no "more results" button.
- Search is in English (TMDB's default).
- The title pages show the basics, the To Watch button, your rating and note, and the watched section (movies) or the seasons and episodes (series). Streaming services come with a later card.
- A refused save (for example a note that is too long) comes back with a message but not with the text you typed, so the form shows what was saved before.
- A removed rating and note cannot be brought back with one button: the form has to be filled in again.
- If you open a title's address while logged out, log in, and land on it, ← Back goes to the login page (the page before it), not to Search.
