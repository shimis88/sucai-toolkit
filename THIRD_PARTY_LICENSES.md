# 运行时依赖 / Runtime dependencies

本仓库只含 shimis 自己写的源码（MIT，见 `LICENSE`）。下面这些是**使用时**由 `install.sh` 在你自己的机器上从官方来源下载的第三方软件，不随仓库分发，各自遵循原许可证。
Everything below is downloaded by `install.sh` from its official source onto your own machine. None of it is part of, or redistributed with, this repository.

## 需要留意的许可证 / Licenses to note

| 组件 | 许可证 | 说明 |
|---|---|---|
| gifski 1.34.0 | AGPL-3.0-or-later | 官方 Release 二进制，sha256 校验，只作为独立程序调用。不想装：`bash install.sh --no-gifski`，GIF 自动改用 ffmpeg。 |
| ffmpeg、gifsicle（系统包） | LGPL/GPL | 由 apt 安装。 |

## 全部依赖 / All

| 组件 | 版本 | 许可证 | 来源 |
|---|---|---|---|
| yt-dlp | ≥2026.11.23 | Unlicense | PyPI |
| yt-dlp-ejs | ≥0.8.0 | Unlicense AND MIT AND ISC | PyPI |
| requests | ≥2.31 | Apache-2.0 | PyPI |
| faster-whisper ≥1.2.1（含 ctranslate2、av、onnxruntime、tokenizers） | — | MIT（依赖各自 MIT / BSD / Apache-2.0） | PyPI |
| Whisper small（Systran/faster-whisper-small） | — | MIT | Hugging Face，首次转写或安装时下载 |
| torch 2.5.1+cpu | — | BSD-3-Clause | download.pytorch.org/whl/cpu |
| demucs 4.1.0 + htdemucs 权重 | — | MIT | PyPI；Hugging Face adefossez/HTDemucs |
| rapidocr-onnxruntime 1.4.4（含 PP-OCRv4 模型） | — | Apache-2.0 | PyPI |
| opencv-python-headless、numpy、pillow、shapely、pyclipper、onnxruntime | — | Apache-2.0 / BSD / MIT-CMU / MIT | PyPI |
| big-lama.pt（LaMa） | — | Apache-2.0 | github.com/Sanster/models Release，sha256 校验 |
| Florence-2-large（仅 `--full`，固定版本 21a599d） | — | MIT | Hugging Face microsoft/Florence-2-large |
| transformers 4.49、timm 1.0.15（仅 `--full`） | — | Apache-2.0 | PyPI |
| oxipng 10.2.1 | — | MIT | 官方 GitHub Release，sha256 校验 |
| webp、libheif、libavif、libjpeg-turbo、pngquant | — | BSD / LGPL / IJG | apt |
| uv（系统没有时） | — | MIT / Apache-2.0 | astral.sh 官方安装脚本 |

不使用任何付费接口，不读浏览器 cookie。No paid APIs, no browser cookies.
