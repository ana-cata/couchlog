# Search and title pages

## What it does

- **Search page** (`/search/`, linked as "Search" in the header). Type a title and matching movies and series appear below the box as you type, a moment after you stop typing. Pressing Enter also works.
- Each result shows the poster, the title, the year and whether it is a movie or a series. People (actors, directors) that TMDB also finds are left out.
- **Open one:** click a result to open its title page. For now it is a simple read-only page: poster, title, year, and TMDB's description. Later cards turn it into the real movie and series pages, with the buttons to add it to the To Watch list and mark it watched.
- **Nothing is saved.** Search results and title pages are read from TMDB each time. Only what you add to your lists is saved, and that comes with later cards.
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
- Without JavaScript, Enter sends the form and the whole page loads with the results.
- An empty or blank search shows no results and does not call TMDB.

**TMDB calls** (`core/tmdb.py`, server side only; the key never reaches the browser)
- `GET /search/multi?query=...` for search. Only `movie` and `tv` results are kept (`tv` is called "series" in Couchlog). Only the first page (up to 20 results) is shown.
- `GET /movie/<id>` and `GET /tv/<id>` for a title page.
- TMDB's 404 becomes a "not found"; other problems become a message that is fine to show to the user.
- The year is the first four characters of TMDB's date, used as given (no time zone conversion).
- Posters are loaded by the browser straight from TMDB's picture server (`https://image.tmdb.org/t/p/`): small ones in the list (width 185), larger on the title page (width 342). No key is involved, but it needs an internet connection.

**Known limits**
- Only the first 20 results; there is no "more results" button.
- Search is in English (TMDB's default).
- The title pages show only the basics. Seasons, episodes, runtimes and streaming services come with later cards.
