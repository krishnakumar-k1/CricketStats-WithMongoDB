from __future__ import annotations

import argparse
import json

from .mongodb_client import MongoSettings, create_client


def main() -> int:
    settings = MongoSettings.from_env()
    parser = argparse.ArgumentParser(description="Run example CricketStats MongoDB queries.")
    parser.add_argument("report", choices=("summary", "top-test-batters", "ipl-orange-caps"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--uri", default=settings.uri)
    args = parser.parse_args()
    with create_client(args.uri) as client:
        if args.report == "summary":
            result = {
                name: {
                    collection: client[name][collection].estimated_document_count()
                    for collection in client[name].list_collection_names()
                    if not collection.startswith("_")
                }
                for name in (settings.database, settings.ipl_database)
            }
        elif args.report == "top-test-batters":
            result = list(client[settings.database].player_career_stats.find(
                {"format_group": "Test", "competition_name": "All"},
                {"_id": 0, "player_name": 1, "runs_scored": 1, "batting_average": 1},
            ).sort([("runs_scored", -1)]).limit(args.limit))
        else:
            result = list(client[settings.ipl_database].orange_cap_winners.find(
                {}, {"_id": 0}
            ).sort([("season", -1)]).limit(args.limit))
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
