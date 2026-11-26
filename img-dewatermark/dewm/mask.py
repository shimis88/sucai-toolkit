"""把方框变成遮罩：过滤过大的框、向外扩一圈。"""
import cv2
import numpy as np


def boxes_to_mask(size, boxes, max_area_ratio, pad_ratio=0.1, pad_min=4):
    w, h = size
    m = np.zeros((h, w), np.uint8)
    kept, dropped = [], []
    for (x1, y1, x2, y2) in boxes:
        bw, bh = x2 - x1, y2 - y1
        if bw <= 0 or bh <= 0:
            continue
        if bw * bh > max_area_ratio * w * h:
            dropped.append((x1, y1, x2, y2))
            continue
        p = max(pad_min, int(pad_ratio * min(bw, bh)))
        a, b = max(0, int(x1) - p), max(0, int(y1) - p)
        c, d = min(w, int(x2) + p), min(h, int(y2) + p)
        m[b:d, a:c] = 255
        kept.append((a, b, c, d))
    return m, kept, dropped


def dilate(m, px):
    if px <= 0:
        return m
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))
    return cv2.dilate(m, k)
