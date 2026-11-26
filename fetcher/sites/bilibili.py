"""B 站：官方接口游客模式（游客 buvid），最高 1080p（DASH 视频 + 音频合并）。"""
import json
import re

from net import UA_PC, new_session
from post import Unreachable
from util import try_each, utc_text
import ytdl

NAME = "bilibili"
MATCH = r"(bilibili\.com|b23\.tv)/"
HOME = "https://www.bilibili.com"
API = "https://api.bilibili.com/x"


def _guest_session():
    s = new_session(UA_PC, HOME)
    ids = s.get(f"{API}/frontend/finger/spi", timeout=20).json()["data"]
    s.cookies.update({"buvid3": ids["b_3"], "buvid4": ids["b_4"]})  # 游客设备号，不是账号
    return s


def _apply_view(post, ids, v):
    ids.update(aid=v["aid"], cid=v["cid"])
    post.title, post.author = v["title"], v["owner"]["name"]
    post.published, post.text = utc_text(v.get("pubdate")), v.get("desc", "")
    st = v["stat"]
    post.stats = {"views": st["view"], "likes": st["like"], "coins": st["coin"], "favorites": st["favorite"],
                  "shares": st["share"], "comments": st["reply"], "danmaku": st["danmaku"]}
    post.images.append(v["pic"].replace("http:", "https:"))


def run(post, opts):
    s = _guest_session()
    if "b23.tv" in post.url:
        post.url = s.get(post.url, timeout=20, allow_redirects=True).url
    m = re.search(r"(BV[0-9A-Za-z]{10})", post.url)
    if not m:
        raise Unreachable("只支持 BV 号视频链接")
    bvid = m.group(1)
    ids = {}

    def api_view(path):
        r = s.get(f"{API}/web-interface/{path}", params={"bvid": bvid}, timeout=20)
        if not r.text.startswith("{"):
            raise Unreachable("被风控返回了网页（常见于机房 IP）")
        body = r.json()
        if body["code"]:
            raise Unreachable(body.get("message"))
        _apply_view(post, ids, body["data"])

    def page_state():
        page = s.get(f"{HOME}/video/{bvid}/", timeout=20).text
        raw = re.search(r"__INITIAL_STATE__=(\{.*?\});\(function", page)
        if not raw:
            raise Unreachable("页面里没有 __INITIAL_STATE__")
        _apply_view(post, ids, json.loads(raw.group(1))["videoData"])

    try_each(post, "content", [
        ("接口 wbi/view", lambda: api_view("wbi/view")),
        ("接口 view（UA + Referer + 游客 buvid）", lambda: api_view("view")),
        ("页面 __INITIAL_STATE__", page_state),
        ("yt-dlp", lambda: ytdl.fill(post, ytdl.info(post.url))),
    ])
    if not ids:
        return

    def play_urls():
        # try_look=1 让游客也能拿到 720p/1080p；挑最高清，同分辨率优先 H.264（兼容性好）
        dash = s.get(f"{API}/player/playurl", timeout=20, params={
            "avid": ids["aid"], "cid": ids["cid"], "fnval": 16, "qn": 80, "try_look": 1}).json()["data"]["dash"]
        audio = max(dash["audio"], key=lambda a: a["bandwidth"])
        video = max(dash["video"], key=lambda v: (v["height"], v["codecs"].startswith("avc"), v["bandwidth"]))
        post.extra["dash_audio"] = [audio["baseUrl"], *(audio.get("backupUrl") or [])]  # 镜像地址，依次试
        post.extra["dash_video"] = [video["baseUrl"], *(video.get("backupUrl") or [])]
        post.extra["video_height"] = video["height"]
        post.videos.append(post.url)

    try_each(post, "media", [("playurl DASH（游客）", play_urls)])

    if opts.with_comments:
        def hot_comments():
            body = s.get(f"{API}/v2/reply", timeout=20,
                         params={"type": 1, "oid": ids["aid"], "sort": 1, "ps": 20}).json()
            replies = (body.get("data") or {}).get("replies") or []
            if not replies:
                raise Unreachable(f"code {body.get('code')}")
            post.comments = [{"author": r["member"]["uname"], "text": r["content"]["message"],
                              "likes": r["like"], "time": utc_text(r["ctime"])} for r in replies]
        try_each(post, "comments", [("/x/v2/reply（游客）", hot_comments)])
