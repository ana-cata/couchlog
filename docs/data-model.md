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
| `core_title` | A movie or series saved from TMDB when someone first adds it (or opens a series page): `kind` (`movie` or `series`), `tmdb_id`, `title`, `year`, `poster_url`, `overview` and, for a series, `episodes_refreshed_at` (when its episodes were last asked from TMDB) and `status` (TMDB's own word, such as "Returning Series" or "Ended"; empty until the first refresh) and, for a movie, `streaming_at` (the earliest streaming release TMDB lists in any country, as a moment at midnight UTC; empty when TMDB has none or the job has not run). One row per title, shared by all accounts. Unique on `kind` + `tmdb_id`. | [To Watch](to-watch.md), [Series](series.md), [Calendar](calendar.md) |
| `core_episode` | One episode of a series, saved from TMDB: `title` (the series, links to `core_title`), `tmdb_id` (TMDB's episode id), `season_number` (0 = Specials), `episode_number`, `name`, `air_date` (empty when TMDB has none) and `runtime` (minutes, may be empty). Shared by all accounts. Unique on `title` + `tmdb_id`. Matched by TMDB's id when refreshed, so a renumbered episode keeps its watches; rows are never deleted. | [Series](series.md), [Calendar](calendar.md) |
| `core_towatchitem` | One title on one account's To Watch list: `user`, `title` (links to `core_title`), `added_at`, `removed_at` (empty while on the list; filled in when removed, so undo can restore it) and `removed_by_watch` (links to `core_watch`; only set when marking the title as watched took it off the list). Unique on `user` + `title`. | [To Watch](to-watch.md), [Search](search.md), [History](history.md), [Calendar](calendar.md) |
| `core_watch` | One time an account watched a title or an episode: `user`, `title` (links to `core_title`; for an episode, its series), `episode` (links to `core_episode`; empty for a movie), `watched_on` (a day; empty means date unknown; for an episode, the day the button was pressed) and `created_at`. No "one per title" limit, so rewatches use the same table. Undo deletes the row (for a whole season marked as not watched, all of that season's rows of the account). | [History](history.md), [Series](series.md) |
| `auth_user` | The accounts (username, password, last login). I create them in Django's admin page. | [Login](profile.md) |
| `auth_group`, `auth_permission` and their link tables | Groups and permissions. Not used by Couchlog for now. | Django's admin page |
| `django_session` | Who is logged in, by browser session. | [Login](profile.md) |
| `django_admin_log` | History of changes made in the admin page. | Django's admin page |
| `django_content_type` | Django's internal list of tables. | Django itself |
| `django_migrations` | Which migrations have already run on this database. | `migrate` |

**Known limits**
- The database path is fixed. When the app moves into Docker on the Pi (milestone M6), the path will need to be configurable so the file can live in a Docker volume.
- Safe SQLite settings against power cuts, and automatic backups, come with the Pi (milestone M6).
