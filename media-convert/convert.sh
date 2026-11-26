#!/usr/bin/env bash
# media-convert entry point.
# Usage: convert.sh <command> [options] -o OUTPUT INPUT...
set -euo pipefail

MC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$MC_ROOT/lib/common.sh"
# shellcheck source=lib/gif.sh
source "$MC_ROOT/lib/gif.sh"
# shellcheck source=lib/video.sh
source "$MC_ROOT/lib/video.sh"
# shellcheck source=lib/image.sh
source "$MC_ROOT/lib/image.sh"
# shellcheck source=lib/stems.sh
source "$MC_ROOT/lib/stems.sh"
# shellcheck source=lib/xpost.sh
source "$MC_ROOT/lib/xpost.sh"

usage() {
  cat <<'U'
素材格式转换  media-convert/convert.sh（或 sucai convert）

用法:
  convert.sh to-gif    [选项] -o 输出.gif   视频或图片...
  convert.sh to-mp4    [选项] -o 输出.mp4   视频        转成能到处播的 H.264
  convert.sh to-size   --max-mb N -o 出.mp4 视频        压到指定大小
  convert.sh to-x      [--crf 19|20] -o 出.mp4 视频     压成适合发 X（长边1920、slow crf20、SSIM 自检）
  convert.sh audio     [--format mp3|aac] -o 输出 视频  抽音轨
  convert.sh cover     [--time 秒] -o 输出.jpg 视频     抽封面
  convert.sh to-jpg    [--quality 92] [--max-dim N] -o 出.jpg 图片
  convert.sh to-png    [--max-dim N] -o 出.png 图片
  convert.sh to-webp   [--quality 90] [--lossless] -o 出.webp 图片
  convert.sh to-avif   [--quality 80] [--lossless] -o 出.avif 图片
  convert.sh compress  [--lossy] [--max-mb N] -o 输出 图片或视频
  convert.sh stems     [--format mp3|wav] -o 目录 视频或音频  人声/伴奏分离（本机 Demucs）
  convert.sh info      文件

默认行为见同目录 README.md。各命令加 -h 看选项。

例子:
  convert.sh to-gif  -o /tmp/a.gif video.mp4
  convert.sh to-gif  --start 3 --end 10 --speed 2 -o /tmp/a.gif video.mp4
  convert.sh to-mp4  -o /tmp/play.mp4  hevc.mp4
  convert.sh to-size --max-mb 25 -o /tmp/chat.mp4 video.mp4
  convert.sh to-jpg  -o /tmp/a.jpg  photo.webp
  convert.sh compress -o /tmp/a.jpg  photo.jpg
  convert.sh audio   --format mp3 -o /tmp/a.mp3 video.mp4
  convert.sh stems   -o /tmp/stems video.mp4
U
}

cmd="${1:-}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$cmd" in
  ""|-h|--help|help) usage; exit 0 ;;
  to-gif|gif) cmd_to_gif "$@" ;;
  to-mp4|mp4) cmd_to_mp4 "$@" ;;
  to-size|size) cmd_to_size "$@" ;;
  to-x|x) cmd_to_x "$@" ;;
  audio|to-mp3|to-aac) 
    if [[ "$cmd" == "to-mp3" ]]; then
      cmd_audio --format mp3 "$@"
    elif [[ "$cmd" == "to-aac" ]]; then
      cmd_audio --format aac "$@"
    else
      cmd_audio "$@"
    fi
    ;;
  cover|thumb) cmd_cover "$@" ;;
  to-jpg|to-jpeg|jpg|jpeg) cmd_to_format jpg "$@" ;;
  to-png|png) cmd_to_format png "$@" ;;
  to-webp|webp) cmd_to_format webp "$@" ;;
  to-avif|avif) cmd_to_format avif "$@" ;;
  compress|minify) cmd_compress "$@" ;;
  info) cmd_info "$@" ;;
  stems|stem|split) cmd_stems "$@" ;;
  *)
    die "未知命令: $cmd
运行 convert.sh --help 看用法"
    ;;
esac
