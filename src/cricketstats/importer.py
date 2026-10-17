from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DB_PATH = Path("cricketstats.sqlite")
JSON_DIR = Path.home() / "CricketInfo" / "all_json"

BOWLER_WICKET_KINDS = {
    "bowled",
    "caught",
    "caught and bowled",
    "hit wicket",
    "lbw",
    "stumped",
}

CATCH_KINDS = {"caught", "caught and bowled"}


@dataclass
class PlayerStats:
    match_id: str
    player_name: str
    team: str
    player_id: str | None = None
    runs_scored: int = 0
    balls_faced: int = 0
    fours: int = 0
    sixes: int = 0
    wickets_taken: int = 0
    balls_bowled: int = 0
    runs_conceded: int = 0
    catches: int = 0
    stumpings: int = 0
    run_outs: int = 0
    dismissals: int = 0
    dismissal_details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def strike_rate(self) -> float | None:
        if self.balls_faced == 0:
            return None
        return round(self.runs_scored * 100 / self.balls_faced, 2)

    @property
    def overs_bowled(self) -> str:
        overs, balls = divmod(self.balls_bowled, 6)
        return f"{overs}.{balls}"

    @property
    def economy_rate(self) -> float | None:
        if self.balls_bowled == 0:
            return None
        return round(self.runs_conceded * 6 / self.balls_bowled, 2)


@dataclass
class InningsPlayerStats(PlayerStats):
    innings_number: int = 0
    innings_team: str = ""
    team_player_position: int | None = None
    batting_position: int | None = None
    bowler_position: int | None = None
    is_current_batter: bool = False
    is_current_bowler: bool = False
    is_out: bool = False
    dismissal_text: str | None = None
    fall_of_wicket_order: int | None = None
    fall_of_wicket_runs: int | None = None
    fall_of_wicket_over: str | None = None
    maidens: int = 0
    wides: int = 0
    no_balls: int = 0


@dataclass
class InningsSummary:
    team: str
    runs: int = 0
    wickets: int = 0
    legal_balls: int = 0
    extras: dict[str, int] = field(default_factory=dict)
    fall_of_wickets: list[dict[str, Any]] = field(default_factory=list)
    batter_order: list[str] = field(default_factory=list)
    bowler_order: list[str] = field(default_factory=list)
    striker: str | None = None
    non_striker: str | None = None
    current_bowler: str | None = None
    bowler_over_runs: dict[tuple[str, int], int] = field(default_factory=dict)
    bowler_over_balls: dict[tuple[str, int], int] = field(default_factory=dict)

    @property
    def overs(self) -> str:
        overs, balls = divmod(self.legal_balls, 6)
        return f"{overs}.{balls}"


@dataclass
class MatchRows:
    match: dict[str, Any]
    innings: list[InningsSummary] = field(default_factory=list)
    players: list[PlayerStats] = field(default_factory=list)
    innings_players: list[InningsPlayerStats] = field(default_factory=list)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS player_match_stats;
        DROP TABLE IF EXISTS player_career_group_stats;
        DROP TABLE IF EXISTS player_career_stats;
        DROP TABLE IF EXISTS player_batting_innings_stats;
        DROP TABLE IF EXISTS player_match_innings_stats;
        DROP TABLE IF EXISTS match_innings_stats;
        DROP TABLE IF EXISTS match_stats;

        CREATE TABLE match_stats (
            match_id TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            match_date TEXT,
            year INTEGER,
            season TEXT,
            match_type TEXT,
            team_type TEXT,
            gender TEXT,
            city TEXT,
            venue TEXT,
            event_name TEXT,
            event_match_number INTEGER,
            event_stage TEXT,
            event_group TEXT,
            event_sub_name TEXT,
            event_json TEXT,
            team1 TEXT,
            team2 TEXT,
            toss_winner TEXT,
            toss_decision TEXT,
            winner TEXT,
            result TEXT,
            won_by_runs INTEGER,
            won_by_wickets INTEGER,
            balls_per_over INTEGER,
            scheduled_overs INTEGER,
            innings_count INTEGER,
            team1_runs INTEGER,
            team1_wickets INTEGER,
            team1_overs TEXT,
            team2_runs INTEGER,
            team2_wickets INTEGER,
            team2_overs TEXT
        );

        CREATE TABLE match_innings_stats (
            match_id TEXT NOT NULL,
            innings_number INTEGER NOT NULL,
            team TEXT NOT NULL,
            runs INTEGER NOT NULL,
            wickets INTEGER NOT NULL,
            overs TEXT NOT NULL,
            legal_balls INTEGER NOT NULL,
            run_rate REAL,
            extras_total INTEGER NOT NULL,
            byes INTEGER NOT NULL,
            legbyes INTEGER NOT NULL,
            wides INTEGER NOT NULL,
            no_balls INTEGER NOT NULL,
            penalties INTEGER NOT NULL,
            extras_text TEXT,
            total_text TEXT,
            fall_of_wickets_json TEXT,
            batting_order_json TEXT,
            bowling_order_json TEXT,
            striker TEXT,
            non_striker TEXT,
            current_bowler TEXT,
            PRIMARY KEY (match_id, innings_number),
            FOREIGN KEY (match_id) REFERENCES match_stats(match_id)
        );

        CREATE TABLE player_match_stats (
            match_id TEXT NOT NULL,
            player_name TEXT NOT NULL,
            player_id TEXT,
            team TEXT NOT NULL,
            runs_scored INTEGER NOT NULL,
            balls_faced INTEGER NOT NULL,
            fours INTEGER NOT NULL,
            sixes INTEGER NOT NULL,
            strike_rate REAL,
            wickets_taken INTEGER NOT NULL,
            balls_bowled INTEGER NOT NULL,
            overs_bowled TEXT NOT NULL,
            runs_conceded INTEGER NOT NULL,
            economy_rate REAL,
            catches INTEGER NOT NULL,
            stumpings INTEGER NOT NULL,
            run_outs INTEGER NOT NULL,
            dismissals INTEGER NOT NULL,
            dismissal_details_json TEXT,
            PRIMARY KEY (match_id, player_name),
            FOREIGN KEY (match_id) REFERENCES match_stats(match_id)
        );

        CREATE TABLE player_match_innings_stats (
            match_id TEXT NOT NULL,
            innings_number INTEGER NOT NULL,
            innings_team TEXT NOT NULL,
            player_name TEXT NOT NULL,
            player_id TEXT,
            team TEXT NOT NULL,
            team_player_position INTEGER,
            batting_position INTEGER,
            bowler_position INTEGER,
            is_current_batter INTEGER NOT NULL,
            is_current_bowler INTEGER NOT NULL,
            is_out INTEGER NOT NULL,
            runs_scored INTEGER NOT NULL,
            balls_faced INTEGER NOT NULL,
            fours INTEGER NOT NULL,
            sixes INTEGER NOT NULL,
            strike_rate REAL,
            wickets_taken INTEGER NOT NULL,
            balls_bowled INTEGER NOT NULL,
            overs_bowled TEXT NOT NULL,
            maidens INTEGER NOT NULL,
            runs_conceded INTEGER NOT NULL,
            economy_rate REAL,
            wides INTEGER NOT NULL,
            no_balls INTEGER NOT NULL,
            catches INTEGER NOT NULL,
            stumpings INTEGER NOT NULL,
            run_outs INTEGER NOT NULL,
            dismissals INTEGER NOT NULL,
            dismissal_kind TEXT,
            dismissal_bowler TEXT,
            dismissal_fielders TEXT,
            dismissal_text TEXT,
            fall_of_wicket_order INTEGER,
            fall_of_wicket_runs INTEGER,
            fall_of_wicket_over TEXT,
            dismissal_details_json TEXT,
            PRIMARY KEY (match_id, innings_number, player_name),
            FOREIGN KEY (match_id) REFERENCES match_stats(match_id)
        );

        CREATE INDEX idx_match_stats_year ON match_stats(year);
        CREATE INDEX idx_match_stats_match_type ON match_stats(match_type);
        CREATE INDEX idx_match_stats_winner ON match_stats(winner);
        CREATE INDEX idx_player_match_stats_player ON player_match_stats(player_name);
        CREATE INDEX idx_player_match_stats_team ON player_match_stats(team);
        CREATE INDEX idx_match_innings_stats_match
            ON match_innings_stats(match_id, innings_number);
        CREATE INDEX idx_player_match_innings_stats_player
            ON player_match_innings_stats(player_name);
        CREATE INDEX idx_player_match_innings_stats_match_innings
            ON player_match_innings_stats(match_id, innings_number);

        CREATE TABLE player_batting_innings_stats (
            player_name TEXT NOT NULL,
            player_id TEXT,
            format_group TEXT,
            match_type TEXT,
            competition_name TEXT,
            match_id TEXT NOT NULL,
            innings_number INTEGER NOT NULL,
            innings_team TEXT NOT NULL,
            player_team TEXT NOT NULL,
            opposition TEXT,
            match_date TEXT,
            year INTEGER,
            venue TEXT,
            city TEXT,
            batting_position INTEGER,
            runs_scored INTEGER NOT NULL,
            is_not_out INTEGER NOT NULL,
            balls_faced INTEGER NOT NULL,
            fours INTEGER NOT NULL,
            sixes INTEGER NOT NULL,
            strike_rate REAL,
            dismissal_kind TEXT,
            dismissal_text TEXT,
            match_label TEXT,
            PRIMARY KEY (player_name, match_id, innings_number),
            FOREIGN KEY (match_id) REFERENCES match_stats(match_id)
        );

        CREATE TABLE player_career_stats (
            player_name TEXT NOT NULL,
            player_id TEXT,
            format_group TEXT NOT NULL,
            match_type TEXT,
            competition_name TEXT,
            span TEXT,
            first_year INTEGER,
            last_year INTEGER,
            matches INTEGER NOT NULL,
            batting_innings INTEGER NOT NULL,
            not_outs INTEGER NOT NULL,
            runs_scored INTEGER NOT NULL,
            highest_score INTEGER,
            highest_score_not_out INTEGER NOT NULL,
            batting_average REAL,
            hundreds INTEGER NOT NULL,
            fifties INTEGER NOT NULL,
            ducks INTEGER NOT NULL,
            balls_faced INTEGER NOT NULL,
            fours INTEGER NOT NULL,
            sixes INTEGER NOT NULL,
            batting_strike_rate REAL,
            wickets_taken INTEGER NOT NULL,
            best_bowling_wickets INTEGER,
            best_bowling_runs INTEGER,
            best_bowling TEXT,
            bowling_average REAL,
            five_wickets INTEGER NOT NULL,
            catches INTEGER NOT NULL,
            stumpings INTEGER NOT NULL,
            average_difference REAL,
            PRIMARY KEY (player_name, player_id, format_group, match_type, competition_name)
        );

        CREATE TABLE player_career_group_stats (
            player_name TEXT NOT NULL,
            player_id TEXT,
            format_group TEXT NOT NULL,
            match_type TEXT,
            competition_name TEXT,
            group_type TEXT NOT NULL,
            group_value TEXT NOT NULL,
            span TEXT,
            first_year INTEGER,
            last_year INTEGER,
            matches INTEGER NOT NULL,
            batting_innings INTEGER NOT NULL,
            not_outs INTEGER NOT NULL,
            runs_scored INTEGER NOT NULL,
            highest_score INTEGER,
            highest_score_not_out INTEGER NOT NULL,
            batting_average REAL,
            hundreds INTEGER NOT NULL,
            fifties INTEGER NOT NULL,
            ducks INTEGER NOT NULL,
            wickets_taken INTEGER NOT NULL,
            best_bowling_wickets INTEGER,
            best_bowling_runs INTEGER,
            best_bowling TEXT,
            bowling_average REAL,
            five_wickets INTEGER NOT NULL,
            catches INTEGER NOT NULL,
            stumpings INTEGER NOT NULL,
            average_difference REAL,
            PRIMARY KEY (player_name, player_id, format_group, match_type, competition_name, group_type, group_value)
        );

        CREATE INDEX idx_player_batting_innings_player
            ON player_batting_innings_stats(player_name, format_group);
        CREATE INDEX idx_player_career_stats_player
            ON player_career_stats(player_name, format_group);
        CREATE INDEX idx_player_career_group_stats_player
            ON player_career_group_stats(player_name, format_group, group_type);
        """
    )


def import_json_directory(json_dir: Path, db_path: Path, *, limit: int | None = None) -> int:
    json_files = sorted(path for path in json_dir.glob("*.json") if path.is_file())
    if limit is not None:
        json_files = json_files[:limit]

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        create_schema(conn)

        imported = 0
        for path in json_files:
            rows = parse_match_file(path)
            insert_match(conn, rows)
            imported += 1
            if imported % 500 == 0:
                conn.commit()
        populate_player_summary_tables(conn)
        conn.commit()

    return imported


def parse_match_file(path: Path) -> MatchRows:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    match_id = path.stem
    info = data.get("info", {})
    teams = list(info.get("teams", []))
    registry = info.get("registry", {}).get("people", {})
    player_teams = _player_teams(info)
    players: dict[str, PlayerStats] = {}

    for player_name, team in player_teams.items():
        players[player_name] = PlayerStats(
            match_id=match_id,
            player_name=player_name,
            team=team,
            player_id=registry.get(player_name),
        )

    innings_summaries: list[InningsSummary] = []
    innings_players: list[InningsPlayerStats] = []
    for innings_number, innings in enumerate(data.get("innings", []), start=1):
        innings_team = innings.get("team", "")
        summary = InningsSummary(team=innings_team)
        innings_summaries.append(summary)
        innings_stats = _innings_players(
            match_id,
            innings_number,
            innings_team,
            player_teams,
            registry,
        )

        for over in innings.get("overs", []):
            for delivery in over.get("deliveries", []):
                over_number = over.get("over")
                _apply_delivery(
                    match_id, delivery, player_teams, players, summary, over_number
                )
                _apply_delivery(
                    match_id,
                    delivery,
                    player_teams,
                    innings_stats,
                    summary=summary,
                    over_number=over_number,
                )

        _finalize_innings_players(summary, innings_stats)

        innings_players.extend(innings_stats.values())

    match = _match_row(match_id, path, info, teams, innings_summaries)
    return MatchRows(
        match=match,
        innings=innings_summaries,
        players=list(players.values()),
        innings_players=innings_players,
    )


def insert_match(conn: sqlite3.Connection, rows: MatchRows) -> None:
    conn.execute(
        """
        INSERT INTO match_stats (
            match_id, source_file, match_date, year, season, match_type, team_type,
            gender, city, venue, event_name, event_match_number, event_stage,
            event_group, event_sub_name, event_json, team1, team2, toss_winner,
            toss_decision, winner, result, won_by_runs, won_by_wickets,
            balls_per_over, scheduled_overs, innings_count, team1_runs,
            team1_wickets, team1_overs, team2_runs, team2_wickets, team2_overs
        ) VALUES (
            :match_id, :source_file, :match_date, :year, :season, :match_type,
            :team_type, :gender, :city, :venue, :event_name, :event_match_number,
            :event_stage, :event_group, :event_sub_name, :event_json, :team1,
            :team2, :toss_winner, :toss_decision, :winner, :result,
            :won_by_runs, :won_by_wickets, :balls_per_over, :scheduled_overs,
            :innings_count, :team1_runs, :team1_wickets, :team1_overs,
            :team2_runs, :team2_wickets, :team2_overs
        )
        """,
        rows.match,
    )
    conn.executemany(
        """
        INSERT INTO match_innings_stats (
            match_id, innings_number, team, runs, wickets, overs, legal_balls,
            run_rate, extras_total, byes, legbyes, wides, no_balls, penalties,
            extras_text, total_text, fall_of_wickets_json, batting_order_json,
            bowling_order_json, striker, non_striker, current_bowler
        ) VALUES (
            :match_id, :innings_number, :team, :runs, :wickets, :overs,
            :legal_balls, :run_rate, :extras_total, :byes, :legbyes, :wides,
            :no_balls, :penalties, :extras_text, :total_text,
            :fall_of_wickets_json, :batting_order_json, :bowling_order_json,
            :striker, :non_striker, :current_bowler
        )
        """,
        [_innings_row(rows.match["match_id"], index, innings) for index, innings in enumerate(rows.innings, start=1)],
    )
    conn.executemany(
        """
        INSERT INTO player_match_stats (
            match_id, player_name, player_id, team, runs_scored, balls_faced, fours,
            sixes, strike_rate, wickets_taken, balls_bowled, overs_bowled,
            runs_conceded, economy_rate, catches, stumpings, run_outs, dismissals,
            dismissal_details_json
        ) VALUES (
            :match_id, :player_name, :player_id, :team, :runs_scored, :balls_faced,
            :fours, :sixes, :strike_rate, :wickets_taken, :balls_bowled,
            :overs_bowled, :runs_conceded, :economy_rate, :catches, :stumpings,
            :run_outs, :dismissals, :dismissal_details_json
        )
        """,
        [_player_row(player) for player in rows.players],
    )
    conn.executemany(
        """
        INSERT INTO player_match_innings_stats (
            match_id, innings_number, innings_team, player_name, player_id, team,
            team_player_position, batting_position, bowler_position,
            is_current_batter, is_current_bowler, is_out, runs_scored,
            balls_faced, fours, sixes, strike_rate,
            wickets_taken, balls_bowled, overs_bowled, maidens, runs_conceded,
            economy_rate, wides, no_balls, catches, stumpings, run_outs,
            dismissals, dismissal_kind, dismissal_bowler, dismissal_fielders,
            dismissal_text, fall_of_wicket_order, fall_of_wicket_runs,
            fall_of_wicket_over, dismissal_details_json
        ) VALUES (
            :match_id, :innings_number, :innings_team, :player_name, :player_id,
            :team, :team_player_position, :batting_position, :bowler_position,
            :is_current_batter, :is_current_bowler, :is_out, :runs_scored,
            :balls_faced, :fours, :sixes, :strike_rate, :wickets_taken,
            :balls_bowled, :overs_bowled,
            :maidens, :runs_conceded, :economy_rate, :wides, :no_balls,
            :catches, :stumpings, :run_outs, :dismissals, :dismissal_kind,
            :dismissal_bowler, :dismissal_fielders, :dismissal_text,
            :fall_of_wicket_order, :fall_of_wicket_runs, :fall_of_wicket_over,
            :dismissal_details_json
        )
        """,
        [_innings_player_row(player) for player in rows.innings_players],
    )


def populate_player_summary_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM player_batting_innings_stats;
        DELETE FROM player_career_group_stats;
        DELETE FROM player_career_stats;

        INSERT INTO player_batting_innings_stats (
            player_name, player_id, format_group, match_type, competition_name,
            match_id, innings_number, innings_team, player_team, opposition,
            match_date, year, venue, city, batting_position, runs_scored,
            is_not_out, balls_faced, fours, sixes, strike_rate, dismissal_kind,
            dismissal_text, match_label
        )
        SELECT
            p.player_name,
            p.player_id,
            CASE
                WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                WHEN m.match_type = 'Test' THEN 'Test'
                WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                ELSE COALESCE(m.match_type, 'Unknown')
            END AS format_group,
            COALESCE(m.match_type, ''),
            COALESCE(m.event_name, ''),
            p.match_id,
            p.innings_number,
            p.innings_team,
            p.team,
            CASE WHEN p.team = m.team1 THEN m.team2 ELSE m.team1 END AS opposition,
            m.match_date,
            m.year,
            m.venue,
            m.city,
            p.batting_position,
            p.runs_scored,
            CASE WHEN p.is_out = 0 THEN 1 ELSE 0 END AS is_not_out,
            p.balls_faced,
            p.fours,
            p.sixes,
            p.strike_rate,
            p.dismissal_kind,
            p.dismissal_text,
            COALESCE(m.match_type, 'Match') || ' # ' || p.match_id
        FROM player_match_innings_stats p
        JOIN match_stats m ON m.match_id = p.match_id
        WHERE p.batting_position IS NOT NULL;

        INSERT INTO player_career_stats (
            player_name, player_id, format_group, match_type, competition_name,
            span, first_year, last_year, matches, batting_innings, not_outs,
            runs_scored, highest_score, highest_score_not_out, batting_average,
            hundreds, fifties, ducks, balls_faced, fours, sixes,
            batting_strike_rate, wickets_taken, best_bowling_wickets,
            best_bowling_runs, best_bowling, bowling_average, five_wickets,
            catches, stumpings, average_difference
        )
        WITH match_player AS (
            SELECT
                p.player_name,
                p.player_id,
                CASE
                    WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                    WHEN m.match_type = 'Test' THEN 'Test'
                    WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                    WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                    ELSE COALESCE(m.match_type, 'Unknown')
                END AS format_group,
                COALESCE(m.match_type, '') AS match_type,
                COALESCE(m.event_name, '') AS competition_name,
                p.match_id,
                p.player_name AS player_key,
                p.wickets_taken,
                p.runs_conceded,
                p.catches,
                p.stumpings,
                m.year
            FROM player_match_stats p
            JOIN match_stats m ON m.match_id = p.match_id
        ), batting AS (
            SELECT
                player_name, player_id, format_group, match_type, competition_name,
                MIN(year) AS first_year,
                MAX(year) AS last_year,
                COUNT(*) AS batting_innings,
                SUM(is_not_out) AS not_outs,
                SUM(runs_scored) AS runs_scored,
                SUM(balls_faced) AS balls_faced,
                SUM(fours) AS fours,
                SUM(sixes) AS sixes,
                SUM(CASE WHEN runs_scored >= 100 THEN 1 ELSE 0 END) AS hundreds,
                SUM(CASE WHEN runs_scored BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN runs_scored = 0 THEN 1 ELSE 0 END) AS ducks
            FROM player_batting_innings_stats
            GROUP BY player_name, player_id, format_group, match_type, competition_name
        ), best_score AS (
            SELECT player_name, player_id, format_group, match_type, competition_name,
                   runs_scored AS highest_score, is_not_out AS highest_score_not_out
            FROM (
                SELECT b.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY player_name, player_id, format_group, match_type, competition_name
                           ORDER BY runs_scored DESC, is_not_out DESC, match_date
                       ) AS rn
                FROM player_batting_innings_stats b
            )
            WHERE rn = 1
        ), match_totals AS (
            SELECT
                player_name, player_id, format_group, match_type, competition_name,
                MIN(year) AS first_year,
                MAX(year) AS last_year,
                COUNT(DISTINCT match_id) AS matches,
                SUM(wickets_taken) AS wickets_taken,
                SUM(runs_conceded) AS runs_conceded,
                SUM(catches) AS catches,
                SUM(stumpings) AS stumpings
            FROM match_player
            GROUP BY player_name, player_id, format_group, match_type, competition_name
        ), best_bowling AS (
            SELECT player_name, player_id, format_group, match_type, competition_name,
                   wickets_taken AS best_bowling_wickets,
                   runs_conceded AS best_bowling_runs
            FROM (
                SELECT
                    p.player_name,
                    p.player_id,
                    CASE
                        WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                        WHEN m.match_type = 'Test' THEN 'Test'
                        WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                        WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                        ELSE COALESCE(m.match_type, 'Unknown')
                    END AS format_group,
                    COALESCE(m.match_type, '') AS match_type,
                    COALESCE(m.event_name, '') AS competition_name,
                    p.wickets_taken,
                    p.runs_conceded,
                    ROW_NUMBER() OVER (
                        PARTITION BY p.player_name, p.player_id,
                                     CASE
                                         WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                                         WHEN m.match_type = 'Test' THEN 'Test'
                                         WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                                         WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                                         ELSE COALESCE(m.match_type, 'Unknown')
                                     END,
                                     COALESCE(m.match_type, ''), COALESCE(m.event_name, '')
                        ORDER BY p.wickets_taken DESC, p.runs_conceded ASC
                    ) AS rn
                FROM player_match_innings_stats p
                JOIN match_stats m ON m.match_id = p.match_id
                WHERE p.bowler_position IS NOT NULL
            )
            WHERE rn = 1
        ), five_wickets AS (
            SELECT
                p.player_name,
                p.player_id,
                CASE
                    WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                    WHEN m.match_type = 'Test' THEN 'Test'
                    WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                    WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                    ELSE COALESCE(m.match_type, 'Unknown')
                END AS format_group,
                COALESCE(m.match_type, '') AS match_type,
                COALESCE(m.event_name, '') AS competition_name,
                SUM(CASE WHEN p.wickets_taken >= 5 THEN 1 ELSE 0 END) AS five_wickets
            FROM player_match_innings_stats p
            JOIN match_stats m ON m.match_id = p.match_id
            WHERE p.bowler_position IS NOT NULL
            GROUP BY p.player_name, p.player_id, format_group, match_type, competition_name
        )
        SELECT
            mt.player_name,
            mt.player_id,
            mt.format_group,
            mt.match_type,
            mt.competition_name,
            CAST(COALESCE(b.first_year, mt.first_year) AS TEXT) || '-' || CAST(COALESCE(b.last_year, mt.last_year) AS TEXT) AS span,
            COALESCE(b.first_year, mt.first_year) AS first_year,
            COALESCE(b.last_year, mt.last_year) AS last_year,
            mt.matches,
            COALESCE(b.batting_innings, 0),
            COALESCE(b.not_outs, 0),
            COALESCE(b.runs_scored, 0),
            bs.highest_score,
            COALESCE(bs.highest_score_not_out, 0),
            CASE WHEN COALESCE(b.batting_innings, 0) - COALESCE(b.not_outs, 0) > 0
                 THEN ROUND(1.0 * b.runs_scored / (b.batting_innings - b.not_outs), 2)
            END AS batting_average,
            COALESCE(b.hundreds, 0),
            COALESCE(b.fifties, 0),
            COALESCE(b.ducks, 0),
            COALESCE(b.balls_faced, 0),
            COALESCE(b.fours, 0),
            COALESCE(b.sixes, 0),
            CASE WHEN COALESCE(b.balls_faced, 0) > 0 THEN ROUND(100.0 * b.runs_scored / b.balls_faced, 2) END,
            COALESCE(mt.wickets_taken, 0),
            bb.best_bowling_wickets,
            bb.best_bowling_runs,
            CASE WHEN bb.best_bowling_wickets IS NOT NULL THEN bb.best_bowling_wickets || '/' || bb.best_bowling_runs END,
            CASE WHEN COALESCE(mt.wickets_taken, 0) > 0 THEN ROUND(1.0 * mt.runs_conceded / mt.wickets_taken, 2) END,
            COALESCE(fw.five_wickets, 0),
            COALESCE(mt.catches, 0),
            COALESCE(mt.stumpings, 0),
            CASE WHEN COALESCE(mt.wickets_taken, 0) > 0
                      AND COALESCE(b.batting_innings, 0) - COALESCE(b.not_outs, 0) > 0
                 THEN ROUND((1.0 * b.runs_scored / (b.batting_innings - b.not_outs)) - (1.0 * mt.runs_conceded / mt.wickets_taken), 2)
            END
        FROM match_totals mt
        LEFT JOIN batting b ON b.player_name = mt.player_name
            AND b.player_id = mt.player_id
            AND b.format_group = mt.format_group
            AND b.match_type = mt.match_type
            AND b.competition_name = mt.competition_name
        LEFT JOIN best_score bs ON bs.player_name = mt.player_name
            AND bs.player_id = mt.player_id
            AND bs.format_group = mt.format_group
            AND bs.match_type = mt.match_type
            AND bs.competition_name = mt.competition_name
        LEFT JOIN best_bowling bb ON bb.player_name = mt.player_name
            AND bb.player_id = mt.player_id
            AND bb.format_group = mt.format_group
            AND bb.match_type = mt.match_type
            AND bb.competition_name = mt.competition_name
        LEFT JOIN five_wickets fw ON fw.player_name = mt.player_name
            AND fw.player_id = mt.player_id
            AND fw.format_group = mt.format_group
            AND fw.match_type = mt.match_type
            AND fw.competition_name = mt.competition_name;
        """
    )
    _populate_player_overall_career_stats(conn)
    _populate_player_group_stats(conn, "opposition")
    _populate_player_group_stats(conn, "year")
    _populate_player_group_stats(conn, "competition")


def _populate_player_overall_career_stats(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        INSERT INTO player_career_stats (
            player_name, player_id, format_group, match_type, competition_name,
            span, first_year, last_year, matches, batting_innings, not_outs,
            runs_scored, highest_score, highest_score_not_out, batting_average,
            hundreds, fifties, ducks, balls_faced, fours, sixes,
            batting_strike_rate, wickets_taken, best_bowling_wickets,
            best_bowling_runs, best_bowling, bowling_average, five_wickets,
            catches, stumpings, average_difference
        )
        WITH match_player AS (
            SELECT
                p.player_name,
                p.player_id,
                CASE
                    WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                    WHEN m.match_type = 'Test' THEN 'Test'
                    WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                    WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                    ELSE COALESCE(m.match_type, 'Unknown')
                END AS format_group,
                COALESCE(m.match_type, '') AS match_type,
                p.match_id,
                p.wickets_taken,
                p.runs_conceded,
                p.catches,
                p.stumpings,
                m.year
            FROM player_match_stats p
            JOIN match_stats m ON m.match_id = p.match_id
        ), batting AS (
            SELECT
                player_name, player_id, format_group, match_type,
                MIN(year) AS first_year,
                MAX(year) AS last_year,
                COUNT(*) AS batting_innings,
                SUM(is_not_out) AS not_outs,
                SUM(runs_scored) AS runs_scored,
                SUM(balls_faced) AS balls_faced,
                SUM(fours) AS fours,
                SUM(sixes) AS sixes,
                SUM(CASE WHEN runs_scored >= 100 THEN 1 ELSE 0 END) AS hundreds,
                SUM(CASE WHEN runs_scored BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN runs_scored = 0 THEN 1 ELSE 0 END) AS ducks
            FROM player_batting_innings_stats
            GROUP BY player_name, player_id, format_group, match_type
        ), best_score AS (
            SELECT player_name, player_id, format_group, match_type,
                   runs_scored AS highest_score, is_not_out AS highest_score_not_out
            FROM (
                SELECT b.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY player_name, player_id, format_group, match_type
                           ORDER BY runs_scored DESC, is_not_out DESC, match_date
                       ) AS rn
                FROM player_batting_innings_stats b
            )
            WHERE rn = 1
        ), match_totals AS (
            SELECT
                player_name, player_id, format_group, match_type,
                MIN(year) AS first_year,
                MAX(year) AS last_year,
                COUNT(DISTINCT match_id) AS matches,
                SUM(wickets_taken) AS wickets_taken,
                SUM(runs_conceded) AS runs_conceded,
                SUM(catches) AS catches,
                SUM(stumpings) AS stumpings
            FROM match_player
            GROUP BY player_name, player_id, format_group, match_type
        ), best_bowling AS (
            SELECT player_name, player_id, format_group, match_type,
                   wickets_taken AS best_bowling_wickets,
                   runs_conceded AS best_bowling_runs
            FROM (
                SELECT
                    p.player_name,
                    p.player_id,
                    CASE
                        WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                        WHEN m.match_type = 'Test' THEN 'Test'
                        WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                        WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                        ELSE COALESCE(m.match_type, 'Unknown')
                    END AS format_group,
                    COALESCE(m.match_type, '') AS match_type,
                    p.wickets_taken,
                    p.runs_conceded,
                    ROW_NUMBER() OVER (
                        PARTITION BY p.player_name, p.player_id,
                                     CASE
                                         WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                                         WHEN m.match_type = 'Test' THEN 'Test'
                                         WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                                         WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                                         ELSE COALESCE(m.match_type, 'Unknown')
                                     END,
                                     COALESCE(m.match_type, '')
                        ORDER BY p.wickets_taken DESC, p.runs_conceded ASC
                    ) AS rn
                FROM player_match_innings_stats p
                JOIN match_stats m ON m.match_id = p.match_id
                WHERE p.bowler_position IS NOT NULL
            )
            WHERE rn = 1
        ), five_wickets AS (
            SELECT
                p.player_name,
                p.player_id,
                CASE
                    WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                    WHEN m.match_type = 'Test' THEN 'Test'
                    WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                    WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                    ELSE COALESCE(m.match_type, 'Unknown')
                END AS format_group,
                COALESCE(m.match_type, '') AS match_type,
                SUM(CASE WHEN p.wickets_taken >= 5 THEN 1 ELSE 0 END) AS five_wickets
            FROM player_match_innings_stats p
            JOIN match_stats m ON m.match_id = p.match_id
            WHERE p.bowler_position IS NOT NULL
            GROUP BY p.player_name, p.player_id, format_group, match_type
        )
        SELECT
            mt.player_name,
            mt.player_id,
            mt.format_group,
            mt.match_type,
            'All',
            CAST(COALESCE(b.first_year, mt.first_year) AS TEXT) || '-' || CAST(COALESCE(b.last_year, mt.last_year) AS TEXT),
            COALESCE(b.first_year, mt.first_year),
            COALESCE(b.last_year, mt.last_year),
            mt.matches,
            COALESCE(b.batting_innings, 0),
            COALESCE(b.not_outs, 0),
            COALESCE(b.runs_scored, 0),
            bs.highest_score,
            COALESCE(bs.highest_score_not_out, 0),
            CASE WHEN COALESCE(b.batting_innings, 0) - COALESCE(b.not_outs, 0) > 0
                 THEN ROUND(1.0 * b.runs_scored / (b.batting_innings - b.not_outs), 2)
            END,
            COALESCE(b.hundreds, 0),
            COALESCE(b.fifties, 0),
            COALESCE(b.ducks, 0),
            COALESCE(b.balls_faced, 0),
            COALESCE(b.fours, 0),
            COALESCE(b.sixes, 0),
            CASE WHEN COALESCE(b.balls_faced, 0) > 0 THEN ROUND(100.0 * b.runs_scored / b.balls_faced, 2) END,
            COALESCE(mt.wickets_taken, 0),
            bb.best_bowling_wickets,
            bb.best_bowling_runs,
            CASE WHEN bb.best_bowling_wickets IS NOT NULL THEN bb.best_bowling_wickets || '/' || bb.best_bowling_runs END,
            CASE WHEN COALESCE(mt.wickets_taken, 0) > 0 THEN ROUND(1.0 * mt.runs_conceded / mt.wickets_taken, 2) END,
            COALESCE(fw.five_wickets, 0),
            COALESCE(mt.catches, 0),
            COALESCE(mt.stumpings, 0),
            CASE WHEN COALESCE(mt.wickets_taken, 0) > 0
                      AND COALESCE(b.batting_innings, 0) - COALESCE(b.not_outs, 0) > 0
                 THEN ROUND((1.0 * b.runs_scored / (b.batting_innings - b.not_outs)) - (1.0 * mt.runs_conceded / mt.wickets_taken), 2)
            END
        FROM match_totals mt
        LEFT JOIN batting b ON b.player_name = mt.player_name
            AND b.player_id = mt.player_id
            AND b.format_group = mt.format_group
            AND b.match_type = mt.match_type
        LEFT JOIN best_score bs ON bs.player_name = mt.player_name
            AND bs.player_id = mt.player_id
            AND bs.format_group = mt.format_group
            AND bs.match_type = mt.match_type
        LEFT JOIN best_bowling bb ON bb.player_name = mt.player_name
            AND bb.player_id = mt.player_id
            AND bb.format_group = mt.format_group
            AND bb.match_type = mt.match_type
        LEFT JOIN five_wickets fw ON fw.player_name = mt.player_name
            AND fw.player_id = mt.player_id
            AND fw.format_group = mt.format_group
            AND fw.match_type = mt.match_type;
        """
    )


def _populate_player_group_stats(conn: sqlite3.Connection, group_type: str) -> None:
    if group_type == "opposition":
        batting_expr = "opposition"
        match_expr = "CASE WHEN p.team = m.team1 THEN m.team2 ELSE m.team1 END"
    elif group_type == "year":
        batting_expr = "'year ' || year"
        match_expr = "'year ' || m.year"
    elif group_type == "competition":
        batting_expr = "competition_name"
        match_expr = "COALESCE(m.event_name, '')"
    else:
        raise ValueError(f"Unsupported group type: {group_type}")

    sql = f"""
        INSERT INTO player_career_group_stats (
            player_name, player_id, format_group, match_type, competition_name,
            group_type, group_value, span, first_year, last_year, matches,
            batting_innings, not_outs, runs_scored, highest_score,
            highest_score_not_out, batting_average, hundreds, fifties, ducks,
            wickets_taken, best_bowling_wickets, best_bowling_runs, best_bowling,
            bowling_average, five_wickets, catches, stumpings, average_difference
        )
        WITH match_player AS (
            SELECT
                p.player_name,
                p.player_id,
                CASE
                    WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                    WHEN m.match_type = 'Test' THEN 'Test'
                    WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                    WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                    ELSE COALESCE(m.match_type, 'Unknown')
                END AS format_group,
                COALESCE(m.match_type, '') AS match_type,
                COALESCE(m.event_name, '') AS competition_name,
                {match_expr} AS group_value,
                p.match_id,
                p.wickets_taken,
                p.runs_conceded,
                p.catches,
                p.stumpings,
                m.year
            FROM player_match_stats p
            JOIN match_stats m ON m.match_id = p.match_id
            WHERE {match_expr} IS NOT NULL AND {match_expr} <> ''
        ), batting AS (
            SELECT
                player_name, player_id, format_group, match_type, competition_name,
                {batting_expr} AS group_value,
                MIN(year) AS first_year,
                MAX(year) AS last_year,
                COUNT(*) AS batting_innings,
                SUM(is_not_out) AS not_outs,
                SUM(runs_scored) AS runs_scored,
                SUM(CASE WHEN runs_scored >= 100 THEN 1 ELSE 0 END) AS hundreds,
                SUM(CASE WHEN runs_scored BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN runs_scored = 0 THEN 1 ELSE 0 END) AS ducks
            FROM player_batting_innings_stats
            WHERE {batting_expr} IS NOT NULL AND {batting_expr} <> ''
            GROUP BY player_name, player_id, format_group, match_type, competition_name, group_value
        ), best_score AS (
            SELECT player_name, player_id, format_group, match_type, competition_name, group_value,
                   runs_scored AS highest_score, is_not_out AS highest_score_not_out
            FROM (
                SELECT b.*, {batting_expr} AS group_value,
                       ROW_NUMBER() OVER (
                           PARTITION BY player_name, player_id, format_group, match_type, competition_name, {batting_expr}
                           ORDER BY runs_scored DESC, is_not_out DESC, match_date
                       ) AS rn
                FROM player_batting_innings_stats b
                WHERE {batting_expr} IS NOT NULL AND {batting_expr} <> ''
            )
            WHERE rn = 1
        ), match_totals AS (
            SELECT
                player_name, player_id, format_group, match_type, competition_name,
                group_value,
                MIN(year) AS first_year,
                MAX(year) AS last_year,
                COUNT(DISTINCT match_id) AS matches,
                SUM(wickets_taken) AS wickets_taken,
                SUM(runs_conceded) AS runs_conceded,
                SUM(catches) AS catches,
                SUM(stumpings) AS stumpings
            FROM match_player
            GROUP BY player_name, player_id, format_group, match_type, competition_name, group_value
        ), best_bowling AS (
            SELECT player_name, player_id, format_group, match_type, competition_name, group_value,
                   wickets_taken AS best_bowling_wickets,
                   runs_conceded AS best_bowling_runs
            FROM (
                SELECT
                    p.player_name,
                    p.player_id,
                    CASE
                        WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                        WHEN m.match_type = 'Test' THEN 'Test'
                        WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                        WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                        ELSE COALESCE(m.match_type, 'Unknown')
                    END AS format_group,
                    COALESCE(m.match_type, '') AS match_type,
                    COALESCE(m.event_name, '') AS competition_name,
                    {match_expr} AS group_value,
                    p.wickets_taken,
                    p.runs_conceded,
                    ROW_NUMBER() OVER (
                        PARTITION BY p.player_name, p.player_id,
                                     CASE
                                         WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                                         WHEN m.match_type = 'Test' THEN 'Test'
                                         WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                                         WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                                         ELSE COALESCE(m.match_type, 'Unknown')
                                     END,
                                     COALESCE(m.match_type, ''), COALESCE(m.event_name, ''), {match_expr}
                        ORDER BY p.wickets_taken DESC, p.runs_conceded ASC
                    ) AS rn
                FROM player_match_innings_stats p
                JOIN match_stats m ON m.match_id = p.match_id
                WHERE p.bowler_position IS NOT NULL AND {match_expr} IS NOT NULL AND {match_expr} <> ''
            )
            WHERE rn = 1
        ), five_wickets AS (
            SELECT
                p.player_name,
                p.player_id,
                CASE
                    WHEN m.event_name = 'Indian Premier League' THEN 'IPL'
                    WHEN m.match_type = 'Test' THEN 'Test'
                    WHEN m.match_type IN ('ODI', 'ODM') THEN 'One Day'
                    WHEN m.match_type IN ('T20', 'IT20') THEN 'T20'
                    ELSE COALESCE(m.match_type, 'Unknown')
                END AS format_group,
                COALESCE(m.match_type, '') AS match_type,
                COALESCE(m.event_name, '') AS competition_name,
                {match_expr} AS group_value,
                SUM(CASE WHEN p.wickets_taken >= 5 THEN 1 ELSE 0 END) AS five_wickets
            FROM player_match_innings_stats p
            JOIN match_stats m ON m.match_id = p.match_id
            WHERE p.bowler_position IS NOT NULL AND {match_expr} IS NOT NULL AND {match_expr} <> ''
            GROUP BY p.player_name, format_group, match_type, competition_name, group_value
        )
        SELECT
            mt.player_name,
            mt.player_id,
            mt.format_group,
            mt.match_type,
            mt.competition_name,
            '{group_type}',
            mt.group_value,
            CAST(COALESCE(b.first_year, mt.first_year) AS TEXT) || '-' || CAST(COALESCE(b.last_year, mt.last_year) AS TEXT),
            COALESCE(b.first_year, mt.first_year),
            COALESCE(b.last_year, mt.last_year),
            mt.matches,
            COALESCE(b.batting_innings, 0),
            COALESCE(b.not_outs, 0),
            COALESCE(b.runs_scored, 0),
            bs.highest_score,
            COALESCE(bs.highest_score_not_out, 0),
            CASE WHEN COALESCE(b.batting_innings, 0) - COALESCE(b.not_outs, 0) > 0
                 THEN ROUND(1.0 * b.runs_scored / (b.batting_innings - b.not_outs), 2)
            END,
            COALESCE(b.hundreds, 0),
            COALESCE(b.fifties, 0),
            COALESCE(b.ducks, 0),
            COALESCE(mt.wickets_taken, 0),
            bb.best_bowling_wickets,
            bb.best_bowling_runs,
            CASE WHEN bb.best_bowling_wickets IS NOT NULL THEN bb.best_bowling_wickets || '/' || bb.best_bowling_runs END,
            CASE WHEN COALESCE(mt.wickets_taken, 0) > 0 THEN ROUND(1.0 * mt.runs_conceded / mt.wickets_taken, 2) END,
            COALESCE(fw.five_wickets, 0),
            COALESCE(mt.catches, 0),
            COALESCE(mt.stumpings, 0),
            CASE WHEN COALESCE(mt.wickets_taken, 0) > 0
                      AND COALESCE(b.batting_innings, 0) - COALESCE(b.not_outs, 0) > 0
                 THEN ROUND((1.0 * b.runs_scored / (b.batting_innings - b.not_outs)) - (1.0 * mt.runs_conceded / mt.wickets_taken), 2)
            END
        FROM match_totals mt
        LEFT JOIN batting b ON b.player_name = mt.player_name
            AND b.player_id = mt.player_id
            AND b.format_group = mt.format_group
            AND b.match_type = mt.match_type
            AND b.competition_name = mt.competition_name
            AND b.group_value = mt.group_value
        LEFT JOIN best_score bs ON bs.player_name = mt.player_name
            AND bs.player_id = mt.player_id
            AND bs.format_group = mt.format_group
            AND bs.match_type = mt.match_type
            AND bs.competition_name = mt.competition_name
            AND bs.group_value = mt.group_value
        LEFT JOIN best_bowling bb ON bb.player_name = mt.player_name
            AND bb.player_id = mt.player_id
            AND bb.format_group = mt.format_group
            AND bb.match_type = mt.match_type
            AND bb.competition_name = mt.competition_name
            AND bb.group_value = mt.group_value
        LEFT JOIN five_wickets fw ON fw.player_name = mt.player_name
            AND fw.player_id = mt.player_id
            AND fw.format_group = mt.format_group
            AND fw.match_type = mt.match_type
            AND fw.competition_name = mt.competition_name
            AND fw.group_value = mt.group_value;
    """
    conn.executescript(sql)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Cricsheet JSON match files into a SQLite cricketstats database."
    )
    parser.add_argument(
        "--json-dir",
        type=Path,
        default=JSON_DIR,
        help=f"Directory containing match JSON files. Default: {JSON_DIR}",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"SQLite database path to create. Default: {DB_PATH}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Import only the first N JSON files, useful for testing.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    imported = import_json_directory(args.json_dir, args.db, limit=args.limit)
    print(f"Imported {imported} match files into {args.db}")


def _player_teams(info: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for team, players in info.get("players", {}).items():
        for player in players:
            mapping[player] = team
    return mapping


def _record_innings_context(
    summary: InningsSummary,
    batter: PlayerStats | None,
    bowler: PlayerStats | None,
    non_striker_name: str | None,
    extras: dict[str, Any],
) -> None:
    if batter is not None and batter.player_name not in summary.batter_order:
        summary.batter_order.append(batter.player_name)
    if non_striker_name and non_striker_name not in summary.batter_order:
        summary.batter_order.append(non_striker_name)
    if bowler is not None and bowler.player_name not in summary.bowler_order:
        summary.bowler_order.append(bowler.player_name)

    summary.striker = batter.player_name if batter is not None else None
    summary.non_striker = non_striker_name
    summary.current_bowler = bowler.player_name if bowler is not None else None

    for key, value in extras.items():
        summary.extras[key] = summary.extras.get(key, 0) + int(value)


def _finalize_innings_players(
    summary: InningsSummary,
    players: dict[str, InningsPlayerStats],
) -> None:
    for index, player_name in enumerate(summary.batter_order, start=1):
        player = players.get(player_name)
        if player is not None:
            player.batting_position = index
    for index, player_name in enumerate(summary.bowler_order, start=1):
        player = players.get(player_name)
        if player is not None:
            player.bowler_position = index

    for (player_name, _over_number), balls in summary.bowler_over_balls.items():
        if balls == 6 and summary.bowler_over_runs.get((player_name, _over_number), 0) == 0:
            player = players.get(player_name)
            if player is not None:
                player.maidens += 1

    for player in players.values():
        player.is_current_batter = player.player_name in {
            summary.striker,
            summary.non_striker,
        }
        player.is_current_bowler = player.player_name == summary.current_bowler


def _innings_players(
    match_id: str,
    innings_number: int,
    innings_team: str,
    player_teams: dict[str, str],
    registry: dict[str, str],
) -> dict[str, InningsPlayerStats]:
    players: dict[str, InningsPlayerStats] = {}
    team_counts: dict[str, int] = {}
    for player_name, team in player_teams.items():
        team_counts[team] = team_counts.get(team, 0) + 1
        players[player_name] = InningsPlayerStats(
            match_id=match_id,
            innings_number=innings_number,
            innings_team=innings_team,
            player_name=player_name,
            team=team,
            player_id=registry.get(player_name),
            team_player_position=team_counts[team],
        )
    return players


def _apply_delivery(
    match_id: str,
    delivery: dict[str, Any],
    player_teams: dict[str, str],
    players: dict[str, PlayerStats],
    summary: InningsSummary | None,
    over_number: int | None = None,
) -> None:
    is_innings_stats = isinstance(next(iter(players.values()), None), InningsPlayerStats)
    batter_name = delivery.get("batter")
    bowler_name = delivery.get("bowler")
    non_striker_name = delivery.get("non_striker")
    runs = delivery.get("runs", {})
    extras = delivery.get("extras", {})
    batter_runs = int(runs.get("batter", 0))
    total_runs = int(runs.get("total", 0))
    bowler_runs = total_runs - int(extras.get("byes", 0)) - int(
        extras.get("legbyes", 0)
    ) - int(extras.get("penalty", 0))
    is_legal_delivery = "wides" not in extras and "noballs" not in extras

    if summary is not None and not is_innings_stats:
        summary.runs += total_runs

    batter = _ensure_player(match_id, batter_name, player_teams, players)
    bowler = _ensure_player(match_id, bowler_name, player_teams, players)

    if is_innings_stats and summary is not None:
        _record_innings_context(summary, batter, bowler, non_striker_name, extras)

    if batter is not None:
        batter.runs_scored += batter_runs
        if is_legal_delivery:
            batter.balls_faced += 1
        if batter_runs == 4:
            batter.fours += 1
        elif batter_runs == 6:
            batter.sixes += 1

    if bowler is not None:
        bowler.runs_conceded += bowler_runs
        if isinstance(bowler, InningsPlayerStats):
            bowler.wides += int(extras.get("wides", 0))
            bowler.no_balls += int(extras.get("noballs", 0))
        if is_legal_delivery:
            bowler.balls_bowled += 1
            if summary is not None and not is_innings_stats:
                summary.legal_balls += 1
        if is_innings_stats and summary is not None and over_number is not None:
            key = (bowler.player_name, int(over_number))
            summary.bowler_over_runs[key] = summary.bowler_over_runs.get(key, 0) + bowler_runs
            if is_legal_delivery:
                summary.bowler_over_balls[key] = summary.bowler_over_balls.get(key, 0) + 1

    for wicket in delivery.get("wickets", []):
        if summary is not None and not is_innings_stats:
            summary.wickets += 1
        player_out = _ensure_player(match_id, wicket.get("player_out"), player_teams, players)
        if player_out is not None:
            player_out.dismissals += 1

        kind = wicket.get("kind", "")
        wicket_bowler = bowler_name if kind in BOWLER_WICKET_KINDS else None
        fielders = [
            fielder_data.get("name")
            for fielder_data in wicket.get("fielders", [])
            if fielder_data.get("name")
        ]
        if player_out is not None:
            player_out.dismissal_details.append(
                {
                    "kind": kind,
                    "bowler": wicket_bowler,
                    "fielders": fielders,
                }
            )
            if isinstance(player_out, InningsPlayerStats):
                player_out.is_out = True
                player_out.dismissal_text = _dismissal_text(kind, wicket_bowler, fielders)
                if summary is not None:
                    player_out.fall_of_wicket_order = summary.wickets
                    player_out.fall_of_wicket_runs = summary.runs
                    player_out.fall_of_wicket_over = summary.overs
                    summary.fall_of_wickets.append(
                        {
                            "order": summary.wickets,
                            "player": player_out.player_name,
                            "runs": summary.runs,
                            "over": summary.overs,
                        }
                    )

        if kind in BOWLER_WICKET_KINDS and bowler is not None:
            bowler.wickets_taken += 1

        for fielder_data in wicket.get("fielders", []):
            fielder = _ensure_player(
                match_id, fielder_data.get("name"), player_teams, players
            )
            if fielder is None:
                continue
            if kind in CATCH_KINDS:
                fielder.catches += 1
            elif kind == "stumped":
                fielder.stumpings += 1
            elif kind == "run out":
                fielder.run_outs += 1


def _ensure_player(
    match_id: str,
    player_name: str | None,
    player_teams: dict[str, str],
    players: dict[str, PlayerStats],
) -> PlayerStats | None:
    if not player_name:
        return None
    if player_name not in players:
        first_player = next(iter(players.values()), None)
        if isinstance(first_player, InningsPlayerStats):
            players[player_name] = InningsPlayerStats(
                match_id=match_id,
                innings_number=first_player.innings_number,
                innings_team=first_player.innings_team,
                player_name=player_name,
                team=player_teams.get(player_name, ""),
                team_player_position=None,
            )
            return players[player_name]
        players[player_name] = PlayerStats(
            match_id=match_id,
            player_name=player_name,
            team=player_teams.get(player_name, ""),
        )
    return players[player_name]


def _match_row(
    match_id: str,
    path: Path,
    info: dict[str, Any],
    teams: list[str],
    innings: list[InningsSummary],
) -> dict[str, Any]:
    dates = info.get("dates", [])
    match_date = dates[0] if dates else None
    season = str(info.get("season", "")) or None
    year = _year(match_date, season)
    outcome = info.get("outcome", {})
    by = outcome.get("by", {})
    toss = info.get("toss", {})
    event = info.get("event", {})

    first = innings[0] if len(innings) > 0 else None
    second = innings[1] if len(innings) > 1 else None

    return {
        "match_id": match_id,
        "source_file": str(path),
        "match_date": match_date,
        "year": year,
        "season": season,
        "match_type": info.get("match_type"),
        "team_type": info.get("team_type"),
        "gender": info.get("gender"),
        "city": info.get("city"),
        "venue": info.get("venue"),
        "event_name": event.get("name"),
        "event_match_number": event.get("match_number"),
        "event_stage": event.get("stage"),
        "event_group": event.get("group"),
        "event_sub_name": event.get("sub_name"),
        "event_json": json.dumps(event, sort_keys=True) if event else None,
        "team1": teams[0] if len(teams) > 0 else None,
        "team2": teams[1] if len(teams) > 1 else None,
        "toss_winner": toss.get("winner"),
        "toss_decision": toss.get("decision"),
        "winner": outcome.get("winner"),
        "result": outcome.get("result"),
        "won_by_runs": by.get("runs"),
        "won_by_wickets": by.get("wickets"),
        "balls_per_over": info.get("balls_per_over"),
        "scheduled_overs": info.get("overs"),
        "innings_count": len(innings),
        "team1_runs": first.runs if first else None,
        "team1_wickets": first.wickets if first else None,
        "team1_overs": first.overs if first else None,
        "team2_runs": second.runs if second else None,
        "team2_wickets": second.wickets if second else None,
        "team2_overs": second.overs if second else None,
    }


def _year(match_date: str | None, season: str | None) -> int | None:
    if match_date:
        return int(match_date[:4])
    if season and season[:4].isdigit():
        return int(season[:4])
    return None


def _innings_row(match_id: str, innings_number: int, innings: InningsSummary) -> dict[str, Any]:
    extras = innings.extras
    extras_total = sum(int(value) for value in extras.values())
    run_rate = round(innings.runs * 6 / innings.legal_balls, 2) if innings.legal_balls else None
    return {
        "match_id": match_id,
        "innings_number": innings_number,
        "team": innings.team,
        "runs": innings.runs,
        "wickets": innings.wickets,
        "overs": innings.overs,
        "legal_balls": innings.legal_balls,
        "run_rate": run_rate,
        "extras_total": extras_total,
        "byes": int(extras.get("byes", 0)),
        "legbyes": int(extras.get("legbyes", 0)),
        "wides": int(extras.get("wides", 0)),
        "no_balls": int(extras.get("noballs", 0)),
        "penalties": int(extras.get("penalty", 0)),
        "extras_text": _extras_text(extras),
        "total_text": f"{innings.runs}-{innings.wickets} ({innings.overs})",
        "fall_of_wickets_json": json.dumps(innings.fall_of_wickets, sort_keys=True)
        if innings.fall_of_wickets
        else None,
        "batting_order_json": json.dumps(innings.batter_order) if innings.batter_order else None,
        "bowling_order_json": json.dumps(innings.bowler_order) if innings.bowler_order else None,
        "striker": innings.striker,
        "non_striker": innings.non_striker,
        "current_bowler": innings.current_bowler,
    }


def _extras_text(extras: dict[str, int]) -> str | None:
    extras_total = sum(int(value) for value in extras.values())
    if extras_total == 0:
        return None
    parts = [f"{extras_total}"]
    labels = [
        ("byes", "b"),
        ("legbyes", "lb"),
        ("noballs", "nb"),
        ("wides", "w"),
        ("penalty", "pen"),
    ]
    parts.extend(f"{label}:{int(extras.get(key, 0))}" for key, label in labels)
    return " ".join(parts)


def _dismissal_text(kind: str, bowler: str | None, fielders: list[str]) -> str:
    fielder_text = ", ".join(fielders)
    if kind == "bowled" and bowler:
        return f"b {bowler}"
    if kind == "caught and bowled" and bowler:
        return f"c & b {bowler}"
    if kind == "caught" and bowler:
        return f"c {fielder_text} b {bowler}" if fielder_text else f"c b {bowler}"
    if kind == "lbw" and bowler:
        return f"lbw b {bowler}"
    if kind == "stumped" and bowler:
        return f"st {fielder_text} b {bowler}" if fielder_text else f"st b {bowler}"
    if kind == "hit wicket" and bowler:
        return f"hit wicket b {bowler}"
    if kind == "run out":
        return f"run out ({fielder_text})" if fielder_text else "run out"
    return kind


def _player_row(player: PlayerStats) -> dict[str, Any]:
    return {
        "match_id": player.match_id,
        "player_name": player.player_name,
        "player_id": player.player_id,
        "team": player.team,
        "runs_scored": player.runs_scored,
        "balls_faced": player.balls_faced,
        "fours": player.fours,
        "sixes": player.sixes,
        "strike_rate": player.strike_rate,
        "wickets_taken": player.wickets_taken,
        "balls_bowled": player.balls_bowled,
        "overs_bowled": player.overs_bowled,
        "runs_conceded": player.runs_conceded,
        "economy_rate": player.economy_rate,
        "catches": player.catches,
        "stumpings": player.stumpings,
        "run_outs": player.run_outs,
        "dismissals": player.dismissals,
        "dismissal_details_json": json.dumps(player.dismissal_details, sort_keys=True)
        if player.dismissal_details
        else None,
    }


def _innings_player_row(player: InningsPlayerStats) -> dict[str, Any]:
    row = _player_row(player)
    row["innings_number"] = player.innings_number
    row["innings_team"] = player.innings_team
    row["team_player_position"] = player.team_player_position
    row["batting_position"] = player.batting_position
    row["bowler_position"] = player.bowler_position
    row["is_current_batter"] = int(player.is_current_batter)
    row["is_current_bowler"] = int(player.is_current_bowler)
    row["is_out"] = int(player.is_out)
    row["maidens"] = player.maidens
    row["wides"] = player.wides
    row["no_balls"] = player.no_balls
    dismissal = player.dismissal_details[0] if player.dismissal_details else {}
    row["dismissal_kind"] = dismissal.get("kind")
    row["dismissal_bowler"] = dismissal.get("bowler")
    row["dismissal_fielders"] = ", ".join(dismissal.get("fielders", [])) or None
    row["dismissal_text"] = player.dismissal_text
    row["fall_of_wicket_order"] = player.fall_of_wicket_order
    row["fall_of_wicket_runs"] = player.fall_of_wicket_runs
    row["fall_of_wicket_over"] = player.fall_of_wicket_over
    return row


if __name__ == "__main__":
    main()
