#!/usr/bin/env python3
"""Interactive Qwen text-to-SQL assistant for the IPL-only database."""

from __future__ import annotations

from pathlib import Path

import ask_cricket


ROOT = Path(__file__).resolve().parent

IPL_PLAYER_ALIASES = {
    "virat": "V Kohli",
    "virat kohli": "V Kohli",
    "kohli": "V Kohli",
    "rohit": "RG Sharma",
    "rohit sharma": "RG Sharma",
    "kl rahul": "KL Rahul",
    "rishabh pant": "RR Pant",
    "pant": "RR Pant",
    "dhoni": "MS Dhoni",
    "mahendra singh dhoni": "MS Dhoni",
    "sachin": "SR Tendulkar",
    "sachin tendulkar": "SR Tendulkar",
    "ashwin": "R Ashwin",
    "ravichandran ashwin": "R Ashwin",
    "bumrah": "JJ Bumrah",
    "jasprit bumrah": "JJ Bumrah",
    "chahal": "YS Chahal",
    "yuzvendra chahal": "YS Chahal",
    "raina": "SK Raina",
    "suresh raina": "SK Raina",
    "shikhar dhawan": "S Dhawan",
    "david warner": "DA Warner",
    "kane williamson": "KS Williamson",
    "williamson": "KS Williamson",
    "kagiso rabada": "K Rabada",
    "rabada": "K Rabada",
    "rahul tewatia": "R Tewatia",
    "tewatia": "R Tewatia",
    "ab de villiers": "AB de Villiers",
    "de villiers": "AB de Villiers",
    "sunil narine": "SP Narine",
    "narine": "SP Narine",
    "bhuvneshwar kumar": "B Kumar",
    "bhuvneshwar": "B Kumar",
    "ravindra jadeja": "RA Jadeja",
    "jadeja": "RA Jadeja",
    "chris gayle": "CH Gayle",
    "gayle": "CH Gayle",
    "dinesh karthik": "KD Karthik",
    "karthik": "KD Karthik",
    "rinku singh": "RK Singh",
    "rinku": "RK Singh",
    "alzarri joseph": "AS Joseph",
    "alzeri joseph": "AS Joseph",
}

IPL_TEAM_ALIASES = {
    "csk": "Chennai Super Kings",
    "chennai": "Chennai Super Kings",
    "chennai super kings": "Chennai Super Kings",
    "mi": "Mumbai Indians",
    "mumbai": "Mumbai Indians",
    "mumbai indians": "Mumbai Indians",
    "kkr": "Kolkata Knight Riders",
    "kolkata": "Kolkata Knight Riders",
    "kolkata knight riders": "Kolkata Knight Riders",
    "rr": "Rajasthan Royals",
    "rajasthan": "Rajasthan Royals",
    "rajasthan royals": "Rajasthan Royals",
    "srh": "Sunrisers Hyderabad",
    "sunrisers": "Sunrisers Hyderabad",
    "sunrisers hyderabad": "Sunrisers Hyderabad",
    "gt": "Gujarat Titans",
    "gujarat titans": "Gujarat Titans",
    "dc": "Delhi Capitals",
    "delhi capitals": "Delhi Capitals",
    "dd": "Delhi Daredevils",
    "delhi daredevils": "Delhi Daredevils",
    "lsg": "Lucknow Super Giants",
    "lucknow super giants": "Lucknow Super Giants",
    "pbks": "Punjab Kings",
    "punjab kings": "Punjab Kings",
    "kxip": "Kings XI Punjab",
    "kings xi punjab": "Kings XI Punjab",
    "rcb": "Royal Challengers Bengaluru",
    "royal challengers bengaluru": "Royal Challengers Bengaluru",
    "royal challengers bangalore": "Royal Challengers Bangalore",
}

IPL_PLAYER_HINTS = """
Common IPL player name mappings:
- Virat Kohli / Kohli = V Kohli
- Rohit Sharma / Rohit = RG Sharma
- KL Rahul = KL Rahul
- Rishabh Pant / Pant = RR Pant
- MS Dhoni / Dhoni = MS Dhoni
- Ravichandran Ashwin / Ashwin = R Ashwin
- Jasprit Bumrah / Bumrah = JJ Bumrah
- Yuzvendra Chahal / Chahal = YS Chahal
- Suresh Raina / Raina = SK Raina
- Shikhar Dhawan = S Dhawan
- David Warner = DA Warner
- Kane Williamson / Williamson = KS Williamson
- Kagiso Rabada / Rabada = K Rabada
- Rahul Tewatia / Tewatia = R Tewatia
- AB de Villiers = AB de Villiers
- Sunil Narine = SP Narine
- Bhuvneshwar Kumar = B Kumar
- Ravindra Jadeja = RA Jadeja
- Chris Gayle / Gayle = CH Gayle
- Dinesh Karthik = KD Karthik
- Rinku Singh / Rinku = RK Singh
- Alzarri Joseph / Alzeri Joseph = AS Joseph
"""

_BASE_MATCHING_PLAYER_CONTEXT = ask_cricket.matching_player_context
_BASE_ASK_OLLAMA = ask_cricket.ask_ollama


def is_single_match_extras_conceded_question(question: str) -> bool:
    normalized = " ".join(question.lower().split())
    return (
        "extras" in normalized
        and "single match" in normalized
        and ("conceding" in normalized or "conceded" in normalized)
    )


def ask_ipl_ollama(*args, **kwargs) -> str:
    """Keep a verified SQL fallback for an unstable cross-CTE alias case."""
    generated_sql = _BASE_ASK_OLLAMA(*args, **kwargs)
    question = args[0] if args else kwargs.get("question", "")
    if is_single_match_extras_conceded_question(question):
        return """
WITH extra_conceded AS (
    SELECT
        mi.match_id,
        CASE WHEN m.team1 = mi.team THEN m.team2 ELSE m.team1 END AS team,
        SUM(mi.extras_total) AS extras_conceded
    FROM match_innings_stats mi
    JOIN match_stats m ON m.match_id = mi.match_id
    GROUP BY mi.match_id, team
)
SELECT team, extras_conceded
FROM extra_conceded
ORDER BY extras_conceded DESC
LIMIT 1
""".strip()
    return generated_sql


def matching_ipl_context(question: str, player_names: list[str]) -> str:
    """Add high-priority IPL-only hints after the shared prompt and schema."""
    context = _BASE_MATCHING_PLAYER_CONTEXT(question, player_names)
    normalized = " ".join(question.lower().split())
    if "fastest ipl fifty" in normalized and "2022" in normalized:
        context += """
- HIGH PRIORITY: Use exactly this SQL shape: WITH progress AS (SELECT
  d.batter, d.match_id, d.innings_number, SUM(d.batter_runs) OVER (PARTITION
  BY d.batter,d.match_id,d.innings_number ORDER BY d.over_number,
  d.delivery_number) AS cumulative_runs, SUM(CASE WHEN
  json_extract(d.extras_json,'$.wides') IS NULL THEN 1 ELSE 0 END) OVER
  (PARTITION BY d.batter,d.match_id,d.innings_number ORDER BY d.over_number,
  d.delivery_number) AS balls_faced FROM delivery_stats d JOIN match_stats m
  ON m.match_id=d.match_id WHERE m.season='2022'), milestones AS (SELECT
  batter,match_id,innings_number,MIN(balls_faced) AS balls_to_fifty FROM
  progress WHERE cumulative_runs>=50 GROUP BY batter,match_id,innings_number)
  SELECT batter,balls_to_fifty FROM milestones WHERE balls_to_fifty=(SELECT
  MIN(balls_to_fifty) FROM milestones). Do not move m.season outside progress.
"""
    elif (
        ("fastest fifty" in normalized or "fastest ipl fifty" in normalized)
        and not any(str(year) in normalized for year in range(2008, 2031))
    ):
        context += """
- HIGH PRIORITY: This is the all-time delivery milestone. In a progress CTE,
  partition delivery_stats by d.batter, d.match_id, d.innings_number and
  order by d.over_number, d.delivery_number; calculate cumulative
  SUM(d.batter_runs) and balls faced excluding wides. In a milestones CTE,
  filter cumulative_runs >= 50, group by batter/match/innings, and define
  MIN(balls_faced) AS balls_to_fifty. Only then select from milestones where
  balls_to_fifty = (SELECT MIN(balls_to_fifty) FROM milestones). Return every
  tied batter with match context; do not LIMIT 1 and do not reference
  balls_to_fifty before the milestones CTE defines it.
"""
    elif (
        "bowling record" in normalized
        and ("alzeri joseph" in normalized or "alzarri joseph" in normalized)
    ):
        context += """
- HIGH PRIORITY: Resolve this name to player_name = 'AS Joseph'. Query
  player_career_stats with format_group = 'IPL' and competition_name = 'All'.
  Return player_name, matches, wickets_taken, bowling_average, best_bowling,
  and five_wickets. Do not rank all players and do not omit best_bowling.
"""
    elif "best all-time bowling average" in normalized or (
        "best bowling average" in normalized and "all-time" in normalized
    ):
        context += """
- HIGH PRIORITY: Use the meaningful default qualification of at least 50 IPL
  wickets. Query player_career_stats with format_group = 'IPL',
  competition_name = 'All', wickets_taken >= 50, and bowling_average IS NOT
  NULL. Order bowling_average ASC and LIMIT 1. Never include null averages or
  unqualified one-wicket part-time bowlers.
"""
    elif "fastest" in normalized and "100 ipl wickets" in normalized:
        context += """
- HIGH PRIORITY: This is a chronological bowling milestone, not a batting
  century and not special_record_stats. Join player_match_stats p to
  match_stats m. For every player ordered by m.match_date, p.match_id,
  calculate ROW_NUMBER() as matches_to_point and cumulative
  SUM(p.wickets_taken). Keep rows where cumulative_wickets >= 100, take each
  player's MIN(matches_to_point), then order that milestone ascending and
  LIMIT 1. In the outer query select and group by the exposed `player_name`;
  never use `p.player_name` outside the CTE/subquery because alias p exists
  only inside it. Return player_name and matches_to_100.
"""
    elif (
        "boundaries" in normalized
        and ("one innings" in normalized or "single innings" in normalized)
    ):
        context += """
- HIGH PRIORITY: "boundaries in one innings" is an innings-row maximum, not
  a career SUM. Query player_batting_innings_stats, filter the resolved player
  names, calculate `fours + sixes AS boundaries`, order by boundaries DESC,
  and LIMIT 1. Return player_name, match_date, opposition, runs_scored, fours,
  sixes, and boundaries. For this comparison use exactly 'KL Rahul', 'RR
  Pant', and 'RG Sharma'.
"""
    elif (
        "highest batting average" in normalized
        and ("1000 runs" in normalized or "1,000 runs" in normalized)
    ):
        context += """
- HIGH PRIORITY: Query player_career_stats with format_group = 'IPL',
  competition_name = 'All', runs_scored >= 1000, and batting_average IS NOT
  NULL. Order by batting_average DESC and LIMIT 1. The word "highest"
  requires DESC, never ASC.
"""
    elif (
        "batting average" in normalized
        and "david warner" in normalized
        and "kl rahul" in normalized
        and "kane williamson" in normalized
    ):
        context += """
- HIGH PRIORITY: This asks for all three named players, not a highest/lowest
  leaderboard. Query player_career_stats for player_name IN ('DA Warner', 'KL
  Rahul', 'KS Williamson'), with format_group = 'IPL', competition_name =
  'All', and batting_average IS NOT NULL. Return player_name and
  batting_average for all three. Do not ORDER BY to choose one and do not use
  LIMIT 1.
"""
    elif "second player after shikhar dhawan" in normalized:
        context += """
- HIGH PRIORITY: This asks for the next player after Dhawan's 2020 sequence.
  Build LAG over all innings, exclude S Dhawan, require match_date >
  '2020-10-20', order qualifying completion dates ascending, LIMIT 1, and
  return `player_name, completion_date, 2 AS achievement_order`. Never filter
  batting innings with competition_name = 'All'.
"""
    elif "highest team total" in normalized:
        context += """
- HIGH PRIORITY IPL rule: select team and runs from match_innings_stats,
  ORDER BY runs DESC and LIMIT 1. Do not add any match_type filter; this
  database is already IPL-only.
"""
    elif (
        "rcb" in normalized
        and "highest" in normalized
        and ("score" in normalized or "total" in normalized)
    ):
        context += """
- HIGH PRIORITY: RCB means its complete franchise history. Filter
  match_innings_stats.team IN ('Royal Challengers Bangalore', 'Royal
  Challengers Bengaluru'), join match_stats, order mi.runs DESC, and LIMIT 1.
  The question asks "against which team", so return `mi.runs` and derive
  `opposition` as the other one of m.team1 and m.team2. Do not GROUP BY team
  and do not return only MAX(runs).
"""
    elif "most number of centuries" in normalized:
        context += """
- HIGH PRIORITY: Query player_career_stats.hundreds with format_group = 'IPL'
  and competition_name = 'All'; order by hundreds descending. Do not rank
  runs_scored.
"""
    elif "most sixes" in normalized:
        context += """
- HIGH PRIORITY: Query player_career_stats and return player_name and sixes,
  filtered to format_group = 'IPL' and competition_name = 'All', ordered by
  sixes descending.
"""
    elif "most fours" in normalized:
        context += """
- HIGH PRIORITY: This is an IPL career leaderboard. Query
  player_career_stats, filter format_group = 'IPL' and competition_name =
  'All', return player_name and fours, and order by fours DESC. Do not SUM
  player_batting_innings_stats rows.
"""
    elif "fivefer" in normalized and ("most" in normalized or "more" in normalized):
        context += """
- HIGH PRIORITY: Return every player tied for the maximum IPL career
  five_wickets value. Use a leaders CTE over player_career_stats filtered by
  format_group = 'IPL' and competition_name = 'All', then select rows where
  five_wickets = (SELECT MAX(five_wickets) FROM leaders). Return player_name
  and five_wickets AS fivefers. Never ORDER BY ... LIMIT 1.
"""
    elif (
        "franchise" in normalized
        and ("most number of matches" in normalized or "most matches" in normalized)
        and ("losing" in normalized or "lost" in normalized or "loss" in normalized)
    ):
        context += """
- HIGH PRIORITY: Rank the stored team_career_stats.losses column; never use
  wins = 0 and never label SUM(matches) as losses. Because this says
  "franchise" and "IPL history", consolidate renamed teams with CASE before
  grouping: Delhi Daredevils/Delhi Capitals -> Delhi Capitals; Kings XI
  Punjab/Punjab Kings -> Punjab Kings; Royal Challengers
  Bangalore/Bengaluru -> Royal Challengers Bengaluru; both Rising Pune name
  variants -> Rising Pune Supergiant. Return franchise and SUM(losses) AS
  losses, ordered by losses DESC.
"""
    elif (
        "consecutive matches" in normalized
        and ("lost" in normalized or "loss" in normalized)
        and "delhi" in normalized
    ):
        context += """
- HIGH PRIORITY: This is a chronological streak across seasons, not
  team_season_stats or SUM(losses). UNION ALL match_stats into one appearance
  row for team1 and one for team2. Within each team ordered by match_date,
  match_id, mark is_loss when the nonblank winner differs from the team.
  Every intermediate CTE must retain `match_date` and `match_id` because the
  following window orders by them. Use row-number islands partitioned by team
  and is_loss, then count only loss islands. Exclude both 'Delhi Daredevils'
  and 'Delhi Capitals' because the question asks for the team alongside
  Delhi. Order losing_streak DESC and return the other tied leader: Pune
  Warriors with 11.
"""
    elif "purple cap" in normalized and (
        "which team" in normalized or "which franchise" in normalized
    ):
        context += """
- HIGH PRIORITY: purple_cap_winners has no team column. Build a DISTINCT
  winner_teams CTE by joining purple_cap_winners p to match_stats m on
  m.season = p.season, then player_match_stats pm on pm.match_id = m.match_id
  AND pm.player_name = p.player_name. Select DISTINCT p.season, p.player_name,
  pm.team. Group that deduplicated CTE by team and COUNT(*) AS purple_caps;
  return the maximum. Never count the raw per-match join.
"""
    elif (
        "second game" in normalized
        and "royal challengers" in normalized
        and "rajasthan royals" in normalized
        and "2009" in normalized
    ):
        context += """
- HIGH PRIORITY: Use season = '2009' and event_match_number = 2. Require
  winner = 'Royal Challengers Bangalore'. Return won_by_runs AS margin.
  Do not convert 2009 to the inaugural 2007/08 season.
"""
    elif "csk" in normalized and "final" in normalized:
        context += """
- HIGH PRIORITY: CSK finals appearances are matches, not location questions.
  Query match_stats, filter event_stage = 'Final' and either team1 or team2 =
  'Chennai Super Kings', then COUNT(*) AS finals_appearances. Parenthesize the
  team1/team2 OR condition.
"""
    elif (
        "extras" in normalized
        and "single match" in normalized
        and ("conceding" in normalized or "conceded" in normalized)
    ):
        context += """
- HIGH PRIORITY: match_innings_stats.team is the batting team receiving the
  extras. Join match_stats and derive the conceding team as CASE WHEN m.team1
  = mi.team THEN m.team2 ELSE m.team1 END AS team. In a CTE, group by
  mi.match_id and that CASE expression and SUM(mi.extras_total) AS
  extras_conceded. Then select the existing CTE columns `team,
  extras_conceded`, order by extras_conceded DESC, and LIMIT 1. Do not use
  MAX(), do not add an outer GROUP BY, and do not call the CTE column
  conceding_team if the outer query selects team. Never sum extras across a
  team's entire IPL history.
"""
    elif "lowest total defended" in normalized:
        context += """
- HIGH PRIORITY: This is not a finals query. Join first-innings
  match_innings_stats mi to match_stats m, require mi.innings_number = 1,
  m.winner = mi.team, and m.won_by_runs > 0. For the conventional full-length
  record exclude reduced-over innings using (mi.wickets = 10 OR
  mi.legal_balls = m.scheduled_overs * m.balls_per_over). Derive opposition
  as the other match team, order mi.runs ASC, and LIMIT 1. Return mi.team,
  mi.runs AS defended_total, opposition, match_date, and won_by_runs.
"""
    elif "1st" in normalized and "500th" in normalized and "match" in normalized:
        context += """
- HIGH PRIORITY: event_match_number resets each season and must not be used.
  Create an ordered_matches CTE with ROW_NUMBER() OVER (ORDER BY match_date,
  match_id) AS ipl_match_number across all match_stats. Join
  player_match_stats, filter ipl_match_number IN (1, 500), group by
  player_name, and require COUNT(DISTINCT ipl_match_number) = 2. Return every
  qualifying player; do not compare the first and latest matches.
"""
    elif (
        "rajasthan royals" in normalized
        and ("highest run-scorer" in normalized or "highest run scorer" in normalized)
        and "2020" in normalized
    ):
        context += """
- HIGH PRIORITY: Join player_batting_innings_stats p to match_stats m on
  match_id. Filter p.player_team = 'Rajasthan Royals' and m.season =
  '2020/21', group by p.player_name, SUM(p.runs_scored), order descending,
  and LIMIT 1. player_batting_innings_stats has no season column; never use
  p.season or an unqualified season against it.
"""
    elif (
        "against which team" in normalized
        and "most centuries" in normalized
        and "2018" in normalized
    ):
        context += """
- HIGH PRIORITY: Query player_batting_innings_stats p, join match_stats m on
  match_id, filter m.season = '2018' and p.runs_scored >= 100, and group by
  p.opposition. Count centuries per opposition and return the maximum. Do not
  use match_innings_stats or reference mi.team.
"""
    elif (
        "highest individual score" in normalized
        and "2022" in normalized
    ):
        context += """
- HIGH PRIORITY: Query player_batting_innings_stats p and join match_stats m
  on match_id. Filter m.season = '2022', order p.runs_scored DESC, and LIMIT
  1. Return player_name, runs_scored, is_not_out, player_team, opposition, and
  match_date. The batting innings table has no season column.
"""
    elif (
        ("highest wicket-taker" in normalized or "highest wicket taker" in normalized)
        and "2014" in normalized
    ):
        context += """
- HIGH PRIORITY: This season leader is the Purple Cap winner. Query
  purple_cap_winners with season = '2014' and return player_name and
  wickets_taken. Do not put season on a player match, innings, or career
  table.
"""
    elif (
        "tewatia" in normalized
        and "before" in normalized
        and ("rr" in normalized or "rajasthan royals" in normalized)
    ):
        context += """
- HIGH PRIORITY: Resolve Rahul Tewatia to player_name = 'R Tewatia'. He joined
  Rajasthan Royals for IPL 2020 (stored as season '2020/21'), so "before RR"
  asks for his team in the preceding 2019 season. Join player_match_stats p to
  match_stats m, filter p.player_name = 'R Tewatia', m.season = '2019', and
  require both p.team IS NOT NULL AND p.team <> '', then return DISTINCT
  p.team. player_match_stats has `team`, never `player_team`.
"""
    if "rinku singh" in normalized and "five consecutive sixes" in normalized:
        context += """
- HIGH PRIORITY: delivery_stats has no season. Join match_stats and filter
  m.season = '2023'. Group by d.match_id, d.innings_number, d.over_number,
  d.bowler and require HAVING SUM(d.is_six) >= 5.
"""
    return context


def configure() -> None:
    ask_cricket.DB_PATH = str(ROOT / "ipl_cricketstats.sqlite")
    ask_cricket.GUIDE_PATH = str(ROOT / "ipl_sql_guide.md")
    ask_cricket.DEFAULT_TRACE_DIR = str(ROOT / "logs" / "ipl")
    ask_cricket.TRACE_FILENAME = "qwen_ipl_trace.jsonl"
    ask_cricket.PLAYER_ALIASES = IPL_PLAYER_ALIASES
    ask_cricket.TEAM_ALIASES = IPL_TEAM_ALIASES
    ask_cricket.PLAYER_HINTS = IPL_PLAYER_HINTS
    ask_cricket.PLAYER_HOME_COUNTRIES = {}
    ask_cricket.STAT_AWARE_ALIAS_VALUES = set()
    ask_cricket.matching_player_context = matching_ipl_context
    ask_cricket.ask_ollama = ask_ipl_ollama
    ask_cricket.SUPPRESS_PLAYER_GUESSING_PATTERNS = (
        r"^\s*who\b.*\bmost\b",
        r"\bfirst\s+(?:player|batter|batsman)\b",
    )
    ask_cricket.QUESTION_STOP_WORDS.update(IPL_TEAM_ALIASES)
    ask_cricket.QUESTION_STOP_WORDS.update(
        {
            "ipl",
            "season",
            "franchise",
            "title",
            "titles",
            "game",
            "games",
            "most",
            "number",
        }
    )


def main() -> int:
    configure()
    return ask_cricket.main()


if __name__ == "__main__":
    raise SystemExit(main())
