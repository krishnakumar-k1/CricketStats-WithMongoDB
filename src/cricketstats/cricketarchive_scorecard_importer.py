from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cricketstats.importer import populate_player_summary_tables


DB_PATH = Path("cricketstats.sqlite")
SCORECARD_ROOT = Path("cricketarchive_wayback_tests_1930_1996")
TEST_COUNTRIES = {
    "Afghanistan",
    "Australia",
    "Bangladesh",
    "England",
    "India",
    "Ireland",
    "New Zealand",
    "Pakistan",
    "South Africa",
    "Sri Lanka",
    "West Indies",
    "Zimbabwe",
}


@dataclass
class PlayerAggregate:
    match_id: str
    player_name: str
    team: str
    runs_scored: int = 0
    balls_faced: int = 0
    fours: int = 0
    sixes: int = 0
    wickets_taken: int = 0
    balls_bowled: int = 0
    overs_bowled: str = "0.0"
    runs_conceded: int = 0
    catches: int = 0
    stumpings: int = 0
    run_outs: int = 0
    dismissals: int = 0
    dismissal_details: list[dict[str, Any]] = field(default_factory=list)


def import_scorecards(
    scorecard_roots: list[Path],
    db_path: Path,
    *,
    min_year: int | None = None,
    max_year: int | None = None,
    delete_before_year: int | None = None,
) -> int:
    files = discover_scorecard_files(scorecard_roots)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_existing_tables(conn)
        if delete_before_year is not None:
            delete_matches_before_year(conn, delete_before_year)
        else:
            delete_existing_cricketarchive_matches(conn)

        imported = 0
        seen_match_ids: set[str] = set()
        for path in files:
            scorecard = parse_scorecard(path)
            if scorecard is None:
                continue
            year = scorecard["match"]["year"]
            if min_year is not None and (year is None or year < min_year):
                continue
            if max_year is not None and (year is None or year > max_year):
                continue
            match_id = scorecard["match"]["match_id"]
            if match_id in seen_match_ids:
                continue
            seen_match_ids.add(match_id)
            insert_scorecard(conn, scorecard)
            imported += 1

        populate_player_summary_tables(conn)
        conn.commit()
    return imported


def discover_scorecard_files(scorecard_roots: list[Path]) -> list[Path]:
    files: dict[str, Path] = {}
    for root in scorecard_roots:
        for path in sorted(root.glob("*/*.json")):
            if path.name == "crawl_index.json":
                continue
            files.setdefault(path.stem, path)
        for path in sorted(root.glob("*/scorecards/*.json")):
            files.setdefault(path.stem, path)
    return sorted(files.values(), key=lambda path: (str(path.parent), path.name))


def ensure_existing_tables(conn: sqlite3.Connection) -> None:
    required = {
        "match_stats",
        "match_innings_stats",
        "player_match_stats",
        "player_match_innings_stats",
        "player_batting_innings_stats",
        "player_career_stats",
        "player_career_group_stats",
    }
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    missing = sorted(required - existing)
    if missing:
        raise RuntimeError(f"Database is missing required tables: {', '.join(missing)}")


def parse_scorecard(path: Path) -> dict[str, Any] | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    scorecard_id = data.get("scorecard_id") or path.stem
    match_id = f"ca_{scorecard_id}"
    summary = data.get("summary") or {}
    title = summary.get("match_title") or ""
    teams = split_teams(title)
    if not is_country_test_scorecard(summary, teams):
        return None
    balls_per_over = _to_int(summary.get("balls_per_over"), default=6)
    innings = parse_innings_tables(data.get("tables", []), match_id, balls_per_over)
    players = aggregate_players(match_id, innings["players"])
    year = extract_year(summary.get("venue")) or extract_year_from_path(path)

    match = {
        "match_id": match_id,
        "source_file": str(path),
        "match_date": extract_match_date(summary.get("venue"), year),
        "year": year,
        "season": str(path.parent.parent.name),
        "match_type": "Test",
        "team_type": None,
        "gender": "male",
        "city": extract_city(summary.get("venue")),
        "venue": summary.get("venue"),
        "event_name": None,
        "event_match_number": extract_test_number(summary),
        "event_stage": None,
        "event_group": None,
        "event_sub_name": None,
        "event_json": json.dumps(summary, sort_keys=True),
        "team1": teams[0] if len(teams) > 0 else None,
        "team2": teams[1] if len(teams) > 1 else None,
        "toss_winner": extract_toss_winner(summary.get("toss")),
        "toss_decision": extract_toss_decision(summary.get("toss")),
        "winner": extract_winner(summary.get("result")),
        "result": summary.get("result"),
        "won_by_runs": extract_win_margin(summary.get("result"), "runs"),
        "won_by_wickets": extract_win_margin(summary.get("result"), "wickets"),
        "balls_per_over": balls_per_over,
        "scheduled_overs": None,
        "innings_count": len(innings["innings"]),
        "team1_runs": innings["innings"][0]["runs"] if len(innings["innings"]) > 0 else None,
        "team1_wickets": innings["innings"][0]["wickets"] if len(innings["innings"]) > 0 else None,
        "team1_overs": innings["innings"][0]["overs"] if len(innings["innings"]) > 0 else None,
        "team2_runs": innings["innings"][1]["runs"] if len(innings["innings"]) > 1 else None,
        "team2_wickets": innings["innings"][1]["wickets"] if len(innings["innings"]) > 1 else None,
        "team2_overs": innings["innings"][1]["overs"] if len(innings["innings"]) > 1 else None,
    }
    return {
        "match": match,
        "innings": innings["innings"],
        "innings_players": innings["players"],
        "players": players,
    }


def parse_innings_tables(
    tables: list[list[list[str]]], match_id: str, balls_per_over: int
) -> dict[str, list[dict[str, Any]]]:
    innings_rows: list[dict[str, Any]] = []
    player_rows: list[dict[str, Any]] = []
    innings_number = 0
    index = 0
    while index < len(tables):
        table = tables[index]
        if not table or not is_batting_table(table):
            index += 1
            continue

        innings_number += 1
        batting_header = table[0][0]
        batting_team = team_from_batting_header(batting_header)
        bowling_table = tables[index + 1] if index + 1 < len(tables) and is_bowling_table(tables[index + 1]) else []
        bowling_team = team_from_bowling_header(bowling_table[0][0]) if bowling_table else ""
        total = parse_total(table, balls_per_over)
        fall_of_wickets = parse_fall_of_wickets(table)

        innings_rows.append(
            {
                "match_id": match_id,
                "innings_number": innings_number,
                "team": batting_team,
                "runs": total["runs"],
                "wickets": total["wickets"],
                "overs": total["overs"],
                "legal_balls": total["legal_balls"],
                "run_rate": (
                    round(total["runs"] * balls_per_over / total["legal_balls"], 2)
                    if total["legal_balls"]
                    else None
                ),
                "extras_total": total["extras_total"],
                "byes": total["extras"].get("b", 0),
                "legbyes": total["extras"].get("lb", 0),
                "wides": total["extras"].get("w", 0),
                "no_balls": total["extras"].get("nb", 0),
                "penalties": total["extras"].get("pen", 0),
                "extras_text": total["extras_text"],
                "total_text": total["total_text"],
                "fall_of_wickets_json": json.dumps(fall_of_wickets),
                "batting_order_json": json.dumps(batting_order(table)),
                "bowling_order_json": json.dumps(bowling_order(bowling_table)),
                "striker": None,
                "non_striker": None,
                "current_bowler": None,
            }
        )

        player_rows.extend(
            batting_player_rows(
                table,
                match_id,
                innings_number,
                batting_team,
                bowling_team,
                fall_of_wickets,
            )
        )
        player_rows.extend(
            bowling_player_rows(
                bowling_table,
                match_id,
                innings_number,
                batting_team,
                bowling_team,
                balls_per_over,
            )
        )
        index += 2 if bowling_table else 1
    return {"innings": innings_rows, "players": player_rows}


def batting_player_rows(
    table: list[list[str]],
    match_id: str,
    innings_number: int,
    batting_team: str,
    bowling_team: str,
    fall_of_wickets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    batting_position = 0
    for row in table[1:]:
        if is_summary_row(row):
            continue
        batting_position += 1
        player_name = clean_player_name(row[0])
        dismissal_text = row[1] if len(row) > 1 else ""
        did_not_bat = dismissal_text.lower() in {"did not bat", "absent"}
        runs = _to_int(row[2] if len(row) > 2 else None)
        balls = _to_int(row[3] if len(row) > 3 else None)
        fours = _to_int(row[5] if len(row) > 5 else None)
        sixes = _to_int(row[6] if len(row) > 6 else None)
        dismissal = parse_dismissal(dismissal_text)
        fow = find_fow(fall_of_wickets, player_name)
        rows.append(
            {
                "match_id": match_id,
                "innings_number": innings_number,
                "innings_team": batting_team,
                "player_name": player_name,
                "player_id": player_id_for(player_name),
                "team": batting_team,
                "team_player_position": batting_position,
                "batting_position": None if did_not_bat else batting_position,
                "bowler_position": None,
                "is_current_batter": 0,
                "is_current_bowler": 0,
                "is_out": 0 if dismissal_text.lower() in {"not out", "did not bat", "absent"} else 1,
                "runs_scored": runs,
                "balls_faced": balls,
                "fours": fours,
                "sixes": sixes,
                "strike_rate": round(runs * 100 / balls, 2) if balls else None,
                "wickets_taken": 0,
                "balls_bowled": 0,
                "overs_bowled": "0.0",
                "maidens": 0,
                "runs_conceded": 0,
                "economy_rate": None,
                "wides": 0,
                "no_balls": 0,
                "catches": 0,
                "stumpings": 0,
                "run_outs": 0,
                "dismissals": 1 if dismissal_text.lower() not in {"not out", "did not bat", "absent"} else 0,
                "dismissal_kind": dismissal["kind"],
                "dismissal_bowler": dismissal["bowler"],
                "dismissal_fielders": json.dumps(dismissal["fielders"]),
                "dismissal_text": dismissal_text,
                "fall_of_wicket_order": fow.get("order") if fow else None,
                "fall_of_wicket_runs": fow.get("runs") if fow else None,
                "fall_of_wicket_over": fow.get("over") if fow else None,
                "dismissal_details_json": json.dumps(
                    [
                        {
                            "kind": dismissal["kind"],
                            "bowler": dismissal["bowler"],
                            "fielders": dismissal["fielders"],
                            "text": dismissal_text,
                        }
                    ]
                    if dismissal["kind"]
                    else []
                ),
            }
        )
        rows.extend(fielding_rows_from_dismissal(match_id, innings_number, bowling_team, batting_team, dismissal))
    return rows


def bowling_player_rows(
    table: list[list[str]],
    match_id: str,
    innings_number: int,
    batting_team: str,
    bowling_team: str,
    balls_per_over: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for position, row in enumerate(table[1:], start=1):
        player_name = clean_player_name(row[0])
        overs = row[1] if len(row) > 1 else "0"
        balls_bowled = overs_to_balls(overs, balls_per_over)
        runs = _to_int(row[3] if len(row) > 3 else None)
        wickets = _to_int(row[4] if len(row) > 4 else None)
        rows.append(
            {
                "match_id": match_id,
                "innings_number": innings_number,
                "innings_team": batting_team,
                "player_name": player_name,
                "player_id": player_id_for(player_name),
                "team": bowling_team,
                "team_player_position": None,
                "batting_position": None,
                "bowler_position": position,
                "is_current_batter": 0,
                "is_current_bowler": 0,
                "is_out": 0,
                "runs_scored": 0,
                "balls_faced": 0,
                "fours": 0,
                "sixes": 0,
                "strike_rate": None,
                "wickets_taken": wickets,
                "balls_bowled": balls_bowled,
                "overs_bowled": overs,
                "maidens": _to_int(row[2] if len(row) > 2 else None),
                "runs_conceded": runs,
                "economy_rate": round(runs * balls_per_over / balls_bowled, 2) if balls_bowled else None,
                "wides": _to_int(row[5] if len(row) > 5 else None),
                "no_balls": _to_int(row[6] if len(row) > 6 else None),
                "catches": 0,
                "stumpings": 0,
                "run_outs": 0,
                "dismissals": 0,
                "dismissal_kind": None,
                "dismissal_bowler": None,
                "dismissal_fielders": "[]",
                "dismissal_text": None,
                "fall_of_wicket_order": None,
                "fall_of_wicket_runs": None,
                "fall_of_wicket_over": None,
                "dismissal_details_json": "[]",
            }
        )
    return rows


def fielding_rows_from_dismissal(
    match_id: str,
    innings_number: int,
    bowling_team: str,
    batting_team: str,
    dismissal: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    kind = dismissal["kind"]
    for fielder in dismissal["fielders"]:
        if not fielder:
            continue
        rows.append(empty_innings_player(match_id, innings_number, batting_team, fielder, bowling_team))
        if kind in {"caught", "caught and bowled"}:
            rows[-1]["catches"] = 1
        elif kind == "stumped":
            rows[-1]["stumpings"] = 1
        elif kind == "run out":
            rows[-1]["run_outs"] = 1
    return rows


def empty_innings_player(
    match_id: str, innings_number: int, innings_team: str, player_name: str, team: str
) -> dict[str, Any]:
    return {
        "match_id": match_id,
        "innings_number": innings_number,
        "innings_team": innings_team,
        "player_name": clean_player_name(player_name),
        "player_id": player_id_for(player_name),
        "team": team,
        "team_player_position": None,
        "batting_position": None,
        "bowler_position": None,
        "is_current_batter": 0,
        "is_current_bowler": 0,
        "is_out": 0,
        "runs_scored": 0,
        "balls_faced": 0,
        "fours": 0,
        "sixes": 0,
        "strike_rate": None,
        "wickets_taken": 0,
        "balls_bowled": 0,
        "overs_bowled": "0.0",
        "maidens": 0,
        "runs_conceded": 0,
        "economy_rate": None,
        "wides": 0,
        "no_balls": 0,
        "catches": 0,
        "stumpings": 0,
        "run_outs": 0,
        "dismissals": 0,
        "dismissal_kind": None,
        "dismissal_bowler": None,
        "dismissal_fielders": "[]",
        "dismissal_text": None,
        "fall_of_wicket_order": None,
        "fall_of_wicket_runs": None,
        "fall_of_wicket_over": None,
        "dismissal_details_json": "[]",
    }


def aggregate_players(match_id: str, innings_players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    players: dict[str, PlayerAggregate] = {}
    for row in innings_players:
        key = row["player_name"]
        player = players.setdefault(
            key,
            PlayerAggregate(match_id=match_id, player_name=row["player_name"], team=row["team"]),
        )
        if not player.team and row["team"]:
            player.team = row["team"]
        player.runs_scored += row["runs_scored"]
        player.balls_faced += row["balls_faced"]
        player.fours += row["fours"]
        player.sixes += row["sixes"]
        player.wickets_taken += row["wickets_taken"]
        player.balls_bowled += row["balls_bowled"]
        player.runs_conceded += row["runs_conceded"]
        player.catches += row["catches"]
        player.stumpings += row["stumpings"]
        player.run_outs += row["run_outs"]
        player.dismissals += row["dismissals"]
        details = json.loads(row["dismissal_details_json"])
        player.dismissal_details.extend(details)

    output = []
    for player in players.values():
        output.append(
            {
                "match_id": match_id,
                "player_name": player.player_name,
                "player_id": player_id_for(player.player_name),
                "team": player.team,
                "runs_scored": player.runs_scored,
                "balls_faced": player.balls_faced,
                "fours": player.fours,
                "sixes": player.sixes,
                "strike_rate": round(player.runs_scored * 100 / player.balls_faced, 2)
                if player.balls_faced
                else None,
                "wickets_taken": player.wickets_taken,
                "balls_bowled": player.balls_bowled,
                "overs_bowled": balls_to_overs(player.balls_bowled, 6),
                "runs_conceded": player.runs_conceded,
                "economy_rate": round(player.runs_conceded * 6 / player.balls_bowled, 2)
                if player.balls_bowled
                else None,
                "catches": player.catches,
                "stumpings": player.stumpings,
                "run_outs": player.run_outs,
                "dismissals": player.dismissals,
                "dismissal_details_json": json.dumps(player.dismissal_details),
            }
        )
    return output


def insert_scorecard(conn: sqlite3.Connection, scorecard: dict[str, Any]) -> None:
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
        scorecard["match"],
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
        scorecard["innings"],
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
        scorecard["players"],
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
        merge_innings_player_rows(scorecard["innings_players"]),
    )


def delete_existing_match(conn: sqlite3.Connection, match_id: str) -> None:
    for table in (
        "player_batting_innings_stats",
        "player_match_innings_stats",
        "player_match_stats",
        "match_innings_stats",
        "match_stats",
    ):
        conn.execute(f"DELETE FROM {table} WHERE match_id = ?", (match_id,))


def delete_existing_cricketarchive_matches(conn: sqlite3.Connection) -> None:
    for table in (
        "player_batting_innings_stats",
        "player_match_innings_stats",
        "player_match_stats",
        "match_innings_stats",
        "match_stats",
    ):
        conn.execute(f"DELETE FROM {table} WHERE match_id LIKE 'ca_%'")


def delete_matches_before_year(conn: sqlite3.Connection, year: int) -> None:
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS matches_to_delete (match_id TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM matches_to_delete")
    conn.execute(
        "INSERT INTO matches_to_delete SELECT match_id FROM match_stats WHERE year < ?",
        (year,),
    )
    for table in (
        "player_batting_innings_stats",
        "player_match_innings_stats",
        "player_match_stats",
        "match_innings_stats",
        "match_stats",
    ):
        conn.execute(
            f"DELETE FROM {table} WHERE match_id IN (SELECT match_id FROM matches_to_delete)"
        )
    conn.execute("DROP TABLE matches_to_delete")


def merge_innings_player_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["match_id"], row["innings_number"], row["player_name"])
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(row)
            continue
        for field in (
            "runs_scored",
            "balls_faced",
            "fours",
            "sixes",
            "wickets_taken",
            "balls_bowled",
            "maidens",
            "runs_conceded",
            "wides",
            "no_balls",
            "catches",
            "stumpings",
            "run_outs",
            "dismissals",
        ):
            existing[field] += row[field]
        for field in (
            "team_player_position",
            "batting_position",
            "bowler_position",
            "dismissal_kind",
            "dismissal_bowler",
            "dismissal_text",
            "fall_of_wicket_order",
            "fall_of_wicket_runs",
            "fall_of_wicket_over",
        ):
            if existing[field] is None:
                existing[field] = row[field]
        if existing["dismissal_fielders"] == "[]":
            existing["dismissal_fielders"] = row["dismissal_fielders"]
        if existing["dismissal_details_json"] == "[]":
            existing["dismissal_details_json"] = row["dismissal_details_json"]
        existing["is_out"] = max(existing["is_out"], row["is_out"])
        existing["overs_bowled"] = row["overs_bowled"] if row["balls_bowled"] else existing["overs_bowled"]
        existing["economy_rate"] = row["economy_rate"] if row["balls_bowled"] else existing["economy_rate"]
        existing["strike_rate"] = (
            round(existing["runs_scored"] * 100 / existing["balls_faced"], 2)
            if existing["balls_faced"]
            else None
        )
    return list(merged.values())


def is_batting_table(table: list[list[str]]) -> bool:
    return bool(table and len(table[0]) >= 2 and table[0][1] == "Runs" and "innings" in table[0][0].lower())


def is_bowling_table(table: list[list[str]]) -> bool:
    return bool(table and len(table[0]) >= 5 and table[0][1] == "Overs" and table[0][0].lower().endswith(" bowling"))


def team_from_batting_header(header: str) -> str:
    return re.sub(r"\s+(first|second|third|fourth)\s+innings$", "", header, flags=re.I).strip()


def team_from_bowling_header(header: str) -> str:
    return re.sub(r"\s+bowling$", "", header, flags=re.I).strip()


def parse_total(table: list[list[str]], balls_per_over: int) -> dict[str, Any]:
    extras = {}
    extras_text = ""
    total_text = ""
    total_runs = 0
    wickets = 0
    overs = "0.0"
    legal_balls = 0
    for row in table:
        if row and row[0] == "Extras":
            extras_text = row[1] if len(row) > 1 else ""
            extras = parse_extras(extras_text)
        elif row and row[0] == "Total":
            total_text = row[1] if len(row) > 1 else ""
            total_runs = _to_int(row[2] if len(row) > 2 else None)
            wickets = parse_wickets(total_text)
            overs = parse_total_overs(total_text)
            legal_balls = overs_to_balls(overs, balls_per_over)
    return {
        "runs": total_runs,
        "wickets": wickets,
        "overs": overs,
        "legal_balls": legal_balls,
        "extras_total": sum(extras.values()),
        "extras": extras,
        "extras_text": extras_text,
        "total_text": total_text,
    }


def parse_extras(text: str) -> dict[str, int]:
    extras = {"b": 0, "lb": 0, "w": 0, "nb": 0, "pen": 0}
    for amount, key in re.findall(r"(\d+)\s+([a-zA-Z-]+)", text):
        normalized = {"no-balls": "nb", "no-ball": "nb", "wides": "w", "wide": "w"}.get(key.lower(), key.lower())
        if normalized in extras:
            extras[normalized] += int(amount)
    return extras


def parse_wickets(text: str) -> int:
    lower = text.lower()
    if "all out" in lower:
        return 10
    match = re.search(r"(\d+)\s+wickets?", lower)
    return int(match.group(1)) if match else 0


def parse_total_overs(text: str) -> str:
    match = re.search(r"(\d+(?:\.\d+)?)\s+overs?", text)
    return match.group(1) if match else "0.0"


def parse_fall_of_wickets(table: list[list[str]]) -> list[dict[str, Any]]:
    for row in table:
        if len(row) == 1 and re.match(r"\d+-\d+", row[0]):
            output = []
            for item in row[0].split(","):
                match = re.search(r"(\d+)-(\d+)\s+\(\s*([^,()]+?)(?:\s*,\s*([0-9.]+)\s*ov)?\s*\)", item)
                if match:
                    output.append(
                        {
                            "order": int(match.group(1)),
                            "runs": int(match.group(2)),
                            "player": clean_player_name(match.group(3)),
                            "over": match.group(4),
                        }
                    )
            return output
    return []


def batting_order(table: list[list[str]]) -> list[str]:
    return [clean_player_name(row[0]) for row in table[1:] if row and not is_summary_row(row)]


def bowling_order(table: list[list[str]]) -> list[str]:
    return [clean_player_name(row[0]) for row in table[1:] if row]


def find_fow(fall_of_wickets: list[dict[str, Any]], player_name: str) -> dict[str, Any] | None:
    clean = clean_player_name(player_name)
    return next((item for item in fall_of_wickets if item["player"] == clean), None)


def is_summary_row(row: list[str]) -> bool:
    return not row or row[0] in {"Extras", "Total"} or (len(row) == 1 and re.match(r"\d+-\d+", row[0]))


def parse_dismissal(text: str) -> dict[str, Any]:
    text = text.strip()
    lower = text.lower()
    if lower in {"", "not out", "did not bat", "absent"}:
        return {"kind": None, "bowler": None, "fielders": []}
    if lower.startswith("c and b "):
        bowler = clean_player_name(text[8:])
        return {"kind": "caught and bowled", "bowler": bowler, "fielders": [bowler]}
    match = re.match(r"c\s+(.+?)\s+b\s+(.+)$", text)
    if match:
        return {
            "kind": "caught",
            "bowler": clean_player_name(match.group(2)),
            "fielders": [clean_player_name(match.group(1))],
        }
    match = re.match(r"st\s+(.+?)\s+b\s+(.+)$", text)
    if match:
        return {
            "kind": "stumped",
            "bowler": clean_player_name(match.group(2)),
            "fielders": [clean_player_name(match.group(1))],
        }
    match = re.match(r"b\s+(.+)$", text)
    if match:
        return {"kind": "bowled", "bowler": clean_player_name(match.group(1)), "fielders": []}
    match = re.match(r"lbw\s+b\s+(.+)$", text)
    if match:
        return {"kind": "lbw", "bowler": clean_player_name(match.group(1)), "fielders": []}
    if lower.startswith("run out"):
        names = re.findall(r"\((.*?)\)", text)
        fielders = [clean_player_name(name) for name in names[0].split("/") if name.strip()] if names else []
        return {"kind": "run out", "bowler": None, "fielders": fielders}
    return {"kind": text, "bowler": None, "fielders": []}


def clean_player_name(name: str) -> str:
    return re.sub(r"^[*+\s]+", "", name).strip()


def player_id_for(player_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", player_name.lower()).strip("_")
    return f"ca:{slug or 'unknown'}"


def overs_to_balls(overs: str, balls_per_over: int) -> int:
    if not overs or overs in {"-", "?"}:
        return 0
    if "." not in overs:
        return int(float(overs)) * balls_per_over
    whole, part = overs.split(".", 1)
    return int(whole or 0) * balls_per_over + int(part or 0)


def balls_to_overs(balls: int, balls_per_over: int) -> str:
    whole, part = divmod(balls, balls_per_over)
    return f"{whole}.{part}"


def split_teams(title: str) -> list[str]:
    return [part.strip() for part in title.split(" v ", 1)] if " v " in title else []


def extract_test_number(summary: dict[str, Any]) -> int | None:
    match = re.search(r"\bt(\d+)\b", summary.get("scorecard_code", ""))
    return int(match.group(1)) if match else None


def is_test_scorecard(summary: dict[str, Any]) -> bool:
    return extract_test_number(summary) is not None


def is_country_test_scorecard(summary: dict[str, Any], teams: list[str]) -> bool:
    if not is_test_scorecard(summary) or len(teams) != 2:
        return False
    return all(normalize_country_name(team) in TEST_COUNTRIES for team in teams)


def normalize_country_name(team: str) -> str:
    return re.sub(r"\s+", " ", team).strip()


def extract_winner(result: str | None) -> str | None:
    if not result or " won by " not in result:
        return None
    return result.split(" won by ", 1)[0]


def extract_win_margin(result: str | None, kind: str) -> int | None:
    if not result:
        return None
    match = re.search(rf"(\d+)\s+{kind}", result)
    return int(match.group(1)) if match else None


def extract_toss_winner(toss: str | None) -> str | None:
    if not toss or " won the toss" not in toss:
        return None
    return toss.split(" won the toss", 1)[0]


def extract_toss_decision(toss: str | None) -> str | None:
    if not toss:
        return None
    if "decided to bat" in toss:
        return "bat"
    if "decided to field" in toss:
        return "field"
    return None


def extract_year(text: str | None) -> int | None:
    if not text:
        return None
    matches = re.findall(r"\b(18|19|20)\d{2}\b", text)
    if not matches:
        return None
    year_match = re.search(r"\b((?:18|19|20)\d{2})\b", text)
    return int(year_match.group(1)) if year_match else None


def extract_year_from_path(path: Path) -> int | None:
    match = re.search(r"\d{4}", str(path))
    return int(match.group(0)) if match else None


def extract_match_date(venue: str | None, year: int | None) -> str | None:
    if year is None or not venue:
        return None
    months = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }
    date_text_match = re.search(r"\bon\s+(.+?)(?:\s+\(\d+-day match\)|$)", venue)
    if not date_text_match:
        return f"{year}-01-01"
    date_text = date_text_match.group(1)
    first_day = re.search(r"(\d{1,2})(?:st|nd|rd|th)?", date_text)
    if not first_day:
        return f"{year}-01-01"
    first_day_end = first_day.end()
    first_month = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b",
        date_text[first_day_end:],
    )
    if not first_month:
        return f"{year}-01-01"
    return f"{year:04d}-{months[first_month.group(1)]:02d}-{int(first_day.group(1)):02d}"


def extract_city(venue: str | None) -> str | None:
    if not venue:
        return None
    before_on = venue.split(" on ", 1)[0]
    parts = [part.strip() for part in before_on.split(",") if part.strip()]
    return parts[-1] if parts else None


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    text = str(value).strip()
    if text in {"", "-"}:
        return default
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else default


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import CricketArchive Wayback scorecard JSON into cricketstats.sqlite."
    )
    parser.add_argument(
        "--scorecard-root",
        type=Path,
        action="append",
        default=None,
        help="Root containing CricketArchive scorecard JSON. Can be passed more than once.",
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--min-year", type=int, default=None)
    parser.add_argument("--max-year", type=int, default=None)
    parser.add_argument(
        "--delete-before-year",
        type=int,
        default=None,
        help="Delete all existing match-linked rows with match_stats.year less than this year before importing.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    roots = args.scorecard_root or [SCORECARD_ROOT]
    imported = import_scorecards(
        roots,
        args.db,
        min_year=args.min_year,
        max_year=args.max_year,
        delete_before_year=args.delete_before_year,
    )
    print(f"Imported CricketArchive scorecards: {imported}")
    print(f"Database: {args.db}")


if __name__ == "__main__":
    main()
