"""模型路径集中放这里，保证离线运行。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
LAMA_PATH = MODELS / "big-lama.pt"
FLORENCE_ID = "microsoft/Florence-2-large"
FLORENCE_REV = "21a599d414c4d928c9032694c424fb94458e3594"  # install.sh 下载的同一个版本

os.environ.setdefault("HF_HOME", str(MODELS / "hf"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
