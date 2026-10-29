# Couchlog: project plan

_Created 2026-10-27. This is a living document: update it at the end of every week._

## 1. What we are building

Couchlog is a web app to track the movies and series I watch.

- Keep a **watchlist** of what I want to see.
- Register the **movies and episodes I have already seen**.
- See a **calendar of release dates** for everything on my list.

**Who it is for:** me. Later, maybe a few close friends. It is a personal project, not commercial, with no public sign-ups.
**Platform:** a web app that runs on my own server at home (self-hosted). I open it in a browser on my computer or phone, and can add it to the phone's home screen (a PWA). Native iOS/Android apps are out of scope.
**Guiding rule:** keep it basic and simple.

What this means in practice:

- **Data belongs to a user from day one.** Even with one user, every saved item is tied to an account, so adding friends later is a small change, not a rewrite.
- **Login stays simple.** A few accounts that I create myself. No public sign-up page.
- **No paid services and no commercial features.** This also keeps us inside TMDB's free non-commercial terms (the TMDB credit stays visible). If a feature turns out to need a paid service, it is removed from the plan.
- **Access in two stages.** Stage 1: the app runs on my home server and I use it only inside my home network. Until the MVP is finished it only runs on my PC. Stage 2 (final goal): reach it from outside the home through a VPN (a private, encrypted connection back to my home network). Stage 2 is not part of the first weeks. See section 9.

## 2. Decisions made

| Topic | Decision | Notes |
|---|---|---|
| Name | **Couchlog** (working name) | Rename later if needed; GitHub redirects the old address. Check domain and trademark before going public. |
| Repo | `ana-cata/couchlog`, private | Cloned to `C:\Users\catym\Documents\couchlog`. |
| Language | Python 3.14, managed with `uv` | Both are installed on the PC. The same Python version is used on the PC and in Docker. |
| App | Django | Login, an admin page, database migrations, sessions and per-user time zones come built in. |
| Screens | Django templates with htmx | The server builds the HTML and htmx swaps pieces of it into the page. No JavaScript app and no build step. Alpine.js only if a tiny client-side bit is needed. |
| Styling | Plain CSS with a small library (Pico CSS) | Works on a phone. No Node.js needed. |
| Database | SQLite (a database stored as one file) | Lives in a Docker volume on the Pi. Plenty for a few users. Backup means copying the file. |
| Login | Django's built-in login with a username and password. I create the accounts in Django's admin page | No public sign-up page. Sessions are stored in the same SQLite file. |
| Time zone | Stored in a `Profile` table (`core_profile`), one row per account, linked to Django's own user | Chosen over a custom user model: simpler and works with the admin page as it is. Added in card #6. |
| Home server | Raspberry Pi 4 with 4 GB RAM, 64-bit Linux, Docker 29 and Docker Compose 5 installed | Checked on 2026-10-27; SSH from my PC works. Not always on yet; it will be later. |
| Hosting | After the MVP, the app runs in a Docker container on the Pi, started with Docker Compose | Opened at the Pi's address on my home network, for example `http://<pi-address>:3000`. No domain name or HTTPS in Stage 1. |
| Deploying | Manual at first: on the Pi, pull the latest code from GitHub and rebuild the container | Automate later only if it becomes tedious. |
| Development | My Windows PC | Run and test the app on the PC with Python and `uv`, and push to GitHub. Docker Desktop is installed on the PC for testing the Docker files. The Pi comes only after the MVP is finished. |
| Calendar job | A Django command run daily by a scheduler on the Pi | Decide how at Milestone M4. It must also catch up when the Pi has been off. |
| Movie/series data | TMDB (The Movie Database) | Free for non-commercial use with a visible credit (the logo and notice on an About page). The only data source: dates are used as TMDB gives them. |
| TMDB requests | `httpx` (Python HTTP client), called only from server code | The key is read from `.env` with `python-dotenv`. It accepts TMDB's short API key or its long read access token. Added in card #3. |
| Search | One TMDB call (`search/multi`) keeps the movies and series and drops people. Results appear as you type, using htmx, 0.4 seconds after typing stops. First page only | Added in card #7. Search results are never saved. The title pages (`/movie/<id>/`, `/series/<id>/`) are read-only for now and grow into the real pages in features 4 and 5. |
| Code + tasks | GitHub (code, pull requests, project board) | |

## 3. Features

Priority uses MoSCoW: Must, Should, Could, Won't. The first version (the MVP) is the Must list only. Should features come next, then Could.

### Summary

| Priority | Features |
|---|---|
| **Must** (first version, the MVP) | Login and time zone · Search movies and series · To Watch list · Mark a movie as watched · Mark episodes as watched (one, a whole season, or "up to here") · Up Next with progress bars · Calendar of upcoming releases from my list |
| **Should** | Rewatch · Time spent watching · News section on the home page · Countdown in days · Statuses (watching / completed / dropped) · Ratings and notes · Where to watch |
| **Could** | Genre and network statistics · Favorites · Similar titles · Personalized recommendations (decided later, depending on the work) |
| **Won't (for now)** | Custom or shareable lists · Push notifications · Countdown in hours and minutes · Voting for characters · Social feed and comments · Native apps · Importing a history from another app |

### Must: the first version

**1. Login and time zone.** Username and password (Django's default login). I create the accounts myself in Django's admin page, with no public sign-up page. Every saved item belongs to an account. Each account also has a time zone, chosen directly from a list at the first login (the browser's time zone is suggested) and changeable later. A **Profile page** shows my account and my time zone (where I can change it) and has the log out button; my statistics are added to it later (feature 9). The time zone decides what "today" means for that user, so "today", "tomorrow" and "in 3 days" are right (features 10 and 11). The country used for streaming services (feature 14) and for movie release dates is taken from the time zone (for example Europe/Lisbon means Portugal).
*Done when:* I can log in and out, the pages that need a login are closed to everyone else, my time zone is saved with my account, and I can see and change it on my Profile page.

**2. Search movies and series.** A search box that asks TMDB and shows posters, titles and years. Search results are not stored; only what I add is saved.
*Done when:* typing a title shows matching movies and series, and I can open one.

**3. To Watch list.** The titles I want to see. I can add or remove a title from the search results or from its own page.
*Done when:* I add a title, reload the page and still see it, I can remove it, and I can undo the removal.

**4. Mark a movie as watched.** One button on the movie page. It saves the date (today by default, and I can change it). A watched movie leaves the To Watch list and goes into my history.
*Done when:* marking a movie moves it to my history with a date, and I can undo it.

**5. Mark episodes as watched.** On the series page, each season lists its episodes with checkboxes. Three ways to mark: one episode; a whole season; or "watched up to here", which marks every episode up to the chosen one. Episodes that have not aired yet cannot be marked. Because I cannot import my old history, this is how I will enter it, so "up to here" must be quick, and a date can be left as "unknown" for old watches.
*Done when:* each of the three ways saves the right episodes, and each can be undone (a whole season or "up to here" in one step).

**6. Up Next with progress bars.** The home screen shows, for each series I am watching, the next episode I have not seen (only episodes that have already aired). Checking it off marks it watched and the next one appears. Each series and each season shows a progress bar (watched episodes out of aired episodes).
*Done when:* after I mark an episode, the next one appears and the bar moves; a series with nothing left to watch leaves the list until a new episode airs; and undoing a check-off brings the episode and the bar back.

**7. Calendar of upcoming releases.** A calendar with the release dates of the episodes and movies I am waiting for: the series I am watching and the titles on my To Watch list. A daily task collects the dates from TMDB and saves them; the calendar screen only reads what is saved. Only the day is shown, never the hour. Dates are used exactly as TMDB gives them, with no conversion between time zones, so a day may occasionally be off by one for a show from another country. Movies use the streaming (digital) release date for the user's country (taken from the time zone). The calendar only needs to give an idea, so an approximate date is fine.
*Done when:* an upcoming episode of a series I am watching or have on my To Watch list appears on the air date TMDB gives, and removing the series removes it from the calendar.

### Should: right after the first version

**8. Rewatch.** After something is marked as watched, a "Watch again" button appears. Pressing it saves another watch with its own date, for a movie, an episode or a whole season. A rewatch does not change progress bars or Up Next, but it counts in the time spent.
*Done when:* pressing it adds a new dated watch; my history shows both; time spent grows by one more runtime; progress bars stay the same; undoing the rewatch removes only that extra watch and its time.

**9. Time spent watching.** A statistic with the total time I have spent watching, shown on the Profile page as years, months, days and hours, from TMDB runtimes and split into movies and series. Every watch counts, including rewatches. When an episode has no runtime, the series' typical episode runtime is used. The total only covers what I register in Couchlog, so it starts at zero.
*Done when:* marking a 100-minute movie adds 100 minutes, a rewatch adds another 100, and undoing a watch takes its minutes off again.

**10. News section on the home page ("coming soon").** A "News" section on the home page shows what is coming soon from my list. For each series or movie that comes out in less than a week (7 days, one setting I can change), it shows only the banner image and the days left until the release ("today", "tomorrow", "in 3 days"). Nothing else: no text and no details. It replaces push notifications. Days are counted in my own time, using my time zone (feature 1).
*Done when:* an episode airing in 3 days appears with its banner and "in 3 days", and one airing in 10 days does not.

**11. Countdown in days.** Next to an upcoming release in the calendar: the same "today", "tomorrow" or "in 3 days" label that the News section shows (feature 10). The label is built once and used in both places.
*Done when:* the label is correct, including around midnight and across time zones.

**12. Statuses.** Each series is "watching", "completed" or "dropped". Up Next only shows the ones I am watching.
*Done when:* dropping a series removes it from Up Next but keeps its history, and I can switch the status back.

**13. Ratings and notes.** A star rating and a short note for each movie or series.
*Done when:* both are saved and shown on the title's page, and I can change or remove them.

**14. Where to watch.** On a title's page, the streaming services that have it in my country (taken from my time zone, feature 1), from TMDB. TMDB's API is free for non-commercial use. This data probably needs a JustWatch credit, which I check before building it. If it turns out to need a paid service, this feature is removed from the plan.
*Done when:* the page shows the services for my country, or says none were found.

### Could: later, if I still want them

- **Genre and network statistics.** My most-watched genres and networks, from TMDB data, shown on the Profile page.
- **Favorites.** Mark movies and series as favorites and see them on the Profile page.
- **Similar titles.** On a title's page, a list of similar titles from TMDB, each with an "add to To Watch" button.
- **Personalized recommendations.** A "for you" list built from my ratings and watch history, with an "add to To Watch" button on each suggestion. Kept as a wish: I decide later whether it is worth the work. "Similar titles" is the simple first step towards it.

### Won't (for now)

| Feature | Why |
|---|---|
| Custom or shareable lists | Removed. The To Watch and Watched lists stay, as Must features. |
| Push notifications | Replaced by the News section. They would also need a secure (HTTPS) address, which we do not have before Stage 2. |
| Countdown in hours and minutes | Not needed. Only the day of the release matters. |
| Voting for characters | A social feature, with nobody to vote against. |
| Social feed and comments | Only if friends join later. |
| Native iOS/Android apps | Web app first. |
| Importing a history from another app | My TV Time export is lost. I enter my history by hand (feature 5). |

### Design rules

1. **Every watch is saved as its own entry with a date** (the date can be "unknown"). This is what makes Rewatch and Time spent possible.
2. **An episode counts as watched in progress if it has at least one watch entry.** Rewatches only add time.
3. **The 7-day News window is one setting**, not repeated in several places.
4. **The TMDB credit is shown properly:** the approved TMDB logo and the notice "This product uses the TMDB API but is not endorsed or certified by TMDB." on an About page, linked from the header next to Search and Profile. The logo is less prominent than my own app's name.
5. **Everything can be undone.** Any action that changes my data can be reversed, because I can make a mistake: marking a movie, an episode, a season or "up to here", a rewatch, adding or removing a title on the To Watch list, changing a status, a rating or a note. Undo is available right after the action and also later (for example by un-marking an episode). A bulk action (a whole season, "up to here") is undone in one step. Undo is part of every feature's "done when".
6. **Details from TMDB are saved in my own database** when I add a title (title, poster, episodes, runtimes, dates) and refreshed now and then. The app works from the saved data. Only searching and adding new titles needs TMDB to be up; if TMDB does not answer, I see a friendly message and try again later.

## 4. How we work

Until the first version (the MVP) is finished, the app only runs on my **Windows PC**. Only when the MVP is complete and everything works there do I deploy it to the **Raspberry Pi**, which then runs the real app. Nothing goes to the Pi before that.

For every feature, repeat this loop. A feature is done when it is tested and merged into `main`.

1. Take the next card on the GitHub project board (To do, Doing, Done). Each card is one feature from section 3, and its "done when" is the test.
2. Build it on a separate branch (`feature/<name>`), never directly on `main`.
3. Write the tests, and run the app on the PC (`uv run python manage.py runserver`) to try it. To check it on my phone, open the PC's address from the phone while both are on the home Wi-Fi.
4. Push the branch and open a pull request. GitHub Actions runs the checks (lint and tests) automatically.
5. Read the changes in the pull request (I do the PR for now). Merge into `main` only when the checks are green.
6. Check the "done when" conditions once more on `main` on the PC. Move the card to Done and add a line to the status log (section 10).

**Deploying to the Pi (only after the MVP is finished):**

1. Before deploying: have the Dockerfile and the Docker Compose file ready, SSH and the deploy key working on the Pi (section 9), and remember that the data on the PC is only test data, so the Pi starts with a fresh database.
2. On the Pi, pull `main`, then build and start the container (`docker compose up -d --build`).
3. Check the "done when" conditions of the MVP features on the real app, from my phone.
4. From then on, each new feature follows the loop above and is then deployed to the Pi the same way.

**Rules:**
- **`main` always works.** If a deploy breaks something, go back to the previous commit and rebuild.
- **Database changes** are written as migration files (scripted changes to the table structure) kept in the repo, so the PC and the Pi stay in step. Copy the database file before deploying a change that alters the tables.
- **Secrets** (the TMDB key and the login secret) live in a `.env` file on each machine and never in GitHub.
- **Undo is part of every card.** A feature that changes my data is not done until it can be undone (design rule 5 in section 3).
- **One card at a time**, and keep cards small: if a card takes more than a few days, split it.
- **Who does what:** I decide what to build and when it is done; Claude writes the code and tests and explains what it did.

## 5. The first weeks

Estimates assume part-time work with AI help. They are rough guesses: **re-estimate at the end of Week 4**. All of these weeks happen on my PC: nothing is deployed to the Pi until the MVP is finished (section 4).

### Week 1: Foundations and the skeleton (M0, part 1)

Goal: an empty Couchlog app runs on my PC and the project is organized.

- [x] Create the private GitHub repo
- [x] Clone it to my PC
- [x] Install Python 3.14 and `uv` (already on my PC; Node.js is not needed)
- [x] Write this plan
- [x] Commit `plan.md` and merge it through a pull request (my first one)
- [x] Create a TMDB account and request an API key (free)
- [x] Create the Django project with `uv`, a first app, htmx and Pico CSS (the skeleton)
- [x] Run it on the PC (`uv run python manage.py runserver`) and see a Couchlog placeholder page
- [x] Put the TMDB key in a local `.env` file and check that Git does not track it
- [x] Make one test request to TMDB from the app's server code to confirm the key works
- [x] Create a GitHub project board (To do / Doing / Done) with one card per Must feature from section 3

Done when: `runserver` shows the Couchlog placeholder page on my PC, the skeleton is merged into `main` on GitHub, the TMDB test request returns data, and the board has the 7 Must cards.

### Week 2: Design, database, login and automated checks (M0, part 2)

Goal: on my PC, only I can log in, and tests run automatically on every pull request. This is the heaviest week: if it runs over, the time zone picker moves to Week 3.

- [ ] Sketch the 7 screens on paper or in Figma: Home (Up Next, and News later), Search, To Watch, Movie page, Series page (seasons with episode checkboxes), Calendar, Profile (account and time zone, statistics later)
- [x] Set up the SQLite database on the PC with Django's built-in migrations (scripted table changes, section 4)
- [x] Set up Django's built-in login (username and password) and a page that only logged-in users can open
- [ ] Create my account in Django's admin page, since there is no public sign-up page
- [x] At the first login, pick my time zone from a list (the browser's time zone is suggested) and save it
- [x] Set up GitHub Actions: lint (ruff) and tests run on every pull request
- [x] Add the first simple test so the checks have something to run

Done when: I can log in and out on my PC, the pages are closed when I am logged out, my time zone is saved, and a pull request shows green checks.

### Weeks 3-4: Search and To Watch list (M1)

Goal: find a movie or series and keep it on my To Watch list.

- [x] Server code that asks TMDB for search results (the key never reaches the browser)
- [x] Search screen with results and posters (results appear as you type)
- [ ] Database table for the To Watch list: user, TMDB ID, movie or series, date added
- [ ] Save the details I need from TMDB in my database when I add a title (design rule 6 in section 3)
- [ ] Add to and remove from the To Watch list
- [ ] To Watch screen
- [x] Add an About page with the TMDB logo and the required notice, linked from the header
- [ ] Tests: search with made-up TMDB responses (done in card #7); the To Watch list saves and removes correctly

Done when: I search for a title, add it, see it on the To Watch screen after reloading, and remove it.

### Week 5: Movies watched (M2)

Goal: register the movies I have already seen.

- [ ] Movie page with details from TMDB
- [ ] "Mark as watched" with a date (today by default, and the date can be "unknown")
- [ ] Database table for watches: one entry per watch, with its own date (design rule 1 in section 3)
- [ ] Viewing history screen
- [ ] A watched movie leaves the To Watch list
- [ ] Tests for the watched/unwatched logic

Done when: I mark a movie as watched, it appears in my history with its date, and I can undo it.

### Week 6: Review, then start series (M3 begins)

- [ ] Review: what was slower or faster than estimated? Update the weeks below
- [ ] Try everything built so far on my phone, over the home Wi-Fi
- [ ] Start the Series page: seasons and episodes from TMDB
- [ ] Save watched episodes in the same watches table as movies: one entry per watch of an episode (design rule 1 in section 3)

## 6. After the first weeks

| Milestone | What we get | Rough effort |
|---|---|---|
| M3 Series | Episodes, "mark season / up to here", progress, next episode | 2-3 weeks (the hardest part) |
| M4 Calendar | Daily job that collects upcoming air dates, plus the calendar screen (the News section can follow right after) | 1-2 weeks |
| **MVP finished** | After M4, all 7 Must features work on my PC | |
| M5 Polish | Phone layout in the browser, fix rough edges, re-check every "done when" of the Must features on the PC | 1 week |
| M6 Deploy to the Pi | The "Deploying to the Pi" checklist from section 4: Dockerfile, SSH, deploy key, my data, first deploy, check on my phone | 1 week (the first time, expect surprises) |

**Rough total:** about 10-12 weeks of part-time work from Week 1 to the MVP running on the Pi (Weeks 1-5 cover M0 to M2, then M3 to M6). Re-estimate at the end of Week 4 and again after M3.

### M3: Series (about 2-3 weeks, starting in Week 6)

Goal: register the episodes I have seen and always know what to watch next.

- [ ] Series page with seasons and episodes from TMDB
- [ ] Mark one episode as watched
- [ ] Mark a whole season as watched
- [ ] "Watched up to here" marks every episode up to the chosen one
- [ ] Un-mark an episode, and undo a whole season or "up to here" in one step; episodes that have not aired yet cannot be marked
- [ ] Progress bars for each series and each season
- [ ] Home screen with Up Next: the next unwatched episode that has aired, for each series I am watching
- [ ] Tests: the "next episode" calculation; marking a season saves the right episodes; specials and episodes without an air date; episodes renumbered after I watched the season

Done when: features 5 and 6 of section 3 pass their "done when".

### M4: Calendar (about 1-2 weeks)

Goal: see the release days of everything on my list.

- [ ] Movies: use TMDB's streaming (digital) release date for my country (decided; it only needs to give an idea)
- [ ] A job that collects upcoming dates from TMDB and saves them. While I develop on the PC I run it by hand or when the app starts; on the Pi it becomes a daily task (M6)
- [ ] Calendar screen that only reads the saved dates
- [ ] Tests: episodes without a date; removing a series removes it from the calendar

Done when: feature 7 of section 3 passes its "done when".

**MVP finished** when all 7 Must features pass their "done when" on my PC.

### M5: Polish (about 1 week)

Goal: the MVP feels finished and is ready to leave my PC.

- [ ] Check the phone-sized layout, in the browser and on my phone over the home Wi-Fi
- [ ] Friendly messages for empty lists, loading, and TMDB not answering
- [ ] Re-check every "done when" of the 7 Must features
- [ ] Write a first Dockerfile and Docker Compose file and test them on the PC (Docker Desktop is installed, section 9)
- [ ] Update this plan with what I learned

Done when: I can use the whole app on my phone's browser without tripping over anything, and the Docker files build on the PC.

### M6: Deploy to the Pi (about 1 week)

Goal: Couchlog runs on the Raspberry Pi with my real data.

- [ ] Follow the "Deploying to the Pi" checklist in section 4
- [ ] SSH from my PC to the Pi works, and the Pi has a deploy key for the repo
- [ ] Start with a fresh database on the Pi (the data on the PC is only test data)
- [ ] Set up the daily calendar task on the Pi, which also runs when the Pi starts
- [ ] Set up automatic database backups and try restoring one (section 8)
- [ ] Use safe SQLite settings so a power cut cannot corrupt the database (section 8)
- [ ] Check the Must features on the Pi, from my phone

Done when: I open Couchlog on my phone at the Pi's address on the home network and all 7 Must features work.

### After M6: the Should features

One card at a time, each merged on the PC and then deployed to the Pi. Agreed order:

1. **Statuses (feature 12).** Small, and it keeps series I dropped out of Up Next while I enter my old history.
2. **News and Countdown in days (features 10 and 11).** Built together, since they share the same "in 3 days" label. They replace notifications and reuse the calendar data.
3. **Rewatch and Time spent (features 8 and 9).** They belong together, and the watches table already supports them.
4. **Where to watch (feature 14).** First check whether TMDB requires a credit for this data.
5. **Ratings and notes (feature 13).**

The order can change if something turns out harder or more useful than expected: review it after each feature. The Could features (genre and network statistics, similar titles, personalized recommendations) come after these, and I decide then whether they are worth the work.

## 7. Testing approach

| Level | What it checks | Example |
|---|---|---|
| Unit tests | One piece of logic | The "next episode" calculation |
| Integration tests | Logic with the database | Marking a season saves the right episodes |
| End-to-end tests | A full path in a real browser | Log in, search, add a series, tick an episode, see it in the calendar |
| Manual testing | Me, on the PC and on my phone over the home Wi-Fi (on the Pi after M6) | The "done when" checklist from section 3 |

**How tests work:**
- **Made-up TMDB responses.** Tests use saved example answers instead of calling the real TMDB, so they are fast and never fail because TMDB is down.
- **A separate test database.** Tests use their own temporary SQLite database, never the one with my real history.
- **A fixed "today".** Tests that depend on dates (coming soon, countdown, calendar) set the date themselves, so they give the same result every day.
- **Tools.** pytest (with pytest-django) for unit and integration tests, respx for the made-up TMDB answers, time-machine for the fixed date, Playwright for Python for end-to-end tests, and ruff for linting.
- **Where they run.** On my PC with `uv run pytest` while I build, and automatically on GitHub for every pull request (section 4). A pull request is merged only when they pass.
- **Keep it basic and simple.** Test the logic that is easy to get wrong (next episode, progress, marking a season, the day in my time zone, time spent, undo) and one main path through the screens. No need to test every button.

**Undo is tested too:** for every action that changes data, a test does it, undoes it, and checks that the data and the progress are back as they were.

**Edge cases to test early:**
- Time zones: "today" and "tomorrow" follow the user's time zone, not the server's.
- Specials, and episodes without an air date yet.
- Movie release dates differ by country and type (cinema or streaming).
- Episodes added or renumbered after a season was already watched.
- A series with no aired episodes yet, and a series where everything is watched.
- A rewatch must not change progress, and undo must work after reloading the page.
- Adding the same title twice.
- TMDB slow or not answering: a friendly message, no crash.
- "Today" and "tomorrow" around midnight, in my time zone.
- An episode with no runtime (use the series' typical runtime).

**When each level arrives:**
- Week 2: the automatic checks and the first simple test.
- M1: unit and integration tests for search and the To Watch list, and the first end-to-end test (log in, search, add a title, remove it). Each later milestone extends it.
- M3 and M4: the heaviest logic tests (next episode, seasons, time zones, undo).
- Before each milestone ends: a quick manual check against the real TMDB, to see that its answers still look like my made-up ones.

**After each deploy to the Pi (from M6):** a five-minute manual check: log in, search for a title, mark an episode and undo it, open the calendar.

## 8. Going live

"Going live" here means running on the Pi at home. It only starts after the MVP is finished (section 4).

```
My PC (build and test) -> GitHub (code) -> Raspberry Pi (Docker container: the app + a SQLite file)
                                                  |
                                  Daily task (updates the calendar from TMDB)

Stage 1: my phone and PC reach the Pi on the home Wi-Fi
Stage 2 (later): from outside the home, through a VPN
```

### Stage 1: on the home network

- **Two versions of the app:** my PC (development, with a test database) and the Pi (the real one, with my real data). There are no preview links.
- **One container.** The Pi runs the app in one Docker container (a small Python image, with gunicorn serving the app and WhiteNoise serving the CSS). The database file lives in a Docker volume outside the container, so rebuilding the app does not erase my data.
- **Address.** I open `http://<pi-address>:3000` on the home network. I give the Pi a fixed address in my router, so the bookmark on my phone keeps working.
- **Starts by itself.** The container restarts automatically when the Pi restarts, so the app is back without me doing anything.
- **Calendar task.** A daily task updates the calendar from TMDB. It also runs when the Pi starts, so the calendar is correct after the Pi was off. How it is built is decided at M4.
- **Backups.** An automatic daily copy of the database, made with SQLite's safe backup command (not a plain file copy while the app is writing), keeping the last 14 copies. The copies go somewhere other than the Pi's SD card, such as a USB drive on the Pi or my PC (decided at M6). I also make a copy before any deploy that changes the tables, and I try restoring one copy once, to be sure it works. A backup contains my account and history, so it stays private.
- **Power cuts.** The database uses safe SQLite settings, so a power cut loses at most the last action and does not corrupt the file. I shut the Pi down properly instead of unplugging it. If something still breaks, I restore the latest backup. Booting the Pi from an SSD instead of the SD card is an option later.
- **Updates.** Deploying is manual (section 4). I also update the Pi's system now and then.
- **Never open the app to the internet.** No port forwarding on the router. Reaching the app from outside is Stage 2, through a VPN.
- **Cost:** 0 EUR a month, apart from the Pi's electricity. No paid services.

### Stage 2: from outside the home (later)

- Set up a VPN to my home network (section 9), once the app works well at home. Options to compare then: Tailscale, or a VPN built into the router.
- Installing the app on the phone's home screen needs a secure (HTTPS) address, so it is solved together with the VPN.
- Friends outside my home would each need VPN access. Decide before inviting anyone.

### If other people use it

- A short privacy note saying what is stored (watch history, time zone). GDPR applies if anyone is in the EU.
- The TMDB credit stays visible.

### Before making the repo or app public

- Check the name (domain, trademark, app stores).

## 9. Risks and open questions

Sorted by when each item matters.

| When | Risk or question | What to do |
|---|---|---|
| Always | Scope creep | New ideas go to "Could" or "Won't" until the Must features are live. |
| Always | Entering my past watch history by hand will take time (no import is possible) | Make "mark a whole season" and "watched up to here" quick, and allow "date unknown" for old watches. |
| Always | TMDB terms if the app is ever commercial | Read TMDB's commercial terms before charging for anything. |
| Accepted | Release dates are used as TMDB gives them, so a day can be off by one for a show from another country | Accepted: the calendar only needs to give an idea. If it bothers me later, revisit it (for example with a second source of air times). |
| Before "Where to watch" | The streaming data (from JustWatch, through TMDB) may need its own credit, and it must be free to use | Check TMDB's documentation before building feature 14. If it turns out to need a paid service, the feature is removed from the plan. |
| M5 | Problems with the Pi only show up at the end, because I deploy only after the MVP | Write the Dockerfile before the MVP is done and test it on the PC (Docker Desktop is installed). Avoid anything that only works on Windows. Leave time after the MVP for the first deploy. |
| M6 | Building the app on the Pi may be slow or fail | The Pi has 4 GB RAM, a 64-bit OS and Docker, and SSH from my PC works, so it should work but will be slow the first time. If it fails, build the image on the PC instead. |
| M6 | The Pi has to download the code from my private GitHub repo | Set up a deploy key on the Pi (a key that only allows reading this one repo) at the first deploy, after the MVP. |
| M6 | The Pi's SD card can fail, or a power cut can damage the file | Automatic backups and safe SQLite settings (section 8). Shut the Pi down properly instead of unplugging it. Consider an SSD later. |
| M6 | The Pi is not always on yet | The daily calendar job must also run when the Pi starts, so the calendar is correct after being off. |
| Stage 2 | How do I set up a VPN to reach the home server from outside? I have little experience with this | Learn it later, with help, once the app works at home. Compare options then (for example Tailscale, or a VPN built into the home router). Not needed in the first weeks. |
| Stage 2 | Friends outside my home network would also need VPN access | Decide before inviting friends. Start with myself only. |
| Stage 2 | Installing the app on a phone needs a secure (HTTPS) address, which a plain home-network address does not have | In Stage 1 I can use the app in the phone's browser. Solve the install-to-home-screen part together with the VPN in Stage 2. |
| If it happens | Someone whose time zone is not in the country of their streaming services (for example living abroad) | Rare. If it happens, add a separate country setting later. |

## 10. Status log

| Date | Update |
|---|---|
| 2026-10-27 | Repo created and cloned, Node.js installed, plan written. |
| 2026-10-27 | Section 1 updated: personal project on my home server, maybe a few close friends later, non-commercial, basic and simple. Sections 2 and 8 still assume Vercel and Supabase and need revising. |
| 2026-10-27 | Access decided in two stages: home network only for now, VPN access from outside later (final goal). |
| 2026-10-27 | Section 2 updated: Raspberry Pi 4 (Linux, Docker) as the home server; SQLite database; the app runs in a Docker container. Vercel and Supabase dropped. |
| 2026-10-27 | Pi checked: 64-bit (aarch64), 4 GB RAM, Docker 29.9.0, Docker Compose 5.6.0. Nothing blocks the plan. |
| 2026-10-27 | Section 3 rewritten with a description and a "done when" for each feature. Decisions: Rewatch is a Should; custom lists and push notifications removed (News section on the home page instead); no import from other apps. |
| 2026-10-27 | Section 3 updated: personalized recommendations moved to Could (decided later); News section shows only the banner and days left; each account has a country, used to convert release dates to the user's time. |
| 2026-10-27 | Section 3 updated: only the release day matters, never the hour (countdown in hours and minutes dropped). The account setting is now a time zone, asked directly; the country is taken from it. |
| 2026-10-27 | Section 4 rewritten for the Pi: build and test on the PC, automatic checks on GitHub, then deploy by hand to the Pi. Preview links dropped. |
| 2026-10-27 | Order decided: build the whole MVP on my PC first; deploy to the Raspberry Pi only when the MVP is finished and everything works. Section 4 now has a separate "Deploying to the Pi" checklist. |
| 2026-10-27 | Section 5 rewritten for the PC-first order: no Vercel, Supabase or live address; Week 1 is the skeleton on the PC and a TMDB key; Week 2 adds database, login and time zone. Sketches now cover 6 screens (Home added). Section 6 now has "MVP finished", M5 Polish and M6 Deploy to the Pi. |
| 2026-10-27 | Section 6 expanded: a checklist and "done when" for each of M3 to M6, and a rough total of 10-12 weeks to the MVP on the Pi. The order of the Should features is still open. |
| 2026-10-27 | New design rule 5: everything that changes my data can be undone (a bulk action in one step). Added to the "done when" of the affected features, to the workflow rules, to the testing approach and to M3. |
| 2026-10-27 | Order of the Should features agreed and written into section 6: Statuses, News and Countdown, Rewatch and Time spent, Where to watch, Ratings and notes. |
| 2026-10-27 | Section 7 updated for the PC-first order: manual testing on the PC and phone over Wi-Fi, how tests work (made-up TMDB answers, separate test database, fixed date), when each level arrives, more edge cases, and a five-minute check after each deploy. |
| 2026-10-27 | Section 8 rewritten for the Raspberry Pi: Stage 1 on the home network (one container, fixed address, automatic restart, backups, never open the app to the internet) and Stage 2 through a VPN later. The "To revise" note in section 2 is removed. |
| 2026-10-27 | Section 9 reorganized by when each item matters (Always, M1, Before M4, M5, M6, Stage 2). New items: back up the PC database during development, depend-on-TMDB (save the details I need), TVmaze terms, streaming data credit, Pi power cuts. |
| 2026-10-27 | Decisions applied: data on the PC is only test data (the Pi starts fresh); backups are set up in M6 (automatic and daily, with safe SQLite settings against power cuts); TMDB details are saved in my database (design rule 6); movies use the streaming date and only need to give an idea; any feature that needs a paid service is removed; SSH works and Docker Desktop is installed. TMDB and TVmaze terms checked. TMDB credit now means the logo plus the required notice on an About page. |
| 2026-10-27 | TVmaze dropped: TMDB is the only data source and release dates are used as TMDB gives them, with no time zone conversion (a day may be off by one, which is accepted). The time zone setting stays, for "today", "tomorrow" and the country. |
| 2026-10-27 | Stack changed from Next.js to Python: Django with htmx, Pico CSS, uv, pytest and ruff, running in a Python Docker image on the Pi. Login is Django's built-in login (username and password), with accounts created in Django's admin page. Node.js is no longer needed. Plan PR #1 was merged into `main`; this change is on the branch `docs/django-stack`. |
| 2026-10-28 | Profile page added (account, time zone, later statistics; favorites as a Could feature). Calendar clarified: it shows the series I am watching and the titles on my To Watch list. |
| 2026-10-29 | Card #3 built (pull request open): Django skeleton with a placeholder page, Pico CSS and htmx saved in the project, `.env` for the TMDB key, and the `tmdb_check` command, which worked with my real key. Cards #4 and #6 rewritten for Django. Week 1 is done once it is merged. |
| 2026-10-29 | Card #3 merged, so Week 1 is done. Card #4 built (pull request open): ruff added to the dev tools and a GitHub Actions workflow that runs the lint and the tests on every pull request. The first simple tests came with card #3. |
| 2026-10-29 | Card #4 merged. Card #5 built (pull request open): the SQLite database and Django's built-in migrations were already working from card #3, so this card adds the proof: tests that show tests use a temporary database and never `db.sqlite3`, a test that fails if a table change has no migration file, and the first docs page (`docs/data-model.md`). |
| 2026-10-29 | Card #5 merged. Card #6 built (pull request open): login and logout, every page closed to people who are not logged in, a `Profile` table with the time zone, and the Profile page where it is chosen at the first login and changed later. Creating my own account in the admin page is still mine to do (`createsuperuser`, see the README). The time zone is only saved for now; "today" and the country come with the cards that need them. |
| 2026-10-29 | Card #6 merged. Card #7 built (pull request open): search for movies and series with results that appear as you type, shown as tiles (poster with the name below), simple read-only title pages so a result can be opened, and the About page with the TMDB logo and notice, linked from the header next to Search and Profile. Nothing is saved by search, so there is no new table. Still open in Weeks 3-4: the To Watch list (card #8). |
