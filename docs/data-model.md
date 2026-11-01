# Data model

The database and its tables. Several pages of the app share these tables, so they are described here and not on each page.

## What it does

- All of Couchlog's data lives in one file, `db.sqlite3`, in the project folder on the PC.
- The file is private: it is never committed to GitHub, and it is not shared between the PC and the Raspberry Pi. The Pi starts with its own fresh database.
- The file is created and changed only by running migrations (scripted table changes). Nobody edits tables by hand.
- Tests never touch this file. They use a temporary database that disappears when the tests finish.

## How it works

**Create or update the database on the PC**
- `uv run python manage.py migrate` creates `db.sqlite3` if it is missing, then applies every migration that has not run yet. It is safe to run again: when everything is up to date it does nothing.
- To start over on the PC, stop the app, delete `db.sqlite3`, and run `migrate` again. Everything in it is lost, so only do this while the data is test data.

**Change a table**
1. Change the model in the app's `models.py`.
2. `uv run python manage.py makemigrations` writes a new migration file in the app's `migrations/` folder.
3. `uv run python manage.py migrate` applies it to the PC's database.
4. Commit the migration file together with the model change. The test `test_every_table_change_has_a_migration_file` fails if the file is missing.

**Tests and the database**
- `pytest-django` gives each test run a temporary database that lives in memory. It is built from the same migrations, so a test run also proves the migrations work from nothing.
- A test can only use the database if it is marked `@pytest.mark.django_db`. Without the mark, touching the database is an error.
- Each test starts from an empty database: what one test saves is gone for the next.
- `core/tests/test_database.py` proves the temporary database is used and `db.sqlite3` is left alone.

**Settings**
- The database is set in `config/settings.py` under `DATABASES`: SQLite, file `db.sqlite3` in the project folder.
- `*.sqlite3` and the other database file types are in `.gitignore`.

**Tables that exist now**

Each card that adds a table updates this list.

| Table | What it holds | Used by |
|---|---|---|
| `core_profile` | Couchlog's own settings for an account, one row per account: `user` (links to `auth_user`, deleted with it) and `timezone` (a name like `Europe/Lisbon`, empty until chosen). | [Profile](profile.md) |
| `core_title` | A movie or series saved from TMDB when someone first adds it, marks it as watched or rates it (or opens a series page): `kind` (`movie` or `series`), `tmdb_id`, `title`, `year`, `poster_url`, `backdrop_url` (the wide banner picture shown in the News section on Home; empty when TMDB has none, and for a title saved before banners were kept, until `refresh_calendar` runs), `overview`, `runtime` (minutes, for the time spent on [Profile](profile.md): a movie's own runtime, or for a series its typical episode runtime, the average of its episodes' runtimes, used for an episode that has none; empty when TMDB has none, and for a title saved before runtimes were kept, until `refresh_calendar` runs) and `genres` (TMDB's genres in its order, a list like `[{"id": 18, "name": "Drama"}]`, shown in the line under a series' name on its page (a movie's page reads them from TMDB each time); empty when TMDB has none, and for a title saved before genres were kept, until `refresh_calendar` runs or, for a series, until its page is opened after a day) and, for a series, `episodes_refreshed_at` (when its episodes were last asked from TMDB) and `status` (TMDB's own word, such as "Returning Series" or "Ended"; empty until the first refresh) and `imdb_id` (its IMDb id as TMDB gives it, empty when TMDB has none) and `tvmaze_id` (its id on TVmaze, remembered once found; empty until then and when TVmaze does not know it) and, for a movie, `cinema_at` and `streaming_at` (the earliest cinema release and the earliest streaming release TMDB lists in any country, as moments at midnight UTC; each empty when TMDB has none or the job has not run). One row per title, shared by all accounts. Unique on `kind` + `tmdb_id`. | [To Watch](to-watch.md), [Series](series.md), [Calendar](calendar.md), [Home](home.md), [Profile](profile.md), [Search](search.md) (the title pages) |
| `core_episode` | One episode of a series, saved from TMDB: `title` (the series, links to `core_title`), `tmdb_id` (TMDB's episode id), `season_number` (0 = Specials), `episode_number`, `name`, `air_date` (empty when TMDB has none) and `runtime` (minutes, may be empty; an episode with none counts as its series' typical runtime in the time spent on [Profile](profile.md)). Shared by all accounts. Unique on `title` + `tmdb_id`. Matched by TMDB's id when refreshed, so a renumbered episode keeps its watches; rows are never deleted. | [Series](series.md), [Calendar](calendar.md) |
| `core_upcomingepisode` | An upcoming episode that TVmaze lists, for the Calendar only: `title` (the series, links to `core_title`), `season_number`, `episode_number`, `name` (as TVmaze gives it, often "TBA") and `air_date` (a day). Not an episode: no watch can point at it, and it is not counted anywhere. All of a series' rows are replaced at each refresh, so rows come and go. Only the Calendar reads it. | [Calendar](calendar.md) |
| `core_towatchitem` | One title on one account's To Watch list: `user`, `title` (links to `core_title`), `added_at`, `removed_at` (empty while on the list; filled in when removed, so undo can restore it) and `removed_by_watch` (links to `core_watch`; only set when marking the title as watched took it off the list; when an older watch of a movie is taken back while newer ones remain, it moves to the earliest watch left). Unique on `user` + `title`. | [To Watch](to-watch.md), [Search](search.md), [History](history.md), [Calendar](calendar.md) |
| `core_watch` | One time an account watched a title or an episode: `user`, `title` (links to `core_title`; for an episode, its series), `episode` (links to `core_episode`; empty for a movie), `watched_on` (a day; empty means date unknown; for an episode, the day the button was pressed) and `created_at`. No "one per title" or "one per episode" limit: a rewatch is simply another row (a movie's "Watch again", an episode's circle pressed again, and "Watch Season N again", which adds one row for each aired episode), and the app counts an episode as watched when it has at least one row. Undo deletes only that row: a movie's "Remove this watch", an episode's "−" (its latest row), a season's "−" (the latest row of each episode that has more than one). Marking a whole season as not watched deletes all of that season's rows of the account. The time spent on [Profile](profile.md) adds up the runtime of every row, so it needs no table of its own. | [History](history.md), [Series](series.md), [Profile](profile.md) |
| `core_droppedseries` | One series one account gave up on: `user`, `title` (links to `core_title`) and `dropped_at`. Unique on `user` + `title`. Dropping only adds this row and bringing back deletes it, so the watches and the To Watch entry are never touched. A series with a row is in no tab but Dropped, and not on Home or the Calendar. | [Series](series.md), [Search](search.md), [Home](home.md), [Calendar](calendar.md) |
| `core_rating` | One account's star rating and short note for one title: `user`, `title` (links to `core_title`), `stars` (1 to 5; empty means no rating), `note` (up to 500 characters, checked by the form; empty means no note). Unique on `user` + `title`. Saving changes the row; removing both the stars and the note deletes it, so a row only exists while something is saved. There is no Undo, so nothing else is kept. Rated titles need not be watched. | [Search](search.md) (the title pages) |
| `auth_user` | The accounts (username, password, last login). I create them in Django's admin page. | [Login](profile.md) |
| `auth_group`, `auth_permission` and their link tables | Groups and permissions. Not used by Couchlog for now. | Django's admin page |
| `django_session` | Who is logged in, by browser session. | [Login](profile.md) |
| `django_admin_log` | History of changes made in the admin page. | Django's admin page |
| `django_content_type` | Django's internal list of tables. | Django itself |
| `django_migrations` | Which migrations have already run on this database. | `migrate` |

**Known limits**
- The database path is fixed. When the app moves into Docker on the Pi (milestone M6), the path will need to be configurable so the file can live in a Docker volume.
- Safe SQLite settings against power cuts, and automatic backups, come with the Pi (milestone M6).
