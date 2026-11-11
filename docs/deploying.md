# Running in Docker

## What it does

- Couchlog runs inside a **Docker container** on the Raspberry Pi, at `http://192.168.1.164:3000` on the home network. It starts by itself when the Pi restarts.
- From outside the home it is at `https://couchlog.ana-cata.com`. A person types their email, and only emails on the allow list receive a one-time code and get through. That is the only sign-in there: no password, and the first time their account is created by itself. The router stays closed. `/admin/` only opens from the home address.
- A second container, **`daily`**, refreshes the Calendar, News and new episodes by itself: once when it starts (so also after the Pi was off) and then every 24 hours. Nobody runs `refresh_calendar` by hand on the Pi.
- The `daily` container also sends a **backup** of the database to Cloudflare R2 (private online storage) at each run, and keeps the newest 14 copies. So a copy survives the SD card, the Pi or the house having a problem. Any copy can be restored, and a restore can be undone.
- The **public demo** is a separate copy on Render, away from the Pi and the home network: [The public demo on Render](#the-public-demo-on-render) below.
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
4. Do the five-minute check, below.

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

### The five-minute check

Do this after every deploy, on the phone, on the home Wi-Fi, at `http://192.168.1.164:3000`. It leaves your data as it was.

1. **Log in.** If you are already logged in, press **Log out** on the Profile page first. Log in with your username and password. Home opens.
2. **Search for a title.** Press **Search** and type a title. Posters and names appear under the box. Add nothing.
3. **Mark an episode and undo it.** Open a series and a season, and press the gray circle of an aired episode you have not marked. If a pop-up asks about earlier episodes, choose **No, only** (it names the episode, for example "No, only S1E7"). The circle turns green and the bars move. Press the small **−** next to it. The circle is gray again and the bars are back. Do not press the green circle: that counts a rewatch (the **−** takes it back).
4. **Open the Calendar.** Press **Calendar**. The upcoming episodes and films of your lists are shown by month and day.

If a step fails, go back to the previous version (below) and open a fix card.

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

### Reaching it from outside

**How a visit works:** the phone asks Cloudflare for `couchlog.ana-cata.com`. **Cloudflare Access** (the email step) checks the person first. Only then does Cloudflare send the request down the **Cloudflare Tunnel**, a connection the Pi opened from the inside, so nothing on the router is open. The `tunnel` container hands it to the app.

**Setting up Cloudflare** (done once; Cloudflare may word these buttons slightly differently). **The order matters:** a route without the Access application would be open to anyone.
1. Buy the domain at Cloudflare (`ana-cata.com`) and leave auto-renew on.
2. Open **Zero Trust**, choose the Free plan, and name the team `ana-cata`.
3. Under **Integrations**, **Identity providers**, add **One-time PIN**.
4. Under **Access controls**, **Applications**, add a **Self-hosted** application named `couchlog`, for subdomain `couchlog` and domain `ana-cata.com`, with an empty path and no `*`. Session duration 1 month. Only One-time PIN as login method, and instant authentication on.
5. On it, add a policy `Allowed emails`: action **Allow**, Include **Emails**, full addresses only. Never **Everyone**, **Emails ending in**, or **Login Methods**: those let strangers in.
6. In the main dashboard, under **Networking**, **Tunnels**, create the tunnel `couchlog-pi`. Do not run the command it shows.
7. On its **Routes** tab, add a **Published application**: subdomain `couchlog`, domain `ana-cata.com`, Service URL `http://couchlog:8000` (the app's name and port inside Docker, not the public address).
8. In that route's settings, turn on **Protect with Access**, with the team name and the application's AUD tag (on the `couchlog` application's page). The tunnel then refuses a request that skipped the email step.

**Setting up the Pi** (done once):
1. Deploy as above, so the Pi has the new `docker-compose.yml`.
2. In the dashboard, open the tunnel and copy the token: the long text after `--token` in the command it shows. Do not paste it anywhere else.
3. `nano .env` on the Pi and add these, with the address also added to the end of the existing `DJANGO_ALLOWED_HOSTS`:
   ```
   DJANGO_ALLOWED_HOSTS=192.168.1.164,homelab.local,couchlog.ana-cata.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://couchlog.ana-cata.com
   COMPOSE_PROFILES=tunnel
   TUNNEL_TOKEN=<the token>
   ```
4. `docker compose up -d`. `docker compose ps` shows `tunnel`, and `docker compose logs --tail 20 tunnel` says `Registered tunnel connection`.

**Turn on the sign-in by email code** (done once, card #97). **The order matters:** if step 2 is skipped, Couchlog makes a new empty account for you.
1. Deploy as above, with the settings below still left out. Nothing changes yet.
2. At home, open `http://192.168.1.164:3000/admin/`, then **Users**, then your account. Fill in **Email address** with the address on the allow list, and save.
3. `nano .env` on the Pi and add these:
   ```
   CLOUDFLARE_ACCESS_TEAM_DOMAIN=ana-cata.cloudflareaccess.com
   CLOUDFLARE_ACCESS_AUD=<the AUD tag on the couchlog application's page>
   CLOUDFLARE_ACCESS_ADDRESS=couchlog.ana-cata.com
   ```
4. `docker compose up -d`. If `docker compose ps` does not show `couchlog` running, `docker compose logs --tail 20 couchlog` says which setting is wrong.
5. Check it on the phone with Wi-Fi off: open the address, type your email and the code, and your history is there. `/admin/` says it only opens from the home address. At home, your username and password still work.

To turn it off again, remove those three lines and run `docker compose up -d`. Couchlog then asks for its username and password after the code again.

**Add a friend:** in Zero Trust, under **Access controls**, **Policies**, add their full email to `Allowed emails`. Their account appears, empty, the first time they sign in. Do nothing in Couchlog.

**Remove a friend:**
1. Remove their email from `Allowed emails`. This stops new codes, but someone already in stays in until their session ends (up to a month).
2. To end it at once, use **Revoke existing tokens** on the `couchlog` application, or revoke the person under **Users**.
3. At home, in `/admin/`, **Users**, open their account and untick **Active**. Their data stays and they stay out. An account can also be deleted there, which erases its data. If the email is still on the allow list, the next sign-in makes a new empty account.

**Change a friend's email:** at home, in `/admin/`, **Users**, change **Email address** on their account first. The username can stay as it is. Then swap the address in `Allowed emails`. In the other order, the new email gets a new empty account.

**"Cannot sign in" page:** it says why. "More than one Couchlog account uses this email" means two accounts in `/admin/` have the same address, so change or clear one. "Another account already uses this email as its username" means an account has that email as its username but a different email address, so fix that account in `/admin/`. "Try again in a few minutes" means the Pi could not fetch Cloudflare's keys, so check that the Pi has internet.

**If the tunnel is down** (the home address keeps working, so Couchlog can still be used at home):
1. `docker compose ps` shows whether `tunnel` is running. `docker compose logs --tail 20 tunnel` says why not.
2. `docker compose restart tunnel`.
3. Cloudflare's error page gives a number. **1033** means the tunnel is not connected: check the Pi is on and has internet. **502** means the tunnel is fine but the app is not answering: `docker compose ps` and `docker compose logs --tail 20 couchlog`. **400** in the app's log means the address is missing from `DJANGO_ALLOWED_HOSTS`, and a **403** on a form means it is missing from `DJANGO_CSRF_TRUSTED_ORIGINS`.

**If the token leaks** (anyone who has it can run the tunnel): delete the tunnel in the dashboard, create a new one with the same route and Protect with Access, and put the new token in `.env`. The Access application stays as it is.

**Updating the tunnel:** change the version in `docker-compose.yml` in a pull request. Keep it at 2026.10.2 or newer, because older versions still trust eMudhra's compromised certificates ([Cloudflare's post](https://blog.cloudflare.com/emudhra-certificate-compromise/)).

## The public demo on Render

The demo ([demo.md](demo.md)) is a separate copy of Couchlog at `https://couchlog-demo.ana-cata.com`, built by Render from this repo's `Dockerfile`. It never runs on the Pi and has none of the Pi's secrets. Render and Cloudflare may word these buttons slightly differently.

**Before (done once):** make the Render account, read the current free plan (going over a free limit must suspend the service, not charge; and whether it asks for a card), and give Render access to `ana-cata/couchlog` only (GitHub → Settings → Applications → Render → Only select repositories).

**Deploy it** (done once):
1. In Render: **New** → **Web Service** → the `couchlog` repo. Language **Docker**, branch `main`, a region in Europe, instance type **Free**. Leave the health check path empty.
2. Under **Environment**, add these, and nothing else (no `R2_…`, no `CLOUDFLARE_ACCESS_…`, no `TUNNEL_TOKEN`: with any of them the demo refuses to start):
   ```
   DEMO_MODE=true
   DJANGO_DEBUG=false
   DJANGO_SECRET_KEY=<a new long random text, not the PC's or the Pi's>
   TMDB_API_KEY=<the TMDB key>
   DJANGO_DB_PATH=/data/db.sqlite3
   DJANGO_ALLOWED_HOSTS=couchlog-demo.ana-cata.com,<name>.onrender.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://couchlog-demo.ana-cata.com,https://<name>.onrender.com
   ```
   Make the secret key with `uv run python -c "import secrets; print(secrets.token_urlsafe(50))"`. `<name>.onrender.com` is the address Render shows at the top of the service. `DJANGO_DB_PATH` matters: the app runs as a normal user that can only write in `/data`.
3. **Deploy.** When the log says gunicorn is listening, open `https://<name>.onrender.com`. The **Try the demo** page with the demo banner appears.
4. **The address.** In Render, service **Settings** → **Custom Domains** → add `couchlog-demo.ana-cata.com`. In Cloudflare, **DNS** for `ana-cata.com`, add a `CNAME` named `couchlog-demo` pointing at `<name>.onrender.com`, with the proxy **off** (grey cloud) until Render shows the domain as verified with its certificate. Then turn the proxy **on** (orange cloud): the rate limiting rule only sees traffic that goes through Cloudflare. Under **SSL/TLS**, the mode must be **Full (strict)**, or the page loops.
5. **The rate limiting rule** (the free plan has one): **Security** → **WAF** → **Rate limiting rules** → create one for requests where the hostname equals `couchlog-demo.ana-cata.com`, counted per IP, 30 requests in 10 seconds, action **Block** for 10 seconds. A demo of another app later can share this one rule: change it to "hostname is in" and list both addresses.
6. **Check it** on the phone on mobile data with Wi-Fi off: open `https://couchlog-demo.ana-cata.com`, press **Try the demo**, see the sample titles on Home, Movies, Series and Calendar. Open it in a second browser: it is a different account. `https://couchlog-demo.ana-cata.com/admin/` says not found. About shows the TMDB credit.

**New versions:** Render deploys by itself after each merge to `main` (Auto-Deploy). A deploy empties the demo, like a restart.

**Switch it off quickly**, from the phone if needed, any one of these:
- **Stop it:** Render → the service → **Settings** → **Suspend Web Service**. The address stops answering. **Resume** brings it back, empty.
- **No new visitors, keep the current ones:** set `DEMO_ACCOUNTS_PER_DAY=0` under **Environment**. The button then says the demo is full. (Saving restarts the demo, which empties it.)
- **Take the address away:** delete the `couchlog-demo` record in Cloudflare's DNS.

**If the TMDB key leaks:** make a new key on TMDB (TMDB account → Settings → API; the old one stops working), and put it in `TMDB_API_KEY` on Render and in the Pi's `.env`.

**Limits:** see [demo.md](demo.md). They are changed under **Environment**, with no new deploy.

## How it works

- **`Dockerfile`**: a small Python 3.14 image. It installs the packages exactly as `uv.lock` says (no dev tools), copies the code, runs `collectstatic`, and runs as a normal user (`app`), not root. On start it applies the migrations, then starts **gunicorn** (the server that runs the app) with 2 workers of 4 threads each on port 8000, so a page waiting for TMDB does not hold up the others. Those numbers are in `gunicorn.conf.py`, which gunicorn reads by itself; in the public demo it is 1 worker, on the port Render gives in `PORT`.
- **`docker-compose.yml`**: three containers. `couchlog` and `daily` come from one image, named `couchlog`; `tunnel` is below. The image is built on the machine's own network (`network: host`): on the Pi, the build's temporary container failed to look up the Python packages' site, most likely because the Pi's first three DNS servers are IPv6 and that container has no IPv6. Docker asks for permission for that, and `docker compose` has no way to give it, so the build is its own command, `docker buildx bake --allow=network.host`. `docker compose up --build` stops on the Pi with "additional privileges requested" (Buildx 0.38.1; Buildx 0.37.0 on the PC did not ask). The permission applies to the build only; the running containers do not use the machine's network. Port 3000 on the host goes to 8000 inside. `.env` is handed to the container when it starts and is never copied into the image. The volume `couchlog-data` is mounted at `/data`. `restart: unless-stopped` brings it back after a crash and when the Pi restarts (but not after you stopped it yourself with `docker compose stop`).
- **The `daily` container** runs `python manage.py run_daily` (`core/management/commands/run_daily.py`), with the same `.env`, settings and volume as the app and no port.
  - It first waits until the database has every migration, checking every 5 seconds, because the app applies them when its own container starts and both start together. The check is in the command, and not Compose's `depends_on`, because Docker does not follow `depends_on` when it restarts containers after a reboot.
  - It then runs the commands in `DAILY_COMMANDS` (`refresh_calendar`, then `backup_db`) and sleeps 24 hours. There is no fixed hour: the 24 hours count from when the container started, so a deploy or a reboot moves the time.
  - Any error is written to the log and the loop goes on. One command failing does not stop the next.
  - `restart: unless-stopped` is what makes it run again when the Pi starts. `init: true` lets `docker compose down` stop it at once.
- **The `tunnel` container** runs Cloudflare's connector (`cloudflared`) at a fixed version, with no port of its own and no access to the database.
  - It is in a Compose **profile** (a group of containers that only starts when asked for), and `COMPOSE_PROFILES=tunnel` in the Pi's `.env` asks for it. The PC has no token, so there it does not start.
  - `TUNNEL_TOKEN` only reaches this container: `couchlog` and `daily` read the same `.env`, so Compose blanks it for them.
  - It reaches the app as `couchlog:8000` on Docker's own network, and `restart: unless-stopped` brings it back when the Pi restarts.
- **`.dockerignore`**: keeps `.env`, the database files, `.venv`, `.git`, the tests, `docs/` and `Identity/` out of the image.
- **Settings** (all in `.env`, see `.env.example`):

| Setting | In Docker |
|---|---|
| `DJANGO_DEBUG` | Always `false`; Compose sets it and it wins over `.env`. |
| `DJANGO_SECRET_KEY` | Required. Without it the container stops with "Set DJANGO_SECRET_KEY in the .env file." |
| `DJANGO_ALLOWED_HOSTS` | Must contain the address you open (`localhost` is the default; on the Pi it is `192.168.1.164,homelab.local,couchlog.ana-cata.com`). |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Only on the Pi: `https://couchlog.ana-cata.com`. Without it, every form sent through that address is refused. Empty means none, which is all the home address needs. |
| `COMPOSE_PROFILES` | `tunnel` on the Pi, so the tunnel starts. Left out on the PC. |
| `TUNNEL_TOKEN` | Only on the Pi. The tunnel's secret. Compose reads it for the `tunnel` container only. |
| `CLOUDFLARE_ACCESS_TEAM_DOMAIN`, `CLOUDFLARE_ACCESS_AUD`, `CLOUDFLARE_ACCESS_ADDRESS` | Only on the Pi: the team's address and the public address (both without `https://`) and the application's AUD tag. All three empty means the sign-in by email code is off. With only some set, or with `https://` in an address, the app refuses to start, so a mistake cannot leave the password form and `/admin/` open on the public address. See [profile.md](profile.md). |
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
- **HTTPS** is Cloudflare's job on the outside address. The app itself still receives plain HTTP from the tunnel, inside the Pi, and the home address is plain HTTP, so the "secure cookie" and "redirect to HTTPS" settings stay off. Turning them on would break the login on `http://` (to be settled in the security check, card #99). Because the app sees HTTP while the browser is on `https://`, Django cannot match a form to its address by itself, which is what `DJANGO_CSRF_TRUSTED_ORIGINS` is for.
- **Tests**: `core/tests/test_production_settings.py` checks the database path (and its fallback to `db.sqlite3`), the power-cut settings, that debug off without a secret key refuses to start, and that the CSS, logo and htmx are served without a login. `core/tests/test_run_daily.py` checks that `run_daily` refreshes at the start and a day later, survives failures, and waits for the migrations. `core/tests/test_backups.py` uses a fake R2 and a made-up database in write-ahead log mode, and checks the copy, that no key or login session is in it, that only 14 copies are left, and that restore and undo work. `core/tests/test_cloudflare_address.py` uses Django's real forged-request protection, and checks that the trusted addresses come from the setting, that a form from a trusted address is accepted and one from another address refused, and that logging in at the home address still works. `core/tests/test_cloudflare_sign_in.py` uses made-up keys and tokens, and checks every way a token can be wrong, how the account is found or created, the home address ignoring the header, `/admin/`, and Log out. The containers, the real R2 and the real Cloudflare are checked by hand with the steps above.

**Known limits**
- `homelab.local` can point to any of the Pi's addresses, including its Wi-Fi one. `192.168.1.164` is the fixed address, so use it for bookmarks.
- A refresh that fails is only tried again 24 hours later. If the Pi's network is not ready just after a restart, that day's first refresh is lost; `docker compose restart daily` runs it again.
- Migrations run at every start. Copying the database before a deploy that changes the tables is still a habit of mine (plan.md, section 4): `backup_db` by hand, above.
- "14 copies" means the last 14 runs, not 14 days. Each restart of `daily` makes one, so a day with many restarts or deploys pushes older copies out sooner.
- If the 5 GB limit is ever reached, backups stop until copies are deleted from the bucket by hand, and the only sign is the line in `docker compose logs daily`. Only Couchlog's copies are counted, not other files or other buckets.
- A failed backup is only tried again 24 hours later; `docker compose exec daily python manage.py backup_db` makes one at once.
- Cloudflare sits in the middle of the outside connection, so it could technically see what passes through. Accepted (plan.md, section 2).
- The login page's logo needs a public web address, and everything under `couchlog.ana-cata.com` is behind the email step, so the page has no logo for now.
