# Welcome page

## What it does

- **A short page that explains how Couchlog works** (`/welcome/`), in five steps:
  1. **Find a title:** Search, and what a title's page shows.
  2. **Keep it for later:** Add to To Watch, one list for movies and one for series.
  3. **Mark what you watch:** a movie with its date, an episode with its round button, or a whole season. Every watch keeps its date and can be taken back.
  4. **The Series tabs:** Watching, To Watch, Finished, Dropped.
  5. **Home and the Calendar:** News for the next 7 days, Up Next, and the Calendar further ahead.
- **A new account sees it once,** right after its first sign-in, on any address: at home, from outside (Cloudflare), and in the demo. At home and from outside, the time zone step comes first ([profile.md](profile.md)) and the welcome page next. In the demo the time zone is already chosen, so Try the demo leads straight to it.
- **Never again by itself.** Opening the page counts as seen, however the visitor leaves it.
- **Skip** (a small quiet button at the top) and **Start using Couchlog** (the main button at the end) both go to Home.
- **Existing accounts** (the ones made before this page existed) count as having seen it, so nobody who already uses Couchlog is interrupted.
- **Read it again any time:** About has a "How Couchlog works" link ([about.md](about.md)). The page is open to everyone, also without signing in, because it shows nothing private.
- **A small picture under each step,** a phone-sized piece of the page it talks about (my decision on card #117, on review: text alone was not enough). The pictures show the demo's sample titles, never anyone's real history. Words in the style of the empty lists ([messages.md](messages.md)); colours from `Identity/identity.md`.
- **Undo:** seeing the page changes nothing of your watches or lists, so there is nothing to undo; the About link is the way back to it.

## How it works

- **Page:** `core/templates/core/welcome.html`, served by the `welcome` view in `core/views.py`, marked `@login_not_required`. Its small CSS (`.welcome-skip`, `.welcome-picture`) is in `couchlog.css`.
- **Pictures:** `core/static/core/welcome/1-search.jpg` to `5-home.jpg`, about 280 KB together. Each is 390 pixels wide on the page (taken at twice that, so they stay sharp on a phone), shown at most 320 wide, with the thin card line around it. Each has its width and height in the page, so the text does not jump while they load, and words for screen readers (`alt`). They load only when scrolled to (`loading="lazy"`).
- **Remembering it:** `welcome_seen` on `core_profile` ([data-model.md](data-model.md)). The `welcome` view sets it to true when a signed-in account opens the page.
  - The field's default is **true** ("seen"), so the migration (`0017_profile_welcome_seen`) marks every account that existed before as seen.
  - The two places where a new account starts set it to **false**: the Profile page when it makes an account's first Profile row (`get_or_create` in the `profile` view, the time zone step) and `start_account` in `core/demo.py` (Try the demo).
- **Sending a new account there:** `FirstStepsMiddleware` (`core/middleware.py`, which replaced `TimeZoneChosenMiddleware`) checks each request of a signed-in account: no time zone yet → the Profile page; time zone chosen but `welcome_seen` false → `/welcome/`. Profile, Log out and the welcome page itself are always open, so there is no loop. Saving the first time zone leads straight to `/welcome/`.
- **Tests:** `core/tests/test_welcome.py` (a new account sees it once, Skip and Start, an existing account never, About opens it, open without a login, the pictures, the migration), the demo in `core/tests/test_demo.py`, and the Cloudflare address in `core/tests/test_cloudflare_sign_in.py`.

**Taking the pictures again** (when a page they show changes)
1. Run a demo copy with its own database, so the real one is never touched (Git Bash, from the project folder; it needs the TMDB key in `.env`):
   `DJANGO_DB_PATH=/tmp/demo.sqlite3 DEMO_MODE=true uv run python manage.py migrate` and then the same with `runserver 127.0.0.1:8766`.
2. In a second window: `uv run python scripts/welcome_screenshots.py http://127.0.0.1:8766`. It presses Try the demo, opens each page at phone width and saves the five pictures over the old ones. Which part of which page each picture shows is the list at the top of the script.
3. If a picture's size changed, put its new width and height (half the file's pixels) in `welcome.html`. Look at the page, then stop the demo copy and delete its database.

**Known limits**
- An account made in Django's admin page before this card, that has never signed in, has no Profile row yet. It counts as new and sees the page at its first sign-in.
- The steps and the pictures show the pages as they are today. A card that changes a button name, a tab or how one of these pages looks should check this page too, and take the pictures again.
- The pictures show TMDB's posters and banners, like the README's screenshots, under the TMDB credit on About.
