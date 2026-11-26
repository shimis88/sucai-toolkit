"""小红书 / rednote：手机分享页（需要链接里的 xsec_token），拿作者原片、全部原图、文案和数据。
不登录、不签名、不读 cookie。必须是新鲜完整的分享链接或 xhslink 短链，旧链接 token 过期会失败。"""
import datetime as dt
import re

from post import Unreachable
from util import try_each
from sites import xhs_share

NAME = "xiaohongshu"
MATCH = r"(xiaohongshu\.com|rednote\.com|xhslink\.(?:com|cn))/"
NOTE_ID = re.compile(r"(?:explore|discovery/item|item)/([0-9a-f]{24})")
BEIJING = dt.timezone(dt.timedelta(hours=8))


def run(post, opts):
    if re.search(r"xhslink\.(?:com|cn)", post.url):
        post.url = xhs_share.resolve_short(post.url)
    has_id = NOTE_ID.search(post.url)
    has_token = re.search(r"xsec_token=([^&]+)", post.url)

    def share_page():
        if not (has_id and has_token):
            raise Unreachable("链接里要带 xsec_token（请复制完整的分享链接）")
        note, comments = xhs_share.parse(xhs_share.fetch_state(post.url))
        user = note.get("user") or {}
        post.title = note.get("title", "")
        post.text = re.sub(r"\[话题\]#", "", note.get("desc", ""))
        post.author = user.get("nickName") or user.get("nickname", "")
        if note.get("time"):
            post.published = dt.datetime.fromtimestamp(note["time"] / 1000, BEIJING).strftime("%Y-%m-%d %H:%M UTC+8")
        info = note.get("interactInfo") or {}
        post.stats = {"likes": info.get("likedCount"), "collects": info.get("collectedCount"),
                      "comments": info.get("commentCount"), "shares": info.get("shareCount")}
        post.extra["note_type"] = note.get("type")
        post.extra["tags"] = [t.get("name") for t in note.get("tagList") or []]
        images = note.get("imageList") or []
        if note.get("type") == "video":
            url, label = xhs_share.best_video(note)
            if url:
                post.videos.append(url)
                post.extra["video_source"] = label
            if images:
                post.images.append(xhs_share.image_url(images[0]))
        else:
            post.images = [xhs_share.image_url(i) for i in images]
        if opts.with_comments and comments:
            post.comments = [{"author": (c.get("user") or {}).get("nickname", ""), "text": c.get("content", ""),
                              "likes": c.get("likeCount")} for c in comments]
            post.note("comments", "分享页（只有第一页）", True)

    try_each(post, "content", [("手机分享页 __INITIAL_STATE__", share_page)])
    if opts.with_comments and not post.comments:
        post.missing("comments")
