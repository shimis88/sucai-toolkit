# 人声 / 伴奏分离（本机 Demucs）

`sucai stems` 的本机部分：Demucs 4.1.0（MIT，`adefossez/demucs`）+ 模型 htdemucs，CPU 版 PyTorch，装在仓库根目录 `.venv-ml`（和图片去水印共用）。
模型约 80MB，由 install.sh 从 Hugging Face 官方仓库下载，缓存在本目录 `models/`（已 .gitignore）。
5 秒测试片约 7 秒，3 分钟的歌约 1 分钟（8 核 CPU）。
