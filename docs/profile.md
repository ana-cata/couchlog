# Profile, login and time zone

## What it does

- **Log in with a username and password.** Every page needs a login. Anyone who is not logged in is sent to the login page, whichever page they try to open.
- **No sign-up page.** Accounts are created by hand in Django's admin page (`/admin/`).
- **Time zone.** The first time an account logs in, every page leads to the Profile page with the note "Choose your time zone to continue." The list suggests the time zone your browser reports. Nothing else opens until one is saved.
- **Profile page** (`/profile/`, linked as "Profile" in the header):
  - shows the username;
  - shows **Time spent watching** (see below);
  - shows the time zone and lets you change it;
  - has the Log out button.
- **Time spent watching:** the total time you have spent watching, in **Movies**, **Series** and a **Total**, as years, months, days, hours and minutes. Units that are zero are left out: a 100-minute film is "1 hour 40 minutes", and when nothing is watched yet it says "0 minutes". It only covers what you register in Couchlog, so it starts at zero.
  - **Every watch counts its runtime,** rewatches too. A film watched 3 more times adds 3 runtimes, an episode pressed twice counts twice, and "Watch Season N again" adds the runtimes of every episode of the season that has aired.
  - **An episode with no runtime** uses its series' typical episode runtime. Anything TMDB has no runtime for counts as 0 minutes.
  - **Undo:** it follows every undo by itself. Taking a watch back (Remove this watch, the "−", Mark as not watched) takes its minutes off again. There is nothing to undo on the page itself.
  - **Only your own watches count:** each account sees its own total.
- **Time zone undo:** to undo a time zone change, choose the old one again. There is no separate undo button.
- Later cards add to this page: favorites.

## How it works

**Pages**

| Address | What | Needs login |
|---|---|---|
| `/login/` | Django's built-in login form (`core/templates/core/login.html`) | No |
| `/logout/` | Logs out. It only accepts a button press (POST), not a plain link | Yes |
| `/profile/` | Username, time spent watching, time zone form, Log out button | Yes |
| `/admin/` | Django's admin page, with its own login screen | Yes |

**Closed by default**
- `LoginRequiredMiddleware` (in `MIDDLEWARE` in `config/settings.py`) sends anonymous visitors to `/login/`. A page is open only if its view is marked `@login_not_required`. Only the login page and the [About page](about.md) are. A new page is closed without anyone having to remember it.
- Django's admin page keeps its own login screen.
- After logging in you land on Home (`LOGIN_REDIRECT_URL`); after logging out you land on the login page (`LOGOUT_REDIRECT_URL`).

**Sessions**
- Who is logged in is stored in the `django_session` table of the SQLite file (Django's default). Logging out deletes the session.

**Time zone**
- Saved in the `core_profile` table, one row per account, in the `timezone` column, as a name such as `Europe/Lisbon`. See [data-model.md](data-model.md).
- The row is created when the account first opens the Profile page, and an empty time zone means "not chosen yet".
- `TimeZoneChosenMiddleware` (`core/middleware.py`) sends a logged-in account without a time zone to `/profile/`. Only the Profile page and Log out are exempt.
- The list comes from Python's time zone data and keeps only real regions (Africa, America, Antarctica, Arctic, Asia, Atlantic, Australia, Europe, Indian, Pacific) plus `UTC`. Old aliases such as `US/Eastern` are left out. The server refuses any name not in the list.
- The browser's time zone is pre-selected by a few lines of JavaScript on the Profile page, only when no time zone is saved yet.

**Time spent watching** (`core/time_spent.py`, shown by `profile` in `core/views.py`)
- **Nothing is stored for the total.** `minutes_watched(user)` works it out from your watches each time the page is built, in two database sums: your movie watches add the movie's `runtime`, and your episode watches add the episode's own `runtime` or else its series' `runtime` or else 0 (`Coalesce`). It returns `(movies, series)`, and the page adds them for the Total. It never asks TMDB (design rule 6): it reads the runtimes that were saved.
- **Where the runtimes come from** (a new `runtime` column on `core_title`, see [data model](data-model.md)):
  - a movie's runtime is saved with the title the first time it is saved from TMDB (marking it, or adding it to To Watch) and again by `refresh_calendar`;
  - a series' typical episode runtime is the **average** of the runtimes of its episodes in regular seasons that have one (specials and episodes with no runtime are left out), rounded to a whole minute. It is worked out each time the series' episodes are refreshed (opening its page when the saved copy is over a day old, or `refresh_calendar`), with no extra TMDB call;
  - each episode's own runtime was already saved with the episode.
- **The words** come from `describe(minutes)` in the same file: years, months, days, hours and minutes, with a year as 365 days and a month as 30 days (it only has to give an idea). Units that are zero are left out.
- **Titles saved before this card** have no runtime until `uv run python manage.py refresh_calendar` has run once (it now also asks about films you have watched that have no runtime saved). Until then they count as 0 minutes.

**Creating an account**
1. `uv run python manage.py createsuperuser` makes the first account (you choose the username and password in the terminal).
2. Further accounts: log in at `/admin/`, open Users, and add one.

**Known limits**
- The time zone is only saved for now. "Today", "tomorrow" and "in N days" are not applied anywhere yet; the first card that shows a date will use it.
- The country for release dates and streaming services (taken from the time zone) is not built yet. It comes with the cards that need it.
- No password reset or change page. Passwords are changed in the admin page.
- No limit on wrong password attempts. This is fine while the app only runs at home.
- Time spent: a very long episode (a finale or a feature-length special in a regular season) raises its series' typical runtime a little, since it is an average. An episode that has no runtime of its own is counted at that typical runtime, not at its real one. A film that TMDB has no runtime for counts as 0 minutes, and `refresh_calendar` asks about it again each time it runs.
- Time spent: a watch with an unknown date counts too. There is no total per year or per month, only the grand total.
