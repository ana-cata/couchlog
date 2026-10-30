# Calendar

## What it does

- **Calendar** in the header (`/calendar/`) lists what is coming up, earliest day first, with a heading for each month and each day. Each line has a small poster, the title (a link to its page) and what is coming.
- **What is on it:**
  - The upcoming episodes of the series in **Series → Watching** and of the series on your **To Watch** list.
  - The **cinema date** and the **streaming date** of the films on your To Watch list, so a film that is not out yet is on it as soon as TMDB knows when it reaches cinemas.
- **Only the day** is shown, never the hour. Today's releases are on it; days that have passed are not.
- **Episodes** are on the air date TMDB gives, as it gives it (no conversion). Several episodes of one series on the same day share one line: "S2E4 · Name" for one, "S2E1–E8 · 8 episodes" for several.
- **Films** have up to two lines: "In cinemas" on the cinema date and "Streaming release" on the streaming date. Couchlog takes the **earliest cinema release and the earliest streaming release TMDB lists in any country** and turns each into a day in **your time zone** (the one on your Profile page), the same way "today" is worked out. A film already in cinemas is only on its streaming date (if TMDB has one), and a date that has passed is not shown.
- **Left out:** specials (season 0), episodes with no air date, films with no cinema and no streaming date, and a film or series that is not on your To Watch list (a series you are watching is on it even if it is not on your list).
- **Removing a title** from To Watch takes it off the calendar, and Undo brings it back, because the page is worked out each time it opens. A series you are already watching stays, since it is in Watching. A film you mark as watched leaves To Watch and the calendar; "Mark as not watched" brings it back.
- **Your own calendar:** each account sees only its own series and list.
- **Empty:** "Nothing coming up" appears, with a reminder of the command below.
- **Adding a title collects its dates at once.** When you press Add to To Watch, Couchlog asks TMDB for the film's cinema and streaming dates, or for the series' episodes, so the Calendar is right straight away. A series with many seasons can make the button take a few seconds the first time.
- **The dates are not live after that.** The page only shows what was saved. Dates TMDB adds or changes later (a streaming date, new episodes) arrive when the `refresh_calendar` command runs. Run it by hand now and then; the daily run comes with the Raspberry Pi.
- **Later:** the "in 3 days" labels (Countdown) and the News section on Home are separate cards.

## How it works

**Pages**

| Address | What | Needs login |
|---|---|---|
| `/calendar/` | The upcoming releases, read from the saved data. TMDB is never asked | Yes |

**Nothing is stored for the calendar itself.** `upcoming(user, today, zone)` in `core/releases.py` works the list out each time the page is built, so a removal or an Undo shows at once and there is no undo of its own. The page never writes anything.

**Where the dates come from**
- Episodes: the existing `core_episode.air_date`, saved by `refresh_episodes` (see [Series](series.md)). The calendar takes those of season 1 and up with an air date on or after your today, for the series in Watching (`series_tabs`) and the active To Watch entries.
- Films: two columns, `core_title.cinema_at` (migration `0007_title_cinema_at`) and `core_title.streaming_at` (`0006_title_streaming_at`), see [data model](data-model.md). Each of the two that is filled in, turned into a day in your time zone, is shown when it is your today or later.

**The job: `refresh_calendar`** (`core/management/commands/refresh_calendar.py`)
- `uv run python manage.py refresh_calendar` first refreshes the series (episodes, air dates, status, as `refresh_series` did before), then asks TMDB for the films on a To Watch list.
- For a film it asks `GET /movie/<id>/release_dates` (`get_movie_releases` in `core/tmdb.py`) and saves the **earliest** entry of two kinds: types 2 and 3 (in cinemas, limited or wide) as `cinema_at`, and type 4 (streaming, "digital") as `streaming_at`. Premieres (type 1), discs (5) and TV (6) are not used. An entry with a missing or odd date is skipped. A kind TMDB has none of is emptied.
- It prints one line per film ("“Made-up Movie”: in cinemas 2026-12-16, streaming no date yet") and "Refreshed N movies." A title that fails (TMDB not answering) is reported on the error output and the others go on; at the end the command exits with an error so a scheduler can tell. A failed title keeps what was saved.
- Films that were watched, removed or that nobody has on a list are not asked about. Running it twice changes nothing the second time.

**Known limits**
- **The day can be one early for you if your time zone is west of UTC** (the Americas). TMDB gives each streaming date as midnight UTC, so a film listed for Friday shows on Thursday evening in New York. For Europe, Africa, Asia and Australia the day is the same. It is the choice made on this card.
- The earliest dates in the world are not necessarily the ones in your country. TMDB often has no streaming date for a film until shortly before it comes out, which is why the cinema date is also shown. A film with neither date is not on the calendar.
- The earliest "limited" cinema showing counts as the cinema date, so a film with a festival or special run first can show up earlier than its wide release.
- No country is used for the calendar. The time zone is only used to turn the film's date into your day.
- If TMDB does not answer at the moment you add a title, the title is added but has no dates until the next `refresh_calendar` run (or, for a series, until you open its page).
- **Only what TMDB lists is shown.** TMDB often has only the first episode of a new season (it lists one date now for Only Murders in the Building season 6, while other sites show weekly dates for all ten). The other episodes appear once TMDB adds them and the dates are refreshed. A second source for upcoming episode dates is a separate card.
- Episode dates are used as TMDB gives them: for a show from another country the day may be one off.
- The page lists every saved upcoming date; there is no limit or "next 30 days" cut.
