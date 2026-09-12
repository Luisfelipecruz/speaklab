#!/usr/bin/env bash
# Convert the recorded .webm walkthroughs to LinkedIn-ready H.264 .mp4.
#
# Uses a containerised ffmpeg so nothing needs installing on the host:
#   ./to-mp4.sh                       convert every .webm beside this script
#   ./to-mp4.sh file.webm 30          convert one file, hard-trimmed to 30s
#   SS=2.6 ./to-mp4.sh file.webm      cut the first 2.6s off the front
#   SCALE=1080:1350 ./to-mp4.sh file.webm   upscale on the way out (lanczos)
#   POSTER=x.png ./to-mp4.sh file.webm   also embed x.png as the cover frame
#   AUDIO=x.wav ./to-mp4.sh file.webm    x.wav is the soundtrack (mix.cjs writes it)
#
# SS exists because a browser recording starts before the browser has anything to show.
# Playwright begins capturing when the context is created, so the opening second or two
# is a page loading, hydrating and collapsing its sidebar -- on a tall portrait canvas
# that reads as a white screen, and it is the first thing a viewer sees. The recorders
# measure the moment the page is actually settled and print it; SS takes that number.
# It is placed BEFORE -i so ffmpeg seeks rather than decoding and discarding, and the
# re-encode below makes the cut frame-accurate regardless of keyframe placement.
#
# POSTER embeds a still as an attached_pic in a second pass. Players that understand it
# (QuickTime, VLC, most file managers) show that frame instead of frame 1. LinkedIn does
# NOT read it -- it wants the .png uploaded by hand in the composer -- so the standalone
# file is the real deliverable and this is a convenience.
#
# Notes on the flags:
#   -pix_fmt yuv420p   required, or Safari/LinkedIn show a black frame
#   -movflags faststart moves the index to the front so it streams immediately
#   silent AAC track    without AUDIO: some platforms reject or mis-transcode video with no audio
set -euo pipefail
cd "$(dirname "$0")"
DIR="$(pwd)"
TRIM="${2:-}"
SS="${SS:-}"
POSTER="${POSTER:-}"
# SCALE exists because the recorders lay the page out SMALLER than they deliver: a page
# rendered at 864x1080 puts far more content in a 4:5 frame than the same page rendered
# at 1080x1350, where the content stopped 43% short of the bottom. Same aspect ratio, so
# this is a clean 1.25x enlargement, not a stretch. lanczos because text is the subject.
SCALE="${SCALE:-}"
# The soundtrack starts at the head cut, as mix.cjs builds it, so SS seeks the video alone.
# It sits beside the input, like the poster, and is padded to the video's length.
AUDIO="${AUDIO:-}"

# The input may live in a subdirectory (out-copilot/), so mount ITS directory rather
# than this script's and refer to everything by basename inside the container.
convert() {
  local in="$1" out="${1%.webm}.mp4"
  local dir base obase
  dir="$(cd "$(dirname "$in")" && pwd)"
  base="$(basename "$in")"
  obase="$(basename "$out")"
  local trim_args=() seek_args=() scale_args=()
  local audio_args=(-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100)
  [ -n "$TRIM" ] && trim_args=(-t "$TRIM")
  [ -n "$SS" ] && seek_args=(-ss "$SS")
  [ -n "$SCALE" ] && scale_args=(-vf "scale=${SCALE}:flags=lanczos")
  if [ -n "$AUDIO" ]; then
    if [ ! -f "$dir/$(basename "$AUDIO")" ]; then
      echo "   $(basename "$AUDIO") is not beside $base" >&2
      return 1
    fi
    audio_args=(-i "/data/$(basename "$AUDIO")")
  fi
  echo "→ $in  →  $obase${SS:+  (head cut at ${SS}s)}${SCALE:+  (scaled to ${SCALE})}${TRIM:+  (trimmed to ${TRIM}s)}${AUDIO:+  (soundtrack $(basename "$AUDIO"))}"
  docker run --rm -v "$dir":/data linuxserver/ffmpeg \
    -hide_banner -loglevel error \
    ${seek_args[@]+"${seek_args[@]}"} \
    -i "/data/$base" \
    "${audio_args[@]}" \
    -map 0:v:0 -map 1:a:0 \
    ${trim_args[@]+"${trim_args[@]}"} \
    ${scale_args[@]+"${scale_args[@]}"} \
    -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -movflags +faststart \
    -af apad -c:a aac -b:a 160k -shortest -r 25 \
    -y "/data/$obase"

  [ -n "$POSTER" ] && embed_cover "$(dirname "$in")/$obase" "$POSTER"
  return 0
}

# Second pass, stream-copied: the video is not re-encoded, only re-muxed with the still
# attached. Cheap, lossless, and reversible by re-running convert without POSTER.
embed_cover() {
  local mp4="$1" png="$2" dir base pbase
  dir="$(cd "$(dirname "$mp4")" && pwd)"
  base="$(basename "$mp4")"
  pbase="$(basename "$png")"
  if [ ! -f "$dir/$pbase" ]; then
    echo "   cover skipped — $pbase is not beside $base"; return 0
  fi
  echo "   embedding cover $pbase"
  docker run --rm -v "$dir":/data linuxserver/ffmpeg \
    -hide_banner -loglevel error \
    -i "/data/$base" -i "/data/$pbase" \
    -map 0 -map 1 -c copy -c:v:1 png \
    -disposition:v:1 attached_pic \
    -y "/data/.cover-$base"
  mv "$dir/.cover-$base" "$dir/$base"
}

if [ -n "${1:-}" ]; then
  convert "$1"
else
  for f in *.webm; do [ -e "$f" ] && convert "$f"; done
fi
echo "done"
