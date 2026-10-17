from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .mongodb_client import MongoSettings, create_client

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("CRICKET_MODEL", "qwen2.5-coder:14b")
ALLOWED_STAGES = {
    "$addFields", "$count", "$facet", "$group", "$limit", "$lookup",
    "$match", "$project", "$replaceRoot", "$set", "$setWindowFields",
    "$skip", "$sort", "$unset", "$unwind",
}
BLOCKED_OPERATORS = {"$accumulator", "$function", "$merge", "$out", "$where"}
PLAYER_ALIASES = {
    "sunil gavaskar": "SM Gavaskar", "gavaskar": "SM Gavaskar",
    "don bradman": "DG Bradman", "bradman": "DG Bradman",
    "sachin tendulkar": "SR Tendulkar", "tendulkar": "SR Tendulkar",
    "brian lara": "BC Lara", "lara": "BC Lara",
    "virat kohli": "V Kohli", "kohli": "V Kohli",
    "joe root": "JE Root", "root": "JE Root",
    "kapil dev": "Kapil Dev",
    "muttiah muralitharan": "M Muralitharan", "muralitharan": "M Muralitharan",
}


def bson_type(value: Any) -> str:
    if value is None: return "null"
    if isinstance(value, bool): return "bool"
    if isinstance(value, int): return "int"
    if isinstance(value, float): return "double"
    if isinstance(value, list): return "array"
    if isinstance(value, dict): return "document"
    return "string"


def schema_summary(db) -> str:
    result = {}
    for name in sorted(n for n in db.list_collection_names() if not n.startswith("_")):
        sample = db[name].find_one({}, {"_id": 0}) or {}
        result[name] = {key: bson_type(value) for key, value in sample.items()}
    return json.dumps(result, indent=2, sort_keys=True)


def player_context(question: str, db, limit: int = 8) -> list[str]:
    lower = question.lower()
    aliases = [value for key, value in PLAYER_ALIASES.items() if re.search(rf"\b{re.escape(key)}\b", lower)]
    tokens = [t for t in re.findall(r"[a-z][a-z'-]+", lower) if len(t) >= 4]
    candidates = list(dict.fromkeys(aliases))
    if tokens:
        pattern = "|".join(re.escape(t) for t in tokens[-4:])
        for name in db.player_career_stats.distinct("player_name", {"player_name": {"$regex": pattern, "$options": "i"}}):
            if name not in candidates:
                candidates.append(name)
            if len(candidates) >= limit:
                break
    return candidates[:limit]


def build_prompt(question: str, schema: str, players: list[str], history: list[dict[str, Any]]) -> str:
    recent = json.dumps(history[-3:], default=str)
    return f"""You are a MongoDB aggregation expert for a cricket statistics database.
Return only one JSON object, without Markdown, in this exact shape:
{{"collection":"collection_name","pipeline":[{{"$match":{{...}}}}, ...]}}

Rules:
- Produce a read-only aggregation pipeline. Never use $out, $merge, $function, $accumulator, or $where.
- Use only collections and fields present in the schema.
- Add a final $limit of at most 50 unless returning a single grouped/count result.
- Resolve player names to the exact stored name from Player candidates when one matches.
- `player_career_stats` contains stored career totals. For career runs, hundreds, wickets,
  catches, batting average, or bowling average, use its stored field rather than counting rows.
- For Test career rows use format_group="Test" and competition_name="All".
- For innings achievements use player_batting_innings_stats.
- For dismissal type and innings bowling use player_match_innings_stats.
- `player_batting_innings_stats` uses player_team; player_match_stats uses team.
- Join match context with $lookup from match_stats using match_id when needed.
- In the IPL database, ball-level facts are in delivery_stats.

Schema:
{schema}

Player candidates: {json.dumps(players)}
Recent session context: {recent}
Question: {question}
"""


def deterministic_plan(question: str, players: list[str]) -> dict[str, Any] | None:
    """Build authoritative plans for common stored career totals.

    These questions should not depend on an LLM choosing between similarly
    named career and grouped-career collections.
    """
    lower = question.lower()
    cap = "orange" if "orange cap" in lower else "purple" if "purple cap" in lower else None
    if cap:
        year_match = re.search(r"\b(20\d{2}|19\d{2})\b", lower)
        match = {"year": int(year_match.group(1))} if year_match else {}
        field = "runs_scored" if cap == "orange" else "wickets_taken"
        return {
            "collection": f"{cap}_cap_winners",
            "pipeline": [
                {"$match": match},
                {"$sort": {"year": -1, field: -1}},
                {"$project": {"_id": 0, "year": 1, "season": 1, "player_name": 1, field: 1}},
                {"$limit": 1 if year_match else 20},
            ],
        }
    if "ipl" in lower and "most" in lower and any(term in lower for term in ("runs", "sixes")):
        field = "sixes" if "sixes" in lower else "runs_scored"
        return {
            "collection": "player_career_stats",
            "pipeline": [
                {"$match": {"format_group": "IPL", "competition_name": "Indian Premier League"}},
                {"$sort": {field: -1, "matches": -1}},
                {"$project": {"_id": 0, "player_name": 1, field: 1, "matches": 1}},
                {"$limit": 1},
            ],
        }
    if "first indian" in lower and "centur" in lower and "both" in lower and "innings" in lower:
        return {
            "collection": "player_batting_innings_stats",
            "pipeline": [
                {"$match": {
                    "format_group": "Test",
                    "player_team": {"$regex": "^India"},
                    "runs_scored": {"$gte": 100},
                }},
                {"$group": {
                    "_id": {"match_id": "$match_id", "player_name": "$player_name"},
                    "match_date": {"$first": "$match_date"},
                    "opposition": {"$first": "$opposition"},
                    "scores": {"$push": "$runs_scored"},
                    "centuries": {"$sum": 1},
                }},
                {"$match": {"centuries": {"$gte": 2}}},
                {"$sort": {"match_date": 1}},
                {"$project": {
                    "_id": 0,
                    "player_name": "$_id.player_name",
                    "match_date": 1,
                    "opposition": 1,
                    "scores": 1,
                }},
                {"$limit": 1},
            ],
        }
    if not players or any(word in lower for word in (" against ", "innings", "season")):
        return None
    metrics = (
        (("hundred", "centur"), "hundreds"),
        (("wicket",), "wickets_taken"),
        (("catch", "catches"), "catches"),
        (("stumping",), "stumpings"),
        (("batting average",), "batting_average"),
        (("bowling average",), "bowling_average"),
        (("career run", "test run"), "runs_scored"),
    )
    field = next((field for phrases, field in metrics if any(p in lower for p in phrases)), None)
    if field is None or "most" in lower or "which player" in lower or "who " in lower:
        return None
    player = players[0]
    match: dict[str, Any] = {
        "player_name": player,
        "format_group": "Test" if "test" in lower else {"$exists": True},
        "competition_name": "All",
    }
    if field in {"wickets_taken", "bowling_average"}:
        match["wickets_taken"] = {"$gt": 0}
    return {
        "collection": "player_career_stats",
        "pipeline": [
            {"$match": match},
            {"$sort": {field: -1, "matches": -1}},
            {"$project": {"_id": 0, "player_name": 1, field: 1}},
            {"$limit": 1},
        ],
    }


def call_ollama(prompt: str, *, url: str = OLLAMA_URL, model: str = MODEL) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode())["response"]


def parse_plan(text: str) -> dict[str, Any]:
    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model did not return a JSON object")
    plan = json.loads(cleaned[start:end + 1])
    if set(plan) != {"collection", "pipeline"}:
        raise ValueError("Plan must contain only collection and pipeline")
    if not isinstance(plan["collection"], str) or not isinstance(plan["pipeline"], list):
        raise ValueError("Invalid collection or pipeline")
    return plan


def walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk(child)
    elif isinstance(value, list):
        for child in value: yield from walk(child)


def validate_plan(plan: dict[str, Any], collections: set[str]) -> dict[str, Any]:
    if plan["collection"] not in collections or plan["collection"].startswith("_"):
        raise ValueError(f"Unknown collection: {plan['collection']}")
    pipeline = plan["pipeline"]
    if len(pipeline) > 30:
        raise ValueError("Pipeline has too many stages")
    for stage in pipeline:
        if not isinstance(stage, dict) or len(stage) != 1:
            raise ValueError("Each pipeline stage must contain one operator")
        operator = next(iter(stage))
        if operator not in ALLOWED_STAGES:
            raise ValueError(f"Blocked pipeline stage: {operator}")
        keys = set(walk(stage))
        blocked = keys & BLOCKED_OPERATORS
        if blocked:
            raise ValueError(f"Blocked operator: {sorted(blocked)[0]}")
        if operator == "$lookup":
            source = stage[operator].get("from")
            if source not in collections or source.startswith("_"):
                raise ValueError(f"Unknown lookup collection: {source}")
    if not pipeline or "$limit" not in pipeline[-1]:
        pipeline.append({"$limit": 50})
    elif not isinstance(pipeline[-1]["$limit"], int) or not 1 <= pipeline[-1]["$limit"] <= 100:
        raise ValueError("Final $limit must be from 1 through 100")
    return plan


def run_plan(db, plan: dict[str, Any]) -> list[dict[str, Any]]:
    return list(db[plan["collection"]].aggregate(
        plan["pipeline"], allowDiskUse=True, maxTimeMS=60_000
    ))


def print_rows(rows: list[dict[str, Any]]) -> None:
    print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))


def answer(question: str, db, schema: str, history: list[dict[str, Any]], trace_dir: Path | None = None):
    players = player_context(question, db)
    prompt = build_prompt(question, schema, players, history)
    plan = deterministic_plan(question, players)
    generated = "deterministic career query" if plan else call_ollama(prompt)
    if plan is None:
        plan = parse_plan(generated)
    plan = validate_plan(plan, set(db.list_collection_names()))
    rows = run_plan(db, plan)
    item = {"question": question, "plan": plan, "rows": rows[:50]}
    history.append({"question": question, "plan": plan, "result": rows[:3]})
    del history[:-5]
    if trace_dir:
        trace_dir.mkdir(parents=True, exist_ok=True)
        record = {"trace_id": str(uuid.uuid4()), "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
                  "model": MODEL, "database": db.name, "prompt": prompt, "generated": generated, **item}
        with (trace_dir / "mongodb_assistant.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
    return item


def main(argv: list[str] | None = None) -> int:
    settings = MongoSettings.from_env()
    parser = argparse.ArgumentParser(description="Ask cricket questions using MongoDB aggregations.")
    parser.add_argument("--ipl", action="store_true")
    parser.add_argument("--question")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--trace-dir", type=Path, default=Path("logs/mongodb"))
    parser.add_argument("--uri", default=settings.uri)
    args = parser.parse_args(argv)
    database = settings.ipl_database if args.ipl else settings.database
    with create_client(args.uri) as client:
        db = client[database]
        schema = schema_summary(db)
        history: list[dict[str, Any]] = []
        if args.question:
            result = answer(args.question, db, schema, history, args.trace_dir if args.trace else None)
            print("MongoDB aggregation plan:")
            print(json.dumps(result["plan"], indent=2))
            print("Result:")
            print_rows(result["rows"])
            return 0
        print(f"CricketStats MongoDB assistant ({database}). Type quit to stop.")
        while True:
            try: question = input("\nAsk cricket stats> ").strip()
            except EOFError: return 0
            if question.lower() in {"quit", "exit"}: return 0
            if not question: continue
            try:
                result = answer(question, db, schema, history, args.trace_dir if args.trace else None)
                print("\nMongoDB aggregation plan:")
                print(json.dumps(result["plan"], indent=2))
                print("\nResult:")
                print_rows(result["rows"])
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
