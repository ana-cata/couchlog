# About

## What it does

- **About page** (`/about/`, linked as "About" in the header of every page, next to Search, Movies, Series and Profile). It says what Couchlog is, shows the TMDB logo, and carries the notice TMDB requires: "This product uses the TMDB API but is not endorsed or certified by TMDB."
- It is the TMDB credit that the free use of TMDB's data depends on (design rule 4 in [plan.md](../plan.md)). The logo is small, less prominent than Couchlog's own name.
- Anyone can open it, even without logging in, so the credit is also reachable from the login page. It shows nothing private.

## How it works

- The page is `core/templates/core/about.html`, served by the `about` view in `core/views.py`. It is marked `@login_not_required`; every other page is closed by default (see [profile.md](profile.md)).
- The header link is in `core/templates/core/base.html`, so every page has it. Search, Movies, Series and Profile only show when you are logged in; About always shows.
- The logo is `core/static/core/tmdb-logo.svg`, TMDB's blue square logo from their [logos and attribution page](https://www.themoviedb.org/about/logos-attribution). It is saved in the project, so the page works without internet. Do not edit the logo or change its colors.

**Known limits**
- If other data sources are added later (for example for streaming services), their credit goes on this page too.
