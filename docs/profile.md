# Profile, login and time zone

## What it does

- **Two ways in, one account.** Every page needs a login, and what you see depends on the address you opened. Your history is the same either way.
  - **At home** (`http://<pi-address>:3000`): a username and password. Anyone who is not logged in is sent to the login page, whichever page they try to open.
  - **From outside** (`https://couchlog.ana-cata.com`): only your email and the one-time code Cloudflare sends. There is no password and no Couchlog login page.
- **No sign-up page.** The first time an email on the allow list signs in from outside, its account is created by itself, empty and with no password. Other accounts are created by hand in Django's admin page (`/admin/`), which only opens from the home address.
- **Friends** only ever come in by email code. Each account sees only its own data.
- **Log out** at home goes back to the login page. From outside it also ends the Cloudflare session, so the next visit asks for a new code.
- **If you cannot get in,** a "Cannot sign in" page says why, for example a deactivated account or two accounts with the same email.
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
| `/login/` | Django's built-in login form (`core/templates/core/login.html`). On the Cloudflare address it just leads to Home | No |
| `/logout/` | Logs out. It only accepts a button press (POST), not a plain link | Yes |
| `/profile/` | Username, time spent watching, time zone form, Log out button | Yes |
| `/admin/` | Django's admin page, with its own login screen. Refused on the Cloudflare address | Yes |

**Sign-in by email code** (`CloudflareSignInMiddleware` in `core/middleware.py`, `core/cloudflare_access.py`, package `PyJWT`)
- **Off unless set up.** With the three `CLOUDFLARE_ACCESS_` settings empty, as on the PC, none of this runs. If only some are set, the app refuses to start ([deploying.md](deploying.md)).
- **Which address.** A request counts as the Cloudflare address when its host, without any port, equals `CLOUDFLARE_ACCESS_ADDRESS`. On any other address the token header is not read, so a made-up header at home signs nobody in.
- **On every request** to the Cloudflare address, the signed token (a tamper-proof note) in the `Cf-Access-Jwt-Assertion` header must be valid: the signature against Cloudflare's public keys, the RS256 signature type, the audience tag, the issuer and the expiry. Anything else gets the "Cannot sign in" page (`core/templates/core/sign_in_refused.html`, status 403, or 503 if Cloudflare's keys cannot be fetched).
- **The keys** are read from `https://<team domain>/cdn-cgi/access/certs` and kept for a few minutes.
- **Finding the account:** the email in the token, ignoring capital letters. A blank email never matches anyone.
  - None found: an account is created with the email as its username and no usable password, and it goes through the time zone step.
  - Two found: refused, never guessed. A deactivated account counts too.
  - Deactivated: refused, and never turned back on.
  - The email is already another account's username: refused, so that account is never opened by accident.
- **No Couchlog session on this address.** The person is whoever the token says, on each request, so a shared browser cannot stay in the wrong account. Cloudflare's session (one month) is the only one, which is why Log out sends the browser to `/cdn-cgi/access/logout`.
- The CSS, logo and htmx are served before this check, as they are for anyone. They hold nothing private, and Cloudflare asks for the email first anyway.

**Closed by default**
- `LoginRequiredMiddleware` (in `MIDDLEWARE` in `config/settings.py`) sends anonymous visitors to `/login/`. A page is open only if its view is marked `@login_not_required`. Only the login page and the [About page](about.md) are. A new page is closed without anyone having to remember it.
- Django's admin page keeps its own login screen.
- After logging in you land on Home (`LOGIN_REDIRECT_URL`); after logging out you land on the login page (`LOGOUT_REDIRECT_URL`).

**Sessions**
- At home, who is logged in is stored in the `django_session` table of the SQLite file (Django's default). Logging out deletes the session.

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
2. Further accounts with a password: log in at `/admin/` on the home address, open Users, and add one.
3. Friends: add their email to the allow list and the account appears at their first sign-in ([deploying.md](deploying.md)).

**Known limits**
- The time zone is only saved for now. "Today", "tomorrow" and "in N days" are not applied anywhere yet; the first card that shows a date will use it.
- The country for release dates and streaming services (taken from the time zone) is not built yet. It comes with the cards that need it.
- No password reset or change page. Passwords are changed in the admin page.
- No limit on wrong password attempts. The password form only works on the home address, so this only matters inside the home network.
- The Profile page shows a friend's email as the account name, because that is the username.
- Deleting an account whose email is still on the allow list makes a new empty one at the next sign-in. Deactivate it, or remove the email first.
- Time spent: a very long episode (a finale or a feature-length special in a regular season) raises its series' typical runtime a little, since it is an average. An episode that has no runtime of its own is counted at that typical runtime, not at its real one. A film that TMDB has no runtime for counts as 0 minutes, and `refresh_calendar` asks about it again each time it runs.
- Time spent: a watch with an unknown date counts too. There is no total per year or per month, only the grand total.
