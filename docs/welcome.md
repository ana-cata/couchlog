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
- **Text only,** no screenshots, so it never goes out of date when a page changes and stays light on the phone (my decision on card #117). Words in the style of the empty lists ([messages.md](messages.md)); colours from `Identity/identity.md`.
- **Undo:** seeing the page changes nothing of your watches or lists, so there is nothing to undo; the About link is the way back to it.

## How it works

- **Page:** `core/templates/core/welcome.html`, served by the `welcome` view in `core/views.py`, marked `@login_not_required`. Its small CSS (`.welcome-skip`) is in `couchlog.css`.
- **Remembering it:** `welcome_seen` on `core_profile` ([data-model.md](data-model.md)). The `welcome` view sets it to true when a signed-in account opens the page.
  - The field's default is **true** ("seen"), so the migration (`0017_profile_welcome_seen`) marks every account that existed before as seen.
  - The two places where a new account starts set it to **false**: the Profile page when it makes an account's first Profile row (`get_or_create` in the `profile` view, the time zone step) and `start_account` in `core/demo.py` (Try the demo).
- **Sending a new account there:** `FirstStepsMiddleware` (`core/middleware.py`, which replaced `TimeZoneChosenMiddleware`) checks each request of a signed-in account: no time zone yet → the Profile page; time zone chosen but `welcome_seen` false → `/welcome/`. Profile, Log out and the welcome page itself are always open, so there is no loop. Saving the first time zone leads straight to `/welcome/`.
- **Tests:** `core/tests/test_welcome.py` (a new account sees it once, Skip and Start, an existing account never, About opens it, open without a login, the migration), the demo in `core/tests/test_demo.py`, and the Cloudflare address in `core/tests/test_cloudflare_sign_in.py`.

**Known limits**
- An account made in Django's admin page before this card, that has never signed in, has no Profile row yet. It counts as new and sees the page at its first sign-in.
- The steps describe the pages as they are today. A card that changes a button name or a tab should check this page too.
