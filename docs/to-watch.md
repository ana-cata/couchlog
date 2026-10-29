# To Watch list

## What it does

- **To Watch screen** (`/to-watch/`, linked as "To Watch" in the header). The movies and series you want to see, as tiles (poster, name, year, movie or series), newest added first. With an empty list it says so and links to Search.
- **Add:** every search result has an "Add to To Watch" button under its tile. Press it and the button turns into "Remove from To Watch" right away, without the results moving. The title is still on the screen after you reload, log out and back in, or restart the app.
- **Remove:** the same button on a search result, or "Remove from To Watch" under a tile on the To Watch screen. The title leaves the list.
- **Undo:** a removed title appears under **Recently removed** at the bottom of the To Watch screen, with an Undo button. Undo puts it back in its old place in the list (the date it was added is kept). The section shows the last 10 removals. It still works after reloading, and later, because nothing is erased. Adding a removed title again from search also puts it back, but as newly added (at the top of the list).
- **The same title twice:** pressing Add on something already on the list does nothing but say so. There is never a second entry.
- **Your own list:** each account has its own list. Nobody else sees yours or can change it.
- **If something goes wrong** you see a message, not a crash:
  - TMDB cannot be reached when you add a title: a message next to the button, and nothing is saved. Try again later.
  - A title TMDB does not have: the normal "page not found" screen.
- The buttons are not on the title page yet. They arrive there with the movie and series pages (features 4 and 5).

## How it works

**Pages and buttons**

| Address | What | Needs login |
|---|---|---|
| `/to-watch/` | The To Watch screen | Yes |
| `/to-watch/add/` | Add a title (button, POST only) | Yes |
| `/to-watch/remove/` | Remove a title (button, POST only) | Yes |
| `/to-watch/undo/` | Put a removed title back (button, POST only) | Yes |

Each button sends `kind` (`movie` or `series`), `tmdb_id` and `next` (the page to come back to). Anything else is refused with a 400, and `next` is only followed if it is a page of this site.

**Tables** (see [data model](data-model.md))
- `core_title`: the TMDB details saved when a title is first added: kind, TMDB id, name, year, poster address, description. One row per title, shared by every account, so later features (watches, episodes, calendar) can point to it. Unique on kind + TMDB id (a movie and a series can have the same number).
- `core_towatchitem`: one row per account and title: `user`, `title`, `added_at`, `removed_at`. Unique on user + title. `removed_at` is empty while the title is on the list.

**Add** (`to_watch_add` in `core/views.py`)
- If the title is already in `core_title`, TMDB is not asked at all. Otherwise one TMDB call (`GET /movie/<id>` or `/tv/<id>`) fetches the details and they are saved (design rule 6). The list is then shown from our own table.
- First time: a new `core_towatchitem` row. Already on the list: nothing changes. Removed earlier: `removed_at` is cleared and `added_at` becomes now.

**Remove and undo**
- Remove only fills in `removed_at`. Undo clears it again and does not touch `added_at`, so the entry comes back exactly as it was (design rule 5; the test `test_undo_puts_everything_back_as_it_was` checks this).
- The To Watch screen lists entries with an empty `removed_at`, newest `added_at` first, and offers Undo for the 10 most recent `removed_at`.

**Live buttons on the search page**
- The buttons on search results use htmx: the page asks the server and swaps in only the button's new state (`_to_watch_button.html`). The search results do not reload and TMDB is not searched again.
- Without htmx the same buttons are normal forms: the server answers with a redirect back to the page and shows a message.
- The search page marks each result as on the list or not by looking at your own list, so the right button shows after a reload.

**Known limits**
- A title's saved details are not refreshed yet. Changes on TMDB (a new poster, a fixed year) do not reach titles already saved. Refreshing comes with later cards.
- "Recently removed" shows only the last 10. Older removals can still be added again from Search.
- The date added is stored but not shown on screen.
