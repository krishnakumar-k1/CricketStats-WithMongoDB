from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from pymongo import MongoClient

DEFAULT_URI = "mongodb://localhost:27017/?directConnection=true"


@dataclass(frozen=True)
class MongoSettings:
    uri: str
    database: str
    ipl_database: str

    @classmethod
    def from_env(cls) -> "MongoSettings":
        return cls(
            uri=os.getenv("MONGODB_URI", DEFAULT_URI),
            database=os.getenv("MONGODB_DATABASE", "cricketstats"),
            ipl_database=os.getenv("MONGODB_IPL_DATABASE", "cricketstats_ipl"),
        )


def create_client(uri: str | None = None) -> MongoClient:
    settings = MongoSettings.from_env()
    return MongoClient(uri or settings.uri, appname="CricketStats-WithMongoDB")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check CricketStats MongoDB connectivity.")
    parser.add_argument("--uri", default=None, help="Defaults to MONGODB_URI.")
    args = parser.parse_args()
    settings = MongoSettings.from_env()
    with create_client(args.uri) as client:
        print(f"MongoDB ping: {client.admin.command('ping')}")
        for name in (settings.database, settings.ipl_database):
            db = client[name]
            collections = db.list_collection_names()
            count = sum(db[c].estimated_document_count() for c in collections if not c.startswith("_"))
            print(f"{name}: {len(collections)} collections, {count} documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
