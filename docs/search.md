# Search and title pages

## What it does

- **Search page** (`/search/`, linked as "Search" in the header). Type a title and matching movies and series appear below the box as you type, a moment after you stop typing. Pressing Enter also works.
- **Suggestions.** While the box is empty, the page shows **Suggested movies** and **Suggested series** below it: up to 10 of each, as normal tiles (they open the title page and have the To Watch button). They are picked from what you watch and save (see below). They appear a moment after the page, they vanish as soon as you type a letter, and clearing the box brings them back. Searching for something shows the results as before.
- Results are shown as **tiles** in a grid: the poster on top, the name below, then the year and whether it is a movie or a series. The whole tile is a link, and when the mouse is over a tile (or you tab to it) its title and year are underlined so the choice is easy to see. The grid fits the screen (about two tiles across on a phone, more on a wide screen), and every tile is the same size: a long name is cut with "..." (hover to see it all). People (actors, directors) that TMDB also finds are left out.
- **Add to your list:** under each tile is an "Add to To Watch" button (or "Remove from To Watch" when the title is already on your list). See [To Watch](to-watch.md).
- **A series you dropped** shows "In your Dropped list" (a link to Series → Dropped) in place of the button, in the results and on its page. Open it to press **Bring back** (see [Series](series.md)).
- **Open one:** click a result to open its title page: poster, title, a line with the year, length and genres (below), and TMDB's description, with the same To Watch button under the poster. A movie's page also has the date box and the **Mark as watched** button (see [History](history.md)). A series page also lists its seasons and episodes, each with a round check button (see [Series](series.md)).
- **The line under the title** has what TMDB knows, with dots between the parts, and leaves out any part TMDB does not have:
  - Movie: `2023 · Movie · 1h 40min · Drama, Thriller`
  - Series: `2023 · Series · Returning Series · ~45 min per episode · Drama, Comedy`. The length is the series' typical episode length (the average of its episodes' lengths, specials left out), so it starts with `~`.
  - Lengths are written `45 min`, `1h 40min` or `2h`. With no length, no genres or no status the line is shorter, and with no year it says "Year unknown".
  - The search tiles do not show it: TMDB's search answer has no genre names.
- **← Back** (top of a title's page) takes you back to the page you opened the title from: Search, Movies (To Watch or History), Series, Home, Calendar. Coming back to Search, the box still has what you typed and the results are still there. One press is always one page back, also after you marked a film as watched, pressed "Watch again", saved a rating or pressed "Stop watching" or "Bring back" on the page. A title opened directly (a bookmark, a typed address, a new tab) has no page to go back to, so ← Back goes to Search.
- **Your rating and note** (movies and series). Under the description, a title's page shows your own stars (like "★★★★☆ 4 of 5") and your note, when you saved them. Below that, "Rate it or add a note" (or, once something is saved, an **edit icon**: a pencil over a square) opens a small form with what is saved filled in: **Stars** (1 to 5 whole stars, or "No rating") and a **Note** box (up to 500 characters), with one **Save** button.
  - **Change:** click the edit icon, pick other stars or edit the note and press Save. Saving what is already saved does nothing.
  - **Remove:** pick "No rating" to remove the stars, or empty the note box to remove the note, then Save. Each can be removed without touching the other, and "No rating" is not the same as 1 star.
  - **Any title:** you do not have to have watched it, or have it on a list. Only your own account sees and changes your rating and note.
  - **Undo:** there is no Undo button and no time limit. The edit icon is always there, so a rating or note can be changed or put back at any time by editing it again (a removed note has to be typed again).
  - Ratings are not shown on tiles or lists, and episodes and seasons cannot be rated (later, if wanted).
- **How the suggestions are picked**, for movies and for series separately:
  1. Your **3 most common genres** among the titles you have watched (a movie watched, or a series with at least one episode watched) or have on your To Watch list. Each title counts once for each of its genres, however often you watched it. On a tie the lower TMDB genre number goes first.
  2. The **most popular** titles of that kind in any of those genres, from TMDB.
  3. **Left out:** anything you have watched, anything on your To Watch list, and any series you dropped. A title you took off To Watch by hand can be suggested again.
  4. If fewer than 10 are left, or you have no genres yet (a new account, or few series registered), the rest comes from **TMDB's trending list** of the week. A title is never suggested twice, and fewer than 10 is possible.
  - Movies and series are counted apart because TMDB numbers their genres differently (Action, Sci-Fi and Fantasy are not the same number for both). Someone who has only watched movies gets trending series.
  - Your rating is not used, and neither are actors.
- **Searching saves nothing**, and neither do the suggestions. Search results, suggestions and movie pages are read from TMDB each time. Only a title you add to your To Watch list (or rate) is saved, and a series is also saved the first time you open its page (with its episodes, see [Series](series.md)).
- **If something goes wrong** you see a message instead of a crash:
  - TMDB cannot be reached, or does not accept the key: a short message under the box. For the suggestions, the message takes the place of the movies (or the series) that could not be loaded, and the other block still shows.
  - Nothing matches: "No movies or series match ...".
  - A title that TMDB does not have: the normal "page not found" screen.
- A result with no poster shows "No poster", and one with no date shows "Year unknown".
- **Undo:** not needed for search itself, because search changes none of your data. For a rating and note, editing again is the way back (see above).

## How it works

**Pages**

| Address | What | Needs login |
|---|---|---|
| `/search/?q=text` | Search box and results. Whole page, or only the results list when htmx asks | Yes |
| `/search/suggestions/` | The suggested movies and series, as a piece of page for htmx to load (not meant to be opened on its own) | Yes |
| `/movie/<TMDB id>/` | Title page of a movie | Yes |
| `/series/<TMDB id>/` | Title page of a series | Yes |

**Live results**
- The box (`core/templates/core/search.html`) uses htmx. A request goes out 0.4 seconds after typing stops (`hx-trigger="input changed delay:400ms, search"`), so TMDB is not asked on every key. A newer request cancels an older one still running (`hx-sync`), so a slow old answer never replaces a newer one.
- The address bar is updated with the search text (`hx-replace-url`), so reloading the page keeps the results.
- The `/search/` view (`core/views.py`) answers a normal request with the whole page (`search.html`) and an htmx request with only the list (`_search_results.html`). The answer is marked `Vary: HX-Request` so the browser never shows the list-only version as a page.
- Each tile (`_tile.html`, with the link part in `_tile_link.html`) is a link to the title page with the To Watch button under it (`_to_watch_button.html`, which is outside the link so a click on the button never opens the page). The view checks your To Watch list to know which button to show.
- Without JavaScript, Enter sends the form and the whole page loads with the results.
- An empty or blank search shows no results and does not call TMDB. It shows a "Loading suggestions…" line instead (`_search_results.html`), which asks `/search/suggestions/` as soon as it is on the screen (`hx-trigger="load"`). So the page and the search box never wait for TMDB, and clearing the box does the same again.

**Suggestions** (`suggest` and `top_genres` in `core/suggestions.py`, the view `search_suggestions` in `core/views.py`, `_suggestions.html`)
- `suggest(user, kind)` returns up to 10 titles shaped like search results. `top_genres` counts the genres saved on the account's titles of that kind (the `genres` column, see [Data model](data-model.md)) and keeps the 3 most common. A title saved before genres were kept has none and counts for nothing until `refresh_calendar` fills them in.
- The view asks for movies and then series, each on its own, and each in a `try`: a TMDB problem in one only shows its message in that block. The answer is marked `never_cache`, so the list is picked again each time (a title just added is then left out).
- Each tile is the same `_tile.html` as a search result, with the To Watch button swapped in place by htmx. Its form comes back to `/search/` when htmx is not there; without JavaScript the suggestions are never loaded.
- Hiding: a rule in `couchlog.css` hides `.suggestions` as soon as the box has text (`:has(input:not(:placeholder-shown))`), without waiting for the 0.4 s delay or TMDB. The results then replace the block in the page, and clearing the box loads it again. A suggestions answer that arrives after the results are already shown never reaches the screen, because the line it was meant to replace is gone (tested with a held-back answer).
- Tests: `core/tests/test_suggestions.py` (genres counted per title, per kind, per account; what is left out; the trending fill-up; a TMDB failure; hide, show and add/remove in a real browser).

**TMDB calls** (`core/tmdb.py`, server side only; the key never reaches the browser)
- `GET /search/multi?query=...` for search. Only `movie` and `tv` results are kept (`tv` is called "series" in Couchlog). Only the first page (up to 20 results) is shown.
- `GET /discover/movie` and `GET /discover/tv` for the suggestions: `with_genres` is the genre numbers joined by `|` (any of them; a comma would mean all of them) and `sort_by=popularity.desc`. `GET /trending/movie/week` and `GET /trending/tv/week` fill up what is missing. Only the first page (20 titles) of each is used. Up to four calls per load of the suggestions, one after the other (a list that is full from the genres does not ask for trending).
- `GET /movie/<id>` for a movie page, and `GET /tv/<id>` the first time a series is saved. A series page's episodes are described in [Series](series.md). The same answers carry the length and the genres, so the line under the title needs no extra call.
- TMDB's 404 becomes a "not found"; other problems become a message that is fine to show to the user.
- The year is the first four characters of TMDB's date, used as given (no time zone conversion).
- Posters are loaded by the browser straight from TMDB's picture server (`https://image.tmdb.org/t/p/w342`), the same size in the tiles and on the title page. No key is involved, but it needs an internet connection.

**The line under the title** (`title_line` in `core/title_line.py`, printed by `title.html`)
- `title_line(kind, year, status, runtime, genres)` joins the parts with ` · ` and skips an empty one. `length(minutes)` writes a length: `45 min` under an hour, `1h 40min`, and `2h` for a whole number of hours. The page text is escaped, so a genre such as "Sci-Fi & Fantasy" shows as written.
- A **movie** page is read from TMDB each time, so its length and genres come straight from that answer (also for a movie that is saved, and nothing is saved by looking). A **series** page is drawn from our saved copy (design rule 6): `runtime` (the typical episode length) and `genres` of the saved title.
- The genres are saved on the title (`genres`, a list like `[{"id": 18, "name": "Drama"}]` in TMDB's order, see [Data model](data-model.md)) wherever a title is saved: when it is added to To Watch, marked as watched or rated, and whenever a series' episodes are refreshed (its page when the saved copy is over a day old, and `refresh_calendar`).
- `refresh_calendar` also asks TMDB about a watched movie that has no runtime or no genres saved yet (a title saved before genres were kept). Run `migrate`, then `refresh_calendar` once.
- Tests: `core/tests/test_title_line.py` (movie line, series line, no length, no genres, genres saved) and the genre tests in `core/tests/test_refresh_calendar.py`.

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
- Suggestions use only the first page of each TMDB list. An account that has already watched or saved most of what is popular in its genres gets fewer than 10 (trending fills what it can). They are asked from TMDB at every load, and nothing is kept between loads.
- The suggestions need JavaScript (htmx). A title you already rated but did not watch or save can still be suggested.
- Search is in English (TMDB's default).
- The title pages show the basics, the To Watch button, your rating and note, and the watched section (movies) or the seasons and episodes (series). Streaming services come with a later card.
- A refused save (for example a note that is too long) comes back with a message but not with the text you typed, so the form shows what was saved before.
- A removed rating and note cannot be brought back with one button: the form has to be filled in again.
- A series saved before genres were kept shows its line without genres until its episodes are refreshed: when its page is opened after the saved copy is over a day old, or by `refresh_calendar`.
- A watched movie that TMDB has no genres (or no runtime) for is asked about again at every `refresh_calendar` run. That is one cheap call, and the movie page itself is not affected.
- If you open a title's address while logged out, log in, and land on it, ← Back goes to the login page (the page before it), not to Search.
