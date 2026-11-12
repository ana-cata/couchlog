# About

## What it does

- **About page** (`/about/`, linked as "About" in the header of every page, next to Search, Movies, Series and Profile). It says what Couchlog is, shows the TMDB logo, and carries the notice TMDB requires: "This product uses the TMDB API but is not endorsed or certified by TMDB." Below it, a line says the dates of upcoming episodes also come from [TVmaze](https://www.tvmaze.com/), whose data is licensed CC BY-SA (a link to its terms).
- Under the credits, a **privacy note** says what Couchlog stores (watch history, ratings and notes, time zone, email), that daily backups are kept in Cloudflare R2, that the connection from outside the home goes through Cloudflare, and that anyone can ask for their data to be removed. GDPR (the EU's data protection law) applies if anyone using the app is in the EU.
- It is the TMDB credit that the free use of TMDB's data depends on (design rule 4 in [plan.md](../plan.md)). The logo is small, less prominent than Couchlog's own name.
- In the public demo ([demo.md](demo.md)) the TMDB credit is the same. The TVmaze line is not there (the demo does not use TVmaze), and the privacy note is replaced by one about the demo: it stores only what the visitor does, no email, no IP address and no backups, and each account is deleted after 24 hours.
- Anyone can open it, even without logging in, so the credit is also reachable from the login page. It shows nothing private.

## How it works

- The page is `core/templates/core/about.html`, served by the `about` view in `core/views.py`. It is marked `@login_not_required`; every other page is closed by default (see [profile.md](profile.md)).
- The header link is in `core/templates/core/base.html`, so every page has it. Search, Movies, Series and Profile only show when you are logged in; About always shows.
- The logo is `core/static/core/tmdb-logo.svg`, TMDB's blue square logo from their [logos and attribution page](https://www.themoviedb.org/about/logos-attribution). It is saved in the project, so the page works without internet. Do not edit the logo or change its colors.

**Keeping TMDB's details**
- TMDB's terms allow keeping what it says for at most 6 months. The daily `refresh_calendar` asks TMDB again about every saved title once its details are more than 5 months old, followed or not (see [Calendar](calendar.md)). Posters are not saved, only their addresses: the picture always comes from TMDB.
- A title TMDB has deleted keeps its saved details, because watches point to it. This is rare, and the command says so in its log.

**Known limits**
- TVmaze asks for credit by linking back to it from the app, which is that line (its terms are on https://www.tvmaze.com/api). If other data sources are added later (for example for streaming services), their credit goes on this page too.
