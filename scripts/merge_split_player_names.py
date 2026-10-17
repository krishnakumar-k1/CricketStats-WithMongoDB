#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


DB_PATH = Path("/Users/rkk/CricketStats/cricketstats.sqlite")
PROJECT_SRC = Path("/Users/rkk/CricketStats/src")


def overs_from_balls(balls: int) -> str:
    return f"{balls // 6}.{balls % 6}"


def strike_rate(runs: int, balls: int) -> float | None:
    if balls <= 0:
        return None
    return round(100.0 * runs / balls, 2)


def economy_rate(runs: int, balls: int) -> float | None:
    if balls <= 0:
        return None
    return round(6.0 * runs / balls, 2)


def prefer_text(primary: str | None, fallback: str | None) -> str | None:
    return primary if primary not in (None, "") else fallback


def detect_pairs(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        WITH pair_rows AS (
            SELECT
                ic.player_name AS canonical,
                so.player_name AS duplicate,
                pc.match_id,
                pc.team AS c_team,
                pd.team AS d_team,
                pc.runs_scored AS c_runs,
                pd.runs_scored AS d_runs,
                pc.wickets_taken AS c_wkts,
                pd.wickets_taken AS d_wkts
            FROM (
                SELECT
                    p.player_name,
                    substr(p.player_name, instr(p.player_name, ' ') + 1) AS surname,
                    MIN(m.match_date) AS first_date,
                    MAX(m.match_date) AS last_date
                FROM player_match_stats p
                JOIN match_stats m ON m.match_id = p.match_id
                WHERE m.match_type = 'Test'
                GROUP BY p.player_name
                HAVING p.player_name GLOB '[A-Z]* *'
                   AND first_date < '2000-01-01'
                   AND last_date >= '2000-01-01'
            ) ic
            JOIN (
                SELECT
                    p.player_name,
                    MIN(m.match_date) AS first_date
                FROM player_match_stats p
                JOIN match_stats m ON m.match_id = p.match_id
                WHERE m.match_type = 'Test'
                GROUP BY p.player_name
                HAVING instr(p.player_name, ' ') = 0
                   AND p.player_name NOT LIKE '%->%'
                   AND first_date < '2000-01-01'
            ) so ON lower(so.player_name) = lower(ic.surname)
            JOIN player_match_stats pc ON pc.player_name = ic.player_name
            JOIN player_match_stats pd
              ON pd.player_name = so.player_name
             AND pd.match_id = pc.match_id
        ),
        scored AS (
            SELECT
                canonical,
                duplicate,
                COUNT(*) AS overlaps,
                SUM(c_team = d_team) AS same_team,
                SUM(c_wkts = 0 AND d_wkts > 0) AS duplicate_bowling_rows,
                SUM(c_runs > 0 AND d_runs = 0) AS canonical_batting_rows,
                SUM(c_wkts > 0 AND d_wkts > 0) AS both_bowling_rows,
                SUM(c_runs > 0 AND d_runs > 0) AS both_batting_rows
            FROM pair_rows
            GROUP BY canonical, duplicate
        ),
        unambiguous AS (
            SELECT duplicate
            FROM scored
            WHERE overlaps >= 5
              AND same_team = overlaps
              AND duplicate_bowling_rows >= 3
              AND both_batting_rows = 0
            GROUP BY duplicate
            HAVING COUNT(*) = 1
        )
        SELECT canonical, duplicate
        FROM scored
        JOIN unambiguous USING (duplicate)
        WHERE overlaps >= 5
          AND same_team = overlaps
          AND duplicate_bowling_rows >= 3
          AND both_batting_rows = 0
        ORDER BY canonical, duplicate
        """
    ).fetchall()
    return [(row["canonical"], row["duplicate"]) for row in rows]


def merge_player_match_stats(conn: sqlite3.Connection, canonical: str, duplicate: str) -> tuple[int, int]:
    overlaps = conn.execute(
        """
        SELECT
            c.match_id,
            c.runs_scored AS c_runs_scored,
            d.runs_scored AS d_runs_scored,
            c.balls_faced AS c_balls_faced,
            d.balls_faced AS d_balls_faced,
            d.fours AS d_fours,
            d.sixes AS d_sixes,
            c.wickets_taken AS c_wickets_taken,
            d.wickets_taken AS d_wickets_taken,
            c.balls_bowled AS c_balls_bowled,
            d.balls_bowled AS d_balls_bowled,
            c.runs_conceded AS c_runs_conceded,
            d.runs_conceded AS d_runs_conceded,
            d.catches AS d_catches,
            d.stumpings AS d_stumpings,
            d.run_outs AS d_run_outs,
            d.dismissals AS d_dismissals,
            d.dismissal_details_json AS d_dismissal_details_json
        FROM player_match_stats c
        JOIN player_match_stats d
          ON d.match_id = c.match_id
         AND d.player_name = ?
        WHERE c.player_name = ?
        """,
        (duplicate, canonical),
    ).fetchall()

    for row in overlaps:
        match_id = row["match_id"]
        runs = row["c_runs_scored"] + row["d_runs_scored"]
        balls = row["c_balls_faced"] + row["d_balls_faced"]
        wickets = row["c_wickets_taken"] + row["d_wickets_taken"]
        balls_bowled = row["c_balls_bowled"] + row["d_balls_bowled"]
        runs_conceded = row["c_runs_conceded"] + row["d_runs_conceded"]
        conn.execute(
            """
            UPDATE player_match_stats
            SET
                runs_scored = ?,
                balls_faced = ?,
                fours = fours + ?,
                sixes = sixes + ?,
                strike_rate = ?,
                wickets_taken = ?,
                balls_bowled = ?,
                overs_bowled = ?,
                runs_conceded = ?,
                economy_rate = ?,
                catches = catches + ?,
                stumpings = stumpings + ?,
                run_outs = run_outs + ?,
                dismissals = dismissals + ?,
                dismissal_details_json = COALESCE(dismissal_details_json, ?)
            WHERE match_id = ?
              AND player_name = ?
            """,
            (
                runs,
                balls,
                row["d_fours"],
                row["d_sixes"],
                strike_rate(runs, balls),
                wickets,
                balls_bowled,
                overs_from_balls(balls_bowled),
                runs_conceded,
                economy_rate(runs_conceded, balls_bowled),
                row["d_catches"],
                row["d_stumpings"],
                row["d_run_outs"],
                row["d_dismissals"],
                row["d_dismissal_details_json"],
                match_id,
                canonical,
            ),
        )
        conn.execute(
            "DELETE FROM player_match_stats WHERE match_id = ? AND player_name = ?",
            (match_id, duplicate),
        )

    renamed = conn.execute(
        """
        UPDATE player_match_stats
        SET player_name = ?
        WHERE player_name = ?
          AND NOT EXISTS (
              SELECT 1
              FROM player_match_stats c
              WHERE c.match_id = player_match_stats.match_id
                AND c.player_name = ?
          )
        """,
        (canonical, duplicate, canonical),
    ).rowcount
    return len(overlaps), renamed


def merge_player_match_innings_stats(
    conn: sqlite3.Connection, canonical: str, duplicate: str
) -> tuple[int, int]:
    overlaps = conn.execute(
        """
        SELECT
            c.match_id,
            c.innings_number,
            d.team_player_position AS d_team_player_position,
            d.batting_position AS d_batting_position,
            d.bowler_position AS d_bowler_position,
            d.is_current_batter AS d_is_current_batter,
            d.is_current_bowler AS d_is_current_bowler,
            d.is_out AS d_is_out,
            c.runs_scored AS c_runs_scored,
            d.runs_scored AS d_runs_scored,
            c.balls_faced AS c_balls_faced,
            d.balls_faced AS d_balls_faced,
            d.fours AS d_fours,
            d.sixes AS d_sixes,
            c.wickets_taken AS c_wickets_taken,
            d.wickets_taken AS d_wickets_taken,
            c.balls_bowled AS c_balls_bowled,
            d.balls_bowled AS d_balls_bowled,
            d.maidens AS d_maidens,
            c.runs_conceded AS c_runs_conceded,
            d.runs_conceded AS d_runs_conceded,
            d.wides AS d_wides,
            d.no_balls AS d_no_balls,
            d.catches AS d_catches,
            d.stumpings AS d_stumpings,
            d.run_outs AS d_run_outs,
            d.dismissals AS d_dismissals,
            d.dismissal_kind AS d_dismissal_kind,
            d.dismissal_bowler AS d_dismissal_bowler,
            d.dismissal_fielders AS d_dismissal_fielders,
            d.dismissal_text AS d_dismissal_text,
            d.fall_of_wicket_order AS d_fall_of_wicket_order,
            d.fall_of_wicket_runs AS d_fall_of_wicket_runs,
            d.fall_of_wicket_over AS d_fall_of_wicket_over,
            d.dismissal_details_json AS d_dismissal_details_json
        FROM player_match_innings_stats c
        JOIN player_match_innings_stats d
          ON d.match_id = c.match_id
         AND d.innings_number = c.innings_number
         AND d.player_name = ?
        WHERE c.player_name = ?
        """,
        (duplicate, canonical),
    ).fetchall()

    for row in overlaps:
        match_id = row["match_id"]
        innings_number = row["innings_number"]
        runs = row["c_runs_scored"] + row["d_runs_scored"]
        balls = row["c_balls_faced"] + row["d_balls_faced"]
        wickets = row["c_wickets_taken"] + row["d_wickets_taken"]
        balls_bowled = row["c_balls_bowled"] + row["d_balls_bowled"]
        runs_conceded = row["c_runs_conceded"] + row["d_runs_conceded"]
        conn.execute(
            """
            UPDATE player_match_innings_stats
            SET
                team_player_position = COALESCE(team_player_position, ?),
                batting_position = COALESCE(batting_position, ?),
                bowler_position = COALESCE(bowler_position, ?),
                is_current_batter = max(is_current_batter, ?),
                is_current_bowler = max(is_current_bowler, ?),
                is_out = max(is_out, ?),
                runs_scored = ?,
                balls_faced = ?,
                fours = fours + ?,
                sixes = sixes + ?,
                strike_rate = ?,
                wickets_taken = ?,
                balls_bowled = ?,
                overs_bowled = ?,
                maidens = maidens + ?,
                runs_conceded = ?,
                economy_rate = ?,
                wides = wides + ?,
                no_balls = no_balls + ?,
                catches = catches + ?,
                stumpings = stumpings + ?,
                run_outs = run_outs + ?,
                dismissals = dismissals + ?,
                dismissal_kind = COALESCE(dismissal_kind, ?),
                dismissal_bowler = COALESCE(dismissal_bowler, ?),
                dismissal_fielders = COALESCE(dismissal_fielders, ?),
                dismissal_text = COALESCE(dismissal_text, ?),
                fall_of_wicket_order = COALESCE(fall_of_wicket_order, ?),
                fall_of_wicket_runs = COALESCE(fall_of_wicket_runs, ?),
                fall_of_wicket_over = COALESCE(fall_of_wicket_over, ?),
                dismissal_details_json = COALESCE(dismissal_details_json, ?)
            WHERE match_id = ?
              AND innings_number = ?
              AND player_name = ?
            """,
            (
                row["d_team_player_position"],
                row["d_batting_position"],
                row["d_bowler_position"],
                row["d_is_current_batter"],
                row["d_is_current_bowler"],
                row["d_is_out"],
                runs,
                balls,
                row["d_fours"],
                row["d_sixes"],
                strike_rate(runs, balls),
                wickets,
                balls_bowled,
                overs_from_balls(balls_bowled),
                row["d_maidens"],
                runs_conceded,
                economy_rate(runs_conceded, balls_bowled),
                row["d_wides"],
                row["d_no_balls"],
                row["d_catches"],
                row["d_stumpings"],
                row["d_run_outs"],
                row["d_dismissals"],
                row["d_dismissal_kind"],
                row["d_dismissal_bowler"],
                row["d_dismissal_fielders"],
                row["d_dismissal_text"],
                row["d_fall_of_wicket_order"],
                row["d_fall_of_wicket_runs"],
                row["d_fall_of_wicket_over"],
                row["d_dismissal_details_json"],
                match_id,
                innings_number,
                canonical,
            ),
        )
        conn.execute(
            """
            DELETE FROM player_match_innings_stats
            WHERE match_id = ?
              AND innings_number = ?
              AND player_name = ?
            """,
            (match_id, innings_number, duplicate),
        )

    renamed = conn.execute(
        """
        UPDATE player_match_innings_stats
        SET player_name = ?
        WHERE player_name = ?
          AND NOT EXISTS (
              SELECT 1
              FROM player_match_innings_stats c
              WHERE c.match_id = player_match_innings_stats.match_id
                AND c.innings_number = player_match_innings_stats.innings_number
                AND c.player_name = ?
          )
        """,
        (canonical, duplicate, canonical),
    ).rowcount
    return len(overlaps), renamed


def replace_name_references(conn: sqlite3.Connection, canonical: str, duplicate: str) -> None:
    conn.execute(
        """
        UPDATE player_match_innings_stats
        SET dismissal_bowler = ?
        WHERE dismissal_bowler = ?
        """,
        (canonical, duplicate),
    )


def canonical_player_id(conn: sqlite3.Connection, canonical: str) -> str | None:
    row = conn.execute(
        """
        SELECT player_id
        FROM player_match_stats
        WHERE player_name = ?
          AND player_id IS NOT NULL
          AND player_id != ''
        GROUP BY player_id
        ORDER BY COUNT(*) DESC, player_id ASC
        LIMIT 1
        """,
        (canonical,),
    ).fetchone()
    if row is None:
        return None
    return row["player_id"]


def normalize_player_id(conn: sqlite3.Connection, canonical: str) -> int:
    player_id = canonical_player_id(conn, canonical)
    if player_id is None:
        return 0

    changed = 0
    for table in ("player_match_stats", "player_match_innings_stats"):
        changed += conn.execute(
            f"""
            UPDATE {table}
            SET player_id = ?
            WHERE player_name = ?
              AND COALESCE(player_id, '') != ?
            """,
            (player_id, canonical, player_id),
        ).rowcount
    return changed


def refresh_summaries(conn: sqlite3.Connection) -> None:
    sys.path.insert(0, str(PROJECT_SRC))
    from cricketstats.importer import populate_player_summary_tables

    populate_player_summary_tables(conn)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument(
        "--pairs-db",
        type=Path,
        help="Optional database to use for detecting split-name pairs.",
    )
    parser.add_argument(
        "--pair",
        nargs=2,
        action="append",
        metavar=("CANONICAL", "DUPLICATE"),
        help=(
            "Merge one explicit duplicate name into a canonical name. "
            "Can be supplied more than once; bypasses automatic pair detection."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    if args.pair:
        pairs = [(canonical, duplicate) for canonical, duplicate in args.pair]
    else:
        pairs_conn = conn
        if args.pairs_db:
            pairs_conn = sqlite3.connect(args.pairs_db)
            pairs_conn.row_factory = sqlite3.Row
        pairs = detect_pairs(pairs_conn)
        if pairs_conn is not conn:
            pairs_conn.close()
    print(f"Detected {len(pairs)} high-confidence split player-name pairs.")
    for canonical, duplicate in pairs:
        print(f"  {duplicate} -> {canonical}")

    if args.dry_run:
        return 0

    backup_path = args.db.with_suffix(args.db.suffix + ".before_split_name_merge.bak")
    if not backup_path.exists():
        backup_conn = sqlite3.connect(backup_path)
        try:
            conn.backup(backup_conn)
        finally:
            backup_conn.close()
        print(f"Backup created: {backup_path}")
    else:
        print(f"Backup already exists: {backup_path}")

    conn.execute("BEGIN")
    try:
        total_match_overlaps = total_match_renames = total_id_updates = 0
        total_innings_overlaps = total_innings_renames = 0
        for canonical, duplicate in pairs:
            match_overlaps, match_renames = merge_player_match_stats(
                conn, canonical, duplicate
            )
            innings_overlaps, innings_renames = merge_player_match_innings_stats(
                conn, canonical, duplicate
            )
            replace_name_references(conn, canonical, duplicate)
            total_id_updates += normalize_player_id(conn, canonical)
            total_match_overlaps += match_overlaps
            total_match_renames += match_renames
            total_innings_overlaps += innings_overlaps
            total_innings_renames += innings_renames

        refresh_summaries(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    print(
        "Merged base rows: "
        f"{total_match_overlaps} match overlaps, {total_match_renames} match renames, "
        f"{total_innings_overlaps} innings overlaps, {total_innings_renames} innings renames, "
        f"{total_id_updates} player_id normalizations."
    )
    print("Refreshed player batting innings, career, and career group summaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
