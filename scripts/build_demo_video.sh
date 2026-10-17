#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
frames_dir="$project_dir/demo_frames"
audio_dir="$project_dir/demo_audio"
clips_dir="$project_dir/demo_clips"
output_dir="$project_dir/demo"

mkdir -p "$audio_dir" "$clips_dir" "$output_dir"

questions=(
  "IPL question one. Who won the IPL Orange Cap in 2023?"
  "IPL question two. Who won the IPL Purple Cap in 2023?"
  "IPL question three. Who won the IPL Orange Cap in 2022?"
  "IPL question four. Who won the IPL Purple Cap in 2022?"
  "IPL question five. Who has scored the most IPL runs?"
  "IPL question six. Who has hit the most sixes in the IPL?"
  "Test question one. What is Sachin Tendulkar's Test batting average?"
  "Test question two. How many Test hundreds did Sachin Tendulkar score?"
  "Test question three. How many Test wickets did Muttiah Muralitharan take?"
)

answers=(
  "Shubman Gill won the 2023 IPL Orange Cap with 890 runs."
  "Mohammed Shami won the 2023 IPL Purple Cap with 28 wickets."
  "J. C. Buttler won the 2022 IPL Orange Cap with 863 runs."
  "Y. S. Chahal won the 2022 IPL Purple Cap with 27 wickets."
  "V. Kohli leads this IPL database with 9,346 runs."
  "C. H. Gayle leads this IPL database with 359 sixes."
  "S. R. Tendulkar has a Test batting average of 54.6 in the available records."
  "S. R. Tendulkar has 42 Test hundreds in the available records."
  "M. Muralitharan has 545 Test wickets in the available records."
)

say -v Samantha -r 178 -o "$audio_dir/intro.aiff" \
  "CricketStats now has a MongoDB-powered question and answer interface. Here are six IPL questions, followed by three Test questions."

for index in "${!questions[@]}"; do
  number=$(printf '%02d' "$((index + 1))")
  say -v Samantha -r 178 -o "$audio_dir/q${number}.aiff" "${questions[$index]}"
  say -v Samantha -r 178 -o "$audio_dir/a${number}.aiff" "${answers[$index]}"
done

say -v Samantha -r 178 -o "$audio_dir/outro.aiff" \
  "Every result came from the selected local MongoDB dataset through validated, read-only aggregations."

make_still_clip() {
  local image_path="$1"
  local audio_path="$2"
  local output_path="$3"
  ffmpeg -loglevel error -y -loop 1 -i "$image_path" -i "$audio_path" \
    -vf "scale=1280:720,fps=30,format=yuv420p" -c:v libx264 -preset medium \
    -c:a aac -b:a 160k -shortest "$output_path"
}

make_still_clip "$frames_dir/q01_before.png" "$audio_dir/intro.aiff" "$clips_dir/00_intro.mp4"

concat_file="$clips_dir/concat.txt"
: > "$concat_file"
printf "file '%s'\n" "$clips_dir/00_intro.mp4" >> "$concat_file"

for index in "${!questions[@]}"; do
  number=$(printf '%02d' "$((index + 1))")
  make_still_clip "$frames_dir/q${number}_before.png" "$audio_dir/q${number}.aiff" "$clips_dir/${number}_question.mp4"

  ffmpeg -loglevel error -y -loop 1 -i "$frames_dir/q${number}_before.png" \
    -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t 0.7 \
    -vf "scale=1280:720,drawbox=x=998:y=591:w=212:h=55:color=0xd9a441@0.95:t=5,fps=30,format=yuv420p" \
    -c:v libx264 -preset medium -c:a aac -b:a 160k -shortest "$clips_dir/${number}_click.mp4"

  make_still_clip "$frames_dir/q${number}_after.png" "$audio_dir/a${number}.aiff" "$clips_dir/${number}_answer.mp4"
  printf "file '%s'\n" "$clips_dir/${number}_question.mp4" >> "$concat_file"
  printf "file '%s'\n" "$clips_dir/${number}_click.mp4" >> "$concat_file"
  printf "file '%s'\n" "$clips_dir/${number}_answer.mp4" >> "$concat_file"
done

make_still_clip "$frames_dir/q09_after.png" "$audio_dir/outro.aiff" "$clips_dir/99_outro.mp4"
printf "file '%s'\n" "$clips_dir/99_outro.mp4" >> "$concat_file"

ffmpeg -loglevel error -y -f concat -safe 0 -i "$concat_file" \
  -c:v libx264 -preset medium -c:a aac -b:a 160k -movflags +faststart \
  "$output_dir/CricketStats_MongoDB_Demo.mp4"

echo "$output_dir/CricketStats_MongoDB_Demo.mp4"
