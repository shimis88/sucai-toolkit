#!/usr/bin/env python3
"""小红书：用合成的分享页数据测试从页面状态到 Post 的转换（不联网、不含真实笔记）。"""
import sys
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from post import Post  # noqa: E402
from sites import detect, xhs_share, xiaohongshu  # noqa: E402

URL = "https://www.xiaohongshu.com/explore/" + "a" * 24 + "?xsec_token=FAKE&xsec_source=pc_share"
NOTE_IMAGES = {"title": "标题", "desc": "正文#标签[话题]#", "type": "normal", "time": 1700000000000,
               "user": {"nickname": "作者"}, "interactInfo": {"likedCount": "9", "collectedCount": "8"},
               "imageList": [{"fileId": "f1"}, {"fileId": "f2"}], "tagList": [{"name": "标签"}]}
NOTE_VIDEO = {**NOTE_IMAGES, "type": "video", "video": {"media": {"stream": {"h264": [
    {"masterUrl": "http://cdn.example/v.mp4", "height": 1080, "streamType": 1}]}}}}


def run_with(note):
    xhs_share.fetch_state = lambda url: {"noteData": {"data": {"noteData": note, "commentData": {}}}}
    post = Post("xiaohongshu", URL)
    xiaohongshu.run(post, Namespace(with_comments=False))
    return post


def test_images():
    p = run_with(NOTE_IMAGES)
    assert p.author == "作者" and p.text == "正文#标签" and p.stats["likes"] == "9"
    assert p.images == ["https://sns-img-bd.xhscdn.com/f1", "https://sns-img-bd.xhscdn.com/f2"], p.images
    assert not p.videos and not p.unavailable


def test_video():
    p = run_with(NOTE_VIDEO)
    assert p.videos == ["https://cdn.example/v.mp4"], p.videos
    assert p.extra["video_source"].startswith("clean stream")


def test_needs_token():
    post = Post("xiaohongshu", "https://www.xiaohongshu.com/explore/" + "b" * 24)
    xiaohongshu.run(post, Namespace(with_comments=False))
    assert "content" in post.unavailable
    assert detect("https://xhslink.com/abc").NAME == "xiaohongshu"


if __name__ == "__main__":
    test_images(); test_video(); test_needs_token()
    print("all xiaohongshu tests passed")
