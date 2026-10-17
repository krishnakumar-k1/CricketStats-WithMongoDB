# MongoDB migration report

Migration completed on 2026-10-13 using MongoDB Community 8.0.

## Targets

- `cricketstats`: 7 data collections, 2,861,363 documents
- `cricketstats_ipl`: 17 data collections, 416,416 documents

Both databases also contain `_migration_state` and `_migration_metadata`
collections for resumability and provenance.

## Verification

Every MongoDB collection count was compared with its corresponding source
SQLite table. All 24 comparisons matched exactly.

The original files remain unchanged:

- `/Users/rkk/CricketStats/cricketstats.sqlite`
- `/Users/rkk/CricketStats/ipl_cricketstats.sqlite`

MongoDB runs as the Homebrew service `mongodb-community@8.0` and listens only
on localhost by default.

## Completed application layer

- General and IPL natural-language assistants execute MongoDB aggregations.
- Generated plans are restricted to approved read-only stages.
- `$out`, `$merge`, `$function`, `$accumulator`, and `$where` are blocked.
- Pipelines have result limits and a 60-second execution timeout.
- Common career totals and IPL cap questions use deterministic pipelines.
- Automated suite: 17 passing tests.
