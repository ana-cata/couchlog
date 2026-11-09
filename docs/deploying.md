# Running in Docker

## What it does

- Couchlog runs inside a **Docker container** on the Raspberry Pi, at `http://192.168.1.164:3000` on the home network. It starts by itself when the Pi restarts.
- A second container, **`daily`**, refreshes the Calendar, News and new episodes by itself: once when it starts (so also after the Pi was off) and then every 24 hours. Nobody runs `refresh_calendar` by hand on the Pi.
- The same setup can be tried on the PC. Everyday work stays the same: `uv run python manage.py runserver` on the PC.
- The container has its own database, kept in a Docker **volume** (storage that belongs to Docker, outside the container). It is not the `db.sqlite3` on the PC. Rebuilding or removing the container does not erase it.

**Try it on the PC** (Docker Desktop must be running):
1. In `.env`, set `DJANGO_SECRET_KEY` to a long random text. Make one with `uv run python -c "import secrets; print(secrets.token_urlsafe(50))"`. Leave `DJANGO_DEBUG` out of `.env` (or `true`): Compose turns debug off by itself, and debug off on the PC would make `runserver` show no CSS.
2. `docker compose up --build` builds the image and starts Couchlog (add `-d` to run it in the background).
3. Open http://localhost:3000. The first time the database is empty, so make an account: `docker compose exec couchlog python manage.py createsuperuser`.
4. `docker compose down` stops and removes the container; the data stays. Starting again with `docker compose up` (or `up --build` after a code change) shows the same data.
5. `docker compose down -v` also deletes the volume, which **erases the database**. Use it only to start from nothing.

## On the Pi

Log in from the PC with `ssh ana-cata@homelab.local`. Commands below run on the Pi, in `~/couchlog`.

**Deploy a new version** (after a pull request is merged):
1. `git pull`
2. `docker compose up -d --build`. The migrations run by themselves when the container starts.
3. Do the five-minute check (plan.md, section 7).

**Go back if a deploy breaks something:**
1. `git log --oneline -5` shows the recent versions. Pick the one before the deploy.
2. `git checkout <that commit>`, then `docker compose up -d --build`.
3. When the fix is merged: `git checkout main`, then deploy as above.

If the broken version changed the tables, the older code may not fit them. Restore a copy of the database made before the deploy.

**First deploy** (done once, kept here in case the SD card has to be set up again):
1. In the router, under DHCP Binding, tie the Pi's cable address (`192.168.1.164`) to its cable MAC address, so the address never changes.
2. Make a key used only for this repo: `ssh-keygen -t ed25519 -C "couchlog-deploy-pi" -f ~/.ssh/couchlog_deploy -N ""`.
3. Add `~/.ssh/couchlog_deploy.pub` to the repo on GitHub, under Settings → Deploy keys, with write access **off**.
4. Add this to `~/.ssh/config`, then run `chmod 600 ~/.ssh/config`. The test `ssh -T git@github-couchlog` should answer `Hi ana-cata/couchlog!`.
   ```
   Host github-couchlog
     HostName github.com
     IdentityFile ~/.ssh/couchlog_deploy
     IdentitiesOnly yes
   ```
5. `git clone git@github-couchlog:ana-cata/couchlog.git ~/couchlog`.
6. In `~/couchlog`, make a `.env` with `chmod 600`: a **new** `DJANGO_SECRET_KEY` (not the PC's), `TMDB_API_KEY`, and `DJANGO_ALLOWED_HOSTS=192.168.1.164,homelab.local`.
7. `docker compose up -d --build`, then `docker compose exec couchlog python manage.py createsuperuser`.
8. Check it by restarting the Pi with `sudo reboot`: Couchlog comes back by itself.

To see what the app is doing: `docker compose ps` and `docker compose logs --tail 20 couchlog`.

**Reading the daily task's log:** `docker compose logs daily`. Each run starts with a line like `2026-11-09 15:52 UTC Starting refresh_calendar.`, then one line per title, then `Finished refresh_calendar.` and `Next run in 24 hours.` A run with a problem says `refresh_calendar failed` and which titles could not be refreshed; the task keeps running and tries again the next day. Times are in UTC, whatever the account's time zone is.

## How it works

- **`Dockerfile`**: a small Python 3.14 image. It installs the packages exactly as `uv.lock` says (no dev tools), copies the code, runs `collectstatic`, and runs as a normal user (`app`), not root. On start it applies the migrations, then starts **gunicorn** (the server that runs the app) with 2 workers on port 8000.
- **`docker-compose.yml`**: two containers from one image, named `couchlog`. The first start may print "pull access denied for couchlog" before building: Compose looked for that name online first, and it is harmless. The image is built on the machine's own network (`network: host`): on the Pi, the build's temporary container failed to look up the Python packages' site, most likely because the Pi's first three DNS servers are IPv6 and that container has no IPv6. Docker wants permission for that, given by `entitlements: network.host` under `build:` (without it the Pi stopped with "additional privileges requested"). It applies to the build only; the running containers do not use the machine's network. Port 3000 on the host goes to 8000 inside. `.env` is handed to the container when it starts and is never copied into the image. The volume `couchlog-data` is mounted at `/data`. `restart: unless-stopped` brings it back after a crash and when the Pi restarts (but not after you stopped it yourself with `docker compose stop`).
- **The `daily` container** runs `python manage.py run_daily` (`core/management/commands/run_daily.py`), with the same `.env`, settings and volume as the app and no port.
  - It first waits until the database has every migration, checking every 5 seconds, because the app applies them when its own container starts and both start together. The check is in the command, and not Compose's `depends_on`, because Docker does not follow `depends_on` when it restarts containers after a reboot.
  - It then runs the commands in `DAILY_COMMANDS` (today only `refresh_calendar`) and sleeps 24 hours. There is no fixed hour: the 24 hours count from when the container started, so a deploy or a reboot moves the time.
  - Any error is written to the log and the loop goes on. One command failing does not stop the next.
  - `restart: unless-stopped` is what makes it run again when the Pi starts. `init: true` lets `docker compose down` stop it at once.
- **`.dockerignore`**: keeps `.env`, the database files, `.venv`, `.git`, the tests, `docs/` and `Identity/` out of the image.
- **Settings** (all in `.env`, see `.env.example`):

| Setting | In Docker |
|---|---|
| `DJANGO_DEBUG` | Always `false`; Compose sets it and it wins over `.env`. |
| `DJANGO_SECRET_KEY` | Required. Without it the container stops with "Set DJANGO_SECRET_KEY in the .env file." |
| `DJANGO_ALLOWED_HOSTS` | Must contain the address you open (`localhost` is the default; on the Pi it is `192.168.1.164,homelab.local`). |
| `DJANGO_DB_PATH` | Set by Compose to `/data/db.sqlite3`. On the PC it is left out and the file is `db.sqlite3` in the project folder. |
| `TMDB_API_KEY` | As on the PC. |

- **Static files** (CSS, logo, htmx): `collectstatic` copies them into `staticfiles/` while the image is built, and **WhiteNoise** serves them, with no login needed. Django's default storage is used, with no file-name hashing.
- **Database safety**: SQLite runs in write-ahead log mode with the "normal" sync level (`config/settings.py`, on the PC too). A power cut loses at most the last action and does not corrupt the file. The database is then a few files (`db.sqlite3`, `-wal`, `-shm`), so a backup must use SQLite's backup command, not a plain copy (the backup comes with a later card). The volume is a named Docker volume, not a folder from Windows, because this mode needs a real Linux disk.
- **No HTTPS** in Stage 1, so the "secure cookie" and "redirect to HTTPS" settings stay off. Turning them on would break the login on `http://`.
- **Tests**: `core/tests/test_production_settings.py` checks the database path (and its fallback to `db.sqlite3`), the power-cut settings, that debug off without a secret key refuses to start, and that the CSS, logo and htmx are served without a login. `core/tests/test_run_daily.py` checks that `run_daily` refreshes at the start and a day later, survives failures, and waits for the migrations. The containers themselves are checked by hand with the steps above.

**Known limits**
- `homelab.local` can point to any of the Pi's addresses, including its Wi-Fi one. `192.168.1.164` is the fixed address, so use it for bookmarks.
- A refresh that fails is only tried again 24 hours later. If the Pi's network is not ready just after a restart, that day's first refresh is lost; `docker compose restart daily` runs it again.
- Migrations run at every start. Copying the database before a deploy that changes the tables is still a habit of mine (plan.md, section 4).
