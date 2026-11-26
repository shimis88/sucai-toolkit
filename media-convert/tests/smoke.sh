#!/usr/bin/env bash
# 冒烟测试：现场用 ffmpeg 生成测试素材，跑一遍常用命令，结束自动删掉。不依赖任何旧文件。
set -euo pipefail
CV="$(cd "$(dirname "$0")/.." && pwd)/convert.sh"
T="$(mktemp -d /tmp/mc-smoke.XXXX)"; trap 'rm -rf "$T"' EXIT
ffmpeg -v error -f lavfi -i testsrc2=size=2560x1440:rate=30 -f lavfi -i sine=frequency=440 -t 3 \
  -c:v libx264 -pix_fmt yuv420p -c:a aac "$T/land.mp4"
ffmpeg -v error -f lavfi -i testsrc2=size=1080x2340:rate=30 -t 2 -c:v libx264 -pix_fmt yuv420p "$T/port.mp4"
ffmpeg -v error -f lavfi -i testsrc2=size=1200x800 -frames:v 1 "$T/still.png"
"$CV" to-x    -o "$T/x_land.mp4" "$T/land.mp4"
"$CV" to-x    -o "$T/x_port.mp4" "$T/port.mp4"
"$CV" to-gif  -o "$T/a.gif"      "$T/land.mp4"
"$CV" to-mp4  -o "$T/a.mp4"      "$T/land.mp4"
"$CV" to-size --max-mb 1 -o "$T/s.mp4" "$T/land.mp4"
"$CV" audio   --format mp3 -o "$T/a.mp3" "$T/land.mp4"
"$CV" cover   -o "$T/c.jpg"      "$T/land.mp4"
"$CV" to-jpg  -o "$T/i.jpg"      "$T/still.png"
"$CV" to-webp -o "$T/i.webp"     "$T/still.png"
"$CV" compress -o "$T/i2.png"    "$T/still.png"
for f in x_land.mp4 x_port.mp4 a.gif a.mp4 s.mp4 a.mp3 c.jpg i.jpg i.webp i2.png; do
  [[ -s "$T/$f" ]] || { echo "失败: $f 没生成"; exit 1; }
done
echo "横屏 to-x: $(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$T/x_land.mp4")（应为 1920,1080）"
echo "竖屏 to-x: $(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$T/x_port.mp4")（应为 886,1920）"
echo "冒烟测试全部通过"
