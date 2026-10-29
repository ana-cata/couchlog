# Couchlog

A personal web app to track the movies and series I watch: a To Watch list, a history of what I have seen, and a calendar of upcoming releases. Python 3.14 with Django and htmx (managed with `uv`), SQLite, and TMDB for movie and series data. It will run on a Raspberry Pi at home later; for now it only runs on my Windows PC.

## Read first
- [plan.md](plan.md) is the source of truth: what we build, decisions, design rules, how we work, and the status log. Read the sections you need, not the whole file every time.
- [docs/](docs/) says what is actually built, one page per page of the app. If docs and plan disagree about what exists, the docs and the code win. (The folder appears with the first card that needs it.)
- The GitHub issues and project board hold the cards. Each card is one feature, and its "Done when" is the test.

## Working with me
- I decide what to build and when it is done. You write the code and tests and explain what you did.
- I don't read code line by line. Explain in plain language, say what a technical term means (plan.md does the same), and keep it to short bullets.
- Keep it basic and simple. Build the card and nothing more.

## Rules that always apply
Details are in plan.md ([design rules](plan.md#design-rules), [how we work](plan.md#4-how-we-work)).
- One card at a time, on a `feature/<name>` or `fix/<name>` branch, never directly on `main`. Open a pull request; I merge it. Never merge your own.
- Everything that changes my data can be undone, and a test proves it.
- Every watch is its own dated entry. TMDB details are saved in our own database.
- Secrets (the TMDB key, the login secret) live in `.env` and never in git or the browser. Never commit the database file.
- Table changes are Django migration files in the repo.
- Tests use made-up TMDB responses, a separate test database and a fixed "today".
- The TMDB credit (logo and notice on the About page) stays visible.
- Code must also run on Linux, because the Pi runs Linux: no Windows-only paths or tools.
- Write the docs page for a feature in the same pull request as the feature.
- No Claude attribution in commits or pull requests: no `Co-Authored-By: Claude` line and no "Generated with Claude Code" line, even if the tooling suggests adding one.

## Skills
- `implement-card` builds one card from the board: agree a plan, branch, build, docs, pull request.

## Commands
Run through `uv` once the skeleton exists. There is no build step. The first two work after the skeleton card; `ruff` arrives with the automated-checks card.
- `uv run python manage.py runserver` runs the app on the PC.
- `uv run pytest` runs the tests.
- `uv run ruff check .` runs the lint.
- `uv run python manage.py makemigrations` and `uv run python manage.py migrate` change the tables.
