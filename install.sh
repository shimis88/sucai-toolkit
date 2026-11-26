#!/usr/bin/env bash
# 素材工具一键安装（可重复运行，已装好的步骤会跳过）。
#   bash install.sh             精简版（约 2.5G）：抓取、批量、转写、压缩、GIF、图片去水印、本机人声分离
#   bash install.sh --full      再加 Florence-2 找无字 logo（多约 2G）
#   bash install.sh --no-gifski 不装 gifski（AGPL-3.0），转 GIF 改用 ffmpeg
#   bash install.sh --scrape-only  只装抓取和转写（约 1G，不装去水印和人声分离）
# 全部装在本仓库目录里（.venv-ml、fetcher/.venv、各 models/），删掉仓库目录即卸载。
# 只从官方源安装：Debian/Ubuntu apt、PyPI、download.pytorch.org、项目官方 GitHub Release、Hugging Face 官方仓库。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
FULL=0 GIFSKI=1 ML=1
# 没带参数时沿用上次的选项（sucai update 用）
if [[ $# -eq 0 && -f .install-flags ]]; then read -r -a _saved < .install-flags; set -- "${_saved[@]}"; fi
echo "$*" > .install-flags
for a in "$@"; do
  case "$a" in
    --full) FULL=1 ;;
    --no-gifski) GIFSKI=0 ;;
    --scrape-only) ML=0 ;;
    -h|--help) sed -n 2,9p "$0"; exit 0 ;;
    *) echo "未知选项: $a" >&2; exit 2 ;;
  esac
done
T0=$SECONDS
step() { printf '\n==> [%ss] %s\n' "$((SECONDS - T0))" "$*"; }
ok()   { echo "    ✓ $*"; }
warn() { echo "    ⚠ $*"; }
die()  { echo "    ✗ $*" >&2; exit 1; }

# ---------- 1. 系统工具 ----------
step "系统工具（ffmpeg、node、图片编解码器）"
SUDO=""
if [[ $EUID -ne 0 ]]; then sudo -n true 2>/dev/null && SUDO="sudo -n"; fi
can_apt() { command -v apt-get >/dev/null && { [[ $EUID -eq 0 ]] || [[ -n "$SUDO" ]]; }; }
declare -A PKG=( [ffmpeg]=ffmpeg [ffprobe]=ffmpeg [curl]=curl [git]=git [node]=nodejs [cwebp]=webp
  [gifsicle]=gifsicle [heif-convert]=libheif-examples [avifenc]=libavif-bin [jpegtran]=libjpeg-turbo-progs
  [pngquant]=pngquant [xz]=xz-utils [flock]=util-linux )
missing=()
for c in "${!PKG[@]}"; do command -v "$c" >/dev/null || missing+=("${PKG[$c]}"); done
if (( ${#missing[@]} )); then
  mapfile -t missing < <(printf '%s\n' "${missing[@]}" | sort -u)
  if can_apt; then
    $SUDO apt-get update -qq && DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq "${missing[@]}" >/dev/null
    ok "apt 装好: ${missing[*]}"
  else
    warn "缺少 ${missing[*]}，没有 apt/sudo 权限自动装，请手动安装（ffmpeg、curl、git 是必须的）"
  fi
else
  ok "都已安装"
fi
for c in ffmpeg ffprobe curl git python3; do command -v "$c" >/dev/null || die "缺少必须的命令: $c"; done

# ---------- 2. uv（官方 Python 包管理器）----------
step "uv"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
command -v uv >/dev/null || die "uv 安装失败"
ok "$(uv --version)"
export UV_LINK_MODE=copy

# ---------- 3. 抓取 + 转写环境 ----------
step "抓取环境 fetcher/.venv（yt-dlp、faster-whisper…）"
[[ -x fetcher/.venv/bin/python ]] || uv venv -q --python 3.12 fetcher/.venv
uv pip install -q --python fetcher/.venv/bin/python -U -r requirements/scrape.txt
ok "yt-dlp $(fetcher/.venv/bin/python -m yt_dlp --version)"

step "口播转写模型 faster-whisper small（约 460MB，首次下载）"
fetcher/.venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("Systran/faster-whisper-small")
PY
ok "已缓存"

# ---------- 4. 图片去水印 + 人声分离环境 ----------
if (( ML )); then
  step "图片去水印 / 人声分离环境 .venv-ml（CPU 版 torch，约 1.2G）"
  [[ -x .venv-ml/bin/python ]] || uv venv -q --python 3.12 .venv-ml
  MLPY=.venv-ml/bin/python
  uv pip install -q --python $MLPY --index-url https://download.pytorch.org/whl/cpu "torch==2.5.1+cpu"
  if (( FULL )); then
    uv pip install -q --python $MLPY --index-url https://download.pytorch.org/whl/cpu "torchvision==0.20.1+cpu"
  fi
  uv pip install -q --python $MLPY -r requirements/ml.txt
  # rapidocr 要 --no-deps，否则会拉进带 GUI 的完整版 opencv
  uv pip install -q --python $MLPY --no-deps rapidocr-onnxruntime==1.4.4
  (( FULL )) && uv pip install -q --python $MLPY -r requirements/ml-full.txt
  ok "torch $($MLPY -c 'import torch;print(torch.__version__)')、demucs、rapidocr"

  step "big-lama 补画模型（197MB，Apache-2.0）"
  LAMA=img-dewatermark/models/big-lama.pt
  LAMA_SHA=344c77bbcb158f17dd143070d1e789f38a66c04202311ae3a258ef66667a9ea9
  mkdir -p img-dewatermark/models
  if [[ ! -f $LAMA ]] || [[ "$(sha256sum $LAMA | cut -d' ' -f1)" != "$LAMA_SHA" ]]; then
    curl -fsSL --retry 3 -o $LAMA.part https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt
    [[ "$(sha256sum $LAMA.part | cut -d' ' -f1)" == "$LAMA_SHA" ]] || { rm -f $LAMA.part; die "big-lama 校验失败"; }
    mv $LAMA.part $LAMA
  fi
  ok "sha256 校验通过"

  if (( FULL )); then
    step "Florence-2-large（1.5GB，MIT）"
    HF_HOME="$ROOT/img-dewatermark/models/hf" $MLPY - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("microsoft/Florence-2-large", revision="21a599d414c4d928c9032694c424fb94458e3594")
PY
    ok "已下载（固定版本 21a599d）"
  fi

  step "Demucs htdemucs 模型（约 80MB）"
  HF_HOME="$ROOT/stem-split/models" $MLPY - <<'PY'
from demucs.pretrained import get_model
get_model("htdemucs")
PY
  ok "已缓存"
fi

# ---------- 5. gifski / oxipng 官方二进制 ----------
step "gifski / oxipng（官方 GitHub Release，sha256 校验）"
BIN=media-convert/bin; mkdir -p $BIN
fetch_bin() {  # name url sha256 path-in-tar
  local name=$1 url=$2 sha=$3 inner=$4 tmp
  [[ -x $BIN/$name ]] && { ok "$name 已有"; return; }
  tmp="$(mktemp -d)"
  curl -fsSL --retry 3 -o "$tmp/pkg" "$url"
  [[ "$(sha256sum "$tmp/pkg" | cut -d' ' -f1)" == "$sha" ]] || { rm -rf "$tmp"; die "$name 校验失败"; }
  tar --warning=no-unknown-keyword -xf "$tmp/pkg" -C "$tmp"
  install -m 755 "$tmp/$inner" "$BIN/$name"
  rm -rf "$tmp"; ok "$name 装好"
}
if [[ "$(uname -m)" == "x86_64" ]]; then
  if (( GIFSKI )); then
    fetch_bin gifski https://github.com/ImageOptim/gifski/releases/download/1.34.0/gifski-1.34.0.tar.xz \
      b9b6591aa163123d737353d9c8581efdf3234d28eeaa45329b31da905cd5a996 linux/gifski
  else
    rm -f $BIN/gifski; ok "跳过 gifski（转 GIF 用 ffmpeg）"
  fi
  fetch_bin oxipng https://github.com/oxipng/oxipng/releases/download/v10.2.1/oxipng-10.2.1-x86_64-unknown-linux-musl.tar.gz \
    1813750ef592c5350ca79c88f98b2c0876d05c826dc7156245256d4255c1ad17 oxipng-10.2.1-x86_64-unknown-linux-musl/oxipng
else
  warn "非 x86_64，跳过 gifski/oxipng（GIF 用 ffmpeg，PNG 不做无损再压）"
fi

# ---------- 6. 命令入口 + 工作目录 ----------
step "命令 sucai"
chmod +x sucai install.sh media-convert/convert.sh img-dewatermark/run.sh media-convert/tests/smoke.sh tests/*.sh
mkdir -p "$HOME/.local/bin"
ln -sf "$ROOT/sucai" "$HOME/.local/bin/sucai"
MEDIA="$("$ROOT/sucai" media)"; mkdir -p "$MEDIA"
ok "~/.local/bin/sucai → $ROOT/sucai；素材目录 $MEDIA（超过 7 天自动清）"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) warn "把 ~/.local/bin 加进 PATH，或直接用 $ROOT/sucai";; esac
uv cache clean -q >/dev/null 2>&1 || true

step "完成，用时 $((SECONDS - T0)) 秒，占用 $(du -sh "$ROOT" | cut -f1)（另有转写模型在 ~/.cache/huggingface）"
echo "    下一步：sucai doctor   （检查）"
echo "            sucai selftest （离线自测，约 1 分钟）"
