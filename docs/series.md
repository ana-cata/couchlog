# Series page and marking episodes

## What it does

- **The series page** (`/series/<TMDB id>/`, open it from a search result or from Series → To Watch) shows the poster, title, year and description, the To Watch button (not for a series you started: see "Remove from all lists" below), and the **seasons and episodes**.
- **Seasons** are folded away: click a season to open or close it. The first season is open when you arrive. **Specials** (TMDB's season 0) are listed last.
- **The page never moves.** Pressing a circle changes only that episode's row, in place: no reload, no jump, and the scroll position and open seasons stay as they are, even deep in a long season.
- **Each episode** shows its number, name and air date, and, if it has aired, a **round check button** on the right:
  - **Gray** = not watched. Press it to mark the episode as watched.
  - **Green** = watched. Press it again and it counts as **another time watched** (see "Watching again" below).
  - **A small "−"** sits next to a green circle. It takes back the latest watch: the undo, at any time later, with no time limit. The green circle itself no longer undoes.
  - The page shows no date for a watch. The day you pressed the button is saved (in your time zone), but Couchlog does not ask for or show a date for episodes.
- **An episode that has not aired** shows "Airs 12 Nov 2026" and has no button. One TMDB has no date for shows "No air date yet" and has no button. Whether it has aired follows your time zone: an episode airing on the 29th is already "aired" in Auckland while it is still the 28th in Lisbon.
- **Marking an episode starts the series.** From the moment one episode is marked, the series is under **Series → Watching** (see below), whether or not you ever added it to your To Watch list, and it is no longer under Series → To Watch. Un-marking that episode puts it back.
- **Many at once:** a whole season, or "did you watch the earlier episodes too?" when the episode you press skips episodes you have not marked (see the next section).
- **TMDB's status** ("Returning Series", "Ended", "Canceled"...) is shown next to the year, so you can see why a series is where it is.
- **History** (Movies → History) lists films only, so episodes you mark do not show there.
- **Your own marks:** each account sees only its own, and can only undo its own.
- **If something goes wrong** you see a message, not a crash:
  - TMDB cannot be reached the first time you open a series: a message, and nothing is saved. Try again later.
  - TMDB cannot be reached for the episodes only: the series is shown with a message, and the episodes appear the next time TMDB answers.
  - TMDB cannot be reached on a later visit (when a refresh was due): the page shows the episodes saved earlier, with a note.
  - A series TMDB does not have: the normal "page not found" screen.
  - TMDB has the series but no episodes: "TMDB has no episodes for this series yet."

## Marking a whole season, or the episodes you skipped

Two ways to enter old history quickly. Both mark only the episodes that **have aired** and that **you have not marked yet**. Episodes that have not aired, have no air date, or are already marked are left alone (one marked earlier keeps its own watch and date). Like one episode, each saves the day you pressed the button, in your time zone, with no date box. Marking starts the series (it moves to Watching), exactly as marking one episode does. Neither shows a message or a notice: the circles turning green are the feedback.

- **Mark Season 2 as watched**: a button above the episodes of each season that has at least one episode aired. The Specials have one too ("Mark Specials as watched").
  - **Press the same button again to undo it.** As soon as every episode of the season that has aired is marked (by this button, by the circles, or both), the button reads **"Mark Season 2 as not watched"**, and pressing it marks the whole season as not watched, in one step. Then it reads "as watched" again. It also flips when you tick the last episode by hand, or un-tick one.
  - Episodes that have not aired or have no date are not counted: a season is "all marked" when everything that has aired is.
  - The button is not offered as "watched" on a season that is already complete, so it cannot be pressed by accident with nothing to do. If a stale page still sends it, nothing happens and nothing is said.
- **A circle that skips episodes asks a question.** There is no extra button: you press the gray circle as always, and if episodes **between the nearest episode you marked before it and it** have aired and are not marked, a pop-up opens. With S1E1 to S1E3 marked and S1E7 pressed:
  "Did you watch the earlier episodes too? S1E7 comes after S1E3, the last episode you marked before it in Made-up Series. Did you watch everything from S1E4 up to it?" With nothing marked before it, it says "Nothing before S1E7 is marked in Made-up Series. Did you watch everything from the beginning (S1E1) up to it?" Nothing is saved until you answer:
  - **Yes, mark all 4** marks that episode **and the episodes it skips** (S1E4 to S1E7), across seasons, in the order the page lists them. Only the skipped ones: an episode you left unmarked earlier, before the nearest marked one, stays as it is.
  - **No, only S1E7** marks just that episode, as a plain single mark (the "−" next to its green circle is its undo).
  - **Cancel** closes the pop-up and saves nothing.
- **It is asked every time an episode skips something, not only on the first mark.** It is **not** asked for the episode right after one you marked, for a single missing episode between two marked ones, for a special, or for an episode that has not aired; episodes that have not aired or have no date are never counted as skipped. Episodes you marked **after** the one you press do not matter (a series you started in season 3 still asks about the seasons before it). Only your own marks count, never another account's, and specials marked on their own do not count. If you answer "No, only this one", the episodes it skipped are not asked about again when you press the next one.
- **Undoing "Yes":** there is no notice and no Undo button. When "Yes" marks every episode of a season, that season's button turns into "as not watched", which takes the season back in one step. Otherwise, un-mark episodes one at a time with the "−" buttons.
- **The page does not move.** The pop-up floats over the page, and only the rows that changed (and the season buttons whose words changed) are swapped in place: open seasons stay open and the scroll position stays.
- **If TMDB renumbers or adds episodes later,** the episodes you marked stay marked. A new episode that has aired in a season you marked makes its button say "as watched" again; pressing it marks only the new one.

## Watching again

A rewatch is one more watch with its own date (the day you pressed the button, in your time zone). It changes **only** the counts: not the progress bars, [Up Next](home.md), the Series tabs below or the [Calendar](calendar.md), because one watch is enough for an episode to count as watched (design rule 2). The one visible side effect: a series is ordered by its latest watch, so a series you watch again moves to the top of Watching and of Up Next.

- **An episode:** press its green circle again. Its row says how many times it was watched ("2×", "3×"...). No question is asked and no other episode is touched. A double click therefore adds two watches by accident; the "−" is the way back.
- **Taking one back:** the "−" next to the circle removes the latest watch of that episode, one at a time. The row's count goes down; at one watch the "−" says "Mark episode N as not watched", and pressing it makes the circle gray again.
- **A season:** once every episode of the season that has aired is watched, a button **Watch Season 2 again** appears next to the season button (also **Watch Specials again**). Each press adds one watch to **every episode of the season that has aired**, in one step, and the rows show their new counts. Episodes that have not aired or have no air date get nothing (and do not stop the button from showing). It is not offered while an aired episode is unwatched: it never marks an episode for the first time.
- **Taking back a season rewatch:** a small **"−"** next to "Watch Season N again" removes the latest watch of every episode of the season that has more than one, in one step. It shows only while some episode has more than one watch.
- **"Mark Season N as not watched"** is unchanged and erases every watch of the season, extra ones included (it is the undo of marking the season).
- **Home's check button** and the question's **"No, only this one"** are about marking an episode for the first time: on a page that is out of date, where the episode was already marked in another tab, they add nothing.
- **Your own counts:** each account has its own watches; another account's never count, and "−" only takes back your own.

## Progress bars

- **The series bar** sits above the seasons, and **each season has its own bar** in its heading, so you see it even when the season is folded. Each says "4 of 9 aired episodes watched" and fills as you watch.
- **What counts:** episodes that have **aired** (on or before today in your time zone). Specials (season 0), episodes that have not aired and episodes with no air date are left out, so a series that is completely caught up shows a full bar. The Specials have no bar. A season or series with nothing aired yet has no bar.
- **They move by themselves:** marking or un-marking an episode, marking a whole season, or answering the question changes the bars in place, with no reload, together with the rows and the season button.
- **An episode counts once** however many times it was watched (design rule 2).
- **Nothing is stored:** the bars are worked out from your watches each time, so un-marking an episode (the "−", or the season button pressed again) takes the bar back, with no undo of their own.
- The series bar is also on each card of [Home](home.md), where the next episode to watch is.

## The Series tabs

Series has four tabs, in this order: **Watching, To Watch, Finished, Dropped**. The **Series** link in the header opens the first one, Watching. The first three are worked out every time from your own watches and TMDB's status, so un-marking an episode moves a series back by itself (there is no separate undo). **Dropped** is the one you set by hand (see below), and it wins over the other three.

| Tab | A series is here when |
|---|---|
| **Watching** (`/series/watching/`) | you have marked at least one episode (any episode, a special too), it is not finished and you have not dropped it |
| **To Watch** (`/series/`) | it is on your To Watch list and you have marked **no** episode of it, and you have not dropped it |
| **Finished** (`/series/finished/`) | TMDB says it **ended or was cancelled** **and** you have watched **every episode that has aired**. Both are needed. Not if you dropped it |
| **Dropped** (`/series/dropped/`) | you pressed **Stop watching** on it and have not brought it back |

- A series you are caught up on that is **still running** stays in Watching. It is simply not in Up Next on [Home](home.md) until a new episode airs.
- A series that **ended but you have not watched completely** stays in Watching.
- **Specials** (season 0) do not have to be watched to finish a series. Episodes that have not aired yet, or have no air date, do not count either. "Aired" follows your time zone.
- If TMDB has not given a status yet (it is empty until the first refresh), the series cannot be finished: it stays in Watching.
- A rewatch of an episode counts once: an episode is watched if it has at least one watch (design rule 2).
- Watching, Finished and Dropped show plain tiles (poster, name, year) with no To Watch button. Watching and Finished list the newest-marked series first, Dropped the one dropped last first. Each says so when empty.
- Marking an episode does not touch your To Watch list: the entry stays, only hidden from the To Watch tab while the series is being watched. If you un-mark every episode of a series that is on your list, it is back under To Watch.

## Dropped series

- **Stop watching** is a button on the series page, above the seasons. It is there for a series that is in one of your tabs: one you have marked an episode of, or one on your To Watch list. A series you never touched does not show it.
- Pressing it moves the series to **Series → Dropped**, and the page says so. The series is then **in no other tab**, **not on Home** (Up Next) and **not on the [Calendar](calendar.md)**, even if it was also on your To Watch list.
- **Nothing else changes:** your watches, your progress and your To Watch entry stay exactly as they were, so your history is kept.
- **A dropped series' page** says "You stopped watching this series." and has a **Bring back** button, and the **Remove from all lists** button in the corner (see below). The episodes are still there. Marking an episode on it does **not** bring the series back: Dropped only changes with these two buttons.
- **Bring back** is the undo, at any time, with no time limit. The series goes back to the tab its watches and TMDB's status give it (To Watch, Watching or Finished), and to Up Next and the Calendar, as if it had never been dropped.
- **In [Search](search.md)** a dropped series shows "In your Dropped list" (a link to the tab) instead of the To Watch button, so there is no way to add it twice. Open it to bring it back.
- **Your own list:** each account has its own Dropped tab, and one account can never drop or bring back another's.

## Remove from all lists

For a series you want gone completely: off every list, with everything you saved about it.

- **Where:** a small **Remove from all lists** button in the **upper right corner** of the series page, level with the title. It is there **only for a dropped series**. A series under Watching or Finished does not show it (press **Stop watching** first), and neither does one that is only on your To Watch list: that one keeps its normal **Remove from To Watch** button, which works as it always did.
- **The ways a series can go**, with the buttons that do it:
  1. To Watch → Watching (mark an episode) → Finished (everything aired is watched).
  2. To Watch → Watching → Dropped (**Stop watching**).
  3. To Watch → off the list (**Remove from To Watch**).
  4. To Watch → Watching → Dropped → off every list (**Remove from all lists**). A finished series gets there the same way: Stop watching first.
- **Bring back** from Dropped puts the series back under Watching, Finished or To Watch, and the corner button goes away again.
- **A series you started has no To Watch button.** It is under Watching or Finished, so adding it to or removing it from To Watch means nothing: the button used to flip while the series stayed in its tab. The same goes for its tile in [Search](search.md). A dropped series still says "In your Dropped list".
- **It asks first.** The browser opens a question: "Remove “Made-up Series” from all your lists? Its 12 watches will be deleted, with your rating and note. You can undo for 10 seconds." **Cancel** changes nothing; **OK** removes.
- **What goes:** your **watches** of every episode (rewatches too, so the time spent on [Profile](profile.md) goes down), your **To Watch entry**, the **dropped** state, and your **rating and note**. The series itself (the saved TMDB details and episodes) is shared with other accounts and stays. Nothing of another account is touched.
- **Where you land:** Series → To Watch, with the message "Removed “…” from all your lists, with its history." and the series under **Recently removed** with an **Undo** button.
- **Undo lasts 10 seconds**, like the one for To Watch. It puts back **everything exactly as it was**: every watch with its own day, the To Watch entry as it was, the dropped state, the rating and the note. After 10 seconds the Undo goes away and the history is gone for good; the way back is marking the episodes again.
- **Undo is refused** (and says so) when the series was changed since, for example you added it to To Watch again from Search before pressing Undo. Putting the old rows back on top of new ones would overwrite what you just did, so nothing is put back.
- **Your own copy:** each account has its own, and one account can never undo another's removal.

## Keeping series up to date: `refresh_calendar`

`uv run python manage.py refresh_calendar` asks TMDB again for every series that is on someone's To Watch list or has a watched episode, and saves its **new episodes, new air dates, status** (ended or still running) **and typical episode runtime**. It also asks TVmaze for each series' upcoming episodes, and collects the cinema and streaming dates of the films on a To Watch list; both are described on the [Calendar](calendar.md) page. It also asks about a film you have **watched** when that film has no runtime saved yet (a film saved before runtimes were kept), so its minutes count in the time spent; once it has one, the film is left alone. (It was called `refresh_series` before the calendar card.)
- It prints one line per series ("“Made-up Series”: Ended, 2 new episodes") and "Refreshed N series.", then the same for films. One title failing (TMDB not answering) does not stop the others: it is reported on the error output, and the command ends with an error so a scheduler can tell. Run it again later.
- Series nobody follows are left alone.
- Running it twice changes nothing the second time.
- For now you run it **by hand**. The daily scheduled run comes with the Raspberry Pi (milestone M6). Opening a series page also refreshes that one series when its saved copy is over a day old.

## How it works

**Pages and buttons**

| Address | What | Needs login |
|---|---|---|
| `/series/watching/` | Series → Watching: the first tab, and where the **Series** link in the header goes | Yes |
| `/series/` | Series → To Watch (see the tabs above). It keeps this address; only the header link moved | Yes |
| `/series/finished/` | Series → Finished | Yes |
| `/series/dropped/` | Series → Dropped | Yes |
| `/series/drop/` | Stop watching (button, POST only). Sends `kind` (only `series`; a film is refused with a 400), `tmdb_id` and `next`. The series must already be saved (opening its page does that): otherwise "page not found" | Yes |
| `/series/bring-back/` | Bring back (button, POST only). Sends `kind`, `tmdb_id` and `next` | Yes |
| `/series/remove-all/` | Remove from all lists (button, POST only). Sends `kind` (only `series`; a film is refused with a 400) and `tmdb_id`. It always goes back to `/series/`. The series must already be saved | Yes |
| `/series/remove-all/undo/` | Undo it (button, POST only), within 10 seconds. Sends `kind`, `tmdb_id` and `next` | Yes |
| `/series/<TMDB id>/` | The series page. `?season=2` opens that season instead of the first | Yes |
| `/watched/episode/add/` | Mark one episode as watched, or watch it again when it already is (round button, POST only). Sends `episode_id` (our own id for the episode) and `next`, and `only_this` when it is the pop-up's "No, only this one" (the check buttons on [Home](home.md) also send `up_next`). An episode that skips unmarked episodes answers with the pop-up question instead of marking | Yes |
| `/watched/remove/` | Take back one watch, the undo (the "−" button, POST only). Sends `watch_id` (the episode's latest watch), `episode_id` and `next`. The same address as the movie undo | Yes |
| `/watched/season/add/` | Mark a whole season (POST only). Sends `tmdb_id` (the series), `season` (0 = Specials) and `next` | Yes |
| `/watched/season/remove/` | Mark a whole season as not watched, the season button pressed again (POST only). Sends `tmdb_id`, `season` and `next` | Yes |
| `/watched/season/again/` | Watch Season N again (POST only). Sends `tmdb_id`, `season` and `next` | Yes |
| `/watched/season/again/remove/` | Take back one season rewatch, the "−" next to it (POST only). Sends `tmdb_id`, `season` and `next` | Yes |
| `/watched/up-to/add/` | Mark an episode and the episodes it skips, the pop-up's "Yes" (POST only). Sends `episode_id` and `next` | Yes |

**In place, with htmx.** Each circle and each "−" is a form with `hx-post`, `hx-target="closest li"` and `hx-swap="outerHTML"` (`_episode_row.html`). The server saves, then answers with just that episode's row in its new state (`_episode_row` in `core/views.py`), and htmx swaps it in. Nothing else on the page is touched, so it does not move. Marking, watching again or taking one back shows no message; the circle changing colour or the count changing is the feedback. If a page is out of date (for example the episode was already un-marked in another tab), the row that comes back shows how things really are now.

**Without htmx** (no JavaScript) the same forms are normal forms: the server saves, then redirects to `next` (the same season, at the same episode, highlighted for a moment; only if it is a page of this site; the Series section otherwise). Messages for refusals ("has not aired yet", "already marked" from Home) only show in this case; with htmx the row simply shows the true state.

**Tables** (see [data model](data-model.md))
- `core_episode`: one row per episode, saved from TMDB and shared by every account: `title` (the series), `tmdb_id` (TMDB's episode id), `season_number` (0 = Specials), `episode_number`, `name`, `air_date` (empty when TMDB has none) and `runtime` (minutes; not shown on the series page, but every watch of the episode adds it to the time spent on [Profile](profile.md)). Unique on `title` + `tmdb_id`.
- `core_title` gets `episodes_refreshed_at` (when the series' episodes were last asked from TMDB) and `status` (TMDB's own word, as of that refresh; empty until then), and `runtime`: the series' typical episode runtime, the average of the runtimes of its regular-season episodes that have one, saved by each refresh (`typical_runtime` in `core/episodes.py`) for the time spent on [Profile](profile.md).
- `core_watch` gets `episode`: filled in for an episode watch (its `title` is the series), empty for a movie watch. An episode watch is its own row, like a movie watch (design rule 1).
- `core_droppedseries` (migration `0009_dropped_series`): one row per account and dropped series: `user`, `title` and `dropped_at`. Unique on `user` + `title`, so dropping twice never makes a second row. **Dropping adds this row and nothing else; bringing back deletes it.** That is why it is a true undo.
- `core_removedseries` (migration `0015_removed_series`): the copy kept for the 10-second Undo of "Remove from all lists": `user`, `title`, `removed_at` and `rows` (the deleted rows written out as text). Unique on `user` + `title`. It exists only while the Undo is possible: the Undo deletes it, and once the 10 seconds are over the next removal, the next visit to Series → To Watch or the block's own recheck deletes it.
- No table change was needed for marking many episodes: each one is an ordinary watch row, exactly like a single mark.

**Opening a series** (`_series_page` in `core/views.py`)
1. The series is saved from TMDB if our table does not have it yet (the same `_saved_title` the To Watch button uses, design rule 6).
2. If its episodes were never saved, or were saved more than a day ago (`EPISODES_REFRESH_AFTER`), they are refreshed (`refresh_episodes` in `core/episodes.py`, the same code the `refresh_calendar` command uses): TMDB is asked for the status and the list of seasons (`GET /tv/<id>`), then for each season (`GET /tv/<id>/season/<n>`), so a long series takes a few seconds the first time. Only after all of that answered are the rows saved, in one database step, so a failure saves nothing.
3. The page is built from our own table. A season that TMDB lists but cannot find (404) is skipped and the others are kept.

**The progress bars** (`_progress.html`, `progress_by_series` in `core/episodes.py`, `_season_info` in `core/views.py`)
- The series bar comes from `progress_by_series` (one database count for the series). Each season's bar is counted from that season's episodes already loaded for the page (`watched_count` and `aired_count` in `_season_info`; 0 and 0 for the Specials). Both use the same rule, and the test `test_the_bars_follow_what_is_watched_and_the_series_bar_is_the_seasons_added_up` checks they agree.
- The bar is the browser's own `<progress>` element, in a `<span id="progress-series">` or `<span id="progress-season-<number>">`. The answers to the round button, the season button and the question (`_episode_answer.html`, `_bulk_result.html`) end with the new bars marked `hx-swap-oob="true"`, which htmx puts in place of the ones with the same id, like the season buttons.

**Dropped** (`series_drop`, `series_bring_back` in `core/views.py`; `dropped_series` and `dropped_tab` in `core/episodes.py`)
- `dropped_series(user)` gives the ids of the account's dropped series. `series_tabs` leaves them out of Watching and Finished (so Up Next, which follows Watching, leaves them out too), the Series → To Watch screen excludes them, and the Calendar (`upcoming` in `core/releases.py`) leaves them out of both the Watching and the To Watch series. `dropped_tab(user)` is the Dropped tab's list.
- The series page asks `core_droppedseries` whether the series is dropped, and shows "Stop watching" only when it is not dropped and is on your list or has a watch of yours (`can_drop` in `_series_page`). Both buttons are normal forms: the server saves, then goes back to `next` with a message ("… is under Series → Dropped now. Bring it back any time." / "Brought … back. It is in its own tab again."). Dropping a series that is already dropped, or bringing back one that is not, changes nothing and says so.
- Search and the To Watch button block (`_to_watch_button.html`): the search view marks each series result you dropped (`result['dropped']`, by TMDB id and kind), and the block shows "In your Dropped list" in place of the button. TMDB is not involved; it is one question to our own table.

**Remove from all lists** (`series_remove_all`, `series_remove_all_undo` in `core/views.py`; `title.html`, `_recently_removed.html`)
- Removing collects the account's rows for the series (`_series_rows`: its watches, To Watch entry, dropped entry and rating), writes them with Django's serializer into one `core_removedseries` row (replacing an earlier copy of the same series), then deletes them, all in one database step. The serializer keeps each row's id and every date, so Undo writes back **the same rows**, watches first because a To Watch entry can point at the watch that took it off the list (`removed_by_watch`). A series with no rows at all answers "is not on any of your lists" and saves no copy.
- Undo needs the copy to be at most `UNDO_WINDOW` (10 seconds) old and the series to have none of those rows now; otherwise it says why and puts nothing back. An expired copy is deleted when someone presses Undo on it too.
- The confirmation is the browser's own `confirm()` question, asked by an `onsubmit` on a plain form (not htmx: the page then changes with a normal redirect). The question's words (`data-confirm`) come from the page: the number of watches (`watch_total`) and whether a rating is saved.
- "Recently removed" on Series → To Watch (`_recently_removed`) lists these copies with the To Watch entries removed by hand, newest first, each with its own Undo (`item.everything` tells them apart). The block's recheck deletes expired copies, so a page left open empties by itself and the history is gone.
- The button is shown when `can_remove_all`, which is true only when the series is dropped. The page is the only gate: `series_remove_all` itself still accepts any series that has rows of yours, so a hand-made request for a series under Watching would work. The To Watch button is left out when `started` (`_series_page`, and `result['started']` in the search view, from `started_series`), and the block for a started series draws nothing (`_to_watch_button.html`).

**Refreshing never loses a watch.** Episodes are matched with TMDB's own id and updated in place (number, name, date, runtime), new ones are added, and none is ever deleted. So if TMDB renumbers an episode, its watch stays on it. The test `test_a_renumbered_episode_keeps_its_watch_and_nothing_is_deleted` checks this.

**Marking** (`episode_watched_add`)
- The episode must exist (404 otherwise) and have an air date on or before today in your time zone (`_today`): otherwise a message and nothing is saved.
- If you already have a watch for it, this press is a rewatch: it skips the question and goes straight to saving. The exceptions are the requests that say they are about the first mark (`up_next` from Home, `only_this` from the pop-up): for those, an episode already watched changes nothing.
- Otherwise, unless the request has `only_this`, an episode that skips unmarked episodes asks first (see "The question" below) and saves nothing.
- One `core_watch` row is created: your account, the series, the episode, and today's date. That is the same for the first mark and every rewatch.

**Undo** (`watched_remove`) deletes that one watch, found only among your own. The "−" on an episode's row sends the id of the episode's latest watch (`_watches_by_episode` in `core/views.py` finds it and counts the watches: the latest by `created_at`, then id). Nothing else was changed by marking (the To Watch list is untouched), so everything is back as before. The tests `test_undo_puts_everything_back_as_it_was` and `test_the_minus_takes_the_latest_watch_back_until_the_circle_is_gray_again` compare all the saved rows before and after.

**Watching again** (`season_watched_again`, `season_watched_again_remove`; the logic is in `core/episodes.py`)
- `rewatch_episodes(user, episodes, today)` adds one `core_watch` row, dated today, for each episode of the season that has aired. It does nothing unless every episode that has aired already has a watch of yours (so a page that is out of date cannot mark episodes for the first time).
- `take_back_rewatch(user, episodes)` deletes the latest watch of each episode of the season that has more than one, and only those. Right after a season rewatch that is exactly the watches the rewatch added (the test `test_taking_back_a_season_rewatch_removes_exactly_the_watches_it_added` compares every saved row). If you also pressed one episode's circle again on its own, that episode keeps one more than the others: the known limit below.
- The buttons are in `_season_rewatch.html`: `season.all_marked` decides whether "Watch Season N again" shows and `season.can_take_back` (some episode has `watch_count` above 1) whether the "−" does (`_season_info` in `core/views.py`). They sit in a `season-buttons` box next to the season button and come back in the same answers as the season button (`_bulk_result.html`, `_episode_answer.html`, marked `hx-swap-oob`), so they appear and disappear without a reload.
- A rewatch changes no number that progress, Up Next, the tabs or the Calendar read: they count episodes with at least one watch. The test `test_a_rewatch_changes_no_progress_bar_no_up_next_no_tab_and_no_calendar` compares those pages before and after.

**The question** (`skipped_episodes` in `core/episodes.py`, `_question` and `_ask_earlier` in `core/views.py`, `_ask_earlier.html`)
- It is asked when the episode is a regular one (not season 0) that has aired and `skipped_episodes` finds at least one skipped episode. It walks back from the pressed episode through `episodes_up_to` (the regular seasons in page order) until it reaches an episode **you** have a watch for (specials do not count; only your own watches do). The episodes it passed that have aired by your day (and have a date) are the skipped ones, and the episode it stopped at is the "last marked" the pop-up names. Reaching the start of the series without finding one is the "nothing before it is marked" case.
- **With htmx** the server answers with the pop-up and the headers `HX-Retarget: #ask` and `HX-Reswap: innerHTML`, so htmx puts it in the empty `<div id="ask">` at the end of the seasons instead of in the episode's row. The pop-up is Pico's own `<dialog open>`, so it needs no extra JavaScript. Its Yes and No forms post with `hx-swap="none"`; the answer (`_bulk_result.html`) ends with an empty `<div id="ask" hx-swap-oob="true">`, which takes the pop-up off the page. Cancel is a `<form method="dialog">`, which closes the pop-up by itself.
- **Without htmx** the server keeps the episode's id in the session and redirects back; the series page works the question out again (so a page that is out of date asks nothing) and shows the same pop-up once.
- "Yes" is `episodes_watched_up_to`; "No, only this one" is `episode_watched_add` with `only_this`; a single mark is its own undo (the green circle).

**A whole season, or "Yes"** (`season_watched_add`, `season_watched_remove`, `episodes_watched_up_to`; the logic is in `core/episodes.py`)
- The views pick the episodes: the season's, or for "Yes" the skipped ones from `skipped_episodes` plus the chosen episode. `mark_episodes` keeps those that have aired on or before today (your time zone) and that you have no watch for, and saves one `core_watch` row for each, in one step, dated today. When there are none, nothing is saved.
- **Marking a season as not watched** (`season_watched_remove` and `unmark_episodes`) deletes your own watches of every episode of that season, in one step, and nothing else (not other seasons, not the To Watch list, not another account's marks). It is the undo of marking the season: the test `test_pressing_the_season_button_again_puts_everything_back_as_it_was` compares every saved row before and after. Marking it again later saves new watches dated that day.
- **Which words the button has** (`_season_info` in `core/views.py`): `all_marked` is true when the season has at least one episode that has aired and every one of them has a watch. The season form (`_season_action.html`) posts to `season/remove/` when it is true and to `season/add/` when not.
- **With htmx** the season and question forms use `hx-swap="none"`, and the answer (`_bulk_result.html`) is only elements marked `hx-swap-oob="true"`, which htmx puts in place of the element with the same id: each changed row (`episode-<id>`), the season's button (`season-action-<number>`, with its new words) and an empty `#ask`. So only those parts change, and nothing else moves. A circle pressed alone answers with its row (as before) and, in the same answer, its season's button (`_episode_answer.html`), so ticking the last episode flips the button without a reload.
- **Without htmx** the forms are normal forms: the server saves and redirects to `next` (the season, at its button). Nothing is said, except for a refusal ("has not aired yet", "has no air date yet").
- "Yes" for a special is refused (400), for an episode that has not aired or has no date it is refused with a message, and an unknown season is "page not found". Nothing is saved in any of these (the page does not offer the pop-up for them).

**The round button** (`_episode_row.html`, `_check_icon.html`, `couchlog.css`): the same circle and check in two colours, gray (`#8b93a0`) and green (`#2e7d32`). Each button has a text label for screen readers and a hover hint: the gray circle says "Mark episode 3 as watched", the green one "Watch episode 3 again", and the "−" says "Mark episode 3 as not watched" while it is the only watch and "Take back the latest watch of episode 3" when there are more. The count ("2×") is in the row next to the name.

**Known limits**
- The season button un-marks the **whole** season, including episodes you had marked one by one before and every extra watch. So it takes back more than the last press if you had marked some of the season before it. A season that is only partly marked can only be un-marked with the "−" buttons.
- The "−" next to "Watch Season N again" takes one watch off every episode that has more than one, and leaves an episode with a single watch alone. If the counts differ (one episode was also pressed again on its own), that episode ends one above its neighbours.
- After "Yes" there is no one-step undo unless it marked a whole season; otherwise un-mark the episodes one at a time.
- The question looks only at the nearest marked episode before the one you press. An episode you skipped earlier, before that one, is never asked about again; mark it with its circle or the season button.
- If you mark episodes far apart on purpose (say a series with fillers), each jump asks once; answer "No, only this one" to skip them.
- Pressing a circle and then reloading the page, or leaving it, without answering simply drops the question: nothing was saved.
- New episodes only appear when the series page is opened (and its copy is over a day old) or when `refresh_calendar` is run by hand. There is no daily schedule yet.
- A series that TMDB has not yet marked as ended stays in Watching even when you have watched everything, until a refresh picks up the change.
- How the tabs are worked out (`series_tabs` in `core/episodes.py`) looks at every series you have started each time a tab opens; that is fine for dozens of series.
- The series' own details (poster, description) are saved once and not refreshed.
- A very long series is slow to open the first time (one TMDB call per season).
- "Remove from all lists" cannot be undone after 10 seconds: that is the point of it. The copy of the history is kept in the database until the window is over and something deletes it (the next removal, a visit to Series → To Watch, or the block's own recheck), so it can sit there a little longer if you never come back.
- There is no confirmation on the server: the question is the browser's. Without JavaScript the button removes straight away.
- A double click on an episode's circle adds two watches (the second counts as a rewatch); the "−" takes them back one at a time. A season button, "Watch Season N again" or a "Yes" pressed twice at once does the same: an extra watch or season rewatch that the "−" buttons take back.
