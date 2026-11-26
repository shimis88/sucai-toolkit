"""yt-dlp 封装：查信息、下载最高清（≤ max_height，优先 H.264+AAC 合成 mp4）、把信息填进 Post。"""
import os
import shutil

from post import Post, YtdlpVideo
from util import utc_text

HAS_FFMPEG = shutil.which("ffmpeg") is not None
# YouTube 需要 JS 运行时（node）配合 yt-dlp-ejs 解校验
JS_RUNTIMES = {"node": {}} if shutil.which("node") else {}


class _Silent:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _options(**more):
    base = {"quiet": True, "no_warnings": True, "noprogress": True, "logger": _Silent(),
            "js_runtimes": JS_RUNTIMES}
    base.update(more)
    return base


def info(url, **more):
    import yt_dlp
    with yt_dlp.YoutubeDL(_options(skip_download=True, ignore_no_formats_error=True, **more)) as y:
        return y.extract_info(url, download=False)


def download(url, outdir, max_height=1080):
    import yt_dlp
    opts = _options(outtmpl=os.path.join(outdir, "video.%(ext)s"),
                    format="bv*+ba/b" if HAS_FFMPEG else "b",
                    format_sort=[f"res:{max_height}", "vcodec:h264", "acodec:m4a"],
                    merge_output_format="mp4")
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])
    return [os.path.join(outdir, f) for f in os.listdir(outdir) if f.startswith("video.")]


def _counter(v):
    # 个别站点把计数存成带符号 32 位整数，超过 2^31 会变负数，这里还原
    if isinstance(v, int) and -2**31 <= v < 0:
        v += 2**32
    return v if isinstance(v, int) and v >= 0 else None


def fill(post: Post, data):
    """把 yt-dlp 的 info 填进 post（播放列表取第一条）。"""
    if data.get("_type") == "playlist" and data.get("entries"):
        first = next(iter(data["entries"]), None)
        if first:
            data = {**first, **{k: v for k, v in data.items() if v and k in ("description", "title")}}
    post.title = post.title or data.get("title") or ""
    post.author = post.author or data.get("uploader") or data.get("channel") or ""
    post.published = post.published or utc_text(data.get("timestamp") or data.get("upload_date") or "")
    post.text = post.text or data.get("description") or ""
    for key, label in (("view_count", "views"), ("like_count", "likes"),
                       ("comment_count", "comments"), ("repost_count", "reposts")):
        n = _counter(data.get(key))
        if n is not None:
            post.stats[label] = n
    cover = data.get("thumbnail") or next(iter(sorted(data.get("thumbnails") or [],
                                                      key=lambda t: t.get("width") or 0, reverse=True)), {}).get("url")
    if cover:
        post.images.append(cover)
    if data.get("formats") or data.get("url"):
        post.videos.append(YtdlpVideo(data.get("webpage_url") or post.url))
    if data.get("comments"):
        post.comments = [{"author": c.get("author"), "text": c.get("text"), "likes": c.get("like_count"),
                          "time": utc_text(c.get("timestamp"))} for c in data["comments"]]
    if data.get("duration"):
        post.extra["duration"] = data["duration"]
    return data
