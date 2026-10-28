---
name: implement-card
description: >-
  Implement one Couchlog card (a GitHub issue on the project board): pick the next
  card or the one the user names, agree a short plan with the user, build it on a
  feature branch with tests, write the matching docs page, self-check against the
  plan's design rules, and open a pull request for human review. Never merges its
  own PR. Use when the user says "implement #5", "build the next card", "work on
  the next feature", "pick up the next issue", or asks what to build next.
---

# Implement Card

Builds one card from the board. The issue (its tasks and "Done when") and [plan.md](../../../plan.md) are the source of truth for *what* to build; the plan's [design rules](../../../plan.md#design-rules) and [workflow rules](../../../plan.md#4-how-we-work) govern *how*. There is no separate spec step: Step 2 is where the user approves the approach before any code is written.

**Talking to the user:** plain language and short bullets. They don't read code line by line, so explain behavior and choices, and say what a technical term means the first time, the way plan.md does. This only applies to chat with the user — code, commit messages, docs and the PR body follow their own rules below.

## Step 0 — Sync and pick the card

```bash
git checkout main
git pull
git status    # must be clean — if not, stop and ask
```

If a previous feature branch was merged, delete it with `git branch -d <branch>` (this refuses if it isn't merged, which is what we want).

Find the board and its Status options. Column names may differ from the plan (`Backlog` / `Ready` / `Doing` / `Done`, or GitHub's `Todo` / `In Progress` / `Done`) — go by meaning:

```bash
gh project list --owner ana-cata
gh project field-list <number> --owner ana-cata --format json    # Status field id + option ids
gh project view <number> --owner ana-cata --format json --jq .id # project id
gh project item-list <number> --owner ana-cata --format json --limit 100
```

Pick the card:
- If the user named one (`#5`), use it.
- Otherwise take the lowest-numbered open card that hasn't been started (issues were created in plan order, so a lower number is earlier).
- **One card at a time** ([section 4](../../../plan.md#4-how-we-work)): if another card is in progress, or `gh pr list --state open` shows an open PR, stop and say which one — unless the user says otherwise.
- If the card is already done or closed, say so instead of redoing it.

Plan checkboxes drift, so before building also check the card isn't already done: `git log --oneline` and `gh pr list --state merged`.

If `gh` isn't installed or logged in, say so once. Do the code work anyway, and at the end hand over the PR title, PR body and board move as steps for the user to do on github.com. (Fix: `winget install GitHub.cli`, `gh auth login`, `gh auth refresh -s project`.)

## Step 1 — Read the card

```bash
gh issue view <n> --comments
```

Read the whole issue, plus its feature entry in plan.md [section 3](../../../plan.md#3-features) and the milestone tasks it came from. Also read the parts of [section 7](../../../plan.md#7-testing-approach) (edge cases, how tests work) that touch this card, and `docs/` for anything already built that this card builds on.

- Tasks marked `(me)` are the user's. Don't do them. List them, and ask for them at the moment they block the work (for example the TMDB key). Never ask the user to paste a secret into chat — they put it in `.env.local` themselves.
- Lines marked "Open at spec time" or "Note" in the issue are questions to settle in Step 2.
- If the issue and plan.md disagree, say so and ask which wins.

## Step 2 — Plan and get approval (the one checkpoint)

Before writing any code, tell the user briefly:

- **What they'll be able to do** when this is finished, tied to each "Done when" condition.
- **What will be built:** screens, tables (and whether a migration is needed), server code, tests (including the undo test).
- **Docs:** which page you'll create or update (Step 7).
- **Plan changes:** which plan.md boxes get ticked, and whether a Decisions-table row changes (for example a library chosen).
- **Decisions that are theirs:** open questions from the issue, gaps in the plan, any choice between two reasonable approaches — each with a recommendation.
- **Size:** if the card looks like more than a few days of work, propose a split ([section 4](../../../plan.md#4-how-we-work): "keep cards small"). After they agree, create the new issues (`gh issue create`), add them to the parent's checklist as `- [ ] #<number>`, and build only the first.
- **Departures from the plan or issue,** and why.

**Wait for an explicit go-ahead.** Don't start coding on your own judgment. This is the only approval gate before code exists, and the user may not catch a wrong approach by reading the diff later.

## Step 3 — Branch and board

```bash
git checkout -b feature/<short-name>     # fix/<short-name> for a bug
```

Move the card to the in-progress column (`gh project item-edit --project-id <project-id> --id <item-id> --field-id <status-field-id> --single-select-option-id <option-id>`). Never work on `main`.

## Step 4 — Implement

Build what was agreed, in an order that lets you test as you go: migration → data code → server logic → screens → tests. Run the project's own scripts after each piece (`npm test`, `npm run lint`, `npm run build` — whatever `package.json` defines) so a mistake shows up while it is fresh.

Keep it basic and simple — it is the plan's guiding rule. Build the card and nothing more: no extra features, no new dependency without saying why, no clever structure the card doesn't need.

How tests work here ([section 7](../../../plan.md#7-testing-approach)):
- Made-up TMDB responses, never the real TMDB.
- A separate temporary test database, never the one with real history.
- A fixed "today" for anything that depends on dates.
- Every action that changes data gets a test that does it, undoes it, and checks everything is back as it was.

## Step 5 — Self-check (against the actual diff)

Run `git diff main...HEAD` and check each item for real, not from memory:

- [ ] Every "Done when" condition of the card is covered by a test or a manual step.
- [ ] **Undo** works for everything that changes data, and is tested (design rule 5).
- [ ] Every watch is its own entry with a date, and progress counts an episode as watched if it has at least one watch (rules 1 and 2).
- [ ] The TMDB key and other secrets never reach the browser and are not in the diff. `.env*` is not tracked.
- [ ] Database files (`*.db`, `*.sqlite*`) are gitignored and not in the diff. If their path isn't in `.gitignore` yet, add it in this PR.
- [ ] Table changes are migration files in the repo, not manual edits.
- [ ] Details from TMDB are saved in our own database, and a TMDB failure shows a friendly message (rule 6).
- [ ] "Today", "tomorrow" and "in N days" use the user's time zone, not the server's.
- [ ] The TMDB logo and notice are still visible if screens changed (rule 4).
- [ ] New code paths have tests, and the tests pass.
- [ ] The work is on a `feature/` or `fix/` branch, not `main`.

If something conflicts with the plan or the agreed approach, stop and flag it. Don't work around it silently.

## Step 6 — Validate

Run everything CI runs (lint, build, tests) once [`.github/workflows`](../../../.github/workflows) exists; before that, run the scripts `package.json` has and say CI isn't set up yet. All of it must pass.

If any screen changed, give the user concrete manual steps for each "Done when" (which page, what to click, what they should see), so they can try it with `npm run dev`. To check on the phone, open the PC's address from the phone on the home Wi-Fi.

## Step 7 — Docs (part of done)

A card is not done without its docs page. Write it from the code **as built**: if the build departed from the issue or plan, the docs follow the code and the PR says so.

Two readers: the user (who does not read the code line by line) and future Claude sessions (who need accurate facts fast). Layout:

- `README.md` — what Couchlog is, how to run it on the PC (install, `.env.local`, `npm run dev`, tests, migrations) and links to `docs/`. Update it whenever setup changes.
- `docs/home.md`, `docs/films.md`, `docs/series.md`, `docs/calendar.md`, `docs/profile.md` — one page per main page of the app. Home: Up Next, News, later suggestions. Calendar: upcoming releases of the series being watched and the titles on the To Watch list. Profile: account, login, time zone, and later statistics and favorites. A feature that doesn't live on one of these gets its own page named after its screen (for example `search`). Say which page in Step 2.
- `docs/data-model.md` — the tables and how they relate, since several pages share them (the watches table serves films, series and Up Next).

Each page has two parts:
- **What it does** — plain words, from the user's point of view.
- **How it works** — tables, pages and routes, TMDB calls, edge cases, known limits.

Update the page, don't append to it. Keep each page to about one screen. Never put secrets in docs.

Then update [plan.md](../../../plan.md): tick the boxes this card finished, add a line to the status log (section 10, with today's date), and change the Decisions table (section 2) if a decision was made. If the card finished a week or milestone that has a review point in the plan (end of Week 4, Week 6, after M3), tell the user.

## Step 8 — Ship

1. Stage the files by name (never `git add -A` or `git add .`, which can pick up `.env` or a database file).
2. Commit: a short imperative subject (about 50 characters), then a body that says *why* in plain words. No Claude attribution lines (no `Co-Authored-By`, no "Generated with Claude Code") in the commit or the PR body — see [CLAUDE.md](../../../CLAUDE.md).
3. `git push -u origin HEAD`
4. Open the PR:

```bash
gh pr create --title "<card title>" --body "$(cat <<'EOF'
Closes #<n>

## What changed
<plain words>

## Done when
- [ ] <each condition> — <how it was checked: test name or manual step>

## Try it yourself
<page, actions, expected result>

## Docs and plan
<docs page created/updated; plan boxes ticked>

## Differs from the issue or plan
<nothing, or what and why>
EOF
)"
```

5. Move the card to the review column if the board has one; otherwise leave it in progress.

**Never merge the PR yourself.** The user reads it, waits for green checks, merges, then re-checks the "Done when" conditions on `main` and moves the card to Done ([section 4](../../../plan.md#4-how-we-work), steps 5 and 6).

## Reference

- Plan, design rules, workflow: [plan.md](../../../plan.md)
- Testing approach: [plan.md section 7](../../../plan.md#7-testing-approach)
