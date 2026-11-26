"""big-lama 补画：只裁水印附近一块去补，补完只贴回遮罩里的像素，其余像素和原图一模一样。"""
import cv2
import numpy as np
import torch

from . import paths

_lama = None


def _load():
    global _lama
    if _lama is None:
        _lama = torch.jit.load(str(paths.LAMA_PATH), map_location="cpu").eval()
    return _lama


def _pad8(x):
    h, w = x.shape[:2]
    ph, pw = (8 - h % 8) % 8, (8 - w % 8) % 8
    if x.ndim == 3:
        return np.pad(x, ((0, ph), (0, pw), (0, 0)), mode="symmetric")
    return np.pad(x, ((0, ph), (0, pw)), mode="symmetric")


@torch.inference_mode()
def _lama_run(rgb, m):
    h, w = rgb.shape[:2]
    rgb_p, m_p = _pad8(rgb), _pad8(m)
    t = torch.from_numpy(rgb_p).permute(2, 0, 1)[None].float() / 255.0
    tm = (torch.from_numpy(m_p)[None, None].float() > 127).float()
    out = _load()(t, tm)[0].permute(1, 2, 0).clamp(0, 1).numpy()
    return (out[:h, :w] * 255).round().astype(np.uint8)


def inpaint(rgb, m, max_side=1024, margin_ratio=1.0, margin_min=128):
    """rgb: HxWx3 uint8；m: HxW uint8（255=要补）。按连通块分别裁剪处理。"""
    out = rgb.copy()
    H, W = m.shape
    n, _, stats, _ = cv2.connectedComponentsWithStats((m > 127).astype(np.uint8))
    # 把相邻的块合成一个裁剪区，避免重复处理
    rects = [stats[i][:4] for i in range(1, n)]
    for (x, y, w, h) in _merge(rects, margin_min):
        mg = max(margin_min, int(margin_ratio * max(w, h)))
        a, b = max(0, x - mg), max(0, y - mg)
        c, d = min(W, x + w + mg), min(H, y + h + mg)
        crop, cm = out[b:d, a:c], m[b:d, a:c]
        ch, cw = crop.shape[:2]
        s = min(1.0, max_side / max(ch, cw))
        if s < 1.0:
            sz = (max(8, int(cw * s)), max(8, int(ch * s)))
            res = _lama_run(cv2.resize(crop, sz, interpolation=cv2.INTER_AREA),
                            cv2.resize(cm, sz, interpolation=cv2.INTER_NEAREST))
            res = cv2.resize(res, (cw, ch), interpolation=cv2.INTER_CUBIC)
        else:
            res = _lama_run(crop, cm)
        # 遮罩边缘羽化 3px，避免硬边
        alpha = cv2.GaussianBlur((cm > 127).astype(np.float32), (7, 7), 0)
        alpha = np.maximum(alpha, (cm > 127).astype(np.float32))[..., None]
        out[b:d, a:c] = (res * alpha + crop * (1 - alpha)).round().astype(np.uint8)
    return out


def _merge(rects, gap):
    rects = [list(r) for r in rects]
    changed = True
    while changed:
        changed = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                x1, y1, w1, h1 = rects[i]
                x2, y2, w2, h2 = rects[j]
                if (x1 - gap < x2 + w2 and x2 - gap < x1 + w1 and
                        y1 - gap < y2 + h2 and y2 - gap < y1 + h1):
                    nx, ny = min(x1, x2), min(y1, y2)
                    rects[i] = [nx, ny, max(x1 + w1, x2 + w2) - nx, max(y1 + h1, y2 + h2) - ny]
                    rects.pop(j)
                    changed = True
                    break
            if changed:
                break
    return rects
