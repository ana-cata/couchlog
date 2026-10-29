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
5. `uv run python manage.py runserver` starts the app. Open http://localhost:8000, log in, and pick your time zone on the Profile page the first time. After that you see the Couchlog placeholder page. Click Search in the header to look up movies and series (this uses your TMDB key), add some to your To Watch list, and see them under To Watch. Open a movie and press Mark as watched to put it in History. Stop it with Ctrl+C.

## Useful commands

- `uv run python manage.py tmdb_check` makes one request to TMDB and says whether your key works.
- `uv run playwright install chromium` downloads the browser that the end-to-end test drives (about 150 MB). Do this once on each machine before the first `uv run pytest`.
- `uv run pytest` runs the tests. They use made-up TMDB answers and a temporary database, never the real TMDB. One test opens a real (invisible) browser and walks through the app.
- `uv run ruff check .` runs the lint (it looks for mistakes and untidy code).
- `uv run python manage.py makemigrations` and `uv run python manage.py migrate` change the database tables. `makemigrations` writes a migration file (commit it); `migrate` applies it to your `db.sqlite3`. See [docs/data-model.md](docs/data-model.md).

## Automatic checks

On every pull request, GitHub runs the lint and the tests (`.github/workflows/checks.yml`) on a Linux machine, with no `.env` and no TMDB key. It downloads the test browser first. A pull request is merged only when both are green. Run the same two commands on the PC before pushing to catch problems early.

## Open it from the phone

On the same Wi-Fi: add the PC's address to `DJANGO_ALLOWED_HOSTS` in `.env` (for example `localhost,127.0.0.1,192.168.1.20`), then start the app with `uv run python manage.py runserver 0.0.0.0:8000` and open `http://<PC address>:8000` on the phone.

## Where things are

- `docs/` says what is built, one page per page of the app. For now: [docs/profile.md](docs/profile.md) (login and time zone), [docs/search.md](docs/search.md) (search and title pages), [docs/to-watch.md](docs/to-watch.md) (the To Watch list), [docs/history.md](docs/history.md) (marking a movie as watched, and History), [docs/about.md](docs/about.md) (the TMDB credit) and [docs/data-model.md](docs/data-model.md) (the database and its tables).
- `config/` holds the Django settings and the main list of addresses.
- `core/` is the first app: the placeholder page, login, Profile, search, title, To Watch, History and About pages (`views.py`, `middleware.py`, `templates/core/`), the `Profile`, `Title`, `ToWatchItem` and `Watch` tables (`models.py`), the TMDB code (`tmdb.py`) and the `tmdb_check` command.
- `core/static/core/` holds Pico CSS 2.1.1 (the styling), htmx 2.0.11 (small page updates without reloading), Couchlog's own few styles (`couchlog.css`) and the TMDB logo. They are saved in the project, so the app works without internet except for TMDB and its poster pictures.
