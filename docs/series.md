# Series page and marking episodes

## What it does

- **The series page** (`/series/<TMDB id>/`, open it from a search result or from Series → To Watch) shows the poster, title, year and description, the To Watch button, and the **seasons and episodes**.
- **Seasons** are folded away: click a season to open or close it. The first season is open when you arrive. **Specials** (TMDB's season 0) are listed last.
- **The page never moves.** Pressing a circle changes only that episode's row, in place: no reload, no jump, and the scroll position and open seasons stay as they are, even deep in a long season.
- **Each episode** shows its number, name and air date, and, if it has aired, a **round check button** on the right:
  - **Gray** = not watched. Press it to mark the episode as watched.
  - **Green** = watched. Press it to mark it as not watched (the undo, at any time later, with no time limit).
  - The page shows no date for a watch. The day you pressed the button is saved (in your time zone), but Couchlog does not ask for or show a date for episodes.
- **An episode that has not aired** shows "Airs 12 Nov 2026" and has no button. One TMDB has no date for shows "No air date yet" and has no button. Whether it has aired follows your time zone: an episode airing on the 29th is already "aired" in Auckland while it is still the 28th in Lisbon.
- **Marking again does nothing:** pressing Mark on an episode that is already marked changes nothing and says so. Watching an episode again is a later feature (Rewatch).
- **Marking an episode starts the series.** From the moment one episode is marked, the series is under **Series → Watching** (see below), whether or not you ever added it to your To Watch list, and it is no longer under Series → To Watch. Un-marking that episode puts it back.
- **TMDB's status** ("Returning Series", "Ended", "Canceled"...) is shown next to the year, so you can see why a series is where it is.
- **History** (Movies → History) lists films only, so episodes you mark do not show there.
- **Your own marks:** each account sees only its own, and can only undo its own.
- **If something goes wrong** you see a message, not a crash:
  - TMDB cannot be reached the first time you open a series: a message, and nothing is saved. Try again later.
  - TMDB cannot be reached for the episodes only: the series is shown with a message, and the episodes appear the next time TMDB answers.
  - TMDB cannot be reached on a later visit (when a refresh was due): the page shows the episodes saved earlier, with a note.
  - A series TMDB does not have: the normal "page not found" screen.
  - TMDB has the series but no episodes: "TMDB has no episodes for this series yet."

## The Series tabs

Series has three tabs. Nothing is stored for them: each is worked out every time from your own watches and TMDB's status, so un-marking an episode moves a series back by itself (there is no separate undo).

| Tab | A series is here when |
|---|---|
| **To Watch** (`/series/`) | it is on your To Watch list and you have marked **no** episode of it |
| **Watching** (`/series/watching/`) | you have marked at least one episode (any episode, a special too), and it is not finished |
| **Finished** (`/series/finished/`) | TMDB says it **ended or was cancelled** **and** you have watched **every episode that has aired**. Both are needed |

- A series you are caught up on that is **still running** stays in Watching. It is simply not in Up Next until a new episode airs (Up Next comes with a later card).
- A series that **ended but you have not watched completely** stays in Watching.
- **Specials** (season 0) do not have to be watched to finish a series. Episodes that have not aired yet, or have no air date, do not count either. "Aired" follows your time zone.
- If TMDB has not given a status yet (it is empty until the first refresh), the series cannot be finished: it stays in Watching.
- A rewatch of an episode counts once: an episode is watched if it has at least one watch (design rule 2).
- Watching and Finished show plain tiles (poster, name, year) with no To Watch button, newest-marked series first. Each says so when empty.
- Marking an episode does not touch your To Watch list: the entry stays, only hidden from the To Watch tab while the series is being watched. If you un-mark every episode of a series that is on your list, it is back under To Watch.
- Dropped (a tab you set by hand) comes with a later card.

## Keeping series up to date: `refresh_series`

`uv run python manage.py refresh_series` asks TMDB again for every series that is on someone's To Watch list or has a watched episode, and saves its **new episodes, new air dates and status** (ended or still running).
- It prints one line per series ("“Made-up Series”: Ended, 2 new episodes") and "Refreshed N series." One series failing (TMDB not answering) does not stop the others: it is reported on the error output, and the command ends with an error so a scheduler can tell. Run it again later.
- Series nobody follows, and movies, are left alone.
- Running it twice changes nothing the second time.
- For now you run it **by hand**. The daily scheduled run comes with the calendar and the Raspberry Pi. Opening a series page also refreshes that one series when its saved copy is over a day old.

## How it works

**Pages and buttons**

| Address | What | Needs login |
|---|---|---|
| `/series/` | Series → To Watch (see the tabs above) | Yes |
| `/series/watching/` | Series → Watching | Yes |
| `/series/finished/` | Series → Finished | Yes |
| `/series/<TMDB id>/` | The series page. `?season=2` opens that season instead of the first | Yes |
| `/watched/episode/add/` | Mark one episode as watched (round button, POST only). Sends `episode_id` (our own id for the episode) and `next` | Yes |
| `/watched/remove/` | Mark as not watched, the undo (round button, POST only). Sends `watch_id`, `episode_id` and `next`. The same address as the movie undo | Yes |

**In place, with htmx.** Each circle is a form with `hx-post`, `hx-target="closest li"` and `hx-swap="outerHTML"` (`_episode_row.html`). The server saves, then answers with just that episode's row in its new state (`_episode_row` in `core/views.py`), and htmx swaps it in. Nothing else on the page is touched, so it does not move. Marking or un-marking shows no message; the circle changing colour is the feedback. If a page is out of date (for example the episode was already un-marked in another tab), the row that comes back shows how things really are now.

**Without htmx** (no JavaScript) the same forms are normal forms: the server saves, then redirects to `next` (the same season, at the same episode, highlighted for a moment; only if it is a page of this site; the Series section otherwise). Messages for refusals ("has not aired yet", "already marked") only show in this case; with htmx the row simply shows the true state.

**Tables** (see [data model](data-model.md))
- `core_episode`: one row per episode, saved from TMDB and shared by every account: `title` (the series), `tmdb_id` (TMDB's episode id), `season_number` (0 = Specials), `episode_number`, `name`, `air_date` (empty when TMDB has none) and `runtime` (minutes; not shown yet, for the time-spent feature). Unique on `title` + `tmdb_id`.
- `core_title` gets `episodes_refreshed_at` (when the series' episodes were last asked from TMDB) and `status` (TMDB's own word, as of that refresh; empty until then).
- `core_watch` gets `episode`: filled in for an episode watch (its `title` is the series), empty for a movie watch. An episode watch is its own row, like a movie watch (design rule 1).

**Opening a series** (`_series_page` in `core/views.py`)
1. The series is saved from TMDB if our table does not have it yet (the same `_saved_title` the To Watch button uses, design rule 6).
2. If its episodes were never saved, or were saved more than a day ago (`EPISODES_REFRESH_AFTER`), they are refreshed (`refresh_episodes` in `core/episodes.py`, the same code the `refresh_series` command uses): TMDB is asked for the status and the list of seasons (`GET /tv/<id>`), then for each season (`GET /tv/<id>/season/<n>`), so a long series takes a few seconds the first time. Only after all of that answered are the rows saved, in one database step, so a failure saves nothing.
3. The page is built from our own table. A season that TMDB lists but cannot find (404) is skipped and the others are kept.

**Refreshing never loses a watch.** Episodes are matched with TMDB's own id and updated in place (number, name, date, runtime), new ones are added, and none is ever deleted. So if TMDB renumbers an episode, its watch stays on it. The test `test_a_renumbered_episode_keeps_its_watch_and_nothing_is_deleted` checks this.
**Marking** (`episode_watched_add`)
- The episode must exist (404 otherwise) and have an air date on or before today in your time zone (`_today`): otherwise a message and nothing is saved. If you already have a watch for it, nothing changes.
- Otherwise one `core_watch` row is created: your account, the series, the episode, and today's date.

**Undo** (`watched_remove`) deletes that one watch, found only among your own. Nothing else was changed by marking (the To Watch list is untouched), so everything is back as before. The test `test_undo_puts_everything_back_as_it_was` compares all the saved rows before and after.

**The round button** (`_episode_row.html`, `_check_icon.html`, `couchlog.css`): the same circle and check in two colours, gray (`#8b93a0`) and green (`#2e7d32`). Each button has a text label for screen readers ("Mark episode 3 as watched" / "...as not watched") and a hover hint.

**Known limits**
- No progress bars and no "next episode" yet (Up Next, card #11). No "whole season" or "watched up to here" yet (card #25).
- New episodes only appear when the series page is opened (and its copy is over a day old) or when `refresh_series` is run by hand. There is no daily schedule yet.
- A series that TMDB has not yet marked as ended stays in Watching even when you have watched everything, until a refresh picks up the change.
- How the tabs are worked out (`series_tabs` in `core/episodes.py`) looks at every series you have started each time a tab opens; that is fine for dozens of series.
- The series' own details (poster, description) are saved once and not refreshed.
- A very long series is slow to open the first time (one TMDB call per season).
- A double click on a Mark button at the very same moment could save two watches for one episode; Un-mark then removes one at a time.
