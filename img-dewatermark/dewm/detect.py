"""找水印候选框：RapidOCR（PP-OCR，中文准、CPU 不到 1 秒）找文字，Florence-2 开放词汇检测找「watermark」logo。"""
from unittest.mock import patch

import torch
from PIL import Image

from . import paths

_model = None
_proc = None


def florence_available() -> bool:
    """精简安装不带 Florence-2（找无字 logo 用，约 1.5GB）；没装时只靠文字识别找水印。"""
    try:
        import transformers  # noqa: F401
    except ImportError:
        return False
    return (paths.MODELS / "hf" / "hub" / "models--microsoft--Florence-2-large").is_dir()


def _no_flash_attn_for(original):
    # Florence-2 的远程代码会强行 import flash_attn，CPU 上没有，这里去掉。
    def get_imports(filename):
        return [i for i in original(filename) if i != "flash_attn"]
    return get_imports


def _load():
    global _model, _proc
    if _model is None:
        from transformers import AutoModelForCausalLM, AutoProcessor
        from transformers.dynamic_module_utils import get_imports
        with patch("transformers.dynamic_module_utils.get_imports", _no_flash_attn_for(get_imports)):
            _model = AutoModelForCausalLM.from_pretrained(
                paths.FLORENCE_ID, revision=paths.FLORENCE_REV, trust_remote_code=True,
                torch_dtype=torch.float32, attn_implementation="eager").eval()
            _proc = AutoProcessor.from_pretrained(paths.FLORENCE_ID, revision=paths.FLORENCE_REV, trust_remote_code=True)
    return _model, _proc


@torch.inference_mode()
def _run(img, task, text=""):
    model, proc = _load()
    inputs = proc(text=task + text, images=img, return_tensors="pt")
    ids = model.generate(input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"],
                         max_new_tokens=512, num_beams=int(__import__("os").environ.get("DEWM_BEAMS", "3")), do_sample=False)
    out = proc.batch_decode(ids, skip_special_tokens=False)[0]
    return proc.post_process_generation(out, task=task, image_size=img.size)[task]


def detect_objects(img: Image.Image, prompt: str):
    """开放词汇检测，返回 [(x1,y1,x2,y2,'ov:'+prompt)]。没装 Florence-2 时返回空。"""
    if not florence_available():
        return []
    r = _run(img, "<OPEN_VOCABULARY_DETECTION>", prompt)
    return [(*map(float, b), "ov:" + prompt) for b in r.get("bboxes", [])]


_ocr = None


def detect_text(img: Image.Image, min_score=0.6):
    """RapidOCR 找所有文字区域，返回 [(x1,y1,x2,y2,'ocr:文字')]，丢掉置信度低于 min_score 的。"""
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    import numpy as np
    r, _ = _ocr(np.array(img)[:, :, ::-1])  # RapidOCR 要 BGR
    res = []
    for quad, text, score in r or []:
        if float(score) < min_score:
            continue
        xs, ys = [p[0] for p in quad], [p[1] for p in quad]
        res.append((float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)), "ocr:" + text))
    return res
