# CricketStats With MongoDB

This hackathon edition stores the existing CricketStats datasets in MongoDB.
The original project and SQLite files under `/Users/rkk/CricketStats` are left
unchanged and act only as migration sources.

## MongoDB quick start

Install the Python package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Start MongoDB with Docker, if available:

```bash
docker compose up -d
```

Alternatively, use MongoDB Community locally or MongoDB Atlas and set its URI:

```bash
export MONGODB_URI='mongodb://localhost:27017/?directConnection=true'
# For Atlas, use its mongodb+srv:// URI instead.
```

Migrate both existing databases:

```bash
cricketstats-migrate-mongodb --source all --drop
cricketstats-mongodb-verify
cricketstats-mongodb-check
```

Try a real MongoDB-backed query:

```bash
cricketstats-mongodb-demo summary
cricketstats-mongodb-demo top-test-batters --limit 10
cricketstats-mongodb-demo ipl-orange-caps --limit 10
```

## MongoDB natural-language assistant

The completed application asks Qwen to produce a read-only MongoDB aggregation
pipeline, validates it against an allowlist, rejects write/JavaScript operators,
and then executes it against the local MongoDB database.

General cricket:

```bash
ask-cricket-mongodb
ask-cricket-mongodb --question "How many Test hundreds did Sachin Tendulkar score?"
```

IPL:

```bash
ask-cricket-mongodb --ipl
ask-cricket-mongodb --ipl --question "Who won the IPL Orange Cap in 2023?"
```

Equivalent checkout scripts are `ask_cricket_mongo.py` and
`ask_ipl_mongo.py`. Add `--trace` to record the prompt, generated pipeline,
and result under `logs/mongodb/`.

## Web interface

Start the local UI:

```bash
cricketstats-web
```

Then open `http://127.0.0.1:8765`. The interface includes a Test/IPL selector,
question suggestions, answer presentation, and optional aggregation details.
It uses the local MongoDB service and remains bound to localhost by default.

Common stored career totals and IPL Orange/Purple Cap questions use
deterministic MongoDB pipelines rather than relying on model collection
selection. All other generated pipelines are read-only, limited, and run with
a 60-second database timeout.

The migration creates:

- `cricketstats`: the main dataset, with one collection per SQLite table.
- `cricketstats_ipl`: the IPL dataset and its additional delivery/team/record collections.
- `_migration_state`: resumable per-collection checkpoints.
- `_migration_metadata`: source and completion metadata.

Rows retain their column names and SQLite `rowid` becomes MongoDB `_id`.
JSON arrays/objects stored as SQLite text are converted into native BSON arrays
and documents. Useful compound indexes are created after each collection is
loaded. A stopped migration can be resumed by rerunning the command without
`--drop`.

The legacy SQLite importers and SQL-based Qwen assistants are preserved only as
reference/source tooling. The supported hackathon interface is the MongoDB
assistant above.

## Legacy SQLite source documentation

Import Cricsheet-style cricket match JSON files into a SQLite database.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Run

```bash
cricketstats --json-dir ~/CricketInfo/all_json --db cricketstats.sqlite
```

The importer creates a SQLite database with seven tables:

- `match_stats`: one row per match with teams, winner, year, venue, event name, event match number, event stage/group/sub-name, match type, toss, result, and innings totals.
- `match_innings_stats`: one row per innings with the team score, wickets, overs, run rate, extras breakdown, total display text, fall-of-wickets JSON, batting order, bowling order, and current striker/non-striker/bowler fields for scoreboard-style screens.
- `player_match_stats`: one row per player per match with batting, bowling, fielding statistics, and a JSON list of dismissal details.
- `player_match_innings_stats`: one row per player per innings with the same batting, bowling, and fielding statistics scoped to that innings. Test matches normally have four innings rows per player when all four innings are present. Each innings row also includes UI-oriented fields such as `team_player_position`, `batting_position`, `bowler_position`, `maidens`, `wides`, `no_balls`, `is_out`, `dismissal_text`, `dismissal_kind`, `dismissal_bowler`, `dismissal_fielders`, and fall-of-wicket fields.
- `player_batting_innings_stats`: one row per batting innings with match context, opposition, venue, date, score, not-out flag, dismissal, balls, boundaries, and strike rate.
- `player_career_stats`: career averages by player and format, including `competition_name = 'All'` rows for overall Tests/One Day/T20/IPL summaries plus competition-specific rows.
- `player_career_group_stats`: grouped career rows for opposition, year, and competition summaries.

SQLite does not support named schemas in the same way as PostgreSQL or SQL Server. The database file is named `cricketstats.sqlite`, and the tables live in SQLite's main database namespace.

For a quick test import:

```bash
cricketstats --json-dir ~/CricketInfo/all_json --db cricketstats.sqlite --limit 10
```

## Separate IPL database

Build an IPL-only database without changing `cricketstats.sqlite`:

```bash
ipl-database \
  --json-dir ~/CricketInfo/all_json \
  --db ipl_cricketstats.sqlite
```

When running directly from a checkout without installing the package:

```bash
PYTHONPATH=src python3 -m cricketstats.ipl_importer \
  --json-dir ~/CricketInfo/all_json \
  --db ipl_cricketstats.sqlite
```

The command selects only Cricsheet files whose event is `Indian Premier
League`. It creates the same match, innings, player-match, player-innings,
batting-innings, and player-career tables as the main importer, plus:

- `delivery_stats`: one row per ball, including match/innings/over context,
  batter, bowler, runs, extras, wickets, and a six indicator.
- `orange_cap_winners`: season run leaders derived from batting totals.
- `purple_cap_winners`: season wicket leaders, resolving ties by playoff
  wickets and then economy rate.
- `supplemental_matches`: verified fixtures that have no ball-by-ball JSON,
  such as matches washed out before a ball was bowled.
- `venue_aliases`: maps source venue spellings to a physical stadium name for
  venue-level aggregation.
- `hat_trick_stats`: one row per delivery that completed three consecutive
  bowler-credited wickets, with match and season context.
- `special_record_stats`: source-backed records requiring metadata not present
  in scorecards, such as historical capped/uncapped status.
- `team_last_place_finishes`: the bottom team in each season's final points
  table, preserving standings tie-break outcomes.
- `team_career_stats`: all-time matches, results, win percentage, runs,
  innings records, and title count for each franchise name.
- `team_season_stats`: the same core measures by IPL season, including a
  `champion` flag.

The source JSON is ball-by-ball data, so the database can answer questions
that aggregate below scorecard level. Re-run the command after adding new
season files; it recreates only the IPL database named with `--db`.

Howstat's IPL scorecards are useful for manual cross-checking, but its site
currently presents an anti-bot challenge to unattended downloads. The
repeatable import therefore uses the already-downloaded Cricsheet JSON rather
than attempting to bypass that protection.

### Ask Qwen IPL questions

Start the IPL-only natural-language interface:

```bash
python3 ask_ipl.py
```

To capture the full prompt, Qwen response, generated SQL, and database result:

```bash
python3 ask_ipl.py --trace
```

IPL traces are written to `logs/ipl/qwen_ipl_trace.jsonl`. The IPL prompt
augmentation lives in `ipl_sql_guide.md`; it is separate from the general
cricket guide.

Run the IPL Qwen regression suite with:

```bash
python3 scripts/eval_qwen.py --assistant ipl
```

Use `--trace` to save eval traces. The IPL suite is stored in
`evals/qwen_ipl_eval_cases.json`.

## Test

```bash
pytest
```

## ESPNcricinfo scorecard crawler

```bash
PYTHONPATH=src python3 -m cricketstats.espn_scorecard_crawler \
  --start-url https://www.espncricinfo.com/records/decade/1990s-199 \
  --output-dir espn_scorecards \
  --max-pages 100 \
  --max-depth 2 \
  --max-scorecards 50 \
  --delay 1.5
```

The crawler writes `espn_scorecards/crawl_index.json` and one JSON file per saved scorecard under `espn_scorecards/scorecards/`. ESPNcricinfo may block automated requests; if that happens, export your browser Cookie header into a text file and pass `--cookie-file path/to/cookies.txt`.

If you see `Crawled pages: 0` and `Failed pages: 1`, open `espn_scorecards/crawl_index.json`. A `403 Forbidden` error means ESPN blocked the request before the crawler could read links. To retry with browser cookies:

1. Open the ESPNcricinfo records page in your browser.
2. Open Developer Tools, go to Network, reload the page, and click the main records request.
3. Copy the request's `Cookie` header value into `cookies.txt` as one line.
4. Rerun the crawler with `--cookie-file cookies.txt`.

## CricketArchive Wayback scorecard crawler

If ESPNcricinfo blocks automated requests, the archived CricketArchive season pages can be crawled through the Internet Archive:

```bash
PYTHONPATH=src python3 -m cricketstats.cricketarchive_wayback_crawler \
  --start-url https://web.archive.org/web/20160323123343/http://cricketarchive.com/Archive/Seasons/index.html \
  --output-dir cricketarchive_wayback \
  --max-pages 100 \
  --max-depth 2 \
  --max-scorecards 50 \
  --delay 1.5
```

The crawler writes `cricketarchive_wayback/crawl_index.json` and one JSON file per saved scorecard under `cricketarchive_wayback/scorecards/`. Add `--include-html` if you also want the raw archived HTML for parser debugging.

## Men's Test scorecard pull

```bash
./scripts/pull_men_tests_scorecards.py \
  --start-url https://web.archive.org/web/20150923012547/http://cricketarchive.com/Archive/Records/Test/Overall/Team/List_of_Matches.html \
  --output-dir /Users/rkk/CricketStats/men_tests \
  --delay 2.5
```

The script saves each scorecard as JSON under `/Users/rkk/CricketStats/men_tests/<year>/`. Existing JSON files are skipped by default, so the pull can be rerun to resume after Wayback failures. Use `--overwrite` to regenerate files.
