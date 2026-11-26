#!/usr/bin/env bash
# 图片去水印入口。用法见 README.md。环境由仓库根目录的 install.sh 装在 ../.venv-ml
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/../.venv-ml/bin/python"
[[ -x "$PY" ]] || { echo "还没安装：先在仓库根目录运行 bash install.sh" >&2; exit 1; }
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-$(nproc 2>/dev/null || echo 4)}"
PYTHONPATH="$DIR${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m dewm.cli "$@"
