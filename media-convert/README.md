# 素材格式转换（media-convert）

在云电脑上把图片、视频、GIF 互相转换，并按专业主流方法压缩。不改原文件，结果另存。

入口：

```bash
media-convert/convert.sh <命令>   # 或 sucai convert <命令> [选项] -o 输出文件 输入文件
```

## 用户一句话时默认怎么做

| 你说的 | 实际做的 |
|---|---|
| 转 GIF | 用 **gifski**（画质最好的主流做法），无限循环，尽量保持原分辨率。自动压到 **15MB 以内**（X 的 GIF 上限）。默认质量 90，视频帧率最多 20。做完再用 gifsicle 无损压一遍。 |
| 转 JPG | WebP / HEIC / AVIF / PNG 等到高质量 JPEG（质量 92，渐进，优化过的 Huffman 表）。透明底填白。已经是 JPG 且不改尺寸时，只做 **jpegtran 无损优化**，不再重新编码。 |
| 转成能播的 | HEVC 或其他不好播的编码 → **H.264 + AAC 的 MP4**，CRF 18（视觉上几乎无损），带 faststart，方便点开就播。已经是 H.264+AAC 的 MP4 就只做流复制，不重编码。 |
| 压缩（没指定大小） | 视频：CRF 20 重编码，画质仍然很高，通常比原片小。JPG：jpegtran 无损优化。PNG：oxipng 无损优化。GIF：gifsicle `-O3`。 |
| 压到能发聊天 | 视频两遍编码，目标 **25MB**，保留音轨。 |
| 压到能发 X | 用 `to-x`：长边缩到 1920（横屏即 `scale=1920:-2`，竖屏按高度，只缩不放），lanczos，libx264 `slow` CRF 20（`--crf 19` 更稳），high profile，yuv420p，AAC 160k，faststart；做完自动算 SSIM（≥0.97 合格）。GIF 仍按 15MB。 |
| 提取 BGM / 抽音轨 | 用 `audio` 把视频里的**整条音轨**导成 MP3（默认，LAME VBR q=2，大约 190kbps）或 AAC/M4A。人声和伴奏会在一起。 |
| 分离人声和伴奏 | 用 `stems`：默认本机 **Demucs v4（htdemucs）**。得到 **人声.mp3** 和 **伴奏.mp3**（默认 320kbps，可 `--format wav`）。只要整条音轨时用 `audio`。 |

可选：截取片段（`--start` `--end`）、倍速（`--speed 2`）、指定宽或帧率、强制有损（`--lossy`，PNG 才会动用 pngquant）。

## 常用例子

```bash
# 视频转 GIF（自动 ≤15MB）
convert.sh to-gif -o /tmp/a.gif video.mp4

# 只取 3 到 10 秒，两倍速
convert.sh to-gif --start 3 --end 10 --speed 2 -o /tmp/a.gif video.mp4

# 多张图拼成循环 GIF
convert.sh to-gif --fps 8 -o /tmp/a.gif img1.jpg img2.jpg img3.png

# HEVC / 不兼容编码 → 能播的 MP4
convert.sh to-mp4 -o /tmp/play.mp4 video.mp4

# 压成适合发 X（自动打印体积和 SSIM）
convert.sh to-x -o /tmp/x.mp4 video.mp4

# 压到 25MB，保留声音
convert.sh to-size --max-mb 25 -o /tmp/chat.mp4 video.mp4

# 抽整条音轨（人声+伴奏在一起）、抽封面
convert.sh audio --format mp3 -o /tmp/a.mp3 video.mp4
convert.sh cover --time 1 -o /tmp/cover.jpg video.mp4

# 分离人声和伴奏（输出目录里会有 人声.mp3、伴奏.mp3）
convert.sh stems -o /tmp/stems video.mp4
convert.sh stems --format wav -o /tmp/stems song.mp3
convert.sh stems --fast -o /tmp/stems song.mp3  # 只用本机 Demucs，约 40 秒

# 图片互转
convert.sh to-jpg  -o /tmp/a.jpg  photo.webp
convert.sh to-png  --max-dim 1080 -o /tmp/a.png photo.heic
convert.sh to-webp -o /tmp/a.webp photo.jpg
convert.sh compress -o /tmp/a.jpg photo.jpg
```

各命令加 `-h` 看全部选项。

## 用了什么方法，为什么是默认

- **视频 → GIF**：gifski。它给每一帧单独选调色板，并做时间抖动，风景、人脸、渐变比 ffmpeg 单套调色板更干净。这是目前公认画质最好的做法。ffmpeg 的两步 palettegen/paletteuse 留作备用（`--engine ffmpeg`），在界面录屏、纯色文字上有时文件更小。
- **GIF 再缩小**：gifsicle `-O3`，无损，通常再省一点点体积。
- **视频转码 / 压体积**：系统自带的 ffmpeg + libx264。兼容性默认 H.264 + AAC 的 MP4；视觉近无损用 CRF 18–20；要卡死体积时用两遍码率控制，不用会截断片子的 `-fs`。不需要重编码时只做流复制。抽音频默认 LAME MP3 VBR q=2（大约 190kbps）。
- **人声 / 伴奏分离**：Demucs 4.1.0（默认模型 **htdemucs**，CPU 版 PyTorch，装在仓库的 `.venv-ml`），两声部模式（`--two-stems vocals`）。
- **静态图互转**：WebP 用官方 `cwebp` / `dwebp`，HEIC 用 `heif-convert`（libheif），AVIF 用官方 `avifenc` / `avifdec`，JPEG 用 libjpeg-turbo 的 `cjpeg` / `jpegtran`。
- **保画质压缩**：JPEG 先走 jpegtran 无损；PNG 用 oxipng 无损（目前主流的 PNG 优化器）。只有你要更小、允许画质下降时，才用 pngquant（有损，会掉颜色数）。

没有装 mozjpeg / jpegli：两者目前都没有好用的官方 Linux 现成二进制，Debian 源里也没有；libjxl-tools 只有 cjxl/djxl，没有 cjpegli。JPEG 有损回退用 libjpeg-turbo 的高质量 `cjpeg`。效果已经很好，只是同等画质下文件可能比 mozjpeg/jpegli 略大一点。

## 注意

- **不改原文件**。输出路径如果跟输入是同一个文件，会直接拒绝。
- gifski 是 **AGPL-3.0-or-later**，由 install.sh 从官方 Release 单独下载（本仓库不分发它的二进制）。介意的话装时加 `--no-gifski`，转 GIF 会自动改用 ffmpeg 调色板方案。
- 还不能把图 **编码成 HEIC**：解码没问题（iPhone 照片转 JPG 可以），但系统里没有 HEVC 的 HEIF 编码插件，故意没再装一大串编码器。
- 有的电脑播放器打不开 HEVC。遇到这种情况用 `to-mp4`。
- 工具版本和许可证见仓库根目录 `THIRD_PARTY_LICENSES.md`。
- 分离别人的歌曲，只适合自用素材；不会因此获得发行权。
