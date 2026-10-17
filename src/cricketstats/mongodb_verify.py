from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from .mongodb_client import MongoSettings, create_client
from .mongodb_migrate import DEFAULT_IPL_SQLITE, DEFAULT_MAIN_SQLITE, quote_identifier, sqlite_tables


def sqlite_counts(path: Path) -> dict[str, int]:
    uri = f"file:{path}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0]
            for table in sqlite_tables(conn)
        }


def verify(path: Path, db) -> bool:
    ok = True
    for table, expected in sqlite_counts(path).items():
        actual = db[table].count_documents({})
        status = "OK" if expected == actual else "MISMATCH"
        print(f"{status:8} {db.name}.{table}: MongoDB={actual:,} SQLite={expected:,}")
        ok &= expected == actual
    return ok


def main() -> int:
    settings = MongoSettings.from_env()
    parser = argparse.ArgumentParser(description="Compare MongoDB collection counts with SQLite.")
    parser.add_argument("--uri", default=settings.uri)
    parser.add_argument("--main-sqlite", type=Path, default=DEFAULT_MAIN_SQLITE)
    parser.add_argument("--ipl-sqlite", type=Path, default=DEFAULT_IPL_SQLITE)
    parser.add_argument("--main-database", default=settings.database)
    parser.add_argument("--ipl-database", default=settings.ipl_database)
    args = parser.parse_args()
    with create_client(args.uri) as client:
        main_ok = verify(args.main_sqlite, client[args.main_database])
        ipl_ok = verify(args.ipl_sqlite, client[args.ipl_database])
    return 0 if main_ok and ipl_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
