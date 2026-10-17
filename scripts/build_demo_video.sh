#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
frames_dir="$project_dir/demo_frames"
clips_dir="$project_dir/demo_clips_silent"
output_dir="$project_dir/demo"

mkdir -p "$clips_dir" "$output_dir"
concat_file="$clips_dir/concat.txt"
: > "$concat_file"

make_clip() {
  local image_path="$1"
  local duration="$2"
  local output_path="$3"
  local filter="$4"
  ffmpeg -loglevel error -y -loop 1 -i "$image_path" -t "$duration" \
    -vf "scale=1280:720,${filter}fps=30,format=yuv420p" \
    -an -c:v libx264 -preset medium "$output_path"
}

for index in $(seq 1 5); do
  number=$(printf '%02d' "$index")
  make_clip "$frames_dir/q${number}_before.png" 2.5 "$clips_dir/${number}_question.mp4" ""
  make_clip "$frames_dir/q${number}_before.png" 0.6 "$clips_dir/${number}_click.mp4" \
    "drawbox=x=998:y=591:w=212:h=55:color=0xd9a441@0.95:t=5,"
  make_clip "$frames_dir/q${number}_after.png" 4.0 "$clips_dir/${number}_answer.mp4" ""

  printf "file '%s'\n" "$clips_dir/${number}_question.mp4" >> "$concat_file"
  printf "file '%s'\n" "$clips_dir/${number}_click.mp4" >> "$concat_file"
  printf "file '%s'\n" "$clips_dir/${number}_answer.mp4" >> "$concat_file"
done

ffmpeg -loglevel error -y -f concat -safe 0 -i "$concat_file" \
  -an -c:v libx264 -preset medium -movflags +faststart \
  "$output_dir/CricketStats_MongoDB_Demo.mp4"

echo "$output_dir/CricketStats_MongoDB_Demo.mp4"
