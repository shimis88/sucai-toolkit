#!/usr/bin/env python3
"""Offline tests for batch URL extraction / normalize / dedupe. No network."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from batch import dedupe_key, extract_urls, normalize_url


def eq(got, expected, label):
    if got != expected:
        raise AssertionError(f"{label}\n  got:      {got!r}\n  expected: {expected!r}")
    print("OK", label)


def test_douyin_share_text():
    text = (
        "6.10 复制打开抖音，看看【千岁遥的图文作品】你可以暂时不听周杰伦 但很难真正离开周杰伦# 如果... "
        "https://v.douyin.com/AbCdEf12345/ JvS:/ y@G.vF 02/15 :0pm"
    )
    urls = extract_urls(text)
    eq(urls, ["https://v.douyin.com/AbCdEf12345/"], "douyin messy share text")


def test_xhs_and_punctuation():
    text = (
        "http://xhslink.com/o/AbCdEfGhIjk，复制这条链接\n"
        "https://www.xiaohongshu.com/discovery/item/65f0aa00000000000b012345?xsec_token=EXAMPLE-not-a-real-token=&author_share=1。"
    )
    urls = extract_urls(text)
    eq(len(urls), 2, "xhs two links")
    eq(urls[0], "http://xhslink.com/o/AbCdEfGhIjk", "xhslink trailing Chinese punct")
    assert "xsec_token=EXAMPLE-not-a-real-token=" in urls[1], urls[1]
    assert not urls[1].endswith("。"), urls[1]
    print("OK xhs token preserved, trailing 。 stripped")


def test_bare_and_markdown():
    text = "see (https://www.youtube.com/shorts/GYy68npQrpU) and x.com/elonmusk/status/1585341984679469056"
    urls = extract_urls(text)
    eq(
        urls,
        [
            "https://www.youtube.com/shorts/GYy68npQrpU",
            "https://x.com/elonmusk/status/1585341984679469056",
        ],
        "markdown parens + bare x.com",
    )


def test_tco_and_canonical_hosts():
    urls = extract_urls("short https://t.co/abcdefghij plus https://b23.tv/abcdef")
    eq(urls, ["https://t.co/abcdefghij", "https://b23.tv/abcdef"], "t.co and b23.tv extracted")


def test_normalize_and_dedupe():
    a = normalize_url("https://twitter.com/elonmusk/status/1585341984679469056?s=20&t=abc")
    b = normalize_url("https://x.com/elonmusk/status/1585341984679469056")
    eq(dedupe_key(a, "x"), dedupe_key(b, "x"), "twitter.com vs x.com + tracking params")
    eq(dedupe_key(a, "x"), ("x", "1585341984679469056"), "x status id key")

    y1 = normalize_url("https://youtu.be/GYy68npQrpU")
    y2 = "https://www.youtube.com/shorts/GYy68npQrpU"
    # host rewrite of youtu.be happens in normalize; shorts path stays, but ids match
    eq(dedupe_key(y1, "youtube"), dedupe_key(y2, "youtube"), "youtu.be vs shorts id")

    d1 = "https://www.douyin.com/video/7000000000000000001"
    d2 = "https://www.iesdouyin.com/share/video/7000000000000000001/"
    eq(dedupe_key(d1, "douyin"), dedupe_key(d2, "douyin"), "douyin video id")

    # xsec_token must survive normalize (still needed to open the note)
    xhs = normalize_url(
        "https://www.xiaohongshu.com/discovery/item/65f0aa00000000000b012345?xsec_token=TOKEN&utm_source=app"
    )
    assert "xsec_token=TOKEN" in xhs, xhs
    assert "utm_source" not in xhs, xhs
    print("OK xhs token kept, utm dropped")


def test_duplicates_in_one_paste():
    text = """
    https://twitter.com/elonmusk/status/1585341984679469056?s=20
    再贴一次 https://x.com/elonmusk/status/1585341984679469056
    和 https://www.youtube.com/watch?v=GYy68npQrpU
    以及 https://youtu.be/GYy68npQrpU
    """
    urls = extract_urls(text)
    # extract keeps raw uniques; dedupe_key collapses later
    keys = []
    for u in urls:
        host = "x" if "x.com" in u or "twitter.com" in u else "youtube"
        k = dedupe_key(normalize_url(u), host)
        if k not in keys:
            keys.append(k)
    eq(len(keys), 2, "four pasted links collapse to 2 after dedupe")


if __name__ == "__main__":
    test_douyin_share_text()
    test_xhs_and_punctuation()
    test_bare_and_markdown()
    test_tco_and_canonical_hosts()
    test_normalize_and_dedupe()
    test_duplicates_in_one_paste()
    print("all extract tests passed")
