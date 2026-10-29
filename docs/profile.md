# Profile, login and time zone

## What it does

- **Log in with a username and password.** Every page needs a login. Anyone who is not logged in is sent to the login page, whichever page they try to open.
- **No sign-up page.** Accounts are created by hand in Django's admin page (`/admin/`).
- **Time zone.** The first time an account logs in, every page leads to the Profile page with the note "Choose your time zone to continue." The list suggests the time zone your browser reports. Nothing else opens until one is saved.
- **Profile page** (`/profile/`, linked as "Profile" in the header):
  - shows the username;
  - shows the time zone and lets you change it;
  - has the Log out button.
- **Undo:** to undo a time zone change, choose the old one again. There is no separate undo button.
- Later cards add to this page: statistics, favorites.

## How it works

**Pages**

| Address | What | Needs login |
|---|---|---|
| `/login/` | Django's built-in login form (`core/templates/core/login.html`) | No |
| `/logout/` | Logs out. It only accepts a button press (POST), not a plain link | Yes |
| `/profile/` | Username, time zone form, Log out button | Yes |
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

**Creating an account**
1. `uv run python manage.py createsuperuser` makes the first account (you choose the username and password in the terminal).
2. Further accounts: log in at `/admin/`, open Users, and add one.

**Known limits**
- The time zone is only saved for now. "Today", "tomorrow" and "in N days" are not applied anywhere yet; the first card that shows a date will use it.
- The country for release dates and streaming services (taken from the time zone) is not built yet. It comes with the cards that need it.
- No password reset or change page. Passwords are changed in the admin page.
- No limit on wrong password attempts. This is fine while the app only runs at home.
