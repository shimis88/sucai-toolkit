"""命令行入口：找水印 -> 做遮罩 -> 补画 -> 按原格式原分辨率保存（附遮罩预览）。"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import paths  # noqa: F401  先设置离线环境变量
from .mask import boxes_to_mask, dilate
from .select import select, siblings, widen_text

EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def parse_box(s):
    x, y, w, h = (float(v) for v in s.split(","))
    return (x, y, x + w, y + h)


def collect(inp):
    p = Path(inp)
    if p.is_dir():
        return sorted(f for f in p.iterdir() if f.suffix.lower() in EXTS and "_mask" not in f.stem)
    return [p]


def save(img, path):
    ext = path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        img.convert("RGB").save(path, quality=95, subsampling=0)
    elif ext == ".webp":
        img.save(path, quality=95, method=6)
    else:
        img.save(path)


def preview(rgb, m):
    v = rgb.copy()
    red = np.zeros_like(v); red[..., 0] = 255
    sel = m > 127
    v[sel] = (0.5 * v[sel] + 0.5 * red[sel]).astype(np.uint8)
    return Image.fromarray(v)


def process(f, args, out_dir):
    t0 = time.time()
    src = ImageOps.exif_transpose(Image.open(f))
    alpha = src.getchannel("A") if src.mode in ("RGBA", "LA") else None
    img = src.convert("RGB")
    W, H = img.size
    cands, keep, skip = [], [], []
    if not args.no_detect:
        from .detect import detect_objects, detect_text
        cands += detect_text(img)
        keep, skip = select(cands, W, H, args.max_area, args.all_text, args.loose, args.anywhere)
        # 水印常是两三行一组（「抖音」+「抖音号：xxx」）：在已认定的水印旁边放大再认一次字，同组的行一起去
        if keep and not args.all_text:
            sib = siblings(img, keep, detect_text)
            if sib:
                cands += sib
                keep, skip = select(cands, W, H, args.max_area, args.all_text, args.loose, args.anywhere)
        # 「watermark」logo 检测只在找到水印文字后才跑（干净图省一半时间）；--loose 时总是跑
        if args.prompt and (keep or args.loose):
            for pr in args.prompt:
                cands += detect_objects(img, pr)
            keep, skip = select(cands, W, H, args.max_area, args.all_text, args.loose, args.anywhere)
    t_det = time.time() - t0
    keep = [widen_text(b, W) for b in keep]
    info = [f"去 {len(keep)} 处"] + [f"留 {r}:{b[4][:20]}" for b, r in skip]
    if args.verbose:
        for b in keep:
            print("   去掉", [int(v) for v in b[:4]], b[4])
        for b, r in skip:
            print("   保留", r, [int(v) for v in b[:4]], b[4])
    m, _, dropped = boxes_to_mask(img.size, [b[:4] for b in keep], 1.0)
    # 最后一道保险：自动找出的遮罩加起来太大，多半是误判，整张保留原图
    frac = (m > 0).mean()
    if frac > args.max_mask:
        info.append(f"遮罩占 {frac:.1%} 超过 {args.max_mask:.0%}，判为误检，保留原图")
        m[:] = 0
    m = dilate(m, args.dilate)
    if args.box:  # 手动框：完全按用户给的来，不受上面任何规则限制
        mm, _, _ = boxes_to_mask(img.size, [parse_box(b) for b in args.box], 1.0, pad_ratio=0, pad_min=0)
        m = np.maximum(m, dilate(mm, args.dilate))
    rgb = np.array(img)
    stem = f.stem
    out_path = out_dir / f.name
    if m.max() == 0:
        print(f"[跳过] {f.name}：没找到水印，原样复制（{'; '.join(info)}）")
        save(src, out_path)
        return
    from .inpaint import inpaint
    res = inpaint(rgb, m, max_side=args.max_side)
    out = Image.fromarray(res)
    if alpha is not None:
        out.putalpha(alpha)
    save(out, out_path)
    preview(rgb, m).save(out_dir / f"{stem}_mask.jpg", quality=90)
    print(f"[完成] {f.name} -> {out_path}  {'; '.join(info)}；"
          f"用时 {time.time()-t0:.1f}s（检测 {t_det:.1f}s）")


def main(argv=None):
    ap = argparse.ArgumentParser(description="图片无痕去水印（Florence-2 + big-lama，CPU）")
    ap.add_argument("input", help="图片或文件夹")
    ap.add_argument("--out", default=None, help="输出文件夹，默认 输入旁边的 dewm_out/")
    ap.add_argument("--box", action="append", default=[], help="手动框 x,y,w,h，可多次")
    ap.add_argument("--prompt", action="append", default=None,
                    help="额外的开放词汇检测词，可多次；默认 watermark")
    ap.add_argument("--all-text", action="store_true",
                    help="画面里所有文字都当水印去（含字幕、中间的字），默认只去边角的")
    ap.add_argument("--loose", action="store_true",
                    help="旧的宽松模式：四个角里的短文字和 logo 也去（会误伤画面自带的字）")
    ap.add_argument("--anywhere", action="store_true",
                    help="不限边缘一圈，画面任何位置的水印文字都去")
    ap.add_argument("--strict", action="store_true", help=argparse.SUPPRESS)  # 旧参数，现在默认就是严格
    ap.add_argument("--max-mask", type=float, default=0.05,
                    help="自动遮罩合计最多占全图比例，超过整张保留原图，默认 0.05")
    ap.add_argument("-v", "--verbose", action="store_true", help="列出每个框去还是留")
    ap.add_argument("--no-detect", action="store_true", help="只用 --box，不自动检测")
    ap.add_argument("--dilate", type=int, default=5, help="遮罩外扩像素，默认 5")
    ap.add_argument("--max-area", type=float, default=0.06,
                    help="单个检测框最多占全图比例，超过当成误检忽略，默认 0.06")
    ap.add_argument("--max-side", type=int, default=1024, help="补画裁块最长边，超过先缩小")
    args = ap.parse_args(argv)
    if args.prompt is None:
        args.prompt = ["watermark"]
    files = collect(args.input)
    if not files:
        sys.exit("没找到图片")
    base = Path(args.input)
    out_dir = Path(args.out) if args.out else (base if base.is_dir() else base.parent) / "dewm_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        process(f, args, out_dir)


if __name__ == "__main__":
    main()
