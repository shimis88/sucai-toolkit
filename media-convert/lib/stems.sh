#!/usr/bin/env bash
# Vocal / accompaniment (BGM) separation with local Demucs (CPU).
# Paths are relative to the repo root (one level above media-convert/).

SUCAI_ROOT="$(cd "$MC_ROOT/.." && pwd)"
STEM_SPLIT_ROOT="$SUCAI_ROOT/stem-split"
STEM_VENV="$SUCAI_ROOT/.venv-ml"
STEM_DEMUCS="$STEM_VENV/bin/demucs"
STEM_HF_HOME="$STEM_SPLIT_ROOT/models"

stems_usage() {
  cat <<'U'
用法:
  convert.sh stems [选项] -o 输出目录 输入

从视频或音频里把人声和伴奏分开。默认得到 人声.mp3 和 伴奏.mp3（320kbps）。

选项:
  --format mp3|wav   默认 mp3
  --bitrate N        MP3 码率，默认 320

用 Demucs htdemucs 在本机 CPU 上分离，3 分钟的歌约 1 分钟。
整条音轨（不分离）请用:  convert.sh audio --format mp3 -o 出.mp3 视频
U
}

_need_demucs() {
  if [[ ! -x "$STEM_DEMUCS" ]]; then
    die "还没装人声分离工具（$STEM_DEMUCS）。先在仓库根目录运行 bash install.sh"
  fi
}

cmd_stems() {
  local out="" fmt="mp3" bitrate="320" model="htdemucs"
  local inputs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -o|--output) out="$2"; shift 2 ;;
      --format) fmt="$2"; shift 2 ;;
      --bitrate) bitrate="$2"; shift 2 ;;
      -h|--help) stems_usage; return 0 ;;
      -*) die "未知选项: $1
运行 convert.sh stems -h 看用法" ;;
      *) inputs+=("$1"); shift ;;
    esac
  done
  (( ${#inputs[@]} == 1 )) || die "stems 只接受一个输入文件"
  require_infile "${inputs[0]}"
  has_audio "${inputs[0]}" || die "这个文件没有音轨: ${inputs[0]}"
  [[ -n "$out" ]] || die "请用 -o 指定输出目录"
  if [[ -e "$out" && ! -d "$out" ]]; then
    die "-o 必须是目录（会在里面写出 人声 和 伴奏）: $out"
  fi
  mkdir -p "$out"
  case "$fmt" in
    mp3|wav) ;;
    *) die "--format 只能是 mp3 或 wav" ;;
  esac
  [[ "$bitrate" =~ ^[0-9]+$ ]] || die "--bitrate 必须是数字"
  _need_demucs
  need ffmpeg

  local in="${inputs[0]}"
  local t0=$SECONDS
  setup_workdir

  # Demucs 读视频不稳，统一先抽成 44.1k 立体声 WAV
  local wav="$MC_WORK/input.wav"
  log "抽出音轨…"
  ffmpeg -hide_banner -loglevel error -nostdin -y -i "$in" \
    -vn -ac 2 -ar 44100 -c:a pcm_s16le "$wav"

  local demucs_out="$MC_WORK/separated"
  mkdir -p "$demucs_out"
  local args=( "$STEM_DEMUCS" -n "$model" --two-stems vocals -d cpu
    -o "$demucs_out" --filename "{stem}.{ext}" )
  if [[ "$fmt" == "mp3" ]]; then
    args+=( --mp3 --mp3-bitrate "$bitrate" --mp3-preset 2 )
  else
    args+=( --int24 )
  fi

  log "分离人声和伴奏（Demucs $model，CPU）…"
  # 模型缓存在工具目录，不写到家目录
  HF_HOME="$STEM_HF_HOME" \
  HUGGINGFACE_HUB_CACHE="$STEM_HF_HOME/hub" \
  "${args[@]}" "$wav"

  local found_vocals="" found_acc=""
  local f
  while IFS= read -r -d '' f; do
    case "$(basename "$f")" in
      vocals.*) found_vocals="$f" ;;
      no_vocals.*) found_acc="$f" ;;
    esac
  done < <(find "$demucs_out" -type f \( -name 'vocals.*' -o -name 'no_vocals.*' \) -print0)

  [[ -n "$found_vocals" && -n "$found_acc" ]] || die "Demucs 跑完了，但没找到 vocals / no_vocals 输出"

  local voc_out="$out/人声.$fmt"
  local acc_out="$out/伴奏.$fmt"
  # 不要覆盖用户原文件
  require_outfile "$voc_out" "$in"
  require_outfile "$acc_out" "$in"
  cp -f "$found_vocals" "$voc_out"
  cp -f "$found_acc" "$acc_out"

  local sec note
  sec="$(elapsed "$t0")"
  if [[ "$fmt" == "mp3" ]]; then
    note="Demucs ${model}（本机 CPU），mp3 ${bitrate}k"
  else
    note="Demucs ${model}（本机 CPU），24-bit wav"
  fi
  print_result "$voc_out" "$sec" "$note"
  print_result "$acc_out" "$sec" "$note"
}
