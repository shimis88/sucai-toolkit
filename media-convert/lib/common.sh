#!/usr/bin/env bash
# Shared helpers for media-convert. Sourced by convert.sh, not run alone.

MC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$MC_ROOT/bin:$PATH"

CHAT_MAX_MB=25
X_VIDEO_MAX_MB=512
X_GIF_MAX_MB=15

die() { echo "错误: $*" >&2; exit 1; }
log() { echo "$*" >&2; }
need() { command -v "$1" >/dev/null 2>&1 || die "缺少命令: $1"; }

abs_path() {
  local p="$1"
  if command -v realpath >/dev/null 2>&1; then
    realpath -m "$p"
  else
    readlink -f "$p" 2>/dev/null || {
      local d b
      d="$(cd "$(dirname "$p")" && pwd)"
      b="$(basename "$p")"
      echo "$d/$b"
    }
  fi
}

same_file() {
  local a b
  a="$(abs_path "$1")"
  b="$(abs_path "$2")"
  [[ -e "$1" && -e "$2" ]] && [[ "$a" == "$b" ]]
}

require_infile() {
  local f="$1"
  [[ -n "$f" ]] || die "没有指定输入文件"
  [[ -f "$f" ]] || die "找不到输入文件: $f"
}

require_outfile() {
  local out="$1"
  shift
  [[ -n "$out" ]] || die "请用 -o 指定输出文件"
  local parent
  parent="$(dirname "$out")"
  mkdir -p "$parent"
  local inp
  for inp in "$@"; do
    if [[ -e "$inp" ]] && same_file "$out" "$inp"; then
      die "拒绝覆盖原文件（输出不能跟输入是同一个路径）: $out"
    fi
  done
}

bytes_of() { wc -c < "$1" | tr -d ' '; }

human_bytes() {
  local n="$1"
  if command -v numfmt >/dev/null 2>&1; then
    numfmt --to=iec --suffix=B --format='%.1f' "$n" | sed 's/\.0B/B/'
  else
    echo "${n}B"
  fi
}

# Elapsed seconds from $SECONDS start mark. Call as: t0=$SECONDS; ...; elapsed "$t0"
elapsed() {
  local start="${1:-0}"
  echo $((SECONDS - start))
}

ffprobe_val() {
  # ffprobe_val FILE stream|format KEY
  local file="$1" section="$2" key="$3"
  ffprobe -v error -select_streams "${4:-}" \
    -show_entries "${section}=${key}" -of default=nw=1:nk=1 "$file" 2>/dev/null | head -n1
}

video_duration() {
  local d
  d="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$1" 2>/dev/null | head -n1)"
  [[ -n "$d" && "$d" != "N/A" ]] || die "读不到视频时长: $1"
  echo "$d"
}

video_width()  { ffprobe -v error -select_streams v:0 -show_entries stream=width  -of default=nw=1:nk=1 "$1" | head -n1; }
video_height() { ffprobe -v error -select_streams v:0 -show_entries stream=height -of default=nw=1:nk=1 "$1" | head -n1; }

video_fps() {
  local r
  r="$(ffprobe -v error -select_streams v:0 -show_entries stream=avg_frame_rate -of default=nw=1:nk=1 "$1" | head -n1)"
  python3 -c "import fractions,sys
r=sys.argv[1].strip()
if not r or r in ('0/0','N/A','0','nan'):
    print(0)
else:
    print(int(round(float(fractions.Fraction(r)))))
" "$r" 2>/dev/null || echo 0
}

video_vcodec() { ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$1" | head -n1; }
video_acodec() { ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$1" | head -n1; }

has_audio() {
  local c
  c="$(video_acodec "$1")"
  [[ -n "$c" ]]
}

image_wh() {
  # prints "WIDTH HEIGHT"
  local csv
  csv="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$1" | head -n1)"
  echo "${csv//,/ }"
}

# Detect a still-image / video kind from extension + ffprobe + magic.
detect_kind() {
  local f="$1"
  local ext base mime
  ext="$(echo "${f##*.}" | tr 'A-Z' 'a-z')"
  case "$ext" in
    jpg|jpeg) echo jpg; return ;;
    png) echo png; return ;;
    webp) echo webp; return ;;
    heic|heif) echo heic; return ;;
    avif) echo avif; return ;;
    jxl) echo jxl; return ;;
    gif) echo gif; return ;;
    tif|tiff) echo tiff; return ;;
    bmp) echo bmp; return ;;
    mp4|mov|m4v|webm|mkv|avi|ts) echo video; return ;;
    mp3|m4a|aac|wav|flac|ogg|opus) echo audio; return ;;
  esac
  if [[ -f "$f" ]]; then
    mime="$(file -b --mime-type "$f" 2>/dev/null || true)"
    case "$mime" in
      image/jpeg) echo jpg; return ;;
      image/png) echo png; return ;;
      image/webp) echo webp; return ;;
      image/heic|image/heif) echo heic; return ;;
      image/avif) echo avif; return ;;
      image/jxl) echo jxl; return ;;
      image/gif) echo gif; return ;;
      video/*) echo video; return ;;
      audio/*) echo audio; return ;;
    esac
    # HEIC/AVIF often look like video/mp4 to `file`
    if command -v python3 >/dev/null 2>&1; then
      local brand
      brand="$(python3 - "$f" <<'PY'
import sys
p=sys.argv[1]
try:
    with open(p,'rb') as f:
        data=f.read(32)
    if data[4:8]==b'ftyp':
        brand=data[8:12].decode('latin1','ignore').lower()
        print(brand)
except Exception:
    pass
PY
)"
      case "$brand" in
        heic|heix|hevc|hevx|mif1|msf1) echo heic; return ;;
        avif|avis) echo avif; return ;;
      esac
    fi
  fi
  echo unknown
}

setup_workdir() {
  MC_WORK="$(mktemp -d /tmp/media-convert.XXXXXX)"
  export MC_WORK
  cleanup_workdir() {
    if [[ -n "${MC_WORK:-}" && -d "${MC_WORK}" ]]; then
      rm -rf "${MC_WORK}"
    fi
  }
  trap cleanup_workdir EXIT
}

print_result() {
  local out="$1" seconds="$2" note="${3:-}"
  local sz
  sz="$(bytes_of "$out")"
  printf '完成  %s  %ss  %s%s\n' "$(human_bytes "$sz")" "$seconds" "$out" "${note:+  ($note)}"
}
