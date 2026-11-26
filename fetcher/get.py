#!/usr/bin/env python3
"""单条链接：python get.py <链接> [--out 目录] [--with-media] [--with-comments] [--transcribe]
只用免费公开方法：不读 cookie、不用付费接口。免费方法拿不到的字段会列在 content.md 的最后并如实说明。"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sites"))

import cleanup
import media
import policy
import report
from post import Post
from sites import detect


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url")
    ap.add_argument("--out", help="输出目录（默认 output/<站点>_<时间>）")
    ap.add_argument("--with-media", action="store_true", help="同时下载图片、视频、音轨")
    ap.add_argument("--with-comments", action="store_true")
    ap.add_argument("--transcribe", action="store_true", help="口播转文字（需要 --with-media）")
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--max-mb", type=int, default=2000, help="单个文件上限，超过就报错、不存半截")
    ap.add_argument("--max-height", type=int, default=1080, help="yt-dlp 站点的最高分辨率")
    ap.add_argument("--max-images", type=int, default=20)
    return ap.parse_args(argv)


def main(argv=None):
    opts = parse_args(argv)
    try:
        cleanup.cleanup()
    except OSError:
        pass
    site = detect(opts.url)
    post = Post(site.NAME, opts.url.strip())
    outdir = opts.out or os.path.join("output", f"{site.NAME}_{time.strftime('%Y%m%d_%H%M%S')}")
    print(f"[{site.NAME}] {opts.url}")
    try:
        site.run(post, opts)
    except Exception as e:
        post.note("content", "setup", False, e)
        post.missing("content")
    if opts.with_media and (post.images or post.videos or post.extra.get("music")):
        media.save_all(post, outdir, opts)
    post.extra.update(policy.judge(post.images))  # 平台干净原图 → 批量处理时跳过去水印
    if post.unavailable:
        print("  [--] 免费方法拿不到: " + ", ".join(post.unavailable) + "（不使用付费接口，直接如实说明）")
    report.write(post, outdir)
    print(f"  -> {outdir}/content.md, meta.json ({len(post.files)} media files)")
    return 2 if any(k in post.unavailable for k in ("content", "profile", "session")) else 0


if __name__ == "__main__":
    sys.exit(main())
