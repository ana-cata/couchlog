# The security check

## What it does

- A careful self-check of Couchlog as it really runs: the code, its packages, the settings, the Docker image, the Pi, the Cloudflare address, the backups and the public demo. It was first run on 2026-11-11 (card #99), before the repo went public.
- **When to run it again:** before any big change, such as opening Couchlog to more people, and after a change to the login, the Cloudflare setup or the demo.
- It is a self-check with standard tools, **not** a professional penetration test. Passing it does not prove there are no problems.
- **Scans only ever target my own addresses and my own Pi.**
- **The result is a private report** on the PC, outside the repo (`couchlog-security-report.md` next to the `couchlog` folder). It stays out of the repo, issues and pull requests while anything in it is unfixed, because those are public. Each finding is rated:
  - **serious** and **medium:** fixed on a `fix/` branch, with a test where one is possible, before going public
  - **low:** I decide whether to fix or accept it

## How it works

Every tool runs once from Docker or `uvx` (which runs a Python tool without adding it to the project), so Couchlog gets no new package. Fixed versions make a re-run comparable; newer ones are fine.

### 1. Secrets
- The whole git history, not only today's files: `docker run --rm -v "${PWD}:/repo:ro" ghcr.io/gitleaks/gitleaks:v8.28.0 git /repo --redact`. Expected: "no leaks found".
- The image holds no `.env` and no database: build it (`docker buildx bake --pull --allow=network.host -f docker-compose.yml couchlog`), then `docker run --rm --entrypoint sh couchlog -c "find / -xdev \( -name '.env*' -o -name '*.sqlite3*' -o -name '*.db' \) 2>/dev/null"`. Expected: nothing printed.
- On the Pi: `ls -l ~/couchlog/.env` shows `-rw-------`.
- Read the issue and pull request text (`gh issue list --state all --json title,body,comments`, the same for `gh pr list`) for emails, keys, tokens and addresses.

### 2. Packages
- Couchlog's packages: `uv export --format requirements-txt --no-hashes --no-emit-project --all-groups -o req.txt`, then `uvx pip-audit==2.9.0 -r req.txt --no-deps --disable-pip`. Expected: "No known vulnerabilities found".
- The image: `docker save couchlog -o couchlog.tar`, then `docker run --rm -v "${PWD}:/scan" aquasec/trivy:0.67.2 image --input /scan/couchlog.tar --scanners vuln,secret --severity HIGH,CRITICAL`. Problems in the base Python image's system packages and in its own copy of `pip` are expected. Check that Couchlog's own packages (in `/app/.venv`) are clean.

### 3. Settings
Run `uv run python manage.py check --deploy` three times, with `DJANGO_DEBUG=false`, a long `DJANGO_SECRET_KEY` and `DJANGO_DB_PATH=:memory:`:
- **as the Pi:** `DJANGO_ALLOWED_HOSTS=192.168.1.164,couchlog.ana-cata.com`
- **as the Cloudflare address:** add the three `CLOUDFLARE_ACCESS_` settings with made-up values
- **as the demo:** `DEMO_MODE=true`

Expected:
- **On the Pi:** the warnings about Secure cookies and HSTS are expected, because the home address is plain HTTP and its login must keep working. The Cloudflare address keeps no login cookie, and Cloudflare adds HSTS there (step 5).
- **Email:** Couchlog sends no email, so the email warning can be ignored.

### 4. The code
- `uv run pytest core/tests/test_security.py` proves the app's promises on every address:
  - every page needs a login, except About, the login page and the demo button
  - every change needs a POST with Django's form code (CSRF)
  - one account cannot read or change another's data
  - notes, searches and TMDB names are shown as plain text
  - no "come back to" address can lead to another website
- Its first test fails when a new address is added without putting it in one of the groups (open, reads, changes). Add the new address to the right group and to the cross-account tests.
- Read through the code with these questions:
  - Is every query on watches, lists, ratings, notes or profiles limited to `request.user`?
  - Does anything use `|safe`, `mark_safe`, `innerHTML` or `csrf_exempt`?
  - Does every `next` go through `url_has_allowed_host_and_scheme`?

### 5. The real address (from any computer)
- `curl -sI https://couchlog.ana-cata.com/`, `/admin/`, `/login/`, and once with a made-up `Cf-Access-Jwt-Assertion` header and a made-up `CF_Authorization` cookie. Expected:
  - each is a `302` to `ana-cata.cloudflareaccess.com`
  - `http://` is a `301` to `https://`
  - the answer has a `strict-transport-security` header (Cloudflare: SSL/TLS → Edge Certificates → HSTS, without "Include subdomains")
- In Zero Trust → Access → Applications: the Couchlog application's domain is exactly `couchlog.ana-cata.com` (no `*`), and the policy lists full emails only.
- On mobile data, away from the home Wi-Fi: a port checker on the home's public address (from `https://ifconfig.me` while on the Wi-Fi), ports 22, 80, 443, 3000 and 8000. Expected: all closed.

### 6. The Pi and the backups
- `sudo sshd -T | grep -Ei 'passwordauthentication|permitrootlogin|kbdinteractive'`. Expected: password and keyboard logins off, root not allowed with a password.
- `sudo apt update && apt list --upgradable`: install what is listed.
- `sudo ss -tlnp`: only SSH and Couchlog (3000) listen.
- R2 bucket settings: public access and the `r2.dev` address disabled, no custom domain.
- A downloaded backup copy: `sqlite3 <file> "select count(*) from django_session;"` gives `0`.

### 7. The demo
- **Passive scan** (it watches and reports, it doesn't attack), within the demo's limits:
  - Run `docker run --rm -v "${PWD}:/zap/wrk:rw" ghcr.io/zaproxy/zaproxy:2.16.1 zap-baseline.py -t https://couchlog-demo.ana-cata.com -m 1 -r zap-demo.html -I`.
  - Expected: no failures.
  - These warnings are by design: the public CSS and scripts can be loaded by other sites, the `csrftoken` cookie can be read by scripts, `eval` appears in htmx, and pages aren't cached.
  - It presses the demo button, so it makes a demo account or two.
- **Mozilla HTTP Observatory** (`https://developer.mozilla.org/en-US/observatory`) on `couchlog-demo.ana-cata.com`.
- **The limits:** make one account and search 31 times; the 31st is refused. Removing a watch by guessing its number says "That watch is not in your history".
- `/admin/` and `couchlog-demo.onrender.com` are "not found".
- In Render's Environment settings, check:
  - there's no `R2_*` and no `CLOUDFLARE_ACCESS_*`
  - nothing names the Pi
