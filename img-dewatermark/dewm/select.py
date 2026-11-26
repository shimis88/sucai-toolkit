"""从候选框里挑出「像水印」的。默认保守：宁可漏一个，不误伤画面。

默认规则（按顺序，任何一条不满足就保留原样）：
1. 太大（超过全图 max_area）不去，免得抹掉主体。
2. 太小（高度不到短边的 0.4%）不去：远处的灯、噪点不会是能看清的水印。
3. 只看画面边缘一圈（离边 15% 以内，--anywhere 关掉这条）。
   文字框宽过全图 45% 的不算（海报顶上的标题横幅；真水印一般不到 30%）。
4. 必须有「水印证据」：OCR 文字像水印——@账号、平台名（抖音/小红书/快手/微博/B站…）、
   「xx号: 123」「ID: 123」、网址、©、图库站名。相机型号、招牌、产品字样一律不碰。
4b. 紧挨着已认定水印的其他文字行（放大重认后找到的）算同一组，一起去。
5. 「watermark」检测框（没有文字的 logo）只有紧挨着第 4 条认定的文字时才去
   （比如抖音 logo + 抖音号），单独的小亮点、小图标不去。
--loose：恢复旧行为，四个角里的短文字和 logo 也去（会误伤画面自带的字）。
--all-text：画面里所有文字都去（含字幕），一般不用。
"""
import re

# 水印证据：账号、平台名、号/ID、网址、版权、图库站
WATERMARK_TEXT = re.compile(
    r"@\s*\S|"
    r"抖音|快手|哔哩|小红书|微博|视频号|今日头条|西瓜视频|好看视频|知乎|豆瓣|微信|公众号|"
    r"B站|bilibili|\bbili\b|weibo|douyin|tiktok|kuaishou|xiaohongshu|rednote|instagram|"
    r"[号號]\s*[:：]?\s*[A-Za-z0-9_.\-]{3,}|\bID\s*[:：]\s*[A-Za-z0-9_.\-]{3,}|\bUID\s*[:：]?\s*\d{4,}|"
    r"https?://|www\.|\b[\w\-]+\.(com|cn|net|org|tv|me)\b|©|\(c\)|copyright|watermark|"
    r"shutterstock|gettyimages|getty images|istock|123rf|dreamstime|alamy|depositphotos|adobe ?stock|"
    r"视觉中国|图虫|千图|包图|摄图|昵图|汇图|站酷|堆糖|花瓣", re.I)


def _center(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def is_subtitle(b, W, H):
    cx, cy = _center(b)
    return abs(cx - W / 2) < 0.12 * W and cy > 0.6 * H and (b[2] - b[0]) > 0.2 * W


def in_edge_band(b, W, H, edge=0.15):
    cx, cy = _center(b)
    return cy < edge * H or cy > (1 - edge) * H or cx < edge * W or cx > (1 - edge) * W


def in_corner(b, W, H, ex=0.35, ey=0.18):
    cx, cy = _center(b)
    return (cx < ex * W or cx > (1 - ex) * W) and (cy < ey * H or cy > (1 - ey) * H)


def too_small(b, W, H, ratio=0.004):
    return (b[3] - b[1]) < max(6, ratio * min(W, H))


def near(a, b, W, H):
    """两个框挨着（间隔不超过较高那个框的 1.5 倍，或重叠）。"""
    g = 1.5 * max(a[3] - a[1], b[3] - b[1])
    return not (a[2] + g < b[0] or b[2] + g < a[0] or a[3] + g < b[1] or b[3] + g < a[1])


def select(cands, W, H, max_area, all_text=False, loose=False, anywhere=False, max_width=0.45):
    keep, skip, logos = [], [], []
    edge = (lambda b: True) if anywhere else (lambda b: in_edge_band(b, W, H))
    for b in cands:
        x1, y1, x2, y2, tag = b
        kind, _, text = tag.partition(":")
        area = (x2 - x1) * (y2 - y1) / (W * H)
        if area > max_area:
            skip.append((b, "太大"))
        elif all_text:
            keep.append(b)
        elif too_small(b, W, H):
            skip.append((b, "太小"))
        elif is_subtitle(b, W, H):
            skip.append((b, "像字幕"))
        elif not edge(b):
            skip.append((b, "不在边缘"))
        elif kind in ("ocr", "group") and (x2 - x1) > max_width * W:
            skip.append((b, "太宽，像标题横幅"))
        elif kind in ("ocr", "group") and (kind == "group" or WATERMARK_TEXT.search(text)):
            keep.append(b)
        elif loose and in_corner(b, W, H) and (kind != "ocr" or len(text.strip()) <= 20):
            keep.append(b)
        elif kind not in ("ocr", "group"):
            logos.append(b)
        else:
            skip.append((b, "文字不像水印"))
    # 没有文字的 logo：只有挨着已认定的水印文字才去
    for b in logos:
        if any(near(b, k, W, H) for k in keep if k[4].startswith(("ocr:", "group:"))):
            keep.append(b)
        else:
            skip.append((b, "单独的图形，没有水印文字"))
    return keep, skip


def siblings(img, keep, detect_text, scale=2.0):
    """在每个水印文字周围（上下各 2.5 行、左右各 4 个字高）放大 2 倍再认字。
    认到的、跟水印挨着的其他行标成 group:，算同一个水印（比如抖音 logo 旁的「抖音」两个字）。"""
    W, H = img.size
    out = []
    for k in keep:
        if not k[4].startswith("ocr:"):
            continue
        h = k[3] - k[1]
        x1, y1 = max(0, int(k[0] - 4 * h)), max(0, int(k[1] - 2.5 * h))
        x2, y2 = min(W, int(k[2] + 4 * h)), min(H, int(k[3] + 2.5 * h))
        crop = img.crop((x1, y1, x2, y2))
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)))
        for a in detect_text(crop):
            b = (x1 + a[0] / scale, y1 + a[1] / scale, x1 + a[2] / scale, y1 + a[3] / scale)
            if any(_iou(b, q) > 0.3 for q in keep):
                continue
            if near(b, k, W, H) and (b[3] - b[1]) < 2.5 * h:
                out.append((*b, "group:" + a[4][4:]))
    return out


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0


def widen_text(b, W, ratio=1.2):
    """文字框左右各扩 1.2 个字高、上下各 0.25 个：水印常是「图标 + 文字」，OCR 只框到文字。"""
    x1, y1, x2, y2, tag = b
    if not tag.startswith(("ocr:", "group:")):
        return b
    h = y2 - y1
    p, v = ratio * h, 0.25 * h  # 上下也扩一点：旁边的图标通常比字高
    return (max(0, x1 - p), max(0, y1 - v), min(W, x2 + p), y2 + v, tag)
