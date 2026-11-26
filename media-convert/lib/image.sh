#!/usr/bin/env bash
# Still-image convert + quality-preserving compress.

image_usage() {
  cat <<'U'
用法:
  convert.sh to-jpg|to-png|to-webp|to-avif [选项] -o 输出 输入
  convert.sh compress [--lossy] [--max-mb N] [--max-dim N] -o 输出 输入

选项:
  --quality N     编码质量。jpg 默认 92，webp 默认 90，avif 默认 80（AVIF 的 80 已是很高画质）
  --max-dim N     最长边不超过 N 像素（按比例缩小）
  --lossless      webp/avif/png 走无损（文件通常更大）
  --lossy         compress 时允许有损：jpg 重编码、png 用 pngquant
  --max-mb N      compress 时的体积上限
U
}

_scale_filter() {
  local dim="$1"
  echo "scale=min(iw\,${dim}):min(ih\,${dim}):force_original_aspect_ratio=decrease:flags=lanczos"
}

# Decode any still image to a PNG in $2, applying optional max-dim.
decode_to_png() {
  local in="$1" out="$2" max_dim="${3:-}"
  local kind
  kind="$(detect_kind "$in")"
  local raw="$out"
  if [[ -n "$max_dim" ]]; then
    raw="${out%.png}.src.png"
  fi

  case "$kind" in
    png)
      if [[ -n "$max_dim" ]]; then
        raw="$out" # scale in one step below from original
        :
      else
        cp -f "$in" "$out"
        return 0
      fi
      # If scaling, fall through to ffmpeg from the original
      if [[ -n "$max_dim" ]]; then
        ffmpeg -hide_banner -loglevel error -y -i "$in" -vf "$(_scale_filter "$max_dim")" -frames:v 1 "$out"
        return
      fi
      ;;
    webp)
      need dwebp
      if ! dwebp "$in" -o "$raw" >/dev/null 2>&1; then
        ffmpeg -hide_banner -loglevel error -y -i "$in" -frames:v 1 "$raw" || die "WebP 解码失败: $in"
      fi
      ;;
    heic)
      need heif-convert
      heif-convert -q 100 "$in" "$raw" >/dev/null || die "HEIC 解码失败: $in（确认是 HEIC/HEIF 图片）"
      ;;
    avif)
      need avifdec
      avifdec "$in" "$raw" >/dev/null || die "AVIF 解码失败: $in"
      ;;
    jpg|jpeg|gif|tiff|bmp|jxl|unknown|video)
      need ffmpeg
      ffmpeg -hide_banner -loglevel error -y -i "$in" -frames:v 1 "$raw" || die "解码失败: $in"
      ;;
    *)
      need ffmpeg
      ffmpeg -hide_banner -loglevel error -y -i "$in" -frames:v 1 "$raw" || die "解码失败: $in"
      ;;
  esac

  if [[ -n "$max_dim" && "$raw" != "$out" ]]; then
    ffmpeg -hide_banner -loglevel error -y -i "$raw" -vf "$(_scale_filter "$max_dim")" -frames:v 1 "$out"
    rm -f "$raw"
  fi
}

# Flatten transparency onto white, write PPM to stdout for cjpeg.
_png_to_jpg() {
  local png="$1" jpg="$2" quality="$3"
  need cjpeg
  # Composite on white so transparent pixels don't turn black.
  ffmpeg -hide_banner -loglevel error -y -i "$png" \
    -filter_complex "color=white,format=rgb24[bg];[0:v]format=rgba[fg];[bg][fg]scale2ref[bg][fg];[bg][fg]overlay=format=auto,format=rgb24" \
    -frames:v 1 -f image2pipe -vcodec ppm - \
    | cjpeg -quality "$quality" -optimize -progressive -outfile "$jpg"
}

_png_to_webp() {
  local png="$1" webp="$2" quality="$3" lossless="$4"
  need cwebp
  local args=( cwebp -quiet -m 6 -metadata icc )
  if [[ "$lossless" == "1" ]]; then
    args+=( -lossless )
  else
    args+=( -q "$quality" )
  fi
  args+=( "$png" -o "$webp" )
  "${args[@]}"
}

_png_to_avif() {
  local png="$1" avif="$2" quality="$3" lossless="$4"
  need avifenc
  local args=( avifenc --speed 6 --yuv 420 )
  if [[ "$lossless" == "1" ]]; then
    args+=( -q 100 )
  else
    args+=( -q "$quality" )
  fi
  args+=( "$png" "$avif" )
  "${args[@]}" >/dev/null
}

_png_to_png() {
  local png="$1" dest="$2"
  need oxipng
  # Never overwrite input in place; --out writes a new file.
  if same_file "$png" "$dest"; then
    die "拒绝覆盖原文件: $dest"
  fi
  # oxipng may refuse if dest exists? We'll write to temp then mv
  local tmp="${dest}.oxi.$$.png"
  oxipng -o 2 --strip safe --out "$tmp" "$png" >/dev/null
  mv -f "$tmp" "$dest"
}

cmd_to_format() {
  local target="$1"
  shift
  local out="" quality="" max_dim="" lossless=0
  local inputs=()
  case "$target" in
    jpg) quality=92 ;;
    webp) quality=90 ;;
    avif) quality=80 ;;
    png) quality="" ;;
  esac
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o|--output) out="$2"; shift 2 ;;
      --quality) quality="$2"; shift 2 ;;
      --max-dim) max_dim="$2"; shift 2 ;;
      --lossless) lossless=1; shift ;;
      --lossy) shift ;;
      --max-mb) shift 2 ;;
      -h|--help) image_usage; return 0 ;;
      -*) die "未知选项: $1" ;;
      *) inputs+=("$1"); shift ;;
    esac
  done
  (( ${#inputs[@]} == 1 )) || die "图片转换一次只接受一个输入文件"
  require_infile "${inputs[0]}"
  require_outfile "$out" "${inputs[0]}"
  setup_workdir
  local t0=$SECONDS in="${inputs[0]}" kind
  kind="$(detect_kind "$in")"

  # Fast path: JPEG → JPEG, no resize: lossless rewrite with jpegtran.
  if [[ "$target" == "jpg" && -z "$max_dim" && ( "$kind" == "jpg" || "$kind" == "jpeg" ) ]]; then
    need jpegtran
    jpegtran -optimize -progressive -copy all -outfile "$out" "$in"
    print_result "$out" "$(elapsed "$t0")" "jpegtran 无损优化"
    return
  fi

  local png="$MC_WORK/src.png"
  decode_to_png "$in" "$png" "$max_dim"

  case "$target" in
    jpg) _png_to_jpg "$png" "$out" "${quality:-92}" ;;
    png) _png_to_png "$png" "$out" ;;
    webp) _png_to_webp "$png" "$out" "${quality:-90}" "$lossless" ;;
    avif) _png_to_avif "$png" "$out" "${quality:-80}" "$lossless" ;;
    *) die "不支持的目标格式: $target" ;;
  esac
  print_result "$out" "$(elapsed "$t0")" "转成 ${target}"
}

_jpeg_compress() {
  local in="$1" out="$2" lossy="$3" max_bytes="${4:-0}" quality="${5:-90}"
  need jpegtran
  # Always try lossless first.
  jpegtran -optimize -progressive -copy all -outfile "$out" "$in"
  if (( max_bytes > 0 && $(bytes_of "$out") > max_bytes )) || [[ "$lossy" == "1" ]]; then
    local q="$quality" cand="$MC_WORK/jpgq.jpg" best="$out"
    if [[ "$lossy" != "1" && "$max_bytes" -le 0 ]]; then
      return
    fi
    # If lossless already under cap and not forced lossy, keep it.
    if [[ "$lossy" != "1" ]] && (( max_bytes > 0 && $(bytes_of "$out") <= max_bytes )); then
      return
    fi
    local try
    for try in "$q" 88 85 80 75 70 60; do
      decode_to_png "$in" "$MC_WORK/j.png"
      _png_to_jpg "$MC_WORK/j.png" "$cand" "$try"
      if (( max_bytes <= 0 )); then
        # forced lossy, take first (requested / default) quality
        cp -f "$cand" "$out"
        return
      fi
      if (( $(bytes_of "$cand") <= max_bytes )); then
        cp -f "$cand" "$out"
        return
      fi
      best="$cand"
    done
    cp -f "$best" "$out"
    log "警告: JPEG 有损压缩后仍大于上限"
  fi
}

_png_compress() {
  local in="$1" out="$2" lossy="$3" max_bytes="${4:-0}" max_dim="${5:-}"
  local src="$in"
  if [[ -n "$max_dim" ]]; then
    src="$MC_WORK/scaled.png"
    decode_to_png "$in" "$src" "$max_dim"
  fi
  _png_to_png "$src" "$out"
  if [[ "$lossy" == "1" ]] || (( max_bytes > 0 && $(bytes_of "$out") > max_bytes )); then
    if [[ "$lossy" != "1" ]] && (( max_bytes > 0 && $(bytes_of "$out") <= max_bytes )); then
      return
    fi
    need pngquant
    local pq="$MC_WORK/pq.png"
    # quality 70-95: don't go below 70 if avoidable
    if pngquant --quality 70-95 --speed 1 --output "$pq" -- "$src"; then
      _png_to_png "$pq" "$out"
    elif pngquant --quality 40-95 --speed 1 --output "$pq" -- "$src"; then
      _png_to_png "$pq" "$out"
      log "警告: 为了体积使用了更低的 pngquant 质量"
    fi
    if (( max_bytes > 0 && $(bytes_of "$out") > max_bytes )); then
      log "警告: PNG 压缩后仍大于上限"
    fi
  fi
}

cmd_compress() {
  local out="" lossy=0 max_mb="" max_dim="" quality=""
  local inputs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o|--output) out="$2"; shift 2 ;;
      --lossy) lossy=1; shift ;;
      --lossless) lossy=0; shift ;;
      --max-mb) max_mb="$2"; shift 2 ;;
      --max-dim) max_dim="$2"; shift 2 ;;
      --quality) quality="$2"; shift 2 ;;
      -h|--help) image_usage; return 0 ;;
      -*) die "未知选项: $1" ;;
      *) inputs+=("$1"); shift ;;
    esac
  done
  (( ${#inputs[@]} == 1 )) || die "compress 只接受一个输入文件"
  require_infile "${inputs[0]}"
  require_outfile "$out" "${inputs[0]}"
  setup_workdir
  local t0=$SECONDS in="${inputs[0]}" kind max_bytes=0
  kind="$(detect_kind "$in")"
  if [[ -n "$max_mb" ]]; then
    max_bytes="$(python3 -c "print(int(float('$max_mb')*1024*1024))")"
  fi

  case "$kind" in
    jpg|jpeg)
      _jpeg_compress "$in" "$out" "$lossy" "$max_bytes" "${quality:-90}"
      print_result "$out" "$(elapsed "$t0")" "JPEG 压缩（默认 jpegtran 无损）"
      ;;
    png)
      _png_compress "$in" "$out" "$lossy" "$max_bytes" "$max_dim"
      if [[ "$lossy" == "1" ]]; then
        print_result "$out" "$(elapsed "$t0")" "PNG 压缩（pngquant 有损 + oxipng）"
      else
        print_result "$out" "$(elapsed "$t0")" "PNG 压缩（oxipng 无损）"
      fi
      ;;
    webp)
      # Re-encode with cwebp; default high quality, or lossless if not --lossy
      decode_to_png "$in" "$MC_WORK/w.png" "$max_dim"
      if [[ "$lossy" == "1" ]]; then
        _png_to_webp "$MC_WORK/w.png" "$out" "${quality:-80}" 0
      else
        _png_to_webp "$MC_WORK/w.png" "$out" "${quality:-90}" 0
      fi
      print_result "$out" "$(elapsed "$t0")" "WebP 再压缩"
      ;;
    gif)
      need gifsicle
      gifsicle -O3 "$in" -o "$out"
      print_result "$out" "$(elapsed "$t0")" "gifsicle -O3"
      ;;
    video)
      if [[ -z "$max_mb" ]]; then
        # Quality-preserving shrink: CRF 20
        cmd_to_mp4 --crf 20 --force -o "$out" "$in"
      else
        cmd_to_size --max-mb "$max_mb" -o "$out" "$in"
      fi
      ;;
    *)
      # Decode and write a high-quality JPEG or PNG based on output suffix
      local ext
      ext="$(echo "${out##*.}" | tr 'A-Z' 'a-z')"
      case "$ext" in
        jpg|jpeg) cmd_to_format jpg -o "$out" ${max_dim:+--max-dim "$max_dim"} "$in" ;;
        png) cmd_to_format png -o "$out" ${max_dim:+--max-dim "$max_dim"} "$in" ;;
        webp) cmd_to_format webp -o "$out" ${max_dim:+--max-dim "$max_dim"} "$in" ;;
        avif) cmd_to_format avif -o "$out" ${max_dim:+--max-dim "$max_dim"} "$in" ;;
        *) die "不知道怎么压缩这种文件（${kind}）。请指定 -o 的后缀，或先转成 jpg/png/mp4" ;;
      esac
      ;;
  esac
}

cmd_info() {
  local f="${1:-}"
  require_infile "$f"
  need ffprobe
  local kind sz
  kind="$(detect_kind "$f")"
  sz="$(human_bytes "$(bytes_of "$f")")"
  echo "文件: $f"
  echo "类型: $kind"
  echo "大小: $sz"
  ffprobe -hide_banner "$f" 2>&1 | sed 's/^/  /'
}
