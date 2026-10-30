# Home: Up Next

## What it does

- **Home** (`/`, the Couchlog name in the header) shows **Up Next**: one card for each series in **Series → Watching** that has an episode left to watch.
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
- **Dropped series** (a later card) will not show on Home, because Home follows the Watching tab.
- **Later:** the News section ("coming soon") is added to this page by a later card.

## How it works

**Pages and buttons**

| Address | What | Needs login |
|---|---|---|
| `/` | Home: the Up Next cards | Yes |
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
