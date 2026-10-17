from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from cricketstats.importer import (
    create_schema,
    insert_match,
    parse_match_file,
    populate_player_summary_tables,
)

DEFAULT_JSON_DIR = Path.home() / "CricketInfo" / "all_json"
DEFAULT_DB_PATH = Path("ipl_cricketstats.sqlite")
IPL_EVENT_NAME = "Indian Premier League"


def drop_ipl_schema_extensions(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS delivery_stats;
        DROP TABLE IF EXISTS purple_cap_winners;
        DROP TABLE IF EXISTS orange_cap_winners;
        DROP TABLE IF EXISTS supplemental_matches;
        DROP TABLE IF EXISTS venue_aliases;
        DROP TABLE IF EXISTS hat_trick_stats;
        DROP TABLE IF EXISTS special_record_stats;
        DROP TABLE IF EXISTS team_last_place_finishes;
        DROP TABLE IF EXISTS team_season_stats;
        DROP TABLE IF EXISTS team_career_stats;
        """
    )


def is_ipl_match(path: Path) -> bool:
    """Return True when a Cricsheet JSON file describes an IPL match."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data: dict[str, Any] = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("info", {}).get("event", {}).get("name") == IPL_EVENT_NAME


def iter_ipl_files(json_dir: Path, *, limit: int | None = None) -> Iterator[Path]:
    selected = 0
    for path in sorted(json_dir.glob("*.json")):
        if not path.is_file() or not is_ipl_match(path):
            continue
        yield path
        selected += 1
        if limit is not None and selected >= limit:
            return


def create_team_summary_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS delivery_stats;
        DROP TABLE IF EXISTS purple_cap_winners;
        DROP TABLE IF EXISTS orange_cap_winners;
        DROP TABLE IF EXISTS supplemental_matches;
        DROP TABLE IF EXISTS venue_aliases;
        DROP TABLE IF EXISTS hat_trick_stats;
        DROP TABLE IF EXISTS special_record_stats;
        DROP TABLE IF EXISTS team_last_place_finishes;
        DROP TABLE IF EXISTS team_season_stats;
        DROP TABLE IF EXISTS team_career_stats;

        CREATE TABLE delivery_stats (
            match_id TEXT NOT NULL,
            innings_number INTEGER NOT NULL,
            over_number INTEGER NOT NULL,
            delivery_number INTEGER NOT NULL,
            batting_team TEXT NOT NULL,
            batter TEXT NOT NULL,
            non_striker TEXT,
            bowler TEXT NOT NULL,
            batter_runs INTEGER NOT NULL,
            extras_runs INTEGER NOT NULL,
            total_runs INTEGER NOT NULL,
            is_six INTEGER NOT NULL,
            extras_json TEXT,
            wickets_json TEXT,
            PRIMARY KEY (
                match_id, innings_number, over_number, delivery_number
            ),
            FOREIGN KEY (match_id) REFERENCES match_stats(match_id)
        );

        CREATE TABLE team_career_stats (
            team TEXT PRIMARY KEY,
            first_season TEXT,
            last_season TEXT,
            first_year INTEGER,
            last_year INTEGER,
            matches INTEGER NOT NULL,
            wins INTEGER NOT NULL,
            losses INTEGER NOT NULL,
            ties INTEGER NOT NULL,
            no_results INTEGER NOT NULL,
            win_percentage REAL,
            runs_for INTEGER NOT NULL,
            runs_against INTEGER NOT NULL,
            highest_innings INTEGER,
            lowest_completed_innings INTEGER,
            titles INTEGER NOT NULL
        );

        CREATE TABLE orange_cap_winners (
            season TEXT NOT NULL,
            year INTEGER NOT NULL,
            player_name TEXT NOT NULL,
            matches INTEGER NOT NULL,
            runs_scored INTEGER NOT NULL,
            source_method TEXT NOT NULL,
            PRIMARY KEY (season, player_name)
        );

        CREATE TABLE supplemental_matches (
            season TEXT NOT NULL,
            event_match_number INTEGER NOT NULL,
            match_date TEXT,
            team1 TEXT NOT NULL,
            team2 TEXT NOT NULL,
            result TEXT NOT NULL,
            note TEXT,
            source_url TEXT,
            PRIMARY KEY (season, event_match_number)
        );

        CREATE TABLE venue_aliases (
            raw_venue TEXT PRIMARY KEY,
            canonical_venue TEXT NOT NULL
        );

        CREATE TABLE hat_trick_stats (
            bowler TEXT NOT NULL,
            match_id TEXT NOT NULL,
            innings_number INTEGER NOT NULL,
            over_number INTEGER NOT NULL,
            delivery_number INTEGER NOT NULL,
            match_date TEXT,
            season TEXT,
            batting_team TEXT,
            source_method TEXT NOT NULL,
            PRIMARY KEY (
                bowler, match_id, innings_number, over_number, delivery_number
            ),
            FOREIGN KEY (match_id) REFERENCES match_stats(match_id)
        );

        CREATE TABLE special_record_stats (
            record_type TEXT NOT NULL,
            season TEXT NOT NULL,
            player_name TEXT NOT NULL,
            record_value INTEGER,
            record_unit TEXT,
            details TEXT,
            source_url TEXT NOT NULL,
            PRIMARY KEY (record_type, season, player_name)
        );

        CREATE TABLE team_last_place_finishes (
            season TEXT PRIMARY KEY,
            year INTEGER NOT NULL,
            team TEXT NOT NULL,
            points INTEGER,
            source_method TEXT NOT NULL,
            source_url TEXT
        );

        CREATE TABLE purple_cap_winners (
            season TEXT NOT NULL,
            year INTEGER NOT NULL,
            player_name TEXT NOT NULL,
            matches INTEGER NOT NULL,
            wickets_taken INTEGER NOT NULL,
            playoff_wickets INTEGER NOT NULL,
            economy_rate REAL,
            source_method TEXT NOT NULL,
            PRIMARY KEY (season, player_name)
        );

        CREATE TABLE team_season_stats (
            season TEXT NOT NULL,
            year INTEGER NOT NULL,
            team TEXT NOT NULL,
            matches INTEGER NOT NULL,
            wins INTEGER NOT NULL,
            losses INTEGER NOT NULL,
            ties INTEGER NOT NULL,
            no_results INTEGER NOT NULL,
            win_percentage REAL,
            runs_for INTEGER NOT NULL,
            runs_against INTEGER NOT NULL,
            highest_innings INTEGER,
            lowest_completed_innings INTEGER,
            champion INTEGER NOT NULL,
            PRIMARY KEY (season, team)
        );

        CREATE INDEX idx_team_season_stats_team
            ON team_season_stats(team, year);
        CREATE INDEX idx_delivery_stats_batter
            ON delivery_stats(batter);
        CREATE INDEX idx_delivery_stats_over
            ON delivery_stats(match_id, innings_number, over_number);
        CREATE INDEX idx_orange_cap_winners_player
            ON orange_cap_winners(player_name);
        CREATE INDEX idx_purple_cap_winners_player
            ON purple_cap_winners(player_name);
        """
    )


def insert_deliveries(conn: sqlite3.Connection, path: Path) -> None:
    with path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)

    rows: list[tuple[Any, ...]] = []
    for innings_number, innings in enumerate(data.get("innings", []), start=1):
        batting_team = innings.get("team", "")
        for over in innings.get("overs", []):
            over_number = int(over.get("over", 0))
            for delivery_number, delivery in enumerate(
                over.get("deliveries", []), start=1
            ):
                runs = delivery.get("runs", {})
                batter_runs = int(runs.get("batter", 0))
                extras_runs = int(runs.get("extras", 0))
                rows.append(
                    (
                        path.stem,
                        innings_number,
                        over_number,
                        delivery_number,
                        batting_team,
                        delivery.get("batter", ""),
                        delivery.get("non_striker"),
                        delivery.get("bowler", ""),
                        batter_runs,
                        extras_runs,
                        int(runs.get("total", batter_runs + extras_runs)),
                        int(batter_runs == 6),
                        json.dumps(delivery.get("extras"), sort_keys=True)
                        if delivery.get("extras")
                        else None,
                        json.dumps(delivery.get("wickets"), sort_keys=True)
                        if delivery.get("wickets")
                        else None,
                    )
                )

    conn.executemany(
        """
        INSERT INTO delivery_stats (
            match_id, innings_number, over_number, delivery_number,
            batting_team, batter, non_striker, bowler, batter_runs,
            extras_runs, total_runs, is_six, extras_json, wickets_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def populate_team_summary_tables(conn: sqlite3.Connection) -> None:
    sql = """
        WITH team_matches AS (
            SELECT match_id, season, year, team1 AS team, winner, result
            FROM match_stats
            UNION ALL
            SELECT match_id, season, year, team2 AS team, winner, result
            FROM match_stats
        ),
        innings_totals AS (
            SELECT
                tm.match_id,
                tm.team,
                SUM(CASE WHEN i.team = tm.team THEN i.runs ELSE 0 END) AS runs_for,
                SUM(CASE WHEN i.team <> tm.team THEN i.runs ELSE 0 END) AS runs_against,
                MAX(CASE WHEN i.team = tm.team THEN i.runs END) AS highest_innings,
                MIN(CASE
                    WHEN i.team = tm.team AND i.wickets = 10 THEN i.runs
                END) AS lowest_completed_innings
            FROM team_matches tm
            LEFT JOIN match_innings_stats i ON i.match_id = tm.match_id
            GROUP BY tm.match_id, tm.team
        ),
        finals AS (
            SELECT season, winner AS champion
            FROM match_stats
            WHERE winner IS NOT NULL
              AND (
                    LOWER(COALESCE(event_stage, '')) = 'final'
                    OR LOWER(COALESCE(event_sub_name, '')) = 'final'
                  )
        ),
        season_rows AS (
            SELECT
                tm.season,
                tm.year,
                tm.team,
                COUNT(*) AS matches,
                SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) AS wins,
                SUM(CASE
                    WHEN tm.winner IS NOT NULL AND tm.winner <> tm.team THEN 1
                    ELSE 0
                END) AS losses,
                SUM(CASE WHEN tm.result = 'tie' THEN 1 ELSE 0 END) AS ties,
                SUM(CASE WHEN tm.result = 'no result' THEN 1 ELSE 0 END) AS no_results,
                ROUND(
                    100.0 * SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE
                        WHEN tm.result = 'no result' THEN 0 ELSE 1
                    END), 0),
                    2
                ) AS win_percentage,
                SUM(COALESCE(it.runs_for, 0)) AS runs_for,
                SUM(COALESCE(it.runs_against, 0)) AS runs_against,
                MAX(it.highest_innings) AS highest_innings,
                MIN(it.lowest_completed_innings) AS lowest_completed_innings,
                MAX(CASE WHEN f.champion = tm.team THEN 1 ELSE 0 END) AS champion
            FROM team_matches tm
            JOIN innings_totals it
              ON it.match_id = tm.match_id AND it.team = tm.team
            LEFT JOIN finals f ON f.season = tm.season
            GROUP BY tm.season, tm.year, tm.team
        )
        INSERT INTO team_season_stats (
            season, year, team, matches, wins, losses, ties, no_results,
            win_percentage, runs_for, runs_against, highest_innings,
            lowest_completed_innings, champion
        )
        SELECT
            season, year, team, matches, wins, losses, ties, no_results,
            win_percentage, runs_for, runs_against, highest_innings,
            lowest_completed_innings, champion
        FROM season_rows;

        INSERT INTO team_career_stats (
            team, first_season, last_season, first_year, last_year, matches,
            wins, losses, ties, no_results, win_percentage, runs_for,
            runs_against, highest_innings, lowest_completed_innings, titles
        )
        SELECT
            team,
            MIN(season),
            MAX(season),
            MIN(year),
            MAX(year),
            SUM(matches),
            SUM(wins),
            SUM(losses),
            SUM(ties),
            SUM(no_results),
            ROUND(100.0 * SUM(wins) / NULLIF(SUM(matches) - SUM(no_results), 0), 2),
            SUM(runs_for),
            SUM(runs_against),
            MAX(highest_innings),
            MIN(lowest_completed_innings),
            SUM(champion)
        FROM team_season_stats
        GROUP BY team;
    """
    conn.executescript(
        """
        DELETE FROM team_season_stats;
        DELETE FROM team_career_stats;
        """
    )
    conn.executescript(sql)


def populate_cap_winner_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM orange_cap_winners;
        DELETE FROM purple_cap_winners;

        INSERT INTO orange_cap_winners (
            season, year, player_name, matches, runs_scored, source_method
        )
        WITH season_batting AS (
            SELECT
                m.season,
                m.year,
                p.player_name,
                COUNT(DISTINCT p.match_id) AS matches,
                SUM(p.runs_scored) AS runs_scored
            FROM player_batting_innings_stats p
            JOIN match_stats m ON m.match_id = p.match_id
            GROUP BY m.season, m.year, p.player_name
        ),
        ranked AS (
            SELECT
                *,
                DENSE_RANK() OVER (
                    PARTITION BY season
                    ORDER BY runs_scored DESC
                ) AS leader_rank
            FROM season_batting
        )
        SELECT
            season,
            year,
            player_name,
            matches,
            runs_scored,
            'derived from season batting totals'
        FROM ranked
        WHERE leader_rank = 1;

        INSERT INTO purple_cap_winners (
            season, year, player_name, matches, wickets_taken,
            playoff_wickets, economy_rate, source_method
        )
        WITH season_bowling AS (
            SELECT
                m.season,
                m.year,
                p.player_name,
                COUNT(DISTINCT p.match_id) AS matches,
                SUM(p.wickets_taken) AS wickets_taken,
                SUM(CASE
                    WHEN m.event_stage IS NOT NULL
                    THEN p.wickets_taken ELSE 0
                END) AS playoff_wickets,
                ROUND(
                    6.0 * SUM(p.runs_conceded)
                    / NULLIF(SUM(p.balls_bowled), 0),
                    2
                ) AS economy_rate
            FROM player_match_stats p
            JOIN match_stats m ON m.match_id = p.match_id
            GROUP BY m.season, m.year, p.player_name
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY season
                    ORDER BY
                        wickets_taken DESC,
                        playoff_wickets DESC,
                        economy_rate ASC,
                        player_name ASC
                ) AS leader_rank
            FROM season_bowling
        )
        SELECT
            season,
            year,
            player_name,
            matches,
            wickets_taken,
            playoff_wickets,
            economy_rate,
            'derived using wickets, playoff wickets, then economy'
        FROM ranked
        WHERE leader_rank = 1;
        """
    )


def populate_supplemental_matches(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM supplemental_matches")
    conn.executemany(
        """
        INSERT INTO supplemental_matches (
            season, event_match_number, match_date, team1, team2, result,
            note, source_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "2009",
                7,
                "2009-04-21",
                "Mumbai Indians",
                "Rajasthan Royals",
                "no result",
                "Washed out without a ball bowled; absent from Cricsheet JSON",
                "https://www.espn.com/cricket/series/8048/report/392187/utils",
            ),
        ],
    )


def populate_venue_aliases(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM venue_aliases")
    raw_venues = [
        row[0]
        for row in conn.execute(
            """
            SELECT DISTINCT venue
            FROM match_stats
            WHERE venue IS NOT NULL AND venue <> ''
            ORDER BY venue
            """
        )
    ]
    canonical_groups = {
        "Arun Jaitley Stadium": {
            "Arun Jaitley Stadium",
            "Arun Jaitley Stadium, Delhi",
            "Feroz Shah Kotla",
        },
        "Brabourne Stadium": {
            "Brabourne Stadium",
            "Brabourne Stadium, Mumbai",
        },
        "Dr DY Patil Sports Academy": {
            "Dr DY Patil Sports Academy",
            "Dr DY Patil Sports Academy, Mumbai",
        },
        "Eden Gardens": {"Eden Gardens", "Eden Gardens, Kolkata"},
        "M Chinnaswamy Stadium": {
            "M Chinnaswamy Stadium",
            "M Chinnaswamy Stadium, Bengaluru",
        },
        "MA Chidambaram Stadium, Chepauk": {
            "MA Chidambaram Stadium, Chepauk",
            "MA Chidambaram Stadium, Chepauk, Chennai",
        },
        "Maharaja Yadavindra Singh International Cricket Stadium": {
            "Maharaja Yadavindra Singh International Cricket Stadium, Mullanpur",
            "Maharaja Yadavindra Singh International Cricket Stadium, New Chandigarh",
        },
        "Punjab Cricket Association Stadium, Mohali": {
            "Punjab Cricket Association IS Bindra Stadium",
            "Punjab Cricket Association IS Bindra Stadium, Mohali",
            "Punjab Cricket Association Stadium, Mohali",
        },
        "Rajiv Gandhi International Stadium": {
            "Rajiv Gandhi International Stadium",
            "Rajiv Gandhi International Stadium, Uppal",
            "Rajiv Gandhi International Stadium, Uppal, Hyderabad",
        },
        "Sawai Mansingh Stadium": {
            "Sawai Mansingh Stadium",
            "Sawai Mansingh Stadium, Jaipur",
        },
        "Wankhede Stadium": {
            "Wankhede Stadium",
            "Wankhede Stadium, Mumbai",
        },
        "Zayed Cricket Stadium": {
            "Sheikh Zayed Stadium",
            "Zayed Cricket Stadium, Abu Dhabi",
        },
    }
    lookup = {
        raw: canonical
        for canonical, variants in canonical_groups.items()
        for raw in variants
    }
    conn.executemany(
        """
        INSERT INTO venue_aliases (raw_venue, canonical_venue)
        VALUES (?, ?)
        """,
        [(venue, lookup.get(venue, venue)) for venue in raw_venues],
    )


def populate_hat_trick_stats(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM hat_trick_stats;

        INSERT INTO hat_trick_stats (
            bowler, match_id, innings_number, over_number, delivery_number,
            match_date, season, batting_team, source_method
        )
        WITH bowler_deliveries AS (
            SELECT
                d.*,
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM json_each(COALESCE(d.wickets_json, '[]')) w
                    WHERE json_extract(w.value, '$.kind') NOT IN (
                        'run out',
                        'retired hurt',
                        'retired out',
                        'obstructing the field'
                    )
                ) THEN 1 ELSE 0 END AS bowler_wicket
            FROM delivery_stats d
        ),
        sequenced AS (
            SELECT
                *,
                LAG(bowler_wicket, 1) OVER (
                    PARTITION BY match_id, innings_number, bowler
                    ORDER BY over_number, delivery_number
                ) AS previous_wicket_1,
                LAG(bowler_wicket, 2) OVER (
                    PARTITION BY match_id, innings_number, bowler
                    ORDER BY over_number, delivery_number
                ) AS previous_wicket_2
            FROM bowler_deliveries
        )
        SELECT
            s.bowler,
            s.match_id,
            s.innings_number,
            s.over_number,
            s.delivery_number,
            m.match_date,
            m.season,
            s.batting_team,
            'three consecutive bowler-credited wickets'
        FROM sequenced s
        JOIN match_stats m ON m.match_id = s.match_id
        WHERE s.bowler_wicket = 1
          AND s.previous_wicket_1 = 1
          AND s.previous_wicket_2 = 1;
        """
    )


def populate_special_record_stats(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM special_record_stats")
    conn.executemany(
        """
        INSERT INTO special_record_stats (
            record_type, season, player_name, record_value, record_unit,
            details, source_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "fastest century by an uncapped Indian player",
                "2022",
                "RM Patidar",
                49,
                "balls",
                "Rajat Patidar reached 100 in 49 balls in the 2022 Eliminator",
                "https://www.iplt20.com/index.php/teams/royal-challengers-bengaluru/squad-details/5471",
            ),
        ],
    )


def populate_team_last_place_finishes(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM team_last_place_finishes")
    source_url = (
        "https://www.mykhel.com/cricket/"
        "ipl-2025-chennai-super-kings-become-10th-team-to-finish-in-bottom-"
        "of-an-ipl-season-check-full-lis-363773.html"
    )
    rows = [
        ("2007/08", 2008, "Deccan Chargers", 4),
        ("2009", 2009, "Kolkata Knight Riders", 7),
        ("2009/10", 2010, "Kings XI Punjab", 8),
        ("2011", 2011, "Delhi Daredevils", 9),
        ("2012", 2012, "Pune Warriors", 9),
        ("2013", 2013, "Delhi Daredevils", 6),
        ("2014", 2014, "Delhi Daredevils", 4),
        ("2015", 2015, "Kings XI Punjab", 6),
        ("2016", 2016, "Kings XI Punjab", 8),
        ("2017", 2017, "Royal Challengers Bangalore", 7),
        ("2018", 2018, "Delhi Daredevils", 10),
        ("2019", 2019, "Royal Challengers Bangalore", 11),
        ("2020/21", 2020, "Rajasthan Royals", 12),
        ("2021", 2021, "Sunrisers Hyderabad", 6),
        ("2022", 2022, "Mumbai Indians", 8),
        ("2023", 2023, "Sunrisers Hyderabad", 8),
        ("2024", 2024, "Mumbai Indians", 8),
        ("2025", 2025, "Chennai Super Kings", 8),
        ("2026", 2026, "Mumbai Indians", 8),
    ]
    conn.executemany(
        """
        INSERT INTO team_last_place_finishes (
            season, year, team, points, source_method, source_url
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                season,
                year,
                team,
                points,
                "historical points-table position; 2026 derived from final standings",
                source_url if year <= 2025 else None,
            )
            for season, year, team, points in rows
        ],
    )


def build_ipl_database(
    json_dir: Path,
    db_path: Path,
    *,
    limit: int | None = None,
) -> int:
    if not json_dir.is_dir():
        raise FileNotFoundError(f"JSON directory does not exist: {json_dir}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        drop_ipl_schema_extensions(conn)
        create_schema(conn)
        create_team_summary_tables(conn)

        imported = 0
        for path in iter_ipl_files(json_dir, limit=limit):
            insert_match(conn, parse_match_file(path))
            insert_deliveries(conn, path)
            imported += 1
            if imported % 250 == 0:
                conn.commit()

        populate_player_summary_tables(conn)
        populate_cap_winner_tables(conn)
        populate_supplemental_matches(conn)
        populate_venue_aliases(conn)
        populate_hat_trick_stats(conn)
        populate_special_record_stats(conn)
        populate_team_last_place_finishes(conn)
        populate_team_summary_tables(conn)
        conn.commit()
    return imported


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a separate IPL-only SQLite database from Cricsheet JSON."
    )
    parser.add_argument(
        "--json-dir",
        type=Path,
        default=DEFAULT_JSON_DIR,
        help=f"Directory containing Cricsheet JSON. Default: {DEFAULT_JSON_DIR}",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"IPL database to create. Default: {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Import only the first N IPL matches (for testing).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    imported = build_ipl_database(args.json_dir, args.db, limit=args.limit)
    print(f"Imported {imported} IPL matches into {args.db}")


if __name__ == "__main__":
    main()
