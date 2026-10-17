#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
"$project_dir/scripts/build_demo_video.sh"
cp "$project_dir/demo/CricketStats_MongoDB_Demo.mp4" \
  "$project_dir/demo/CricketStats_MongoDB_Demo_NoVoice.mp4"
echo "$project_dir/demo/CricketStats_MongoDB_Demo_NoVoice.mp4"
