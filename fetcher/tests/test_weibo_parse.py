#!/usr/bin/env python3
"""微博模块离线测试：链接解析、短 ID 换算、分享文案抽链去重、原图/最高清选择、转发不重复下视频。不联网。
运行：.venv/bin/python tests/test_weibo_parse.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from batch import dedupe_key, extract_urls  # noqa: E402
from post import Post  # noqa: E402
from sites import detect, weibo  # noqa: E402


def test_bid_to_mid():
    assert weibo.bid_to_mid("RsnMuf2kM") == "5367646023583896"
    assert weibo.bid_to_mid("Rrookh8wG") == "5365286204084354"


def test_parse_url():
    cases = {
        "https://weibo.com/2656274875/RsnMuf2kM": ("status", "RsnMuf2kM"),
        "https://www.weibo.com/2656274875/5367646023583896?refer_flag=1001030103_": ("status", "5367646023583896"),
        "https://weibo.com/detail/5367646023583896": ("status", "5367646023583896"),
        "https://m.weibo.cn/detail/5367646023583896": ("status", "5367646023583896"),
        "https://m.weibo.cn/status/RsnMuf2kM?wm=3333_2001": ("status", "RsnMuf2kM"),
        "https://m.weibo.cn/2656274875/5367646023583896": ("status", "5367646023583896"),
        "https://share.api.weibo.cn/share/123456,5367646023583896.html": ("status", "5367646023583896"),
        "https://video.weibo.com/show?fid=1034%3A5367637216264228": ("video", "1034:5367637216264228"),
        "https://weibo.com/tv/show/1034:5367637216264228?from=old_pc_videoshow": ("video", "1034:5367637216264228"),
        "http://t.cn/AXTM7XQ3": ("short", "http://t.cn/AXTM7XQ3"),
        "https://weibo.cn/sinaurl?u=https%3A%2F%2Fweibo.com%2F2656274875%2FRsnMuf2kM": ("status", "RsnMuf2kM"),
        "https://weibo.com/u/2656274875": (None, None),
        "https://passport.weibo.com/visitor/visitor?entry=krvideo&a=enter&url=https%3A%2F%2Fweibo.com%2Ftv%2Fshow%2F1034%3A5367637216264228%3Ffrom%3Dold_pc_videoshow&domain=.weibo.com": ("video", "1034:5367637216264228"),
    }
    for u, want in cases.items():
        got = weibo.parse_url(u)
        assert got == want, (u, got, want)
        assert detect(u).NAME == "weibo", u
    assert detect("https://www.youtube.com/watch?v=abc").NAME == "youtube"
    assert detect("https://xt.cn/abc").NAME == "web"


def test_share_text_dedupe():
    text = ("【#周深试图教我唱光亮#】在#中国唱将2026#舞台上… https://weibo.com/2656274875/RsnMuf2kM ，"
            "也可以看 m.weibo.cn/detail/5367646023583896 视频 http://t.cn/AXTM7XQ3")
    urls = extract_urls(text)
    assert urls == ["https://weibo.com/2656274875/RsnMuf2kM", "http://t.cn/AXTM7XQ3",
                    "https://m.weibo.cn/detail/5367646023583896"], urls
    k1 = dedupe_key("https://weibo.com/2656274875/RsnMuf2kM", "weibo")
    k2 = dedupe_key("https://m.weibo.cn/detail/5367646023583896", "weibo")
    assert k1 == k2 == ("weibo", "5367646023583896"), (k1, k2)


def test_large_and_best_video():
    assert weibo.large("http://wx1.sinaimg.cn/orj480/abc.jpg") == "https://wx1.sinaimg.cn/large/abc.jpg"
    pi = {"media_info": {"playback_list": [
        {"meta": {"label": "mp4_720p"}, "play_info": {"url": "https://f.video.weibocdn.com/o0/a.mp4?template=720x1280.24.0"}},
        {"meta": {"label": "mp4_1080p"}, "play_info": {"url": "https://f.video.weibocdn.com/o0/b.mp4?template=1080x1920.24.0"}},
        {"meta": {"label": "scrubber_hd"}, "play_info": {"url": "https://wx2.sinaimg.cn/large/x.jpg"}}],
        "stream_url": "http://f.video.weibocdn.com/o0/c.mp4?template=540x960.24.0"}}
    u, label = weibo.best_video(None, pi)
    assert "b.mp4" in u and label == "mp4_1080p", (u, label)


def test_retweet_media_once():
    vid = {"type": "video", "media_info": {"mp4_720p_mp4": "https://f.video.weibocdn.com/o0/v.mp4?template=720x1280.24.0&e=1"}}
    rt = {"id": 2, "mblogid": "B", "user": {"id": 22, "screen_name": "原作者"}, "text_raw": "原文 #话题#",
          "created_at": "Sat Nov 21 11:00:01 +0800 2026", "page_info": vid,
          "pic_ids": ["p1"], "pic_infos": {"p1": {"largest": {"url": "https://wx1.sinaimg.cn/large/p1.jpg"}, "type": "pic"}}}
    st = {"id": 1, "mblogid": "A", "user": {"id": 11, "screen_name": "转发者"}, "text_raw": "转发语",
          "created_at": "Sat Nov 21 12:00:01 +0800 2026", "attitudes_count": 5, "comments_count": 6, "reposts_count": 7,
          "page_info": {"type": "video", "media_info": {"mp4_720p_mp4": "https://f.video.weibocdn.com/o0/v.mp4?template=720x1280.24.0&e=2"}},
          "retweeted_status": rt}
    res = Post("weibo", "https://weibo.com/11/A")
    weibo.fill(res, None, st)
    assert len(res.videos) == 1, res.videos
    assert res.images == ["https://wx1.sinaimg.cn/large/p1.jpg"], res.images
    assert res.stats == {"likes": 5, "comments": 6, "reposts": 7}
    assert res.extra["retweet"]["author"] == "原作者" and "//转发自 @原作者" in res.text
    assert res.published == "2026-11-21 12:00 UTC+8"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
    print("all weibo tests passed")
