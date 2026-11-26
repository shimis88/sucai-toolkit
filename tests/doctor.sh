#!/usr/bin/env bash
# sucai doctor：只检查，不改任何东西。
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
pass=0 fail=0
chk() { if eval "$2" >/dev/null 2>&1; then echo "  ✓ $1"; pass=$((pass+1)); else echo "  ✗ $1${3:+  → $3}"; fail=$((fail+1)); fi; }
opt() { if eval "$2" >/dev/null 2>&1; then echo "  ✓ $1"; else echo "  - $1（可选，未装）${3:+  → $3}"; fi; }
echo "必需："
chk "ffmpeg / ffprobe" "command -v ffmpeg && command -v ffprobe" "apt install ffmpeg"
chk "抓取环境 (yt-dlp)" "$ROOT/fetcher/.venv/bin/python -m yt_dlp --version" "bash install.sh"
chk "口播转写 faster-whisper" "$ROOT/fetcher/.venv/bin/python -c 'import faster_whisper'" "bash install.sh"
chk "图片去水印环境" "$ROOT/.venv-ml/bin/python -c 'import torch, rapidocr_onnxruntime, cv2'" "bash install.sh"
chk "big-lama 模型" "test -s $ROOT/img-dewatermark/models/big-lama.pt" "bash install.sh"
chk "人声分离 demucs" "test -x $ROOT/.venv-ml/bin/demucs" "bash install.sh"
echo "可选："
opt "node（YouTube 需要）" "command -v node" "apt install nodejs"
opt "gifski（更好的 GIF）" "test -x $ROOT/media-convert/bin/gifski"
opt "oxipng（PNG 无损压缩）" "test -x $ROOT/media-convert/bin/oxipng"
opt "图片编解码 cwebp/heif/avif" "command -v cwebp && command -v heif-convert && command -v avifenc"
opt "Florence-2（找无字 logo）" "test -d $ROOT/img-dewatermark/models/hf/hub/models--microsoft--Florence-2-large" "bash install.sh --full"
echo "素材目录：$("$ROOT/sucai" media)"
echo "结果：必需项 $pass 通过，$fail 缺失"
exit $(( fail > 0 ))
