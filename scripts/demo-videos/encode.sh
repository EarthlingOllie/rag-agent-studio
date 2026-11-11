#!/usr/bin/env bash
# Turns record.cjs's WebM recordings into the MP4s and poster images that docs/demo.md links.
#   scripts/demo-videos/encode.sh [recordings-dir]
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
IN=${1:-$HERE/out}
OUT=$HERE/../../docs/demo
mkdir -p "$OUT"
for webm in "$IN"/*.webm; do
  slug=$(basename "$webm" .webm)
  ffmpeg -v error -y -i "$webm" -vf "fps=25,scale=1280:-2" -c:v libx264 -crf 28 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -an "$OUT/$slug.mp4"
  duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/$slug.mp4")
  # The poster is a frame past the set-up, at the story's payoff: 60% of the way through, or
  # later for a story whose 60% mark falls between two pages.
  at=0.6; [ "$slug" = 09-team-and-cost ] && at=0.73
  ffmpeg -v error -y -ss "$(python3 -c "print($duration * $at)")" -i "$OUT/$slug.mp4" -frames:v 1 -vf scale=640:-2 -q:v 4 "$OUT/$slug.jpg"
  printf '%s\t%.0fs\t%s\n' "$slug" "$duration" "$(du -h "$OUT/$slug.mp4" | cut -f1)"
done
