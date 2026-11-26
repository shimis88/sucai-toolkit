"""素材自动清理：删掉超过 7 天的下载和成品。

只清两处，别的目录一概不碰：
  1. fetcher/output/   —— get.py / batch.py 不写 --out 时的默认输出
  2. 素材工作目录 $SUCAI_MEDIA（默认 /workspace/media，没有 /workspace 时用 ~/sucai-media）
get.py、batch.py 每次启动自动先清；其他流程用 `sucai clean` 或本脚本 -q。
"""
import os, shutil, sys, time
from pathlib import Path

KEEP_DAYS = int(os.environ.get("SUCAI_KEEP_DAYS", "7"))


def media_root() -> Path:
    env = os.environ.get("SUCAI_MEDIA")
    if env:
        return Path(env).expanduser()
    return Path("/workspace/media") if os.access("/workspace", os.W_OK) else Path.home() / "sucai-media"


ROOTS = (Path(__file__).resolve().parent / "output", media_root())


def cleanup(days: int = KEEP_DAYS) -> list:
    removed = []
    cutoff = time.time() - days * 86400
    for root in ROOTS:
        if not root.is_dir():
            continue
        for p in root.iterdir():
            if p.name.startswith("."):  # 隐藏文件（如 .keep）不删
                continue
            try:
                if p.stat().st_mtime < cutoff:
                    shutil.rmtree(p) if p.is_dir() else p.unlink()
                    removed.append(str(p))
            except OSError:
                pass
    return removed


if __name__ == "__main__":
    r = cleanup()
    if "-q" not in sys.argv or r:
        print("removed:", r)
