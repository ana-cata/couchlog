# Running in Docker

## What it does

- Couchlog runs inside a **Docker container** on the Raspberry Pi, at `http://192.168.1.164:3000` on the home network. It starts by itself when the Pi restarts.
- A second container, **`daily`**, refreshes the Calendar, News and new episodes by itself: once when it starts (so also after the Pi was off) and then every 24 hours. Nobody runs `refresh_calendar` by hand on the Pi.
- The `daily` container also sends a **backup** of the database to Cloudflare R2 (private online storage) at each run, and keeps the newest 14 copies. So a copy survives the SD card, the Pi or the house having a problem. Any copy can be restored, and a restore can be undone.
- The same setup can be tried on the PC. Everyday work stays the same: `uv run python manage.py runserver` on the PC.
- The container has its own database, kept in a Docker **volume** (storage that belongs to Docker, outside the container). It is not the `db.sqlite3` on the PC. Rebuilding or removing the container does not erase it.

**Try it on the PC** (Docker Desktop must be running):
1. In `.env`, set `DJANGO_SECRET_KEY` to a long random text. Make one with `uv run python -c "import secrets; print(secrets.token_urlsafe(50))"`. Leave `DJANGO_DEBUG` out of `.env` (or `true`): Compose turns debug off by itself, and debug off on the PC would make `runserver` show no CSS.
2. `docker buildx bake --allow=network.host -f docker-compose.yml couchlog` builds the image, and `docker compose up -d` starts Couchlog.
3. Open http://localhost:3000. The first time the database is empty, so make an account: `docker compose exec couchlog python manage.py createsuperuser`.
4. `docker compose down` stops and removes the container; the data stays. Starting again with `docker compose up -d` (after a code change, build first as in step 2) shows the same data.
5. `docker compose down -v` also deletes the volume, which **erases the database**. Use it only to start from nothing.

## On the Pi

Log in from the PC with `ssh ana-cata@homelab.local`. Commands below run on the Pi, in `~/couchlog`.

**Deploy a new version** (after a pull request is merged):
1. `git pull`
2. `docker buildx bake --allow=network.host -f docker-compose.yml couchlog` builds the new version.
3. `docker compose up -d` starts it. The migrations run by themselves when the container starts.
4. Do the five-minute check (plan.md, section 7).

**Go back if a deploy breaks something:**
1. `git log --oneline -5` shows the recent versions. Pick the one before the deploy.
2. `git checkout <that commit>`, then build and start it as in the deploy steps above.
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
7. Build and start it as in the deploy steps above, then `docker compose exec couchlog python manage.py createsuperuser`.
8. Check it by restarting the Pi with `sudo reboot`: Couchlog comes back by itself.

To see what the app is doing: `docker compose ps` and `docker compose logs --tail 20 couchlog`.

**Reading the daily task's log:** `docker compose logs daily`. Each run starts with a line like `2026-11-09 15:52 UTC Starting refresh_calendar.`, then one line per title, then `Finished refresh_calendar.` and `Next run in 24 hours.` A run with a problem says `refresh_calendar failed` and which titles could not be refreshed; the task keeps running and tries again the next day. Times are in UTC, whatever the account's time zone is.

### Backups

**Setting up Cloudflare** (done once; Cloudflare may word these buttons slightly differently):
1. In the Cloudflare dashboard, open **R2 Object Storage** and create a bucket named `couchlog-backups`. Leave it private: do not turn on public access or add a public domain. Leave the default storage class on **Standard**.
2. On the R2 overview page, copy the **Account ID**.
3. Under **API Tokens** on that same page, create an **Account API token** with the permission **Object Read & Write**, applied to **`couchlog-backups` only**.
4. Cloudflare then shows an **Access Key ID** and a **Secret Access Key**. The secret is shown only once. Keep the page open for the next step and do not save them anywhere else.
5. On the Pi, add these to `~/couchlog/.env` with `nano .env`, and only there:
   ```
   R2_ACCOUNT_ID=<Account ID>
   R2_ACCESS_KEY_ID=<Access Key ID>
   R2_SECRET_ACCESS_KEY=<Secret Access Key>
   R2_BUCKET=couchlog-backups
   ```
6. Deploy as above. `docker compose logs daily` should say `Uploaded couchlog-...sqlite3.`, and the copy appears in the bucket.
7. Under **Billable Usage** in the Cloudflare dashboard, set a budget alert to the lowest amount it accepts. It only sends an email and does not stop anything, but it would tell you if R2 ever started to cost money.

Without those settings (as on the PC), the backup says what is missing and does nothing.

**Make a copy by hand** (before a deploy that changes the tables): `docker compose exec daily python manage.py backup_db`.

**Restore a copy:**
1. `docker compose exec couchlog python manage.py restore_db` lists the copies, newest first. The names are the date and time in UTC.
2. `docker compose exec couchlog python manage.py restore_db couchlog-2026-11-09-155200.sqlite3` puts that copy in place of the database. The app can stay on.
3. `docker compose restart couchlog` brings the tables up to the current version, in case the copy is older.
4. Log in again, because a copy holds no login sessions, and check the data.

**Undo a restore:** `docker compose exec couchlog python manage.py restore_db --undo`, then `docker compose restart couchlog`. It puts back the database from just before the last restore, and can be used once per restore.

**If `restore_db` itself does not work** (the manual way):
1. Download the copy from the bucket in the Cloudflare dashboard, and put it in `~/couchlog` on the Pi with `scp <file> ana-cata@homelab.local:couchlog/`.
2. `docker compose stop couchlog daily`
3. Save the current database and put the copy in its place (this is one command; use the real file name):
   ```
   docker compose run --rm -v "$PWD:/restore:ro" couchlog sh -c 'mkdir -p /data/before-manual && cp /data/db.sqlite3* /data/before-manual/ && rm -f /data/db.sqlite3-wal /data/db.sqlite3-shm && cp /restore/couchlog-2026-11-09-155200.sqlite3 /data/db.sqlite3'
   ```
4. `docker compose up -d`, then delete the downloaded file from `~/couchlog`.

## How it works

- **`Dockerfile`**: a small Python 3.14 image. It installs the packages exactly as `uv.lock` says (no dev tools), copies the code, runs `collectstatic`, and runs as a normal user (`app`), not root. On start it applies the migrations, then starts **gunicorn** (the server that runs the app) with 2 workers of 4 threads each on port 8000, so a page waiting for TMDB does not hold up the others.
- **`docker-compose.yml`**: two containers from one image, named `couchlog`. The image is built on the machine's own network (`network: host`): on the Pi, the build's temporary container failed to look up the Python packages' site, most likely because the Pi's first three DNS servers are IPv6 and that container has no IPv6. Docker asks for permission for that, and `docker compose` has no way to give it, so the build is its own command, `docker buildx bake --allow=network.host`. `docker compose up --build` stops on the Pi with "additional privileges requested" (Buildx 0.38.1; Buildx 0.37.0 on the PC did not ask). The permission applies to the build only; the running containers do not use the machine's network. Port 3000 on the host goes to 8000 inside. `.env` is handed to the container when it starts and is never copied into the image. The volume `couchlog-data` is mounted at `/data`. `restart: unless-stopped` brings it back after a crash and when the Pi restarts (but not after you stopped it yourself with `docker compose stop`).
- **The `daily` container** runs `python manage.py run_daily` (`core/management/commands/run_daily.py`), with the same `.env`, settings and volume as the app and no port.
  - It first waits until the database has every migration, checking every 5 seconds, because the app applies them when its own container starts and both start together. The check is in the command, and not Compose's `depends_on`, because Docker does not follow `depends_on` when it restarts containers after a reboot.
  - It then runs the commands in `DAILY_COMMANDS` (`refresh_calendar`, then `backup_db`) and sleeps 24 hours. There is no fixed hour: the 24 hours count from when the container started, so a deploy or a reboot moves the time.
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
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | Only on the Pi. All four are needed, or no backup is made. |

- **Static files** (CSS, logo, htmx): `collectstatic` copies them into `staticfiles/` while the image is built, and **WhiteNoise** serves them, with no login needed. Django's default storage is used, with no file-name hashing.
- **Database safety**: SQLite runs in write-ahead log mode with the "normal" sync level (`config/settings.py`, on the PC too). A power cut loses at most the last action and does not corrupt the file. The database is then a few files (`db.sqlite3`, `-wal`, `-shm`), so a backup must use SQLite's backup command, not a plain copy. The volume is a named Docker volume, not a folder from Windows, because this mode needs a real Linux disk.
- **Backups** (`core/backups.py`, commands `backup_db` and `restore_db`, package `boto3`, which R2 accepts because it works like Amazon S3):
  - **Making a copy:** SQLite's backup command writes a copy in a temporary folder, inside the container and not in the volume. The folder is removed afterwards, also when something fails. The copy is uploaded with its UTC date and time in the name (`couchlog-YYYY-MM-DD-HHMMSS.sqlite3`).
  - **What is kept:** only after a successful upload, the oldest copies are deleted so 14 are left. A file counts as Couchlog's only if its whole name fits that pattern, so anything else in the bucket is left alone.
  - **Staying on the free plan** (10 GB of storage and 1 million uploads and lists a month; Cloudflare has no hard spending limit for R2): each backup is one list and one upload, and deleting is free. Uploads always use Standard storage, because the free plan does not cover Infrequent Access. Before the upload, the sizes of Couchlog's copies are added up (`STORAGE_LIMIT`, 5 GB, in `core/backups.py`). If the new copy would take the total over the limit, nothing is uploaded or deleted and the log says `backup_db failed: Nothing was uploaded: the copies in R2 would take more than 5 GB`.
  - **No keys in a copy:** the TMDB key, the login secret and the R2 keys live in `.env`, which is never part of a backup. The login sessions (the "you are logged in" codes) are erased from the copy and the file is rebuilt with `VACUUM`, because erased rows otherwise stay readable in it. The app's own database keeps them. Just before the upload, the copy is searched for the values of those four keys; if one is found, nothing is uploaded and the log names the setting, never the value.
  - **What a copy does hold:** the account (with the password stored scrambled, which a restored copy needs for logging in) and the history. It is not encrypted, so the bucket stays private and the R2 key reaches only that bucket.
  - **Restoring:** the copy is downloaded and checked (a real, undamaged database with Couchlog's account table). The current database is then saved as `db-before-restore.sqlite3` next to it, in the volume, and SQLite's backup command writes the copy into the database. This keeps write-ahead log mode and is safe with the app running: a page opened at that moment may just wait a moment. The saved file stays on the Pi, is replaced by the next restore, and is removed by `--undo`.
- **No HTTPS** in Stage 1, so the "secure cookie" and "redirect to HTTPS" settings stay off. Turning them on would break the login on `http://`.
- **Tests**: `core/tests/test_production_settings.py` checks the database path (and its fallback to `db.sqlite3`), the power-cut settings, that debug off without a secret key refuses to start, and that the CSS, logo and htmx are served without a login. `core/tests/test_run_daily.py` checks that `run_daily` refreshes at the start and a day later, survives failures, and waits for the migrations. `core/tests/test_backups.py` uses a fake R2 and a made-up database in write-ahead log mode, and checks the copy, that no key or login session is in it, that only 14 copies are left, and that restore and undo work. The containers and the real R2 are checked by hand with the steps above.

**Known limits**
- `homelab.local` can point to any of the Pi's addresses, including its Wi-Fi one. `192.168.1.164` is the fixed address, so use it for bookmarks.
- A refresh that fails is only tried again 24 hours later. If the Pi's network is not ready just after a restart, that day's first refresh is lost; `docker compose restart daily` runs it again.
- Migrations run at every start. Copying the database before a deploy that changes the tables is still a habit of mine (plan.md, section 4): `backup_db` by hand, above.
- "14 copies" means the last 14 runs, not 14 days. Each restart of `daily` makes one, so a day with many restarts or deploys pushes older copies out sooner.
- If the 5 GB limit is ever reached, backups stop until copies are deleted from the bucket by hand, and the only sign is the line in `docker compose logs daily`. Only Couchlog's copies are counted, not other files or other buckets.
- A failed backup is only tried again 24 hours later; `docker compose exec daily python manage.py backup_db` makes one at once.
