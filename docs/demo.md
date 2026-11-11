# The public demo

## What it does

- Anyone, for example a recruiter, opens `https://demo.ana-cata.com` and presses **Try the demo**. They get their own throwaway account, already filled with sample movies and series, and can use the app for real. No email and no password.
- The demo is a **separate copy** of Couchlog on Render's free plan, with its own database and its own login secret. It has no connection to the Pi, the home network or my real data. How to deploy it and switch it off: [deploying.md](deploying.md#the-public-demo-on-render).
- Each visitor has their own account, so nobody sees what another visitor did. Pressing the button again in another browser gives another new account.
- **Sample data:** 3 movies watched (one with an unknown date), 2 movies on To Watch (one still to come out in cinemas), Fleabag finished, Severance and Tulsa King halfway, and Chernobyl and The Rings of Power on To Watch. The dates of the watches are counted back from the visitor's today, so they always look recent. Tulsa King, The Rings of Power and Dune: Part Three keep the Calendar and News from being empty.
- A **banner** on every page says it is a demo, that it is erased regularly, and links to the code on GitHub.
- **Erased:** an account is deleted, with everything in it, 24 hours after it was made (when the next visitor starts one). After 15 minutes with no visitors Render puts the demo to sleep; the next visitor waits about a minute and the demo starts again from an empty database.
- **What it stores:** only what the visitor does in it (titles, watches, ratings, notes, the time zone) and the limit counts below. No email and no IP address, no backups. The About page says so, and the TMDB credit stays on it.
- **TVmaze is off** in the demo, so its ShareAlike licence does not come up. The demo's Calendar uses TMDB's dates only, and the About page has no TVmaze line.
- `/admin/` and the username and password form do not exist in the demo.

**The limits.** When one is reached, the visitor sees a friendly message and nothing is saved.

| Limit | Default | Setting on Render |
|---|---|---|
| Searches, per visitor | 30 an hour | `DEMO_SEARCHES_PER_HOUR` |
| Changes, per visitor | 100 a day | `DEMO_CHANGES_PER_DAY` |
| New accounts, whole demo | 50 a day (then the button says the demo is full, try again tomorrow) | `DEMO_ACCOUNTS_PER_DAY` |
| TMDB requests, whole demo | 300 an hour | `DEMO_TMDB_REQUESTS_PER_HOUR` |

- **A change** is a press that adds something: Add to To Watch, Mark as watched (a movie, an episode, a season, "up to here", Watch again), Drop and Remove from all lists.
- **Never counted and never blocked:** Undo, Remove from To Watch, Mark as not watched, the − buttons and Bring back, so everything can still be undone at the limit (design rule 5). Ratings, notes and the time zone are not counted either: each holds one entry per title, and saving again is their undo.
- "An hour" and "a day" are the last 60 minutes and the last 24 hours, not the clock's hour or day.
- **To change a limit:** on Render, open the service, **Environment**, add or change the setting, and save. Render restarts the demo with it (which also empties it). No new deploy is needed.

## How it works

- **Demo mode** is the setting `DEMO_MODE=true`. It is off by default, and off means the app works exactly as before. Only the demo's settings on Render turn it on. The limits are in `config/settings.py`, each read from its setting above.
- **Safety catch:** `config/settings.py` refuses to start in demo mode if any backup setting (`R2_…`) or Cloudflare sign-in setting (`CLOUDFLARE_ACCESS_…`) is there, so the real Couchlog can never be switched into the demo by mistake.
- `core/demo.py` holds everything else: the sample TMDB ids (`WATCHED_MOVIES`, `TO_WATCH_MOVIES`, `STARTED_SERIES`, `TO_WATCH_SERIES`), the limit counting, and `start_account`.
- **Try the demo** posts to `/demo/start/` (not found outside the demo). It sends the browser's time zone, or UTC if that is not a real one. `start_account` checks the account limit, makes sure the sample titles are saved (only the first visitor after a start asks TMDB, about 33 requests; later ones use the saved copy, and a series' episodes are asked again after a day), deletes accounts older than 24 hours (only usernames starting `demo-`), then makes the account (`demo-` and 12 random letters and digits, no usable password, the time zone chosen) with its sample rows, and signs the visitor in. If TMDB fails, no account is made and the page says to try again in a minute.
- **The login page** (`/login/`, the `login` view) shows `core/templates/core/demo_login.html` in demo mode, and ignores a username and password sent to it.
- **`/admin/`:** `DemoMiddleware` (`core/middleware.py`) answers "not found" for every address under it in demo mode.
- **Counting:** each search, change, new account and TMDB request is a row in `core_demoevent` (see [data-model.md](data-model.md)); a limit counts the rows of the last hour or day. Searches are checked in the `search` view, before TMDB is asked. Changes are checked by `@counts_as_change` on each adding view. Every TMDB request is checked in `core/tmdb.py`, so past the limit any page shows TMDB's usual friendly error with the demo's own words. Rows older than 24 hours are deleted with the old accounts.
- **The message:** a refused button with htmx gets a 429 answer ("too many requests") whose text `problems.js` shows in the line under the header. Without htmx, it goes back to the page with the message.
- **TVmaze:** `core/tvmaze.py` refuses every request in demo mode, before anything is sent. The callers already treat that like TVmaze not answering.
- **The banner and About:** `core.demo.context` gives every page `demo_mode` and `demo_repo_url`; `base.html` shows the banner and `about.html` its demo note.
- **Size:** `gunicorn.conf.py` runs one worker in demo mode (two on the Pi), to fit the free plan's 512 MB, on the port Render gives in `PORT` (8000 on the Pi).
- Tests: `core/tests/test_demo.py`.

**Known limits**
- **When the Calendar goes empty:** Tulsa King and The Rings of Power air until late 2026 and Dune: Part Three opens in December 2026. After that, swap them in `core/demo.py` for titles that air or open soon (TMDB's "On the air" list), with few seasons, so the first visitor's wait stays short.
- Two visitors pressing at the same moment can each get one search, change or account past a limit. It is a few at most.
- A visitor who logs out cannot get back into that account (it has no password). Pressing Try the demo gives a new one.
- The free plan's sleep means the first visitor after a quiet spell waits about a minute, and what earlier visitors did is gone. Accepted on card #98.
