#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.request
import uuid
from difflib import SequenceMatcher, get_close_matches
from typing import Any


DB_PATH = "/Users/rkk/CricketStats/cricketstats.sqlite"
GUIDE_PATH = "/Users/rkk/CricketStats/cricket_sql_guide.md"
DEFAULT_TRACE_DIR = "/Users/rkk/CricketStats/logs"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5-coder:14b"
TRACE_FILENAME = "qwen_trace.jsonl"
SUPPRESS_PLAYER_GUESSING_PATTERNS: tuple[str, ...] = ()


PLAYER_HINTS = """
Common player name mappings:
- Sunil Gavaskar = SM Gavaskar
- Gavaskar = SM Gavaskar
- Don Bradman = DG Bradman
- Bradman = DG Bradman
- Sachin Tendulkar = SR Tendulkar
- Tendulkar = SR Tendulkar
- Brian Lara = BC Lara
- Lara = BC Lara
- Geoff Boycott = G Boycott
- Boycott = G Boycott
- Gundappa Viswanath = GR Viswanath
- Gundappa Vishwanath = GR Viswanath
- Viswanath = GR Viswanath
- Vishwanath = GR Viswanath
- Lala Amarnath = L Amarnath
- Amarnath = L Amarnath when the question clearly refers to Lala Amarnath
- Surinder Amarnath = S Amarnath
- Dennis Lillee bowling/career bowling = Lillee
- Kapil Dev = Kapil Dev
- Kapildev = Kapil Dev
- Muttiah Muralitharan = M Muralitharan
- Muttiah Muralidharan = M Muralitharan
- Muralitharan = M Muralitharan
- Muralidharan = M Muralitharan
"""

PLAYER_ALIASES = {
    "gavaskar": "SM Gavaskar",
    "sunil gavaskar": "SM Gavaskar",
    "bradman": "DG Bradman",
    "don bradman": "DG Bradman",
    "tendulkar": "SR Tendulkar",
    "sachin tendulkar": "SR Tendulkar",
    "lara": "BC Lara",
    "brian lara": "BC Lara",
    "boycott": "G Boycott",
    "geoff boycott": "G Boycott",
    "viswanath": "GR Viswanath",
    "vishwanath": "GR Viswanath",
    "gundappa viswanath": "GR Viswanath",
    "gundappa vishwanath": "GR Viswanath",
    "lala amarnath": "L Amarnath",
    "surinder amarnath": "S Amarnath",
    "dennis lillee": "Lillee",
    "kapil dev": "Kapil Dev",
    "kapildev": "Kapil Dev",
    "muttiah muralitharan": "M Muralitharan",
    "muttiah muralidharan": "M Muralitharan",
    "muralitharan": "M Muralitharan",
    "muralidharan": "M Muralitharan",
}

PLAYER_HOME_COUNTRIES = {
    "DG Bradman": "Australia",
    "SM Gavaskar": "India",
}

TEAM_ALIASES = {
    "afghan": "Afghanistan",
    "afghanistan": "Afghanistan",
    "australian": "Australia",
    "australia": "Australia",
    "bangladeshi": "Bangladesh",
    "bangladesh": "Bangladesh",
    "english": "England",
    "england": "England",
    "indian": "India",
    "india": "India",
    "irish": "Ireland",
    "ireland": "Ireland",
    "new zealand": "New Zealand",
    "new zealander": "New Zealand",
    "pakistani": "Pakistan",
    "pakistan": "Pakistan",
    "south african": "South Africa",
    "south africa": "South Africa",
    "sri lankan": "Sri Lanka",
    "sri lanka": "Sri Lanka",
    "west indian": "West Indies",
    "west indies": "West Indies",
    "zimbabwean": "Zimbabwe",
    "zimbabwe": "Zimbabwe",
}

STAT_AWARE_ALIAS_VALUES = {
    "SM Gavaskar",
}

QUESTION_STOP_WORDS = {
    "against",
    "average",
    "any",
    "best",
    "career",
    "catch",
    "catches",
    "compare",
    "debut",
    "did",
    "each",
    "first",
    "for",
    "fours",
    "fielding",
    "has",
    "her",
    "him",
    "his",
    "how",
    "inning",
    "innings",
    "make",
    "many",
    "match",
    "matches",
    "more",
    "player",
    "players",
    "play",
    "played",
    "playing",
    "runs",
    "score",
    "scored",
    "stats",
    "take",
    "taken",
    "test",
    "tests",
    "that",
    "the",
    "what",
    "when",
    "where",
    "which",
    "wickets",
    "year",
    *TEAM_ALIASES.keys(),
}


def get_schema() -> str:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return "\n\n".join(sql for _name, sql in rows if sql)


def get_player_names() -> list[str]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT player_name
            FROM player_match_stats
            WHERE player_name IS NOT NULL
            UNION
            SELECT DISTINCT player_name
            FROM player_batting_innings_stats
            WHERE player_name IS NOT NULL
            UNION
            SELECT DISTINCT player_name
            FROM player_career_stats
            WHERE player_name IS NOT NULL
            ORDER BY player_name
            """
        ).fetchall()
    return [row[0] for row in rows]


def get_guide() -> str:
    try:
        with open(GUIDE_PATH, "r", encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""


def ask_ollama(
    question: str,
    schema: str,
    guide: str,
    player_names: list[str],
    history: list[dict[str, Any]],
    trace: dict[str, Any] | None = None,
) -> str:
    player_context = matching_player_context(question, player_names)
    session_context = format_session_history(history)
    prompt = f"""
You are a SQLite expert for a cricket statistics database.

Return ONLY one SQLite SELECT query.
Do not use markdown.
Do not explain the query.
Do not modify data.
Use only columns that exist in the SQLite schema below.
Before writing the final SQL, first resolve the user's player wording to a database player_name.
Use the resolved player_name in the final query with exact equality whenever Extra context provides one.
Do not query with the user's raw full name if the database uses an abbreviation, initials, or surname-only row.
Never invent or expand player_name values. Use only exact database names provided in Extra context, such as 'M Vijay', not guessed names like 'Murali V Vijay'.
For player team filters:
- player_batting_innings_stats uses player_team.
- player_match_stats and player_match_innings_stats use team.
Never use player_team with player_match_stats or player_match_innings_stats; use p.team in SELECT, CASE, WHERE, and joins.
For highest team innings totals, use match_innings_stats joined to match_stats. match_innings_stats does not have match_type; filter Tests with m.match_type = 'Test' from match_stats. Use match_innings_stats.runs as the team innings total.
When a highest team innings question names a team, the final SQL MUST filter match_innings_stats.team to that team. For "India's highest total in a Test innings", include mi.team = 'India'; do not return the overall Test innings record.
For "which team has won the most Test matches", use match_stats.winner, exclude NULL and blank winner values before grouping, then order by COUNT(*) descending. A NULL winner is not a team and MUST NOT be included.
For "did PLAYER play a Test in COUNTRY" or "played in COUNTRY", the country is a match location, not the player's team. Use player_match_stats joined to match_stats and filter match_stats.city or match_stats.venue for locations. Never use p.player_team for location questions.
For "visiting batsman/player in COUNTRY", the country is match location and "visiting" means exclude players whose team is that country. For player_batting_innings_stats, filter location using match_stats.city/venue and add p.player_team <> COUNTRY.
For "overseas" or "abroad" Test hundreds/centuries for PLAYER, use player_batting_innings_stats joined to match_stats, filter runs_scored >= 100, and exclude matches played in that specific player's home country. Do not always exclude India. For Indian players such as Gavaskar, overseas/abroad means NOT played in India. For Australian players such as Bradman, overseas/abroad means NOT played in Australia. Use the matching home-country city/venue predicate.
For Tests played in India, use Indian host cities/old names from match_stats.city or match_stats.venue, such as Bombay, Mumbai, Calcutta, Kolkata, Madras, Chennai, Delhi, Kanpur, Bangalore, Bengaluru, Hyderabad, Ahmedabad, Nagpur, Mohali, Chandigarh, Pune, Ranchi, Rajkot, Indore, Lucknow, Dharamsala, Cuttack, Guwahati, Jaipur, Jamshedpur, and Visakhapatnam.
For Tests played in Australia, use Australian host cities from match_stats.city or match_stats.venue, such as Sydney, Melbourne, Adelaide, Perth, Brisbane, Hobart, Canberra, Darwin, Cairns, and Gold Coast.
For yes/no "did PLAYER play any Test in COUNTRY" questions, return COUNT(*) AS tests_in_country without GROUP BY so zero matches returns 0 instead of no rows.
Use LIMIT 50 unless the user asks for all rows.
For a player's Test batting average, use player_career_stats.batting_average with format_group = 'Test' and competition_name = 'All'.
Do not calculate batting average as AVG(runs_scored / balls_faced); that is not batting average.
For "how many Test hundreds/centuries did PLAYER score", SELECT player_career_stats.hundreds with format_group = 'Test' and competition_name = 'All', then ORDER BY runs_scored DESC, batting_innings DESC before LIMIT 1. Never use COUNT(*) on player_career_stats for hundreds; COUNT(*) counts career rows, not hundreds.
For "how many Test hundreds/centuries did PLAYER score against TEAM", use player_batting_innings_stats, filter format_group = 'Test', opposition = TEAM, and runs_scored >= 100. Do not use player_team != TEAM; that does not filter the opposition.
For "which COUNTRY player has scored the most/more double centuries", use player_batting_innings_stats, filter format_group = 'Test', player_team = 'COUNTRY', and runs_scored >= 200; GROUP BY player_name, count the qualifying innings, order by that count descending, and LIMIT 1. A double-century is an individual innings of 200 or more. NEVER use player_career_stats.hundreds because hundreds includes scores from 100 to 199 as well. Do not resolve a generic phrase such as "Indian player" to one player_name.
For "which player has scored the most/more triple hundreds/centuries in Test cricket", search ALL players in player_batting_innings_stats with format_group = 'Test' and runs_scored >= 300. Group by player_name and count qualifying innings. Do not add a player_name filter and do not use fuzzy player candidates. Return every player tied for the maximum count, using a grouped CTE and filtering to MAX(triple_hundreds); do not use LIMIT 1 when the lead is tied.
For "most/more consecutive Test hundreds/centuries", build the streak over ALL Test batting innings first. Do not put runs_scored >= 100 in the first CTE before ROW_NUMBER(); that removes non-hundred innings and turns total career hundreds into a fake streak. Create is_hundred = CASE WHEN runs_scored >= 100 THEN 1 ELSE 0 END, compute row-number islands partitioned by player_name and is_hundred over all Test innings ordered by match_date, match_id, innings_number, then filter is_hundred = 1 and count each streak.
For "runs scored by PLAYER when he scored centuries in each innings of a Test match", first filter that player's Test innings to runs_scored >= 100, group by player_name and match_id to find matches with COUNT(*) >= 2, then return the matching innings rows ordered by match_date and innings_number. Do not GROUP BY innings_number, and do not SUM runs unless the user asks for a total.
For "how many times did PLAYER score centuries in each innings of a Test match", count the qualifying matches after grouping by player_name and match_id with HAVING COUNT(*) >= 2. Return one scalar count. Do not return COUNT(*) grouped by match_id, because that returns 2 for each qualifying match.
For batting career stats from player_career_stats, if duplicate rows match the player, prefer the row with batting data: ORDER BY runs_scored DESC, batting_innings DESC before LIMIT 1.
For "how many catches did PLAYER take", use player_career_stats.catches with format_group = 'Test' and competition_name = 'All' unless another format is specified. Do not use SUM(catches) from player_match_stats for career catch totals. For fielding/catches career stats, prefer the career row with catches > 0 and ORDER BY catches DESC, matches DESC before LIMIT 1.
For "which COUNTRY player has taken the most catches", rank player_career_stats.catches with format_group = 'Test' and competition_name = 'All', and restrict players to that national team with EXISTS (SELECT 1 FROM player_match_stats pm WHERE pm.player_name = player_career_stats.player_name AND pm.team = 'COUNTRY'). player_career_stats has no player_team or team column. NEVER use player_team with player_career_stats or player_match_stats. Order by catches DESC, matches DESC and LIMIT 1.
For career stumpings, select player_career_stats.stumpings directly with format_group = 'Test' and competition_name = 'All' unless another format is specified. Never use SUM(stumpings) or COUNT(*) for a stored career stumpings total.
For a player's bowling record or career bowling stats, use player_career_stats with format_group = 'Test' and competition_name = 'All' unless the user names another format.
For "how many wickets has PLAYER taken" or "how many wickets did PLAYER take", SELECT player_career_stats.wickets_taken AS total_wickets with format_group = 'Test' and competition_name = 'All' unless the user names another format. Never use COUNT(*) for career wicket totals; COUNT(*) counts career rows and returns 1. Do not use SUM(wickets_taken) from player_match_stats for career totals.
For a player's Test bowling average, use player_career_stats.bowling_average with format_group = 'Test' and competition_name = 'All'.
For bowling career stats, prefer the career row with wickets_taken > 0; some bowlers have an initialed name row with 0 wickets and a surname-only bowling row.
For full-name wicket or bowling questions, do not stop at the initial-plus-surname candidate if a surname-only Test career row has more wickets. For example, "Richard Hadlee" should resolve to the bowling row with the highest Test wickets for Hadlee, not automatically to 'RJ Hadlee'.
For bowling record, bowling average, wickets, best bowling, and five-wicket career questions, the final SQL MUST include AND wickets_taken > 0 when using player_career_stats, and MUST use ORDER BY wickets_taken DESC, matches DESC before LIMIT 1. Never ORDER BY runs_scored or batting_innings for a bowling question.
Even when there is an exact resolved player_name for a bowling/wicket career question, keep ORDER BY wickets_taken DESC, matches DESC before LIMIT 1 so duplicate or split career rows choose the bowling row.
For "has PLAYER taken any Test wicket" or "did PLAYER take any Test wickets", SELECT player_career_stats.wickets_taken AS test_wickets_taken with format_group = 'Test' and competition_name = 'All'. Never use COUNT(*) for these questions; COUNT(*) counts rows, not wickets, even on player_career_stats.
The terms "fivefer", "fivefers", "fifer", "fifers", "fiver", "fivers", "five-for", "five-fors", "five-wicket haul", and "5 wickets per innings" all mean an innings-level five-wicket haul. Count qualifying rows from player_match_innings_stats joined to match_stats, with wickets_taken >= 5 and m.match_type = 'Test' unless another format is specified. NEVER use player_match_stats for fivefers/fivers: its wickets_taken value is the combined match total, so it can count a match without a five-wicket innings and can collapse two five-wicket hauls in one match into one.
For "who has taken all 10 wickets in a Test match innings" or "10 wickets in an innings", use player_match_innings_stats joined to match_stats and filter p.wickets_taken >= 10. In this query p.player_name is the bowler. Do not use dismissal_bowler or GROUP BY dismissal_bowler.
Never use player_batting_innings_stats for wickets or bowling questions.
For "wickets did PLAYER take by lbw/bowled/caught/etc.", count rows in player_match_innings_stats where dismissal_bowler = PLAYER_NAME and dismissal_kind matches the dismissal type. Join match_stats and include m.match_type = 'Test' unless another format is specified. Do not use player_name for the bowler in dismissal-type wicket questions; player_name is the dismissed batter.
For "which bowler has taken the wicket of PLAYER the most" or "who dismissed PLAYER most", the named player is the dismissed batter. Use player_match_innings_stats where player_name = BATTER_NAME, join match_stats for Tests, exclude blank/null dismissal_bowler, group by dismissal_bowler, and order by COUNT(*) DESC. Do not use wickets_taken for this question.
Dismissed-batter questions must resolve the named player as a batter, not as a bowling or fielding row. For "wicket of Gavaskar" or "who dismissed Gavaskar", use player_name = 'SM Gavaskar', not player_name = 'Gavaskar'.
When the user gives a player's common name, use the mapping above when available, except bowling/wicket or fielding/catches questions where stat-aware Test career context resolves a different row.
If Extra context inferred from the question says "Use player_name = '...'", you MUST use that exact equality predicate.
Do not replace an inferred exact player_name with a LIKE predicate.
Never use every "Possible database player_name match" in an IN list. If there is a resolved exact/stat-aware player_name, use only that one name.
When resolving a full player name, prefer an exact full-name database match first.
If the full name is not found, try the first character of the first name plus the last name, for example player_name = 'L Amarnath'.
If that is not found, search by the distinctive last name.
For Test questions, resolve names only to players who have Test rows when possible; avoid domestic-only players when a Test player also matches the name.
If the exact database player_name is uncertain, use a case-insensitive LIKE match, for example:
lower(player_name) LIKE lower('%Gavaskar%').
For common full names that may not match the database abbreviation, do not search for the full common name.
Search for the known database alias when available, or use a distinctive surname/key token like '%Amarnath%'.
For first/earliest occurrence questions, do not use MIN(match_date) with non-aggregated columns.
Instead filter to the event rows, ORDER BY match_date ASC, match_id ASC, innings_number ASC, and LIMIT 1.
For "first Indian player to score a hundred/century in a Test match", use player_batting_innings_stats
where format_group = 'Test', player_team = 'India', and runs_scored >= 100, then order by date and innings.
For "first match", find the earliest match_date for that player and return all innings in that match, plus the match total if asked for runs.

{PLAYER_HINTS}

Cricket SQL guide:
{guide}

SQLite schema:
{schema}

User question:
{question}

Extra context inferred from the question:
{player_context}

Recent session memory:
{session_context}
"""
    if trace is not None:
        trace["player_context"] = player_context
        trace["session_context"] = session_context
        trace["prompt"] = prompt
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
        },
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    if trace is not None:
        trace["ollama_elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        trace["ollama_response"] = data
    return data["response"].strip()


def matching_player_context(question: str, player_names: list[str]) -> str:
    lower_question = question.lower()
    matches = []
    for alias, player_name in PLAYER_ALIASES.items():
        if alias not in lower_question:
            continue
        home_country = PLAYER_HOME_COUNTRIES.get(player_name)
        if is_dismissed_batter_question(lower_question):
            matches.append(
                f"- Use player_name = '{player_name}' for '{alias}'. In this question that name is the dismissed batter, not the bowler; use equality, not LIKE."
            )
        elif (
            is_bowling_question(lower_question) or is_fielding_question(lower_question)
        ) and player_name in STAT_AWARE_ALIAS_VALUES:
            matches.append(
                f"- Common alias candidate for '{alias}': player_name = '{player_name}'. "
                "For bowling/wicket or fielding/catches questions, use this only if stat-aware Test career context does not resolve a better row for the requested statistic."
            )
        else:
            matches.append(
                f"- Use player_name = '{player_name}' for '{alias}'. This is an exact database name; use equality, not LIKE."
            )
        if home_country and is_overseas_or_abroad_question(lower_question):
            matches.append(
                f"- Home country for player_name = '{player_name}' is {home_country}. For overseas/abroad questions, exclude matches played in {home_country}, not India unless the player's home country is India."
            )
    team_matches = matching_team_context(lower_question)
    if team_matches:
        matches.extend(team_matches)
    exact_matches = exact_full_name_matches(question, player_names)
    if exact_matches:
        matches.extend(
            f"- Exact full-name database match: use player_name = '{name}'. Prefer this over initial-plus-last-name."
            for name in exact_matches
        )
    initial_matches = initial_surname_matches(question, player_names)
    if initial_matches:
        if exact_matches:
            matches.extend(
                f"- Initial-plus-last-name fallback candidate: use player_name = '{name}' only if no exact full-name database match exists."
                for name in initial_matches
            )
        else:
            matches.extend(
                f"- Resolved initial-plus-last-name database player_name: use player_name = '{name}'. No exact full-name database match was found; use equality, not a guessed expanded name."
                for name in initial_matches
            )
    generic_player_subject_question = bool(
        re.search(
            r"^\s*(?:which|what)\s+(?:[a-z]+\s+){0,2}player\b",
            lower_question,
        )
    ) or any(
        re.search(pattern, lower_question)
        for pattern in SUPPRESS_PLAYER_GUESSING_PATTERNS
    )
    generic_team_player_question = bool(team_matches) and any(
        term in lower_question for term in ("player", "batsman", "batter", "bowler")
    )
    suppress_player_guessing = (
        generic_player_subject_question or generic_team_player_question
    )
    fuzzy_matches = (
        []
        if suppress_player_guessing
        else fuzzy_player_matches(question, player_names)
    )
    if fuzzy_matches:
        matches.append(
            "- Possible database player_name matches: "
            + ", ".join(f"'{name}'" for name in fuzzy_matches)
        )
    phrase_matches = (
        []
        if is_dismissed_batter_question(lower_question)
        or suppress_player_guessing
        else career_name_matches_by_phrase(question)
    )
    if phrase_matches:
        for phrase, player_name in phrase_matches:
            matches.append(
                f"- Resolved database player_name for '{phrase}': use player_name = '{player_name}'. Use this exact name for innings and career queries."
            )
    test_matches = test_career_name_matches(question)
    if test_matches and not is_dismissed_batter_question(lower_question):
        per_token_matches = test_career_name_matches_by_token(question)
        if len(per_token_matches) >= 2 or any(" " in token for token, _name in per_token_matches):
            for token, player_name in per_token_matches:
                matches.append(
                    f"- Resolved stat-aware Test player_name for '{token}': use player_name = '{player_name}'. Use this exact name for that compared player."
                )
            if len(per_token_matches) >= 2:
                matches.append(
                    "- For comparison questions with multiple resolved player_name values, include each resolved name in the final query."
                )
        else:
            matches.append(
                f"- Resolved stat-aware Test player_name: use player_name = '{test_matches[0]}'. This is the best match for the requested statistic; use equality, not IN."
            )
            if is_bowling_question(lower_question) or is_fielding_question(lower_question):
                matches.append(
                    "- For this stat-specific question, the stat-aware Test player_name overrides any common batting alias candidate."
                )
        matches.append(
            "- Stat-aware Test career player_name matches, preferred for this Test question: "
            + ", ".join(f"'{name}'" for name in test_matches)
        )
    if not matches and suppress_player_guessing:
        return (
            "- This is a ranking across all qualifying players. Do not infer, "
            "resolve, or add any player_name filter."
        )
    if not matches:
        return "- No exact player alias inferred. Use lower(player_name) LIKE lower('%name%') if needed."
    return "\n".join(matches)


def matching_team_context(lower_question: str) -> list[str]:
    matches = []
    for alias, team in sorted(TEAM_ALIASES.items(), key=lambda item: -len(item[0])):
        if alias in lower_question:
            if re.search(rf"\b(in|at)\s+{re.escape(alias)}\b", lower_question):
                matches.append(
                    f"- The phrase 'in {alias}' refers to match location. Use match_stats.city or "
                    f"match_stats.venue for locations in {team}; do not use player_team or p.team as the location filter."
                )
                break
            if re.search(rf"\bagainst\s+{re.escape(alias)}\b", lower_question):
                matches.append(
                    f"- The phrase 'against {alias}' refers to opposition. Use opposition = '{team}' "
                    "on batting innings/group tables, or derive opposition from match_stats teams for match tables. "
                    "Do not use player_team != that team."
                )
                break
            matches.append(
                f"- The phrase '{alias}' refers to team/country. Use player_team = '{team}' "
                "for player nationality/team filters, not player_name."
            )
            break
    return matches


def exact_full_name_matches(question: str, player_names: list[str], limit: int = 5) -> list[str]:
    words = [
        word
        for word in re.findall(r"[A-Za-z']+", question)
        if len(word) >= 2 and word.lower() not in QUESTION_STOP_WORDS
    ]
    if len(words) < 2:
        return []

    normalized_names = {normalize_name(name): name for name in player_names}
    matches: list[str] = []
    for start in range(len(words) - 1):
        for end in range(len(words), start + 1, -1):
            phrase = " ".join(words[start:end])
            match = normalized_names.get(normalize_name(phrase))
            if match and match not in matches:
                matches.append(match)
            if len(matches) >= limit:
                return matches
    return matches


def initial_surname_matches(question: str, player_names: list[str], limit: int = 5) -> list[str]:
    words = [
        word
        for word in re.findall(r"[A-Za-z']+", question)
        if len(word) >= 2 and word.lower() not in QUESTION_STOP_WORDS
    ]
    if len(words) < 2:
        return []

    player_name_set = set(player_names)
    matches: list[str] = []
    for first, last in zip(words, words[1:]):
        candidate = f"{first[0].upper()} {last.title()}"
        if candidate in player_name_set and candidate not in matches:
            matches.append(candidate)
        if len(matches) >= limit:
            break
    return matches


def test_career_name_matches(question: str, limit: int = 8) -> list[str]:
    lower_question = question.lower()
    if not is_test_context(lower_question):
        return []
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z']+", question)
        if len(word) >= 4 and word.lower() not in QUESTION_STOP_WORDS
    ]
    if not words:
        return []
    clauses = " OR ".join("lower(player_name) LIKE ?" for _word in words)
    params = [f"%{word}%" for word in words]
    if is_bowling_question(lower_question):
        order_by = """
            CASE WHEN wickets_taken > 0 THEN 0 ELSE 1 END,
            wickets_taken DESC,
            matches DESC,
            player_name ASC
        """
    elif is_fielding_question(lower_question):
        order_by = """
            CASE WHEN catches > 0 THEN 0 ELSE 1 END,
            catches DESC,
            matches DESC,
            player_name ASC
        """
    elif any(word in lower_question for word in ("batting", "runs", "hundred", "century", "fifties")):
        order_by = """
            CASE WHEN batting_innings > 0 OR runs_scored > 0 THEN 0 ELSE 1 END,
            runs_scored DESC,
            batting_innings DESC,
            matches DESC,
            player_name ASC
        """
    else:
        order_by = """
            matches DESC,
            runs_scored DESC,
            wickets_taken DESC,
            player_name ASC
        """
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            f"""
            SELECT player_name, matches, batting_innings, runs_scored, wickets_taken
            FROM player_career_stats
            WHERE format_group = 'Test'
              AND competition_name = 'All'
              AND ({clauses})
            ORDER BY {order_by}
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return [row[0] for row in rows]


def career_name_matches_by_phrase(question: str) -> list[tuple[str, str]]:
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z']+", question)
        if len(word) >= 4 and word.lower() not in QUESTION_STOP_WORDS
    ]
    output: list[tuple[str, str]] = []
    for start in range(len(words) - 1):
        phrase = " ".join(words[start : start + 2])
        matches = test_career_name_matches_for_phrase(phrase, question.lower())
        if matches:
            output.append((phrase, matches[0]))
    return output


def test_career_name_matches_by_token(question: str) -> list[tuple[str, str]]:
    lower_question = question.lower()
    if not is_test_context(lower_question):
        return []
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z']+", question)
        if len(word) >= 4 and word.lower() not in QUESTION_STOP_WORDS
    ]
    output: list[tuple[str, str]] = []
    used_word_indexes: set[int] = set()
    for start in range(len(words) - 1):
        phrase = " ".join(words[start : start + 2])
        matches = test_career_name_matches_for_phrase(phrase, lower_question)
        if matches:
            best = matches[0]
            output.append((phrase, best))
            used_word_indexes.update({start, start + 1})

    for word in words:
        word_index = words.index(word)
        if word_index in used_word_indexes:
            continue
        matches = test_career_name_matches_for_word(word, lower_question)
        if matches:
            best = matches[0]
            if (word, best) not in output:
                output.append((word, best))
    return output


def test_career_name_matches_for_phrase(
    phrase: str, lower_question: str, limit: int = 4
) -> list[str]:
    terms = phrase.split()
    if not terms:
        return []
    clauses = " AND ".join("lower(player_name) LIKE ?" for _term in terms)
    params = [f"%{term}%" for term in terms]
    if len(terms) >= 2:
        first_initial = terms[0][0]
        surname = terms[-1]
        clauses = (
            f"(({clauses}) OR "
            "(lower(player_name) LIKE ? AND lower(player_name) LIKE ?)"
        )
        params.extend([f"{first_initial}%", f"% {surname}"])
        if is_bowling_question(lower_question) or is_fielding_question(lower_question):
            clauses += " OR lower(player_name) = ?"
            params.append(surname)
        clauses += ")"
    order_by = stat_aware_test_order_by(lower_question)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            f"""
            SELECT player_name
            FROM player_career_stats
            WHERE format_group = 'Test'
              AND competition_name = 'All'
              AND {clauses}
            ORDER BY {order_by}
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return [row[0] for row in rows]


def test_career_name_matches_for_word(word: str, lower_question: str, limit: int = 4) -> list[str]:
    order_by = stat_aware_test_order_by(lower_question)
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            f"""
            SELECT player_name
            FROM player_career_stats
            WHERE format_group = 'Test'
              AND competition_name = 'All'
              AND lower(player_name) LIKE ?
            ORDER BY {order_by}
            LIMIT ?
            """,
            (f"%{word}%", limit),
        ).fetchall()
    return [row[0] for row in rows]


def stat_aware_test_order_by(lower_question: str) -> str:
    if is_bowling_question(lower_question):
        return """
            CASE WHEN wickets_taken > 0 THEN 0 ELSE 1 END,
            wickets_taken DESC,
            matches DESC,
            player_name ASC
        """
    if is_fielding_question(lower_question):
        return """
            CASE WHEN catches > 0 THEN 0 ELSE 1 END,
            catches DESC,
            matches DESC,
            player_name ASC
        """
    if any(term in lower_question for term in ("batting", "runs", "hundred", "hundreds", "century", "centuries", "fifties")):
        return """
            CASE WHEN batting_innings > 0 OR runs_scored > 0 THEN 0 ELSE 1 END,
            runs_scored DESC,
            batting_innings DESC,
            matches DESC,
            player_name ASC
        """
    return """
        matches DESC,
        runs_scored DESC,
        wickets_taken DESC,
        player_name ASC
    """


def is_test_context(lower_question: str) -> bool:
    if "test" in lower_question:
        return True
    bowling_terms = (
        "bowling",
        "wicket",
        "wickets",
        "bowler",
        "five-wicket",
        "fivefer",
        "fifer",
        "fiver",
        "five-for",
    )
    career_terms = ("average", "career", "record", "stats", "how many")
    has_bowling_term = any(term in lower_question for term in bowling_terms)
    if is_fielding_question(lower_question):
        return True
    return has_bowling_term and (
        "innings" in lower_question
        or any(term in lower_question for term in career_terms)
    )


def is_bowling_question(lower_question: str) -> bool:
    return any(
        term in lower_question
        for term in (
            "bowling",
            "wicket",
            "wickets",
            "bowler",
            "five-wicket",
            "fivefer",
            "fifer",
            "fiver",
            "five-for",
        )
    )


def is_dismissed_batter_question(lower_question: str) -> bool:
    return (
        ("wicket of" in lower_question or "dismissed" in lower_question)
        and any(term in lower_question for term in ("bowler", "wicket", "dismissed"))
    )


def is_fielding_question(lower_question: str) -> bool:
    return any(term in lower_question for term in ("catch", "catches", "fielding"))


def is_overseas_or_abroad_question(lower_question: str) -> bool:
    return any(term in lower_question for term in ("overseas", "abroad", "away from home"))


def fuzzy_player_matches(question: str, player_names: list[str], limit: int = 8) -> list[str]:
    words = [
        word
        for word in re.findall(r"[A-Za-z']+", question.lower())
        if len(word) >= 4 and word not in QUESTION_STOP_WORDS
    ]
    if not words:
        return []

    normalized_names = {normalize_name(name): name for name in player_names}
    candidates: list[tuple[float, str]] = []
    for normalized, original in normalized_names.items():
        score = 0.0
        name_tokens = normalized.split()
        for word in words:
            if word in normalized:
                score = max(score, 1.0)
            else:
                close = get_close_matches(word, name_tokens, n=1, cutoff=0.78)
                if close:
                    score = max(score, 0.92)
                else:
                    token_score = max(
                        (SequenceMatcher(None, word, token).ratio() for token in name_tokens),
                        default=0.0,
                    )
                    score = max(score, token_score)
        if score >= 0.72:
            candidates.append((score, original))

    candidates.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    output: list[str] = []
    for _score, name in candidates:
        if name not in output:
            output.append(name)
        if len(output) >= limit:
            break
    return output


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9']+", " ", name.lower()).strip()


def format_session_history(history: list[dict[str, Any]]) -> str:
    if not history:
        return "- No previous questions in this session."
    lines = []
    for index, item in enumerate(history[-5:], start=1):
        lines.append(f"{index}. Question: {item['question']}")
        lines.append(f"   SQL: {item['sql']}")
        lines.append(f"   Result summary: {item['result_summary']}")
    return "\n".join(lines)


def clean_sql(sql: str) -> str:
    sql = sql.replace("```sql", "").replace("```", "").strip()
    if ";" in sql:
        sql = sql.split(";", 1)[0].strip()

    lower_sql = sql.lower().lstrip()
    if not lower_sql.startswith("select") and not lower_sql.startswith("with"):
        raise ValueError(f"Only SELECT queries are allowed. Got: {sql}")

    blocked = (
        "insert ",
        "update ",
        "delete ",
        "drop ",
        "alter ",
        "create ",
        "replace ",
        "pragma ",
        "attach ",
        "detach ",
        "vacuum",
    )
    padded = f" {lower_sql} "
    if any(word in padded for word in blocked):
        raise ValueError(f"Unsafe SQL blocked: {sql}")
    return sql


def run_sql(sql: str) -> list[sqlite3.Row]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql).fetchall()


def print_rows(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("No rows returned.")
        return

    columns = rows[0].keys()
    widths = {
        column: max(len(column), *(len(format_cell(row[column])) for row in rows[:50]))
        for column in columns
    }
    header = "  ".join(column.ljust(widths[column]) for column in columns)
    print(header)
    print("  ".join("-" * widths[column] for column in columns))
    for row in rows[:50]:
        print("  ".join(format_cell(row[column]).ljust(widths[column]) for column in columns))
    if len(rows) > 50:
        print(f"... {len(rows) - 50} more rows")


def format_cell(value: Any) -> str:
    return "" if value is None else str(value)


def summarize_rows(rows: list[sqlite3.Row]) -> str:
    if not rows:
        return "No rows returned."
    sample = []
    for row in rows[:3]:
        sample.append({key: row[key] for key in row.keys()})
    suffix = f" Total rows: {len(rows)}." if len(rows) > 3 else ""
    return f"First rows: {sample}.{suffix}"


def row_dicts(rows: list[sqlite3.Row], limit: int = 10) -> list[dict[str, Any]]:
    return [{key: row[key] for key in row.keys()} for row in rows[:limit]]


def new_trace_record(question: str) -> dict[str, Any]:
    return {
        "trace_id": str(uuid.uuid4()),
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "question": question,
        "model": MODEL,
        "ollama_url": OLLAMA_URL,
        "db_path": DB_PATH,
        "guide_path": GUIDE_PATH,
    }


def write_trace(trace: dict[str, Any], trace_dir: str | Path) -> Path:
    trace_path = Path(trace_dir)
    trace_path.mkdir(parents=True, exist_ok=True)
    output_path = trace_path / TRACE_FILENAME
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
    return output_path


def answer_question(
    question: str,
    schema: str,
    guide: str,
    player_names: list[str],
    history: list[dict[str, Any]],
    trace_dir: str | Path | None = None,
    print_output: bool = True,
) -> dict[str, Any]:
    trace = new_trace_record(question) if trace_dir else None
    started = time.perf_counter()
    try:
        generated_sql = ask_ollama(
            question,
            schema,
            guide,
            player_names,
            history,
            trace=trace,
        )
        sql = clean_sql(generated_sql)
        rows = run_sql(sql)
        result_summary = summarize_rows(rows)
        if print_output:
            print("\nSQL:")
            print(sql)
            print("\nResult:")
            print_rows(rows)
        history.append(
            {
                "question": question,
                "sql": sql,
                "result_summary": result_summary,
            }
        )
        del history[:-5]
        output = {
            "question": question,
            "generated_sql": generated_sql,
            "sql": sql,
            "row_count": len(rows),
            "rows": row_dicts(rows),
            "result_summary": result_summary,
        }
        if trace is not None:
            trace.update(output)
            trace["status"] = "ok"
            trace["total_elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            write_trace(trace, trace_dir)
        return output
    except Exception as exc:
        if trace is not None:
            trace["status"] = "error"
            trace["error_type"] = type(exc).__name__
            trace["error"] = str(exc)
            trace["total_elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            write_trace(trace, trace_dir)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask Qwen cricket SQLite questions.")
    parser.add_argument(
        "--trace",
        action="store_true",
        default=os.environ.get("CRICKET_QWEN_TRACE") == "1",
        help="Write JSONL traces of prompts, Qwen responses, SQL, and results.",
    )
    parser.add_argument(
        "--trace-dir",
        default=os.environ.get("CRICKET_QWEN_TRACE_DIR", DEFAULT_TRACE_DIR),
        help=f"Directory for {TRACE_FILENAME} when tracing is enabled.",
    )
    args = parser.parse_args()
    schema = get_schema()
    guide = get_guide()
    player_names = get_player_names()
    history: list[dict[str, Any]] = []
    print("Cricket stats assistant is ready. Type 'exit' or 'quit' to stop.")
    if args.trace:
        print(f"Trace logging enabled: {Path(args.trace_dir) / TRACE_FILENAME}")
    while True:
        try:
            question = input("\nAsk cricket stats> ").strip()
        except EOFError:
            print()
            return 0
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            return 0
        try:
            answer_question(
                question,
                schema,
                guide,
                player_names,
                history,
                trace_dir=args.trace_dir if args.trace else None,
            )
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
