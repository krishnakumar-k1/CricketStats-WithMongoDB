import json
import sqlite3

from cricketstats.importer import import_json_directory


def test_import_json_directory_populates_match_and_player_tables(tmp_path) -> None:
    json_dir = tmp_path / "json"
    json_dir.mkdir()
    match_file = json_dir / "1.json"
    match_file.write_text(json.dumps(_sample_match()), encoding="utf-8")
    db_path = tmp_path / "cricketstats.sqlite"

    imported = import_json_directory(json_dir, db_path)

    assert imported == 1
    with sqlite3.connect(db_path) as conn:
        match = conn.execute(
            """
            SELECT match_id, year, match_type, venue, team1, team2, winner,
                   won_by_runs, team1_runs, team1_wickets, team1_overs,
                   team2_runs, team2_wickets, team2_overs, event_name,
                   event_match_number, event_stage, event_group,
                   event_sub_name, event_json
            FROM match_stats
            """
        ).fetchone()
        assert match == (
            "1",
            2024,
            "ODI",
            "Example Ground",
            "Alpha",
            "Beta",
            "Alpha",
            10,
            12,
            1,
            "1.0",
            0,
            1,
            "0.1",
            "Example Series",
            2,
            "Final",
            "Group A",
            "Example Sub Series",
            '{"group": "Group A", "match_number": 2, "name": "Example Series", "stage": "Final", "sub_name": "Example Sub Series"}',
        )

        striker = conn.execute(
            """
            SELECT runs_scored, balls_faced, fours, sixes, strike_rate, dismissals,
                   dismissal_details_json
            FROM player_match_stats
            WHERE player_name = 'A Batter'
            """
        ).fetchone()
        assert striker == (
            10,
            3,
            1,
            1,
            333.33,
            1,
            '[{"bowler": "B Bowler", "fielders": ["B Keeper"], "kind": "caught"}]',
        )

        bowler = conn.execute(
            """
            SELECT wickets_taken, balls_bowled, overs_bowled, runs_conceded,
                   economy_rate
            FROM player_match_stats
            WHERE player_name = 'B Bowler'
            """
        ).fetchone()
        assert bowler == (1, 6, "1.0", 12, 12.0)

        fielder = conn.execute(
            """
            SELECT catches, stumpings
            FROM player_match_stats
            WHERE player_name = 'B Keeper'
            """
        ).fetchone()
        assert fielder == (1, 1)

        innings_summary = conn.execute(
            """
            SELECT innings_number, team, runs, wickets, overs, run_rate,
                   extras_total, wides, no_balls, extras_text, total_text
            FROM match_innings_stats
            ORDER BY innings_number
            """
        ).fetchall()
        assert innings_summary == [
            (1, "Alpha", 12, 1, "1.0", 12.0, 2, 1, 1, "2 b:0 lb:0 nb:1 w:1 pen:0", "12-1 (1.0)"),
            (2, "Beta", 0, 1, "0.1", 0.0, 0, 0, 0, None, "0-1 (0.1)"),
        ]

        innings_rows = conn.execute(
            """
            SELECT innings_number, innings_team, player_name, runs_scored,
                   balls_faced, wickets_taken, balls_bowled, overs_bowled,
                   catches, stumpings, dismissal_kind, dismissal_bowler,
                   dismissal_fielders, dismissal_text
            FROM player_match_innings_stats
            WHERE player_name IN ('A Batter', 'A Bowler', 'B Bowler', 'B Keeper')
            ORDER BY innings_number, player_name
            """
        ).fetchall()
        assert innings_rows == [
            (1, "Alpha", "A Batter", 10, 3, 0, 0, "0.0", 0, 0, "caught", "B Bowler", "B Keeper", "c B Keeper b B Bowler"),
            (1, "Alpha", "A Bowler", 0, 0, 0, 0, "0.0", 0, 0, None, None, None, None),
            (1, "Alpha", "B Bowler", 0, 0, 1, 6, "1.0", 0, 0, None, None, None, None),
            (1, "Alpha", "B Keeper", 0, 0, 0, 0, "0.0", 1, 0, None, None, None, None),
            (2, "Beta", "A Batter", 0, 0, 0, 0, "0.0", 0, 0, None, None, None, None),
            (2, "Beta", "A Bowler", 0, 0, 1, 1, "0.1", 0, 0, None, None, None, None),
            (2, "Beta", "B Bowler", 0, 0, 0, 0, "0.0", 0, 0, None, None, None, None),
            (2, "Beta", "B Keeper", 0, 0, 0, 0, "0.0", 0, 1, None, None, None, None),
        ]

        batter = conn.execute(
            """
            SELECT dismissal_kind, dismissal_bowler, dismissal_fielders
            FROM player_match_innings_stats
            WHERE innings_number = 2 AND player_name = 'B Batter'
            """
        ).fetchone()
        assert batter == ("stumped", "A Bowler", "B Keeper")

        career = conn.execute(
            """
            SELECT format_group, competition_name, matches, batting_innings,
                   not_outs, runs_scored, highest_score, batting_average,
                   wickets_taken, best_bowling, catches, stumpings
            FROM player_career_stats
            WHERE player_name = 'A Batter' AND competition_name = 'All'
            """
        ).fetchone()
        assert career == ("One Day", "All", 1, 1, 0, 10, 10, 10.0, 0, None, 0, 0)

        innings = conn.execute(
            """
            SELECT opposition, runs_scored, is_not_out, balls_faced, fours, sixes,
                   dismissal_kind
            FROM player_batting_innings_stats
            WHERE player_name = 'A Batter'
            """
        ).fetchone()
        assert innings == ("Beta", 10, 0, 3, 1, 1, "caught")


def _sample_match() -> dict:
    return {
        "info": {
            "balls_per_over": 6,
            "city": "Example City",
            "dates": ["2024-01-02"],
            "gender": "male",
            "event": {
                "name": "Example Series",
                "match_number": 2,
                "stage": "Final",
                "group": "Group A",
                "sub_name": "Example Sub Series",
            },
            "match_type": "ODI",
            "outcome": {"winner": "Alpha", "by": {"runs": 10}},
            "overs": 50,
            "players": {
                "Alpha": ["A Batter", "A Non Striker", "A Bowler"],
                "Beta": ["B Bowler", "B Keeper", "B Batter"],
            },
            "registry": {
                "people": {
                    "A Batter": "a1",
                    "A Non Striker": "a2",
                    "A Bowler": "a3",
                    "B Bowler": "b1",
                    "B Keeper": "b2",
                    "B Batter": "b3",
                }
            },
            "season": "2024",
            "team_type": "international",
            "teams": ["Alpha", "Beta"],
            "toss": {"winner": "Alpha", "decision": "bat"},
            "venue": "Example Ground",
        },
        "innings": [
            {
                "team": "Alpha",
                "overs": [
                    {
                        "over": 0,
                        "deliveries": [
                            _delivery("A Batter", "B Bowler", 4),
                            _delivery("A Batter", "B Bowler", 6),
                            _delivery("A Batter", "B Bowler", 0, wickets=[_wicket("A Batter", "caught", "B Keeper")]),
                            _delivery("A Non Striker", "B Bowler", 0, extras={"wides": 1}, total=1),
                            _delivery("A Non Striker", "B Bowler", 0, extras={"noballs": 1}, total=1),
                            _delivery("A Non Striker", "B Bowler", 0),
                            _delivery("A Non Striker", "B Bowler", 0),
                            _delivery("A Non Striker", "B Bowler", 0),
                        ],
                    }
                ],
            },
            {
                "team": "Beta",
                "overs": [
                    {
                        "over": 0,
                        "deliveries": [
                            _delivery("B Batter", "A Bowler", 0, wickets=[_wicket("B Batter", "stumped", "B Keeper")]),
                        ],
                    }
                ],
            },
        ],
    }


def _delivery(batter, bowler, batter_runs, extras=None, total=None, wickets=None):
    delivery = {
        "batter": batter,
        "bowler": bowler,
        "non_striker": "A Non Striker",
        "runs": {
            "batter": batter_runs,
            "extras": sum((extras or {}).values()),
            "total": batter_runs + sum((extras or {}).values()) if total is None else total,
        },
    }
    if extras:
        delivery["extras"] = extras
    if wickets:
        delivery["wickets"] = wickets
    return delivery


def _wicket(player_out, kind, fielder):
    return {"player_out": player_out, "kind": kind, "fielders": [{"name": fielder}]}
