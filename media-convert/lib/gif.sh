#!/usr/bin/env bash
# Video or image sequence → GIF. Default engine: gifski, then gifsicle -O3.
# ffmpeg palettegen/paletteuse is the fallback (--engine ffmpeg).

gif_usage() {
  cat <<'U'
用法: convert.sh to-gif [选项] -o 输出.gif 输入视频或图片...

选项:
  --start SEC        从第几秒开始（仅视频）
  --end SEC          到第几秒结束（仅视频）
  --fps N            帧率。视频默认：原帧率（最高 20）；图片序列默认 8
  --width N          最宽边像素。默认保持原宽（gifski 默认会缩到约 800，这里会关掉）
  --speed N          倍速，例如 2 表示两倍速（仅视频）
  --quality 1-100    gifski 质量，默认 90
  --max-mb N         自动压到不超过 N MB，默认 15（X 的 GIF 上限）。0 表示不限制
  --engine gifski|ffmpeg
  --no-optimize      做完后不用 gifsicle 再无损压一遍
  --loop N           循环次数：0 无限（默认），-1 只播一次
U
}

# Write a y4m stream (stdout) from a trimmed video.
# gifski handles fps (--fps) and speed (--fast-forward) itself.
_gif_ffmpeg_y4m() {
  local input="$1" start="$2" end="$3"
  local args=( ffmpeg -hide_banner -loglevel error -nostdin -y -i "$input" )
  [[ -n "$start" ]] && args+=( -ss "$start" )
  [[ -n "$end" ]] && args+=( -to "$end" )
  args+=( -an -map 0:v:0 -pix_fmt yuv420p -f yuv4mpegpipe - )
  "${args[@]}"
}

_gif_ffmpeg_palette() {
  local input="$1" out="$2" start="$3" end="$4" speed="$5" fps="$6" width="$7"
  # Explicit [0:v] + labeled output; do not mix -map 0:v:0 with -filter_complex.
  local vf="[0:v]"
  if [[ -n "$speed" && "$speed" != "1" && "$speed" != "1.0" ]]; then
    vf+="setpts=PTS/${speed},"
  fi
  [[ -n "$fps" ]] && vf+="fps=${fps},"
  [[ -n "$width" ]] && vf+="scale=${width}:-2:flags=lanczos,"
  vf+="split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a[out]"
  local args=( ffmpeg -hide_banner -loglevel error -nostdin -y )
  [[ -n "$start" ]] && args+=( -ss "$start" )
  [[ -n "$end" ]] && args+=( -to "$end" )
  args+=( -i "$input" -an -filter_complex "$vf" -map "[out]" "$out" )
  "${args[@]}"
}

_gif_optimize() {
  local src="$1" dest="$2"
  need gifsicle
  gifsicle -O3 "$src" -o "$dest"
}

# Encode once with current settings. Writes $out (already final path or temp).
_gif_encode_once() {
  local engine="$1" input_kind="$2" out="$3"
  local start="$4" end="$5" speed="$6" fps="$7" width="$8" quality="$9" loop="${10}"
  shift 10
  local inputs=("$@")

  if [[ "$engine" == "ffmpeg" ]]; then
    [[ "$input_kind" == "video" ]] || die "ffmpeg 引擎目前只用于视频转 GIF，图片序列请用 gifski"
    _gif_ffmpeg_palette "${inputs[0]}" "$out" "$start" "$end" "$speed" "$fps" "$width"
    return
  fi

  need gifski
  local gs=( gifski --output "$out" --quality "$quality" --repeat "$loop" --quiet )
  [[ -n "$fps" ]] && gs+=( --fps "$fps" )
  [[ -n "$width" ]] && gs+=( --width "$width" )
  if [[ "$input_kind" == "video" ]]; then
    # Prefer official y4m pipe. Apply speed in gifski when no fps resampling conflict.
    if [[ -n "$speed" && "$speed" != "1" && "$speed" != "1.0" ]]; then
      gs+=( --fast-forward "$speed" )
    fi
    _gif_ffmpeg_y4m "${inputs[0]}" "$start" "$end" | "${gs[@]}" -
  else
    gs+=( --no-sort )
    "${gs[@]}" "${inputs[@]}"
  fi
}

cmd_to_gif() {
  local out="" start="" end="" fps="" width="" speed="1" quality="90"
  local max_mb="$X_GIF_MAX_MB" engine="gifski" optimize=1 loop="0"
  local inputs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o|--output) out="$2"; shift 2 ;;
      --start) start="$2"; shift 2 ;;
      --end) end="$2"; shift 2 ;;
      --fps) fps="$2"; shift 2 ;;
      --width) width="$2"; shift 2 ;;
      --speed) speed="$2"; shift 2 ;;
      --quality) quality="$2"; shift 2 ;;
      --max-mb) max_mb="$2"; shift 2 ;;
      --engine) engine="$2"; shift 2 ;;
      --no-optimize) optimize=0; shift ;;
      --loop) loop="$2"; shift 2 ;;
      -h|--help) gif_usage; return 0 ;;
      --) shift; inputs+=("$@"); break ;;
      -*) die "未知选项: $1" ;;
      *) inputs+=("$1"); shift ;;
    esac
  done
  (( ${#inputs[@]} )) || die "请指定输入文件"
  require_outfile "$out" "${inputs[@]}"
  local f
  for f in "${inputs[@]}"; do require_infile "$f"; done
  need ffmpeg
  [[ "$engine" == "gifski" || "$engine" == "ffmpeg" ]] || die "--engine 只能是 gifski 或 ffmpeg"

  local input_kind
  if (( ${#inputs[@]} > 1 )); then
    input_kind="images"
  else
    local k
    k="$(detect_kind "${inputs[0]}")"
    case "$k" in
      video|gif) input_kind="video" ;;
      jpg|jpeg|png|webp|heic|avif|jxl|tiff|bmp) input_kind="images" ;;
      *)
        # If ffprobe sees a duration and video stream, treat as video
        if ffprobe -v error -select_streams v:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "${inputs[0]}" | grep -q video \
           && ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "${inputs[0]}" | grep -Eq '^[0-9]'; then
          input_kind="video"
        else
          input_kind="images"
        fi
        ;;
    esac
  fi
  # 没装 gifski（安装时选了 --no-gifski）：视频自动改用 ffmpeg 调色板
  if [[ "$engine" == "gifski" ]] && ! command -v gifski >/dev/null 2>&1 && [[ "$input_kind" == "video" ]]; then
    log "没装 gifski，改用 ffmpeg 调色板转 GIF"
    engine="ffmpeg"
  fi

  # Image sequence may be webp/heic etc. — gifski wants PNG (or y4m / png/jpg).
  setup_workdir

  if [[ "$input_kind" == "images" ]]; then
    # gifski 要求每一帧同尺寸；先全部解成 PNG，再统一缩放到目标宽高。
    local converted=() i=0 tmp img k
    local max_w=0 max_h=0 wh w h
    for img in "${inputs[@]}"; do
      need ffmpeg
      tmp="$(printf '%s/raw_%04d.png' "$MC_WORK" "$i")"
      k="$(detect_kind "$img")"
      if [[ "$k" == "png" ]]; then
        cp -f "$img" "$tmp"
      else
        ffmpeg -hide_banner -loglevel error -y -i "$img" -frames:v 1 "$tmp" \
          || die "这张图转不成 PNG，gifski 没法用: $img"
      fi
      wh="$(image_wh "$tmp")"
      w="${wh%% *}"; h="${wh##* }"
      (( w > max_w )) && max_w=$w
      (( h > max_h )) && max_h=$h
      converted+=("$tmp")
      i=$((i+1))
    done
    local target_w="$max_w" target_h="$max_h"
    if [[ -n "$width" ]]; then
      target_w="$width"
      # 按最大宽高比保持比例估算高度
      target_h="$(python3 -c "print(max(1, int(round($max_h * $width / float($max_w)))))")"
    fi
    local unified=() j=0 u
    for tmp in "${converted[@]}"; do
      u="$(printf '%s/frame_%04d.png' "$MC_WORK" "$j")"
      # 等比缩小后居中贴到固定画布，避免 gifski 报 Frame has wrong size
      ffmpeg -hide_banner -loglevel error -y -i "$tmp"         -vf "scale=${target_w}:${target_h}:force_original_aspect_ratio=decrease:flags=lanczos,pad=${target_w}:${target_h}:(ow-iw)/2:(oh-ih)/2:color=black"         -frames:v 1 "$u" || die "统一帧尺寸失败: $tmp"
      unified+=("$u")
      j=$((j+1))
    done
    inputs=("${unified[@]}")
    # 必须把宽度传给 gifski，否则它会把画面默认缩到大约 800x600
    width="$target_w"
    if [[ -z "$fps" ]]; then
      fps=8
    fi
  else
    local src_w src_fps
    src_w="$(video_width "${inputs[0]}")"
    src_fps="$(video_fps "${inputs[0]}")"
    if [[ -z "$width" ]]; then
      width="$src_w"
    fi
    if [[ -z "$fps" ]]; then
      if (( src_fps > 20 )); then
        fps=20
      elif (( src_fps > 0 )); then
        fps="$src_fps"
      else
        fps=15
      fi
    fi
  fi

  local t0=$SECONDS
  local raw="$MC_WORK/raw.gif"
  local try_width="$width" try_fps="$fps" try_q="$quality"
  local max_bytes=0
  if [[ "$max_mb" != "0" && -n "$max_mb" ]]; then
    max_bytes="$(python3 -c "print(int(float('$max_mb')*1024*1024))")"
  fi

  _gif_encode_once "$engine" "$input_kind" "$raw" "$start" "$end" "$speed" "$try_fps" "$try_width" "$try_q" "$loop" "${inputs[@]}"
  local sz
  sz="$(bytes_of "$raw")"

  # Auto-fit under max size: shrink width, then fps, then quality.
  if (( max_bytes > 0 && sz > max_bytes )); then
    log "第一版 $(human_bytes "$sz")，超过 ${max_mb}MB，开始自动缩小……"
    local widths=() fps_list=() q_list=()
    local base_w="${try_width:-720}"
    local w
    for w in "$base_w" 720 540 480 360 240; do
      if [[ -n "$w" ]] && (( w > 0 && w <= base_w )); then
        widths+=("$w")
      fi
    done
    # unique, descending
    widths=($(printf '%s\n' "${widths[@]}" | awk '!a[$0]++'))
    local f
    for f in "$try_fps" 15 12 10 8; do
      if [[ -n "$f" ]]; then
        fps_list+=("$f")
      fi
    done
    fps_list=($(printf '%s\n' "${fps_list[@]}" | awk '!a[$0]++'))
    q_list=("$try_q" 85 80 70)
    q_list=($(printf '%s\n' "${q_list[@]}" | awk '!a[$0]++'))

    local best="$raw" best_sz="$sz" done_fit=0
    local W F Q cand
    for Q in "${q_list[@]}"; do
      for F in "${fps_list[@]}"; do
        for W in "${widths[@]}"; do
          # skip the exact first attempt already done
          if [[ "$W" == "$try_width" && "$F" == "$try_fps" && "$Q" == "$try_q" ]]; then
            continue
          fi
          cand="$MC_WORK/try_${W}_${F}_${Q}.gif"
          log "尝试 width=$W fps=$F quality=$Q"
          if ! _gif_encode_once "$engine" "$input_kind" "$cand" "$start" "$end" "$speed" "$F" "$W" "$Q" "$loop" "${inputs[@]}"; then
            continue
          fi
          sz="$(bytes_of "$cand")"
          if (( sz < best_sz )); then
            best="$cand"; best_sz="$sz"
          fi
          if (( sz <= max_bytes )); then
            raw="$cand"; done_fit=1
            break 3
          fi
        done
      done
    done
    if (( done_fit == 0 )); then
      raw="$best"
      log "警告: 已经尽力缩小，仍然是 $(human_bytes "$best_sz")，超过 ${max_mb}MB"
    fi
  fi

  if (( optimize )); then
    if ! _gif_optimize "$raw" "$out"; then
      log "gifsicle 优化失败，使用未优化版本"
      cp -f "$raw" "$out"
    else
      # If optimize somehow grew the file, keep the smaller one
      if (( $(bytes_of "$out") > $(bytes_of "$raw") )); then
        cp -f "$raw" "$out"
      fi
    fi
  else
    cp -f "$raw" "$out"
  fi

  local note="engine=$engine"
  if [[ "$engine" == "gifski" ]]; then
    note="gifski q${quality}"
  fi
  print_result "$out" "$(elapsed "$t0")" "$note"
}
