# Running in Docker

## What it does

- Couchlog can run inside a **Docker container** on the PC, set up the way it will run on the Raspberry Pi later. Everyday work stays the same: `uv run python manage.py runserver` on the PC. Docker is for trying the Pi setup.
- Nothing goes to the Pi yet. The Pi steps (SSH, deploy key, first deploy) come with the deploy card.
- The container has its own database, kept in a Docker **volume** (storage that belongs to Docker, outside the container). It is not the `db.sqlite3` on the PC. Rebuilding or removing the container does not erase it.

**Try it on the PC** (Docker Desktop must be running):
1. In `.env`, set `DJANGO_SECRET_KEY` to a long random text. Make one with `uv run python -c "import secrets; print(secrets.token_urlsafe(50))"`. Leave `DJANGO_DEBUG` out of `.env` (or `true`): Compose turns debug off by itself, and debug off on the PC would make `runserver` show no CSS.
2. `docker compose up --build` builds the image and starts Couchlog (add `-d` to run it in the background).
3. Open http://localhost:3000. The first time the database is empty, so make an account: `docker compose exec couchlog python manage.py createsuperuser`.
4. `docker compose down` stops and removes the container; the data stays. Starting again with `docker compose up` (or `up --build` after a code change) shows the same data.
5. `docker compose down -v` also deletes the volume, which **erases the database**. Use it only to start from nothing.

## How it works

- **`Dockerfile`**: a small Python 3.14 image. It installs the packages exactly as `uv.lock` says (no dev tools), copies the code, runs `collectstatic`, and runs as a normal user (`app`), not root. On start it applies the migrations, then starts **gunicorn** (the server that runs the app) with 2 workers on port 8000.
- **`docker-compose.yml`**: one container. Port 3000 on the host goes to 8000 inside. `.env` is handed to the container when it starts and is never copied into the image. The volume `couchlog-data` is mounted at `/data`. `restart: unless-stopped` brings it back after a crash and when the Pi restarts (but not after you stopped it yourself with `docker compose stop`).
- **`.dockerignore`**: keeps `.env`, the database files, `.venv`, `.git`, the tests, `docs/` and `Identity/` out of the image.
- **Settings** (all in `.env`, see `.env.example`):

| Setting | In Docker |
|---|---|
| `DJANGO_DEBUG` | Always `false`; Compose sets it and it wins over `.env`. |
| `DJANGO_SECRET_KEY` | Required. Without it the container stops with "Set DJANGO_SECRET_KEY in the .env file." |
| `DJANGO_ALLOWED_HOSTS` | Must contain the address you open (`localhost` is the default; on the Pi add its address). |
| `DJANGO_DB_PATH` | Set by Compose to `/data/db.sqlite3`. On the PC it is left out and the file is `db.sqlite3` in the project folder. |
| `TMDB_API_KEY` | As on the PC. |

- **Static files** (CSS, logo, htmx): `collectstatic` copies them into `staticfiles/` while the image is built, and **WhiteNoise** serves them, with no login needed. Django's default storage is used, with no file-name hashing.
- **Database safety**: SQLite runs in write-ahead log mode with the "normal" sync level (`config/settings.py`, on the PC too). A power cut loses at most the last action and does not corrupt the file. The database is then a few files (`db.sqlite3`, `-wal`, `-shm`), so a backup must use SQLite's backup command, not a plain copy (the backup comes with a later card). The volume is a named Docker volume, not a folder from Windows, because this mode needs a real Linux disk.
- **No HTTPS** in Stage 1, so the "secure cookie" and "redirect to HTTPS" settings stay off. Turning them on would break the login on `http://`.
- **Tests**: `core/tests/test_production_settings.py` checks the database path (and its fallback to `db.sqlite3`), the power-cut settings, that debug off without a secret key refuses to start, and that the CSS, logo and htmx are served without a login. The container itself is checked by hand with the steps above.

**Known limits**
- The 64-bit ARM build (the Pi's chip) was not run on the PC, because Docker Desktop here has no ARM emulator. The Python and uv base images exist for ARM and every package Couchlog needs is pure Python, so it should build; the first real check is on the Pi.
- The calendar is not refreshed by itself yet. Run it by hand with `docker compose exec couchlog python manage.py refresh_calendar`; the daily task comes with the next card.
- Migrations run at every start. Copying the database before a deploy that changes the tables is still a habit of mine (plan.md, section 4).
