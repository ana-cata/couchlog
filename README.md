# couchlog
Track the movies and series you watch, keep a watchlist, and see upcoming releases in a calendar.

_Log what you watch from the couch._

Couchlog is a personal project. [plan.md](plan.md) says what is being built and why. Python 3.14, Django, htmx, SQLite and TMDB.

## Run it on the PC

You need [uv](https://docs.astral.sh/uv/) (it installs Python and the packages). Run these in the project folder:

1. `uv sync` installs the packages.
2. Copy `.env.example` to `.env` and put your TMDB key after `TMDB_API_KEY=`. The `.env` file is private and never goes to GitHub.
3. `uv run python manage.py migrate` creates the local database file (`db.sqlite3`, also private).
4. `uv run python manage.py createsuperuser` makes your account. It asks for a username and a password in the terminal. There is no sign-up page, so this is how the first account is made; more can be added in the admin page (http://localhost:8000/admin/). See [docs/profile.md](docs/profile.md).
5. `uv run python manage.py runserver` starts the app. Open http://localhost:8000, log in, and pick your time zone on the Profile page the first time. After that you see Home with Up Next (empty until you have marked an episode of a series). Click Search in the header to look up movies and series (this uses your TMDB key), add some to your To Watch list, and see them under Movies or Series (each has a To Watch tab). Open a movie and press Mark as watched to put it in Movies → History. Open Calendar in the header to see what is coming up from your series and To Watch list (adding a title to To Watch collects its dates). Stop the app with Ctrl+C.

## Useful commands

- `uv run python manage.py tmdb_check` makes one request to TMDB and says whether your key works.
- `uv run python manage.py refresh_calendar` asks TMDB again about every series on a To Watch list or with a watched episode (new episodes, air dates, whether it has ended) and about the films on a To Watch list (their cinema and streaming dates). It also asks TVmaze for the upcoming episodes TMDB does not list yet. The Calendar page shows what was saved: adding a title to To Watch saves its dates at once, and this command brings in later changes (a streaming date, new episodes, new TVmaze dates). On the PC, run it by hand now and then; on the Pi it runs by itself (`run_daily`, see [docs/deploying.md](docs/deploying.md)). See [docs/calendar.md](docs/calendar.md) and [docs/series.md](docs/series.md).
- `uv run playwright install chromium` downloads the browser that the end-to-end test drives (about 150 MB). Do this once on each machine before the first `uv run pytest`.
- `uv run pytest` runs the tests. They use made-up TMDB answers and a temporary database, never the real TMDB. One test opens a real (invisible) browser and walks through the app.
- `uv run ruff check .` runs the lint (it looks for mistakes and untidy code).
- `uv run python manage.py makemigrations` and `uv run python manage.py migrate` change the database tables. `makemigrations` writes a migration file (commit it); `migrate` applies it to your `db.sqlite3`. See [docs/data-model.md](docs/data-model.md).

## Automatic checks

On every pull request, GitHub runs the lint and the tests (`.github/workflows/checks.yml`) on a Linux machine, with no `.env` and no TMDB key. It downloads the test browser first. A pull request is merged only when both are green. Run the same two commands on the PC before pushing to catch problems early.

## Run it in Docker

The real app runs in Docker on the Raspberry Pi; on the PC, Docker is for trying that setup and everyday work stays with `runserver`. With Docker Desktop running and a `DJANGO_SECRET_KEY` in `.env`, `docker buildx bake --allow=network.host -f docker-compose.yml couchlog` builds it and `docker compose up -d` starts Couchlog at http://localhost:3000, with its own database in a Docker volume that survives `docker compose down`. See [docs/deploying.md](docs/deploying.md) for the steps on the PC and the Pi, the settings and what is checked.

## The public demo

A separate copy of Couchlog on Render's free plan, at `https://demo.ana-cata.com`: anyone presses **Try the demo** and gets a throwaway account with sample titles, with limits. It is turned on with `DEMO_MODE=true`, which is never set on the PC or the Pi. See [docs/demo.md](docs/demo.md) for what it does and its limits, and [docs/deploying.md](docs/deploying.md#the-public-demo-on-render) for deploying it and switching it off.

## Open it from the phone

On the same Wi-Fi: add the PC's address to `DJANGO_ALLOWED_HOSTS` in `.env` (for example `localhost,127.0.0.1,192.168.1.20`), then start the app with `uv run python manage.py runserver 0.0.0.0:8000` and open `http://<PC address>:8000` on the phone.

## Where things are

- `docs/` says what is built, one page per page of the app. For now: [docs/home.md](docs/home.md) (Home and Up Next), [docs/profile.md](docs/profile.md) (login and time zone), [docs/search.md](docs/search.md) (search and title pages), [docs/to-watch.md](docs/to-watch.md) (the Movies and Series sections and their To Watch lists), [docs/history.md](docs/history.md) (marking a movie as watched, and History), [docs/series.md](docs/series.md) (the series page, marking episodes and progress bars), [docs/calendar.md](docs/calendar.md) (the Calendar of upcoming releases), [docs/about.md](docs/about.md) (the TMDB credit), [docs/deploying.md](docs/deploying.md) (running in Docker, and the demo on Render), [docs/demo.md](docs/demo.md) (the public demo), [docs/messages.md](docs/messages.md) (every empty, loading and error message) and [docs/data-model.md](docs/data-model.md) (the database and its tables).
- `config/` holds the Django settings and the main list of addresses.
- `core/` is the first app: the Home page, login, Profile, search, title, Movies, Series, History, Calendar and About pages (`views.py`, `middleware.py`, `templates/core/`), the `Profile`, `Title`, `Episode`, `ToWatchItem` and `Watch` tables (`models.py`), the series logic (`episodes.py`), the calendar logic (`releases.py`), the TMDB code (`tmdb.py`) and the `tmdb_check`, `refresh_calendar` and `run_daily` commands.
- `core/static/core/` holds Pico CSS 2.1.1 (the styling), htmx 2.0.11 (small page updates without reloading), Couchlog's own few styles (`couchlog.css`), Couchlog's logo, tab icon and phone home screen icon, and the TMDB logo. They are saved in the project, so the app works without internet except for TMDB and its poster pictures.
