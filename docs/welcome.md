# Welcome page

## What it does

- **A short page that explains how Couchlog works** (`/welcome/`), in eight steps:
  1. **Find a title:** the search box, the **+** on a poster, and opening a title's page.
  2. **Keep it for later:** Add to To Watch (and Remove from To Watch).
  3. **A movie's page:** Rate it or add a note, the date, Mark as watched / Watch again, Date unknown, Mark as not watched / Remove this watch, and Where to watch.
  4. **A series' page:** Stop watching, Bring back, Remove from all lists, Add to To Watch; a season's line, Mark Season N as watched (and not watched), Watch Season N again, the round button for an episode (and the question about earlier episodes), the "−".
  5. **Your lists:** the tabs of Series (Watching, To Watch, Finished, Dropped) and Movies (To Watch, History).
  6. **Home:** News, Up Next and its round button.
  7. **Calendar:** what comes out further ahead.
  8. **Profile:** time spent watching, the time zone, Log out.
- **A new account sees it once,** right after its first sign-in, on any address: at home, from outside (Cloudflare), and in the demo. At home and from outside, the time zone step comes first ([profile.md](profile.md)) and the welcome page next. In the demo the time zone is already chosen, so Try the demo leads straight to it.
- **Never again by itself.** Opening the page counts as seen, however the visitor leaves it.
- **Skip** (a small quiet button at the top) and **Start using Couchlog** (the main button at the end) both go to Home.
- **Existing accounts** (the ones made before this page existed) count as having seen it, so nobody who already uses Couchlog is interrupted.
- **Read it again any time:** About has a "How Couchlog works" link ([about.md](about.md)). The page is open to everyone, also without signing in, because it shows nothing private.
- **Pictures with numbered red arrows.** Each step has a phone-sized picture of the page it talks about (two for a series' page), with numbered red arrows on what you can press. The numbered list under the picture says what each one does, with the same numbers. The pictures show the demo's sample titles, never anyone's real history. My decisions on card #117, on review: pictures (text alone was not enough), a step for each page, red arrows (an exception to the palette, written in `Identity/identity.md`) with numbers. Words in the style of the empty lists ([messages.md](messages.md)).
- **Undo:** seeing the page changes nothing of your watches or lists, so there is nothing to undo; the About link is the way back to it.

## How it works

- **Page:** `core/templates/core/welcome.html`, served by the `welcome` view in `core/views.py`, marked `@login_not_required`. Its small CSS (`.welcome-skip`, `.welcome-picture`) is in `couchlog.css`.
- **Pictures:** `core/static/core/welcome/1-search.jpg` to `9-profile.jpg`, about 450 KB together. Each is 390 pixels wide on the page (taken at twice that, so they stay sharp on a phone), shown at most 320 wide, with the thin card line around it. Each has its width and height in the page, so the text does not jump while they load, and words for screen readers (`alt`) that also say where each arrow points. They load only when scrolled to (`loading="lazy"`).
- **The arrows are drawn by the script** that takes the pictures (`scripts/welcome_screenshots.py`), on the real page, just before the picture is taken. Each one is aimed at a part of the page (a button, a box, or the words of a name), so they stay in the right place when the pictures are taken again. The list at the top of the script says, for each picture, which part of which page it shows and where each arrow points.
- **Remembering it:** `welcome_seen` on `core_profile` ([data-model.md](data-model.md)). The `welcome` view sets it to true when a signed-in account opens the page.
  - The field's default is **true** ("seen"), so the migration (`0017_profile_welcome_seen`) marks every account that existed before as seen.
  - The two places where a new account starts set it to **false**: the Profile page when it makes an account's first Profile row (`get_or_create` in the `profile` view, the time zone step) and `start_account` in `core/demo.py` (Try the demo).
- **Sending a new account there:** `FirstStepsMiddleware` (`core/middleware.py`, which replaced `TimeZoneChosenMiddleware`) checks each request of a signed-in account: no time zone yet → the Profile page; time zone chosen but `welcome_seen` false → `/welcome/`. Profile, Log out and the welcome page itself are always open, so there is no loop. Saving the first time zone leads straight to `/welcome/`.
- **Tests:** `core/tests/test_welcome.py` (a new account sees it once, Skip and Start, an existing account never, About opens it, open without a login, the eight steps, the pictures and their sizes, the migration), the demo in `core/tests/test_demo.py`, and the Cloudflare address in `core/tests/test_cloudflare_sign_in.py`.

**Taking the pictures again** (when a page they show changes)
1. Run a demo copy with its own database, so the real one is never touched (Git Bash, from the project folder; it needs the TMDB key in `.env`):
   `DJANGO_DB_PATH=/tmp/demo.sqlite3 DEMO_MODE=true uv run python manage.py migrate` and then the same with `runserver 127.0.0.1:8766`.
2. In a second window: `uv run python scripts/welcome_screenshots.py http://127.0.0.1:8766`. It presses Try the demo, opens each page at phone width, draws the arrows and saves the nine pictures over the old ones. It also writes each picture's new size into `welcome.html`.
3. Look at each picture: an arrow must point at its button and cover nothing important. To move one, change its side, place or length in the script's list and run it again. If a page gained or lost a button, change the arrows and the numbered list in `welcome.html` together. Then stop the demo copy and delete its database.

**Known limits**
- An account made in Django's admin page before this card, that has never signed in, has no Profile row yet. It counts as new and sees the page at its first sign-in.
- The steps and the pictures show the pages as they are today. A card that adds, removes or renames a button on one of these pages, or changes how one looks, should update the step and its numbered list, and take the pictures again.
- The pictures show TMDB's posters and banners, like the README's screenshots, under the TMDB credit on About.
