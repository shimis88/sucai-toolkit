"""通用站点：交给 yt-dlp。YouTube（含字幕）、TikTok、Instagram、Reddit、Facebook、Threads 等都走这里。"""
import ytdl
from util import try_each

NAME = "web"
MATCH = r"."
SUBTITLE_LANGS = ("zh-Hans", "zh", "en", "en-orig")


def _pick_subtitle(post, data):
    subs = {**(data.get("automatic_captions") or {}), **(data.get("subtitles") or {})}
    post.extra["subtitle_langs"] = sorted(subs)[:30]
    for lang in SUBTITLE_LANGS:
        for fmt in subs.get(lang, []):
            if fmt.get("ext") == "vtt":
                post.extra["subtitle_url"], post.extra["subtitle_lang"] = fmt["url"], lang
                return


def run(post, opts):
    extra = {}
    if opts.with_comments:
        extra = {"getcomments": True, "extractor_args": {"youtube": {"max_comments": ["20", "all", "0", "0"]}}}
    if "youtu" in post.url:
        extra.update({"writesubtitles": True, "writeautomaticsub": True})

    def lookup():
        data = ytdl.fill(post, ytdl.info(post.url, **extra))
        if "youtu" in post.url:
            _pick_subtitle(post, data)
        if not (post.title or post.text or post.videos):
            raise RuntimeError("yt-dlp 没拿到内容（可能要登录）")

    site = "yt-dlp"
    try_each(post, "content", [(site, lookup)])
    if opts.with_comments and not post.comments:
        post.missing("comments")
