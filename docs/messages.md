# Messages

## What it does

Couchlog never leaves you with an empty page or a button that does nothing: an empty list says what to do, a slow answer says it is on its way, and a problem says what went wrong. This page lists them all in one place (card #74, M5).

**Empty lists**

| Where | What it says |
|---|---|
| Home, News | "Nothing coming out in the next 7 days." |
| Home, Up Next | "Nothing to watch next. Mark an episode of a series as watched…" (also when the last card is checked off) |
| Movies or Series → To Watch | "No movies on your To Watch list yet. Search for a movie and add it." (or series) |
| Movies → History | "Nothing in your history yet. Open a movie and press "Mark as watched"…" |
| Series → Watching, Finished, Dropped | One line each on how a series gets there (mark an episode; watch every aired episode of an ended series; press "Stop watching") |
| Calendar | "Nothing coming up." and which titles the calendar shows |
| Search | "No movies or series match …" |
| A series page | "TMDB has no episodes for this series yet." |

**Waiting**

| Where | What it says |
|---|---|
| Search, while TMDB is asked | "Searching…" with a small spinner under the box. It goes when the results arrive. |
| Search, empty box | "Loading suggestions…" until the suggestions arrive |
| Add / Remove from To Watch | The button says "Adding…" or "Removing…" and cannot be pressed twice |

**TMDB does not answer** (Couchlog answers, with a message in place of what TMDB would have given)
- "Could not reach TMDB. Check the internet connection and try again." on Search, the suggestions (only the block that failed), a title's page, and the buttons that save a title (Add to To Watch, Mark as watched, Save rating). Nothing is saved.
- A series page shows the episodes it saved earlier, with that message and "Showing the episodes saved earlier."
- "TMDB answered with an error (code …). Try again later." when TMDB answers with an error, and a note about the key when TMDB does not accept it (only you would see that one).
- Home, the lists, History and the Calendar never ask TMDB, so they work without it.

**Couchlog does not answer** (new on card #74)
- A button or a search that gets **no answer** (the phone lost the Wi-Fi, the PC or the Pi is off) shows a line just under the header bar: **"Couchlog did not answer. Check the Wi-Fi and try again."**
- One that gets an **error** from Couchlog (a crash on the server) shows **"Something went wrong. Try again."** in the same place.
- The line is in the bar at the top, so you see it wherever the page is scrolled. It goes by itself as soon as a button or a search works again. Nothing was changed, so there is nothing to undo: press the button again.

## How it works

- **Empty lists:** each list template has its own text for an empty list (`{% else %}` or `{% empty %}`). Up Next's text is always on the page and CSS shows it only while the list has no card, so it also appears when htmx takes away the last card.
- **"Searching…"** (`search.html`, `couchlog.css`): a `<p id="searching" aria-busy="true">` under the box. The box has `hx-indicator="#searching"`, so htmx gives the line the class `htmx-request` while a search is on its way, and the CSS shows the line only with that class (`display: none` otherwise, so it takes no space). `aria-busy` is what makes Pico draw the spinner. Without JavaScript it never shows (the whole page loads instead).
- **TMDB problems** are caught on the server: `core/tmdb.py` turns any failure into `TmdbError` with a message that is fine to show, and each view puts that message on the page (see [Search and title pages](search.md), [To Watch](to-watch.md), [Series](series.md)).
- **Couchlog does not answer** (`core/static/core/problems.js`, loaded on every page, and the `<p id="problem" role="alert" hidden>` in the header of `base.html`). Every button and search that updates the page in place goes through htmx, which fires an event when a request fails:
  - `htmx:sendError` (no answer at all) → "Couchlog did not answer…"
  - `htmx:responseError` (an answer with an error code, 400 or above) → "Something went wrong…"
  - `htmx:afterRequest` with a successful answer → the line is hidden again.
  - `role="alert"` makes a screen reader read the line out when it appears. Its look follows `Identity/identity.md`: off-white in a thin box, not pink, because it is not something to press.
- **Tests:** `core/tests/test_messages.py`, in a real browser with the answers faked: "Searching…" while a search is held back and gone after; a To Watch button with no answer (the line shows, nothing is saved, the next search that works takes it away); a search with no answer; and a server error (the old results stay). The empty-list and TMDB messages are tested with each page.

**Known limits**
- The line covers what htmx sends. A form that reloads the whole page (only without JavaScript) or opening a page from the menu gets the browser's own "no connection" page instead.
- A request that is very slow but does answer shows no line. Only Search shows "Searching…"; the other buttons change as soon as their answer arrives (usually well under a second).
- While the line is showing, the bar is taller, so a jump to an episode can end slightly under it.
