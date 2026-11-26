#!/usr/bin/env bash
# sucai selftest：离线自测（不联网）。现场生成素材，跑完自删。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d /tmp/sucai-selftest.XXXX)"; trap 'rm -rf "$T"' EXIT
echo "1/4 转换与压缩（media-convert）"
bash "$ROOT/media-convert/tests/smoke.sh"
echo "2/4 抓取模块单元测试"
for t in "$ROOT"/fetcher/tests/test_*.py; do "$ROOT/fetcher/.venv/bin/python" "$t" >/dev/null; done
echo "  ✓ fetcher 单元测试通过"
echo "3/4 图片去水印（合成一张右下角带 @账号 的图）"
"$ROOT/.venv-ml/bin/python" - "$T/wm.png" <<'PY'
import sys
from PIL import Image, ImageDraw, ImageFont
im = Image.new("RGB", (1280, 960))
d = ImageDraw.Draw(im)
for y in range(960):
    d.line([(0, y), (1280, y)], fill=(40 + y // 8, 90, 160 - y // 10))
d.ellipse([400, 250, 880, 730], fill=(230, 180, 60))
d.text((900, 880), "@sucai_test", fill=(255, 255, 255), font=ImageFont.load_default(size=40))
im.save(sys.argv[1])
PY
"$ROOT/img-dewatermark/run.sh" "$T/wm.png" --out "$T/dewm" | tee "$T/dewm.log"
ls "$T/dewm" | grep -q "_mask" || { echo "  ✗ 没去掉合成水印"; exit 1; }
echo "  ✓ 合成水印已去掉"
echo "4/4 人声分离（Demucs，5 秒合成音）"
ffmpeg -v error -f lavfi -i "sine=frequency=330:duration=5" -f lavfi -i "sine=frequency=880:duration=5" \
  -filter_complex amix=inputs=2 -ac 2 "$T/mix.wav"
"$ROOT/media-convert/convert.sh" stems -o "$T/stems" "$T/mix.wav"
[[ -s "$T/stems/人声.mp3" && -s "$T/stems/伴奏.mp3" ]] || { echo "  ✗ 没生成人声/伴奏"; exit 1; }
echo "全部通过 ✓"
