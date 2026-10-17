#!/usr/bin/env bash

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

START_YEAR="${1:-1930}"
END_YEAR="${2:-1996}"
WAYBACK_TIMESTAMP="${WAYBACK_TIMESTAMP:-20150908131340}"
OUTPUT_ROOT="${OUTPUT_ROOT:-cricketarchive_wayback_tests_1930_1996}"
MAX_PAGES="${MAX_PAGES:-100}"
MAX_DEPTH="${MAX_DEPTH:-2}"
MAX_SCORECARDS="${MAX_SCORECARDS:-50}"
DELAY="${DELAY:-2.5}"
PYTHONPATH_VALUE="${PYTHONPATH:-src}"

mkdir -p "$OUTPUT_ROOT"

for ((year = START_YEAR; year <= END_YEAR; year++)); do
  start_url="https://web.archive.org/web/${WAYBACK_TIMESTAMP}/http://cricketarchive.com/Archive/Seasons/Lists/${year}_t_Match_List.html"
  output_dir="${OUTPUT_ROOT}/${year}"

  echo "Crawling Test match list for ${year}"
  echo "  URL: ${start_url}"
  echo "  Output: ${output_dir}"

  if PYTHONPATH="$PYTHONPATH_VALUE" python3 -m cricketstats.cricketarchive_wayback_crawler \
    --start-url "$start_url" \
    --output-dir "$output_dir" \
    --max-pages "$MAX_PAGES" \
    --max-depth "$MAX_DEPTH" \
    --max-scorecards "$MAX_SCORECARDS" \
    --delay "$DELAY"; then
    echo "Finished ${year}"
  else
    echo "FAILED ${year}" | tee -a "${OUTPUT_ROOT}/failed_years.txt"
  fi

  echo
done

echo "Done. Output root: ${OUTPUT_ROOT}"
