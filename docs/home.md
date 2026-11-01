# Home: News and Up Next

## What it does

- **Home** (`/`, the Couchlog name in the header) shows **News** (what comes out in the next days) above **Up Next**.

**News**
- **A banner** (TMDB's wide picture) for each series or film that comes out soon, with only the days left on it: "today", "tomorrow" or "in 3 days". There is no other text on the page: the title is only the picture's hidden description for screen readers. A banner opens the title's page.
- **Which titles:** exactly the ones on the [Calendar](calendar.md): the series in Watching and on To Watch, and the films on To Watch (cinema and streaming dates), including episodes only TVmaze knows. A dropped series, a title you removed from To Watch and a film you watched are not on it.
- **How soon:** less than 7 days away: today and the next 6 days. A release in 6 days is in, one in 7 days is not. The 7 is one setting (`NEWS_DAYS`, see below).
- **One banner for each title,** on its nearest day: several episodes of a series on the same day, episodes on two different days, or a film with both a cinema and a streaming date in the window are still one banner. The nearest day comes first.
- **Your day:** "today" is your day in your time zone (Profile). The same episode can be "tomorrow" in Lisbon and "today" in Auckland, and the label changes at your midnight. A film's date is turned into your day like on the Calendar.
- **A title with no banner saved** (saved before banners were kept, or TMDB has none) shows a plain box with its name, so it can still be told apart. Run `uv run python manage.py refresh_calendar` once to give the older titles their banners.
- **Nothing coming up:** "Nothing coming out in the next 7 days."
- **Undo:** News only reads what is saved and changes nothing, so there is nothing to undo.

**Up Next**
- **Up Next** is one card for each series in **Series → Watching** that has an episode left to watch.
- **A card** shows the poster, the series name (a link to its page), the **next episode** (for example `S2E4 · Name`) with its air date, a **progress bar** with "4 of 9 aired episodes watched", and a round check button on the right.
- **The next episode** is the first episode you have not watched that has already aired, in the order the series page lists them (season, then episode number). So if you marked only S3E4 ("No, only this one"), Up Next shows S1E1 until you mark it. It never shows a special (season 0), an episode that has not aired, or an episode with no air date.
- **Check it off** with the round button. The episode is marked as watched (on the day you pressed the button, in your time zone, like on the series page) and the card turns into the next episode, with the bar moved. The page does not reload or move.
- **Nothing left to watch:** when you check off the last episode that has aired, the card goes. The series stays in Watching; it comes back on Home by itself when a new episode airs (or `refresh_calendar` brings one in).
- **A finished series** (TMDB says it ended and you watched everything that has aired) is not on Home. A series on your To Watch list that you have not started is not on Home either.
- **Order:** the series you marked most recently come first.
- **Empty:** "Nothing to watch next." shows whenever the list has no card, also right after you check off the last one.
- **Undo:** there is no Undo button on Home. To take a check-off back, open the series and press the episode's green circle; that brings the episode and the bar back (see [Series](series.md)). On Home the card is back after a reload.
- **Progress bars** are also on the series page: one for the whole series and one for each season (see [Series](series.md)).
- **Your own Up Next:** each account sees only its own series and watches.
- **A dropped series** is not on Home, because Home follows the Watching tab and a dropped series is in no other tab. Bringing it back (see [Series](series.md)) puts its card back if it has an episode left to watch.

## How it works

**The News section**

- **Nothing is stored for News.** `news(user, today, zone)` in `core/releases.py` takes the Calendar's own list (`upcoming()`, which is not changed), keeps the days from `today` up to but not including `today` + `NEWS_DAYS`, and keeps each title once, on its nearest day. It returns `title`, `day` and `label` for each.
- **The label** is `countdown_label(day, today)` in the same file: "today" (0 days), "tomorrow" (1) or "in N days". It is the only place the words are made.
- **The window** is `NEWS_DAYS = 7` at the top of `core/releases.py`. It is the one place to change it; the code and the "Nothing coming out in the next 7 days." line both read it.
- **The banner** is `core_title.backdrop_url` (see [data model](data-model.md)), TMDB's `backdrop_path` at width 780 (`BACKDROP_BASE_URL` in `core/tmdb.py`). The browser loads the picture straight from TMDB's image server, like posters, with no key. It is saved when a title is saved (search result or `GET /movie|tv/<id>`), and refreshed with the dates: a series by `refresh_episodes` (the same `/tv/<id>` call) and a film by `refresh_movie` (`GET /movie/<id>?append_to_response=release_dates`, one call for the dates and the banner). If TMDB does not answer, the saved banner is kept; if TMDB has none, it is emptied.
- **Home never asks TMDB or TVmaze.** It reads what is saved, like the Calendar.
- **The template** is `home.html`; the styles are `.news`, `.banner`, `.no-banner` and `.news-days` in `couchlog.css`.

**Pages and buttons**

| Address | What | Needs login |
|---|---|---|
| `/` | Home: the News banners and the Up Next cards | Yes |
| `/watched/episode/add/` | The check button of a card (POST only). Sends `episode_id`, `up_next` and `next` (the same address as the series page's circle; `up_next` tells it the button is on Home) | Yes |

**Nothing is stored for Up Next or for the bars.** Both are worked out from your watches and the saved episodes each time the page is built, so un-marking an episode changes them by itself and there is no undo of their own. No table changed for this feature.

**The calculation** (`core/episodes.py`)
- `progress_by_series(user, series_ids, today)` gives `{series id: (watched, aired)}`. `aired` counts episodes of season 1 and up with an air date on or before `today` (your day, from your time zone). `watched` counts those that have at least one watch of yours (design rule 2), so a rewatch counts once. Specials, unaired and undated episodes are left out. The Series tabs use the same function, so a series is "Finished" by the same count the bar shows.
- `up_next(user, today)` takes the series in Watching (`series_tabs`), finds for each the first aired episode of season 1 and up with none of your watches (ordered by season, episode number, then id, like the series page), and returns one entry per series that has one: `series`, `episode`, `watched`, `aired`.

**The check button** (`episode_watched_add` in `core/views.py`, `_up_next_card.html`)
- It is the same view as the series page's circle, so the same rules apply: an episode must have aired, and one already marked is not marked twice.
- With htmx the answer is that series' card again (`_up_next_card`): the next episode, or nothing at all when the series has no episode left (htmx then removes the card). Without JavaScript the form is a normal form: the server saves and goes back to Home with the message "Marked “Series” S2E4 as watched.".
- A card on a page that is out of date shows how things really are now: pressing a card whose episode was already marked (in another tab) saves nothing and shows the card as it is.
- The "did you watch the earlier episodes too?" question is never asked from Home: the next episode is the first one you have not watched, so it skips nothing. If a stale page would trigger it (your marks changed in another tab), nothing is marked and the card comes back as it is now.

**Known limits**
- No Undo on Home (a decision on the card). Undo from the series page.
- Without JavaScript, checking off an episode reloads Home (with a message) instead of changing the card in place.
- Home works out Watching for every series you have started each time it opens; that is fine for dozens of series.
- News has the Calendar's limits: a film's day can be one early west of UTC (the Americas), and the dates are only as fresh as the last `refresh_calendar` run.
- A title's banner is the one TMDB lists first for it; there is no way to choose another.
