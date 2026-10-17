import json
import sqlite3

from cricketstats.ipl_importer import build_ipl_database
from test_importer import _sample_match


def test_build_ipl_database_filters_matches_and_builds_team_stats(tmp_path) -> None:
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    ipl_match = _sample_match()
    ipl_match["info"]["event"]["name"] = "Indian Premier League"
    ipl_match["info"]["event"]["stage"] = "Final"
    ipl_match["info"]["match_type"] = "T20"
    ipl_match["info"]["season"] = "2024"
    (json_dir / "ipl.json").write_text(json.dumps(ipl_match), encoding="utf-8")

    other_match = _sample_match()
    (json_dir / "other.json").write_text(json.dumps(other_match), encoding="utf-8")

    db_path = tmp_path / "ipl.sqlite"
    imported = build_ipl_database(json_dir, db_path)

    assert imported == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM match_stats").fetchone() == (1,)
        assert conn.execute(
            """
            SELECT format_group, competition_name, matches
            FROM player_career_stats
            WHERE player_name = 'A Batter' AND competition_name = 'All'
            """
        ).fetchone() == ("IPL", "All", 1)
        assert conn.execute(
            """
            SELECT matches, wins, losses, runs_for, runs_against, titles
            FROM team_career_stats
            WHERE team = 'Alpha'
            """
        ).fetchone() == (1, 1, 0, 12, 0, 1)
        assert conn.execute(
            """
            SELECT matches, wins, losses, champion
            FROM team_season_stats
            WHERE season = '2024' AND team = 'Beta'
            """
        ).fetchone() == (1, 0, 1, 0)
        assert conn.execute(
            """
            SELECT batter, bowler, SUM(is_six)
            FROM delivery_stats
            GROUP BY batter, bowler
            ORDER BY SUM(is_six) DESC
            LIMIT 1
            """
        ).fetchone() == ("A Batter", "B Bowler", 1)
        assert conn.execute(
            """
            SELECT player_name, runs_scored
            FROM orange_cap_winners
            WHERE season = '2024'
            """
        ).fetchone() == ("A Batter", 10)
        assert conn.execute(
            """
            SELECT player_name, wickets_taken
            FROM purple_cap_winners
            WHERE season = '2024'
            ORDER BY player_name
            """
        ).fetchall() == [("A Bowler", 1)]
        assert conn.execute(
            """
            SELECT team1, team2, result
            FROM supplemental_matches
            WHERE season = '2009' AND event_match_number = 7
            """
        ).fetchone() == ("Mumbai Indians", "Rajasthan Royals", "no result")
        assert conn.execute(
            """
            SELECT canonical_venue
            FROM venue_aliases
            WHERE raw_venue = 'Example Ground'
            """
        ).fetchone() == ("Example Ground",)
        assert conn.execute("SELECT COUNT(*) FROM hat_trick_stats").fetchone() == (0,)
        assert conn.execute(
            """
            SELECT player_name, record_value, record_unit
            FROM special_record_stats
            WHERE record_type = 'fastest century by an uncapped Indian player'
              AND season = '2022'
            """
        ).fetchone() == ("RM Patidar", 49, "balls")
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM team_last_place_finishes
            WHERE team = 'Delhi Daredevils'
            """
        ).fetchone() == (4,)
