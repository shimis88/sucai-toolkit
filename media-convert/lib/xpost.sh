#!/usr/bin/env bash
# to-x: 压成适合发 X 的 MP4，并用 SSIM 自检画质。
# 固定参数（2026-11 定）：长边最多 1920（横屏即 scale=1920:-2，竖屏按高度），lanczos，
# libx264 -preset slow -crf 19~20 -profile:v high -pix_fmt yuv420p，AAC 128~160k，+faststart。

xpost_usage() {
  cat <<'U'
用法:
  convert.sh to-x [--crf 19|20] [--abr 160k] [--max-side 1920] -o 输出.mp4 视频
默认 crf 20、音频 160k、长边 1920（只缩小不放大）。做完打印体积和 SSIM（对比同尺寸缩放后的原片）。
SSIM ≥ 0.97 算画质合格；低于会提示改用 --crf 19。
U
}

cmd_to_x() {
  local out="" crf=20 abr=160k maxside=1920 in=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o) out="$2"; shift 2 ;;
      --crf) crf="$2"; shift 2 ;;
      --abr) abr="$2"; shift 2 ;;
      --max-side) maxside="$2"; shift 2 ;;
      -h|--help) xpost_usage; return 0 ;;
      *) in="$1"; shift ;;
    esac
  done
  [[ -n "$in" && -n "$out" ]] || { xpost_usage; die "需要 -o 输出 和 输入视频"; }
  require_infile "$in"; require_outfile "$out" "$in"
  local w h vf
  w="$(video_width "$in")"; h="$(video_height "$in")"
  if (( w >= h )); then
    vf="scale='min(${maxside},iw)':-2:flags=lanczos"
  else
    vf="scale=-2:'min(${maxside},ih)':flags=lanczos"
  fi
  local args=( ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in" -map 0:v:0
    -vf "$vf" -c:v libx264 -preset slow -crf "$crf" -profile:v high -pix_fmt yuv420p )
  if has_audio "$in"; then
    args+=( -map 0:a:0 -c:a aac -b:a "$abr" )
  fi
  args+=( -movflags +faststart "$out" )
  log "压缩中：${w}x${h} → 长边≤${maxside}，crf ${crf}"
  "${args[@]}"
  local ow oh ssim
  ow="$(video_width "$out")"; oh="$(video_height "$out")"
  ssim="$(ffmpeg -hide_banner -nostdin -i "$out" -i "$in" -lavfi \
    "[1:v]scale=${ow}:${oh}:flags=lanczos,format=yuv420p[r];[0:v]format=yuv420p[d];[d][r]ssim" \
    -f null - 2>&1 | grep -o 'All:[0-9.]*' | tail -1 | cut -d: -f2)"
  log "完成：${w}x${h} $(human_bytes "$(bytes_of "$in")") → ${ow}x${oh} $(human_bytes "$(bytes_of "$out")")，SSIM ${ssim:-?}"
  # 压完反而更大，且原片本来就是 X 能直接收的 H.264(+AAC)、尺寸不超：直接用原片（只重排 faststart，不重编码）
  local vc ac
  vc="$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$in")"
  ac="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$in")"
  if (( $(bytes_of "$out") >= $(bytes_of "$in") )) && [[ "$vc" == h264 && ( -z "$ac" || "$ac" == aac ) ]] \
     && (( w <= maxside && h <= maxside )); then
    ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in" -map 0:v:0 -map '0:a:0?' -c copy -movflags +faststart "$out"
    log "原片已经适合发 X 且更小，改用原片（无损，只加 faststart）：$(human_bytes "$(bytes_of "$out")")"
    echo "$out"; return 0
  fi
  if [[ -n "$ssim" ]] && python3 -c "import sys;sys.exit(0 if float('$ssim')<0.97 else 1)"; then
    if [[ "$crf" == 20 ]]; then
      log "SSIM 低于 0.97，自动用 crf 19 重压…"
      cmd_to_x --crf 19 --abr "$abr" --max-side "$maxside" -o "$out" "$in"; return
    fi
    log "提示：SSIM 仍低于 0.97，可试 --crf 18"
  fi
  echo "$out"
}
