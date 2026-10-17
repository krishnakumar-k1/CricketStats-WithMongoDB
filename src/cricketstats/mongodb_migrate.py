from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from pymongo import ASCENDING, MongoClient
from pymongo.errors import BulkWriteError

from .mongodb_client import MongoSettings, create_client

DEFAULT_MAIN_SQLITE = Path("/Users/rkk/CricketStats/cricketstats.sqlite")
DEFAULT_IPL_SQLITE = Path("/Users/rkk/CricketStats/ipl_cricketstats.sqlite")

INDEXES: dict[str, tuple[tuple[str, ...], ...]] = {
    "match_stats": (("match_id",), ("match_type", "match_date"), ("winner",), ("event_name", "season")),
    "match_innings_stats": (("match_id", "innings_number"), ("team", "runs")),
    "player_match_stats": (("player_name", "match_id"), ("team", "match_id")),
    "player_match_innings_stats": (
        ("player_name", "match_id", "innings_number"),
        ("dismissal_bowler", "dismissal_kind"),
    ),
    "player_batting_innings_stats": (
        ("player_name", "format_group", "match_date"),
        ("player_team", "format_group", "runs_scored"),
    ),
    "player_career_stats": (("player_name", "format_group", "competition_name"),),
    "player_career_group_stats": (("player_name", "format_group", "group_type", "group_value"),),
    "delivery_stats": (
        ("match_id", "innings_number", "over_number", "ball_number"),
        ("batter",),
        ("bowler",),
    ),
    "team_season_stats": (("season", "team"),),
    "team_career_stats": (("team",),),
}


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    return [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]


def maybe_decode_json(value: Any, parse_json: bool) -> Any:
    if not parse_json or not isinstance(value, str):
        return value
    candidate = value.strip()
    if not candidate or candidate[0] not in "[{":
        return value
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return value


def batches(cursor: sqlite3.Cursor, size: int) -> Iterable[list[sqlite3.Row]]:
    while rows := cursor.fetchmany(size):
        yield rows


def create_indexes(db, table: str) -> None:
    for fields in INDEXES.get(table, ()):
        db[table].create_index([(field, ASCENDING) for field in fields], background=True)


def migrate_table(
    conn: sqlite3.Connection,
    db,
    table: str,
    *,
    batch_size: int,
    parse_json: bool,
    drop: bool,
) -> int:
    collection = db[table]
    state = db["_migration_state"]
    if drop:
        collection.drop()
        state.delete_one({"_id": table})
    checkpoint = state.find_one({"_id": table}) or {}
    last_rowid = int(checkpoint.get("last_rowid", 0))
    query = f"SELECT rowid AS __rowid__, * FROM {quote_identifier(table)} WHERE rowid > ? ORDER BY rowid"
    cursor = conn.execute(query, (last_rowid,))
    columns = [item[0] for item in cursor.description]
    migrated = 0
    for rows in batches(cursor, batch_size):
        documents = []
        for row in rows:
            raw = dict(zip(columns, row))
            rowid = int(raw.pop("__rowid__"))
            doc = {key: maybe_decode_json(value, parse_json) for key, value in raw.items()}
            doc["_id"] = rowid
            documents.append(doc)
        try:
            collection.insert_many(documents, ordered=False)
        except BulkWriteError as exc:
            errors = [e for e in exc.details.get("writeErrors", []) if e.get("code") != 11000]
            if errors:
                raise
        last_rowid = int(rows[-1][0])
        migrated += len(rows)
        state.update_one(
            {"_id": table},
            {"$set": {"last_rowid": last_rowid, "updated_at_epoch": time.time()}},
            upsert=True,
        )
        print(f"  {table}: {last_rowid:,} source rows processed", flush=True)
    create_indexes(db, table)
    state.update_one(
        {"_id": table},
        {"$set": {"complete": True, "document_count": collection.count_documents({})}},
        upsert=True,
    )
    return migrated


def migrate_database(
    sqlite_path: Path,
    client: MongoClient,
    database_name: str,
    *,
    batch_size: int = 5_000,
    parse_json: bool = True,
    drop: bool = False,
) -> dict[str, int]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(sqlite_path)
    db = client[database_name]
    result: dict[str, int] = {}
    uri = f"file:{sqlite_path}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        for table in sqlite_tables(conn):
            print(f"Migrating {sqlite_path.name}:{table} -> {database_name}.{table}")
            result[table] = migrate_table(
                conn, db, table, batch_size=batch_size, parse_json=parse_json, drop=drop
            )
    db["_migration_metadata"].replace_one(
        {"_id": "source"},
        {"_id": "source", "sqlite_path": str(sqlite_path), "completed_at_epoch": time.time(), "tables": result},
        upsert=True,
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    settings = MongoSettings.from_env()
    parser = argparse.ArgumentParser(description="Migrate CricketStats SQLite data to MongoDB.")
    parser.add_argument("--source", choices=("main", "ipl", "all"), default="all")
    parser.add_argument("--main-sqlite", type=Path, default=DEFAULT_MAIN_SQLITE)
    parser.add_argument("--ipl-sqlite", type=Path, default=DEFAULT_IPL_SQLITE)
    parser.add_argument("--uri", default=settings.uri)
    parser.add_argument("--main-database", default=settings.database)
    parser.add_argument("--ipl-database", default=settings.ipl_database)
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--drop", action="store_true", help="Drop target collections first.")
    parser.add_argument("--keep-json-strings", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    with create_client(args.uri) as client:
        client.admin.command("ping")
        common = dict(batch_size=args.batch_size, parse_json=not args.keep_json_strings, drop=args.drop)
        if args.source in ("main", "all"):
            migrate_database(args.main_sqlite, client, args.main_database, **common)
        if args.source in ("ipl", "all"):
            migrate_database(args.ipl_sqlite, client, args.ipl_database, **common)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
