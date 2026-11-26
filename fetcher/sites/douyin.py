"""抖音：iesdouyin 分享页（游客 ttwid + 安卓 UA），拿无水印视频、图集原图、图文 BGM。不登录、不读 cookie。"""
import html
import json
import re

import requests

from net import UA_ANDROID, new_session
from post import Unreachable
from util import try_each, utc_text

NAME = "douyin"
MATCH = r"(douyin\.com|iesdouyin\.com)/"
AWEME_ID = re.compile(r"(?:video|note|share/video|share/note|modal_id=)/?(\d{15,20})")


def _guest_ttwid():
    r = requests.post("https://ttwid.bytedance.com/ttwid/union/register/", timeout=20, json={
        "region": "cn", "aid": 1768, "needFid": False, "service": "www.ixigua.com",
        "migrate_info": {"ticket": "", "source": "node"}, "cbUrl": "https://www.ixigua.com", "union": True})
    return r.cookies.get("ttwid")


def _find_aweme(node):
    """在页面 JSON 里递归找到作品对象（同时有 aweme_id 和 video/images）。"""
    if isinstance(node, dict):
        if "aweme_id" in node and ("video" in node or "images" in node):
            return node
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        hit = _find_aweme(child)
        if hit:
            return hit
    return None


def _music_url(aweme, page):
    """图文作品的 BGM：play_url 常为空，真实 mp3 在 video.play_addr.uri 或页面 <audio> 里。"""
    uri = ((aweme.get("video") or {}).get("play_addr") or {}).get("uri") or ""
    if isinstance(uri, str) and uri.startswith("http") and ("ies-music" in uri or uri.split("?")[0].endswith(".mp3")):
        return uri
    for pattern in (r'<audio[^>]+src="(https://[^"]*ies-music[^"]+)"', r'(https:[^"\\ ]*ies-music[^"\\ ]*)'):
        m = re.search(pattern, page)
        if m:
            return html.unescape(m.group(1))
    return None


def run(post, opts):
    if "v.douyin.com" in post.url:
        post.url = new_session(UA_ANDROID).get(post.url, timeout=20).url
    m = AWEME_ID.search(post.url)
    if not m:
        raise Unreachable("链接里找不到作品 ID")
    aweme_id = m.group(1)
    post.url = f"https://www.douyin.com/video/{aweme_id}"

    def share_page():
        s = new_session(UA_ANDROID, cookies={"ttwid": _guest_ttwid()})
        page = s.get(f"https://www.iesdouyin.com/share/video/{aweme_id}/", timeout=20).text
        raw = re.search(r"_ROUTER_DATA\s*=\s*(\{.*?\})</script>", page, re.S)
        data = json.loads(raw.group(1)) if raw else {}
        aweme = _find_aweme(data)
        if not aweme:
            why = re.findall(r'"filter_reason":\s*"([^"]+)"', json.dumps(data))
            raise Unreachable("页面里没有作品数据" + (f"（抖音过滤：{why[0]}，短剧/付费合集不公开）" if why else ""))
        post.title = post.text = aweme.get("desc", "")
        post.author = aweme["author"]["nickname"]
        post.published = utc_text(aweme.get("create_time"))
        st = aweme.get("statistics", {})
        post.stats = {"likes": st.get("digg_count"), "comments": st.get("comment_count"),
                      "shares": st.get("share_count"), "collects": st.get("collect_count")}
        video = aweme.get("video") or {}
        cover = (video.get("origin_cover") or video.get("cover") or {}).get("url_list") or []
        post.images += cover[:1]
        pics = aweme.get("images") or []
        for pic in pics:  # 图集
            post.images.append((pic.get("url_list") or [None])[-1])
        play = (video.get("play_addr") or {}).get("url_list") or []
        if play and not pics:
            # playwm 是带水印版，换成 play；ratio=1080p 取源画质
            post.videos.append(re.sub(r"ratio=\d+p", "ratio=1080p", play[0].replace("playwm", "play")))
        if pics:
            music = _music_url(aweme, page)
            if music:
                post.extra["music"] = music
                meta = aweme.get("music") or {}
                for key, field in (("music_title", "title"), ("music_author", "author")):
                    if meta.get(field):
                        post.extra[key] = meta[field]

    try_each(post, "content", [("iesdouyin 分享页（游客 ttwid + 安卓 UA）", share_page)])
    if opts.with_comments:
        post.note("comments", "web API", False, "需要 a_bogus 签名，免费方法拿不到")
        post.missing("comments")
