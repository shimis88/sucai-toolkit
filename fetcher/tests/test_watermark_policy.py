"""policy：哪些图床算平台干净原图。运行：.venv/bin/python tests/test_policy.py（无需联网）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from policy import judge, judge_url


def test_clean_platforms():
    for u in ["https://pbs.twimg.com/media/abc?format=jpg&name=orig",
              "https://sns-img-bd.xhscdn.com/notes_pre_post/1040g3k0326ujgtvlme6g4ac65k0elhumc652afg",
              "https://p3-pc-sign.douyinpic.com/tos-cn-i-0813/abc~tplv-dy-aweme-images:q75.webp"]:
        assert judge_url(u)[0], u


def test_marked_or_unknown():
    for u in ["https://wx1.sinaimg.cn/large/abc.jpg", "https://mmbiz.qpic.cn/mmbiz_jpg/abc/640",
              "https://p3.douyinpic.com/tos/abc~tplv-dy-water-v2.jpeg", "https://example.com/a.jpg"]:
        assert not judge_url(u)[0], u


def test_judge_all_or_nothing():
    assert judge(["https://pbs.twimg.com/a?name=orig"])["watermark_free"] is True
    assert judge(["https://pbs.twimg.com/a?name=orig", "https://wx1.sinaimg.cn/a.jpg"])["watermark_free"] is False
    assert judge([]) == {}


if __name__ == "__main__":
    test_clean_platforms(); test_marked_or_unknown(); test_judge_all_or_nothing()
    print("all policy tests passed")
