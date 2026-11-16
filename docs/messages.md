# Messages

## What it does

Couchlog never leaves you with an empty page or a button that does nothing: an empty list says what to do, a slow answer says it is on its way, and a problem says what went wrong. This page lists them all in one place (card #74, M5).

**Empty lists**

Each one speaks to someone using Couchlog for the first time: what the list is for, and the next step, with a link (**bold** below). No command names and no "TMDB" (card #116, M7).

| Where | What it says |
|---|---|
| Home, News | "Nothing from your lists comes out in the next 7 days. The **Calendar** shows what's further ahead." |
| Home, Up Next | "Up Next shows the next episode of each series you're watching. **Find a series** and mark an episode as watched to start." (also when the last card is checked off) |
| Movies or Series → To Watch | "Keep the movies you want to see here. **Search** for one and add it to your To Watch list." (or series) |
| Movies → History | "Every movie you mark as watched is kept here, with its date. **Search** for one you've seen." |
| Series → Watching | "A series shows up here once you mark one of its episodes as watched. **Search** for one you're watching." |
| Series → Finished | "Series you've watched to the end land here. See what you're **Watching**." |
| Series → Dropped | "A series you stop watching moves here. Its history is kept, and you can bring it back any time. See what you're **Watching**." |
| Calendar | "Nothing coming up. The Calendar shows the release dates of the movies and series on your lists. **Search** for something to add." |
| Search | "Nothing found for “…”. Check the spelling, or try fewer words or the original title." (no link: the box is right there) |
| A series page | "No episodes announced yet. They'll show up here once they are." (no link: there is nothing to do but wait) |

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

- **Empty lists:** each list template has its own text for an empty list (`{% else %}` or `{% empty %}`). Up Next's text is always on the page and CSS shows it only while the list has no card, so it also appears when htmx takes away the last card. `core/tests/test_empty_lists.py` opens every empty list and checks its text, its link, and that no code word (`refresh_calendar`, "command", `<code>`, "TMDB") is on the page.
- **"Searching…"** (`search.html`, `couchlog.css`): a `<p id="searching" aria-busy="true">` under the box. The box has `hx-indicator="#searching"`, so htmx gives the line the class `htmx-request` while a search is on its way, and the CSS shows the line only with that class (`display: none` otherwise, so it takes no space). `aria-busy` is what makes Pico draw the spinner. Without JavaScript it never shows (the whole page loads instead).
- **TMDB problems** are caught on the server: `core/tmdb.py` turns any failure into `TmdbError` with a message that is fine to show, and each view puts that message on the page (see [Search and title pages](search.md), [To Watch](to-watch.md), [Series](series.md)).
- **Couchlog does not answer** (`core/static/core/problems.js`, loaded on every page, and the `<p id="problem" role="alert" hidden>` in the header of `base.html`). Every button and search that updates the page in place goes through htmx, which fires an event when a request fails:
  - `htmx:sendError` (no answer at all) → "Couchlog did not answer…"
  - `htmx:responseError` (an answer with an error code, 400 or above) → "Something went wrong…"
  - `htmx:afterRequest` with a successful answer → the line is hidden again.
  - `role="alert"` makes a screen reader read the line out when it appears. Its look follows `Identity/identity.md`: off-white in a thin box, not pink, because it is not something to press.
- **Tests:** `core/tests/test_messages.py`, in a real browser with the answers faked: "Searching…" while a search is held back and gone after; a To Watch button with no answer (the line shows, nothing is saved, the next search that works takes it away); a search with no answer; and a server error (the old results stay). The empty-list and TMDB messages are tested with each page.

**Known limits**
- The line covers what htmx sends, which changes the page you are on. Anything that loads a whole new page gets the browser's own "no connection" page instead, because there is no Couchlog page to put the line on: a link in the menu, reloading, pressing Enter in the search box, or any form without JavaScript.
- A request that is very slow but does answer shows no line. Only Search shows "Searching…"; the other buttons change as soon as their answer arrives (usually well under a second).
- While the line is showing, the bar is taller, so a jump to an episode can end slightly under it.
