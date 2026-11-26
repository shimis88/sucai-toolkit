"""X / Twitter：一条推里所有图、视频、GIF 按最高质量下载。不登录、不用 cookie。
顺序：公开 syndication 接口 → fxtwitter 公开 API → yt-dlp。"""
import re

from net import fetch
from post import Unreachable
from util import try_each, utc_text
import ytdl

NAME = "x"
MATCH = r"(twitter\.com|x\.com)/"
TWEET_ID = re.compile(r"/status/(\d+)")


def _original(url):
    """pbs.twimg.com 的图加 name=orig 才是原图，裸地址常是较小的默认尺寸。"""
    if not url or "pbs.twimg.com" not in url:
        return url
    if "name=" in url:
        return re.sub(r"name=[^&]+", "name=orig", url)
    return url + ("&" if "?" in url else "?") + "name=orig"


def _top_mp4(variants):
    mp4s = [v for v in variants or [] if (v.get("content_type") or v.get("type")) == "video/mp4" and v.get("url")]
    return max(mp4s, key=lambda v: v.get("bitrate") or 0)["url"] if mp4s else None


def _add_image(post, url):
    url = _original(url)
    if url and url not in post.images:
        post.images.append(url)


def _add_media(post, items):
    """按推文里的顺序加入图片和视频/GIF；视频的封面也留在 images 里。"""
    for m in items or []:
        kind = m.get("type") or ""
        mp4 = _top_mp4((m.get("video_info") or {}).get("variants") or m.get("variants"))
        if kind in ("video", "animated_gif", "gif") or (not kind and mp4):
            if mp4:
                post.videos.append(mp4)
            _add_image(post, m.get("media_url_https") or m.get("thumbnail_url"))
        elif kind != "video":
            _add_image(post, m.get("media_url_https") or m.get("url"))


def run(post, opts):
    m = TWEET_ID.search(post.url)
    if not m:
        raise Unreachable("只支持单条推文链接（.../status/数字）")
    tweet_id = m.group(1)

    def syndication():
        d = fetch(f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token=4&lang=en").json()
        if not isinstance(d, dict) or not d.get("id_str"):
            raise Unreachable("syndication 返回空")
        post.text = d.get("text") or ""
        post.title = post.text[:80]
        user = d.get("user") or {}
        post.author = f'{user.get("name", "")} (@{user.get("screen_name", "")})'
        post.published = utc_text(d.get("created_at"))
        post.stats = {"likes": d.get("favorite_count"), "replies": d.get("conversation_count")}
        _add_media(post, d.get("mediaDetails"))
        for photo in d.get("photos") or []:
            _add_image(post, photo.get("url"))

    def fxtwitter():
        d = fetch(f"https://api.fxtwitter.com/status/{tweet_id}").json()
        t = d.get("tweet") if isinstance(d, dict) else None
        if not t:
            raise Unreachable("fxtwitter 返回空")
        post.text = post.text or t.get("text") or ""
        post.title = post.title or post.text[:80]
        a = t.get("author") or {}
        post.author = post.author or f'{a.get("name", "")} (@{a.get("screen_name", "")})'
        post.published = post.published or utc_text(t.get("created_at") or t.get("created_timestamp") or "")
        stats = t.get("stats") or {}
        likes, replies = t.get("likes") or stats.get("likes"), t.get("replies") or stats.get("replies")
        if not post.stats and (likes is not None or replies is not None):
            post.stats = {"likes": likes, "replies": replies}
        _add_media(post, (t.get("media") or {}).get("all"))

    def via_ytdlp():
        data = ytdl.info(post.url)
        entries = [e for e in (data.get("entries") or [data]) if e]
        if not entries:
            raise Unreachable("yt-dlp 没有内容")
        first = entries[0]
        post.text = post.text or data.get("description") or first.get("description") or ""
        post.title = post.title or (data.get("title") or first.get("title") or "")[:80]
        post.author = post.author or data.get("uploader") or first.get("uploader") or ""
        post.published = post.published or utc_text(data.get("timestamp") or first.get("timestamp") or "")
        if first.get("like_count") is not None and not post.stats:
            post.stats = {"likes": first["like_count"]}
        for entry in entries:  # 多视频推文是播放列表，每条都要
            direct = [f for f in entry.get("formats") or []
                      if f.get("url") and f.get("vcodec") != "none" and "m3u8" not in (f.get("url") or "")
                      and (f.get("ext") == "mp4" or "mp4" in f["url"])]
            if direct:
                post.videos.append(max(direct, key=lambda f: f.get("tbr") or 0)["url"])
                _add_image(post, entry.get("thumbnail"))
            elif entry.get("url"):
                post.videos.append(entry["url"])
        if not post.videos and not post.images:
            raise Unreachable("yt-dlp 没找到媒体")

    try_each(post, "content", [("syndication tweet-result", syndication), ("fxtwitter", fxtwitter),
                               ("yt-dlp twitter", via_ytdlp)])
    if opts.with_comments:
        post.missing("comments")
