#!/usr/bin/env bash
# Video transcode, size-target compression, audio extract, cover frame.

video_usage() {
  cat <<'U'
用法:
  convert.sh to-mp4   [选项] -o 输出.mp4 输入
  convert.sh to-size  --max-mb N [选项] -o 输出.mp4 输入
  convert.sh audio    [--format mp3|aac] -o 输出 输入
  convert.sh cover    [--time 秒] -o 输出.jpg 输入

to-mp4 / to-size 选项:
  --crf N          画质，18 几乎无损，20 高画质更小。to-mp4 默认 18
  --preset NAME    x264 预设，默认 medium
  --force          已经是 H.264+AAC 的 MP4 也强制重编码
  --max-mb N       目标体积上限（to-size 必填；to-mp4 也可加）
U
}

# True if the file is already a widely playable H.264 + AAC (or no audio) MP4/MOV.
is_playable_mp4() {
  local f="$1"
  local fmt v a
  fmt="$(ffprobe -v error -show_entries format=format_name -of default=nw=1:nk=1 "$f" | head -n1)"
  v="$(video_vcodec "$f")"
  a="$(video_acodec "$f")"
  [[ "$fmt" == *mp4* || "$fmt" == *mov* || "$fmt" == *m4a* ]] || return 1
  [[ "$v" == "h264" ]] || return 1
  if [[ -n "$a" && "$a" != "aac" ]]; then
    return 1
  fi
  return 0
}

_ffmpeg_base() { echo ffmpeg -hide_banner -loglevel error -nostdin -y; }

# Remux with faststart, stream copy.
_remux_faststart() {
  local in="$1" out="$2"
  ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in" -c copy -movflags +faststart "$out"
}

_x264_encode() {
  local in="$1" out="$2" crf="$3" preset="$4"
  local args=( ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in"
    -map 0:v:0 -c:v libx264 -crf "$crf" -preset "$preset" -pix_fmt yuv420p )
  if has_audio "$in"; then
    local a
    a="$(video_acodec "$in")"
    if [[ "$a" == "aac" ]]; then
      args+=( -map 0:a:0 -c:a copy )
    else
      args+=( -map 0:a:0 -c:a aac -b:a 192k )
    fi
  fi
  args+=( -movflags +faststart "$out" )
  "${args[@]}"
}

# Two-pass (or one-pass -fs as last resort already avoided) to hit a byte cap.
_x264_twopass_size() {
  local in="$1" out="$2" max_bytes="$3" preset="$4"
  local dur vbitrate audio_bps=0
  dur="$(video_duration "$in")"
  if has_audio "$in"; then
    audio_bps=128000
  fi
  # 96% of the budget, minus audio, safety margin for container overhead.
  vbitrate="$(python3 -c "
dur=float('$dur')
budget=int('$max_bytes')*8*0.96
audio=int('$audio_bps')
if dur<=0:
    print(150000); raise SystemExit
vb=int((budget/dur)-audio)
print(max(vb, 120000))
")"
  log "目标 $(human_bytes "$max_bytes")，时长 ${dur}s，视频码率 ${vbitrate} bps"
  local passlog="$MC_WORK/ffpass"
  ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in" \
    -map 0:v:0 -c:v libx264 -b:v "$vbitrate" -preset "$preset" -pix_fmt yuv420p \
    -pass 1 -passlogfile "$passlog" -an -f mp4 /dev/null
  local args=( ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in"
    -map 0:v:0 -c:v libx264 -b:v "$vbitrate" -preset "$preset" -pix_fmt yuv420p
    -pass 2 -passlogfile "$passlog" )
  if has_audio "$in"; then
    args+=( -map 0:a:0 -c:a aac -b:a 128k )
  fi
  args+=( -movflags +faststart "$out" )
  "${args[@]}"

  # If still over (mux overhead / rate control), retry with a tighter budget or a smaller scale.
  local sz w h
  sz="$(bytes_of "$out")"
  if (( sz <= max_bytes )); then
    return 0
  fi
  log "第一轮两遍编码后是 $(human_bytes "$sz")，略超上限，收紧码率再来一遍"
  vbitrate="$(python3 -c "
print(max(int($vbitrate * $max_bytes / $sz * 0.92), 100000))
")"
  ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in" \
    -map 0:v:0 -c:v libx264 -b:v "$vbitrate" -preset "$preset" -pix_fmt yuv420p \
    -pass 1 -passlogfile "$passlog" -an -f mp4 /dev/null
  args=( ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in"
    -map 0:v:0 -c:v libx264 -b:v "$vbitrate" -preset "$preset" -pix_fmt yuv420p
    -pass 2 -passlogfile "$passlog" )
  if has_audio "$in"; then
    args+=( -map 0:a:0 -c:a aac -b:a 128k )
  fi
  args+=( -movflags +faststart "$out" )
  "${args[@]}"
  sz="$(bytes_of "$out")"
  if (( sz <= max_bytes )); then
    return 0
  fi
  # Last resort: scale to 720p-ish and tighter rate
  w="$(video_width "$in")"
  h="$(video_height "$in")"
  log "仍然超限 ($(human_bytes "$sz"))，缩小分辨率再压"
  local scale
  if (( w >= h )); then
    scale="scale='min(1280,iw)':-2:flags=lanczos"
  else
    scale="scale=-2:'min(1280,ih)':flags=lanczos"
  fi
  vbitrate="$(python3 -c "print(max(int($vbitrate * 0.8), 80000))")"
  ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in" \
    -map 0:v:0 -vf "$scale" -c:v libx264 -b:v "$vbitrate" -preset "$preset" -pix_fmt yuv420p \
    -pass 1 -passlogfile "$passlog" -an -f mp4 /dev/null
  args=( ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in"
    -map 0:v:0 -vf "$scale" -c:v libx264 -b:v "$vbitrate" -preset "$preset" -pix_fmt yuv420p
    -pass 2 -passlogfile "$passlog" )
  if has_audio "$in"; then
    args+=( -map 0:a:0 -c:a aac -b:a 128k )
  fi
  args+=( -movflags +faststart "$out" )
  "${args[@]}"
}

cmd_to_mp4() {
  local out="" crf="18" preset="medium" force=0 max_mb=""
  local inputs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o|--output) out="$2"; shift 2 ;;
      --crf) crf="$2"; shift 2 ;;
      --preset) preset="$2"; shift 2 ;;
      --force) force=1; shift ;;
      --max-mb) max_mb="$2"; shift 2 ;;
      -h|--help) video_usage; return 0 ;;
      -*) die "未知选项: $1" ;;
      *) inputs+=("$1"); shift ;;
    esac
  done
  (( ${#inputs[@]} == 1 )) || die "to-mp4 只接受一个输入文件"
  require_infile "${inputs[0]}"
  require_outfile "$out" "${inputs[0]}"
  need ffmpeg
  setup_workdir
  local t0=$SECONDS in="${inputs[0]}"

  if [[ -n "$max_mb" ]]; then
    cmd_to_size --max-mb "$max_mb" --preset "$preset" -o "$out" "$in"
    return
  fi

  if (( force == 0 )) && is_playable_mp4 "$in"; then
    _remux_faststart "$in" "$out"
    print_result "$out" "$(elapsed "$t0")" "流复制 + faststart，未重编码"
    return
  fi

  _x264_encode "$in" "$out" "$crf" "$preset"
  print_result "$out" "$(elapsed "$t0")" "libx264 crf=$crf preset=$preset"
}

cmd_to_size() {
  local out="" preset="medium" max_mb=""
  local inputs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o|--output) out="$2"; shift 2 ;;
      --preset) preset="$2"; shift 2 ;;
      --max-mb) max_mb="$2"; shift 2 ;;
      --crf) shift 2 ;; # ignored in size mode
      --force) shift ;;
      -h|--help) video_usage; return 0 ;;
      -*) die "未知选项: $1" ;;
      *) inputs+=("$1"); shift ;;
    esac
  done
  [[ -n "$max_mb" ]] || die "to-size 需要 --max-mb（聊天建议 25，X 视频上限 512）"
  (( ${#inputs[@]} == 1 )) || die "to-size 只接受一个输入文件"
  require_infile "${inputs[0]}"
  require_outfile "$out" "${inputs[0]}"
  need ffmpeg
  setup_workdir
  local t0=$SECONDS in="${inputs[0]}"
  local max_bytes
  max_bytes="$(python3 -c "print(int(float('$max_mb')*1024*1024))")"
  local src_sz
  src_sz="$(bytes_of "$in")"
  if (( src_sz <= max_bytes )) && is_playable_mp4 "$in"; then
    _remux_faststart "$in" "$out"
    print_result "$out" "$(elapsed "$t0")" "已小于 ${max_mb}MB，流复制"
    return
  fi
  if (( src_sz <= max_bytes )); then
    # Under size but not playable: transcode at high quality, should stay under if we're lucky
    _x264_encode "$in" "$out" "18" "$preset"
    if (( $(bytes_of "$out") <= max_bytes )); then
      print_result "$out" "$(elapsed "$t0")" "libx264 crf=18，已小于 ${max_mb}MB"
      return
    fi
    log "高画质转码后超过 ${max_mb}MB，改用两遍码率控制"
  fi
  _x264_twopass_size "$in" "$out" "$max_bytes" "$preset"
  if (( $(bytes_of "$out") > max_bytes )); then
    log "警告: 最终 $(human_bytes "$(bytes_of "$out")")，仍略超 ${max_mb}MB"
  fi
  print_result "$out" "$(elapsed "$t0")" "两遍压到约 ${max_mb}MB"
}

cmd_audio() {
  local out="" fmt=""
  local inputs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o|--output) out="$2"; shift 2 ;;
      --format) fmt="$2"; shift 2 ;;
      -h|--help) video_usage; return 0 ;;
      -*) die "未知选项: $1" ;;
      *) inputs+=("$1"); shift ;;
    esac
  done
  (( ${#inputs[@]} == 1 )) || die "audio 只接受一个输入文件"
  require_infile "${inputs[0]}"
  has_audio "${inputs[0]}" || die "这个文件没有音轨: ${inputs[0]}"
  if [[ -z "$fmt" ]]; then
    if [[ "$out" == *.m4a || "$out" == *.aac ]]; then
      fmt="aac"
    else
      fmt="mp3"
    fi
  fi
  if [[ -z "$out" ]]; then
    die "请用 -o 指定输出文件"
  fi
  require_outfile "$out" "${inputs[0]}"
  need ffmpeg
  local t0=$SECONDS
  case "$fmt" in
    mp3)
      ffmpeg -hide_banner -loglevel error -nostdin -y -i "${inputs[0]}" -vn -c:a libmp3lame -q:a 2 "$out"
      print_result "$out" "$(elapsed "$t0")" "mp3 VBR q=2（约 190kbps，高质量）"
      ;;
    aac|m4a)
      ffmpeg -hide_banner -loglevel error -nostdin -y -i "${inputs[0]}" -vn -c:a aac -b:a 192k -movflags +faststart "$out"
      print_result "$out" "$(elapsed "$t0")" "aac 192k"
      ;;
    *) die "--format 只能是 mp3 或 aac" ;;
  esac
}

cmd_cover() {
  local out="" time=""
  local inputs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o|--output) out="$2"; shift 2 ;;
      --time) time="$2"; shift 2 ;;
      -h|--help) video_usage; return 0 ;;
      -*) die "未知选项: $1" ;;
      *) inputs+=("$1"); shift ;;
    esac
  done
  (( ${#inputs[@]} == 1 )) || die "cover 只接受一个输入文件"
  require_infile "${inputs[0]}"
  require_outfile "$out" "${inputs[0]}"
  need ffmpeg
  local t0=$SECONDS
  local args=( ffmpeg -hide_banner -loglevel error -nostdin -y -i "${inputs[0]}" )
  # After -i for accurate seek; default first frame.
  if [[ -n "$time" ]]; then
    args=( ffmpeg -hide_banner -loglevel error -nostdin -y -ss "$time" -i "${inputs[0]}" )
  fi
  # High-quality JPEG via libjpeg-turbo when possible
  local ppm_pipe=0
  if command -v cjpeg >/dev/null 2>&1; then
    args+=( -frames:v 1 -f image2pipe -vcodec ppm - )
    "${args[@]}" | cjpeg -quality 92 -optimize -progressive -outfile "$out"
  else
    args+=( -frames:v 1 -q:v 2 "$out" )
    "${args[@]}"
  fi
  print_result "$out" "$(elapsed "$t0")" "封面帧 quality=92"
}
