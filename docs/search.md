# Search and title pages

## What it does

- **Search page** (`/search/`, linked as "Search" in the header). Type a title and matching movies and series appear below the box as you type, a moment after you stop typing. Pressing Enter also works.
- Results are shown as **tiles** in a grid: the poster on top, the name below, then the year and whether it is a movie or a series. The whole tile is a link, and when the mouse is over a tile (or you tab to it) its title and year are underlined so the choice is easy to see. The grid fits the screen (about two tiles across on a phone, more on a wide screen), and every tile is the same size: a long name is cut with "..." (hover to see it all). People (actors, directors) that TMDB also finds are left out.
- **Add to your list:** under each tile is an "Add to To Watch" button (or "Remove from To Watch" when the title is already on your list). See [To Watch](to-watch.md).
- **A series you dropped** shows "In your Dropped list" (a link to Series → Dropped) in place of the button, in the results and on its page. Open it to press **Bring back** (see [Series](series.md)).
- **Open one:** click a result to open its title page: poster, title, year, and TMDB's description, with the same To Watch button under the poster. A movie's page also has the date box and the **Mark as watched** button (see [History](history.md)). A series page also lists its seasons and episodes, each with a round check button (see [Series](series.md)).
- **Searching saves nothing.** Search results and movie pages are read from TMDB each time. Only a title you add to your To Watch list is saved, and a series is also saved the first time you open its page (with its episodes, see [Series](series.md)).
- **If something goes wrong** you see a message instead of a crash:
  - TMDB cannot be reached, or does not accept the key: a short message under the box.
  - Nothing matches: "No movies or series match ...".
  - A title that TMDB does not have: the normal "page not found" screen.
- A result with no poster shows "No poster", and one with no date shows "Year unknown".
- **Undo:** not needed, because search changes none of your data.

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

**Known limits**
- Only the first 20 results; there is no "more results" button.
- Search is in English (TMDB's default).
- The title pages show the basics, the To Watch button, and the watched section (movies) or the seasons and episodes (series). Runtimes and streaming services come with later cards.
