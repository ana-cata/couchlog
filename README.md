# couchlog
Track the movies and series you watch, keep a watchlist, and see upcoming releases in a calendar.

_Log what you watch from the couch._

Couchlog is a personal project. [plan.md](plan.md) says what is being built and why. Python 3.14, Django, htmx, SQLite and TMDB.

## Run it on the PC

You need [uv](https://docs.astral.sh/uv/) (it installs Python and the packages). Run these in the project folder:

1. `uv sync` installs the packages.
2. Copy `.env.example` to `.env` and put your TMDB key after `TMDB_API_KEY=`. The `.env` file is private and never goes to GitHub.
3. `uv run python manage.py migrate` creates the local database file (`db.sqlite3`, also private).
4. `uv run python manage.py runserver` starts the app. Open http://localhost:8000 and you see the Couchlog placeholder page. Stop it with Ctrl+C.

## Useful commands

- `uv run python manage.py tmdb_check` makes one request to TMDB and says whether your key works.
- `uv run pytest` runs the tests. They use made-up TMDB answers and a temporary database, never the real TMDB.
- `uv run python manage.py makemigrations` and `uv run python manage.py migrate` change the database tables (from the first card that adds tables).

## Open it from the phone

On the same Wi-Fi: add the PC's address to `DJANGO_ALLOWED_HOSTS` in `.env` (for example `localhost,127.0.0.1,192.168.1.20`), then start the app with `uv run python manage.py runserver 0.0.0.0:8000` and open `http://<PC address>:8000` on the phone.

## Where things are

- `config/` holds the Django settings and the main list of addresses.
- `core/` is the first app: the placeholder page (`views.py`, `templates/core/`), the TMDB code (`tmdb.py`) and the `tmdb_check` command.
- `core/static/core/` holds Pico CSS 2.1.1 (the styling) and htmx 2.0.11 (small page updates without reloading). They are saved in the project, so the app works without internet except for TMDB.
