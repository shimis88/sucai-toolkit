"""判断抓到的图是不是「平台干净原图」（平台本身没盖水印），决定要不要跑去水印。

依据是图片地址的域名：下面这些 CDN 发的都是作者上传的原图或无水印版本，
平台不往像素里盖 logo/账号。微博（sinaimg）、公众号（mmbiz）和不认识的网站一律当「可能有水印」。
注意：干净只代表平台没盖水印；作者自己加在图上的签名不算，需要时 batch.py --dewm-force。
"""
import re
from urllib.parse import urlparse

# 域名后缀 -> 平台说明。地址里带 water / watermark 的变体不算干净。
CLEAN_HOSTS = {
    "twimg.com": "X 原图（pbs ?name=orig）",
    "xhscdn.com": "小红书原图（按 fileId 取，无水印）",
    "douyinpic.com": "抖音图集 url_list（无水印版）",
    "byteimg.com": "抖音/头条图床无水印版",
    "tiktokcdn.com": "TikTok 封面",
    "tiktokcdn-us.com": "TikTok 封面",
    "cdninstagram.com": "Instagram 原图",
    "fbcdn.net": "Facebook/Instagram/Threads 原图",
    "bsky.app": "Bluesky 原图",
    "redd.it": "Reddit 原图",
    "pinimg.com": "Pinterest 原图",
    "licdn.com": "LinkedIn 原图",
    "ytimg.com": "YouTube 封面",
    "hdslb.com": "B 站封面/动态原图",
    "telesco.pe": "Telegram 原图",
    "substackcdn.com": "Substack 原图",
    "medium.com": "Medium 原图",
}
MARKED = re.compile(r"water|watermark|[_/!]wm[_/.\-]", re.I)


def judge_url(url: str) -> tuple[bool, str]:
    host = (urlparse(url or "").hostname or "").lower()
    if MARKED.search(url or ""):
        return False, f"地址带水印标记（{host}）"
    for suf, why in CLEAN_HOSTS.items():
        if host == suf or host.endswith("." + suf):
            return True, why
    return False, f"未知或会盖水印的图床（{host or '无地址'}）"


def judge(images: list) -> dict:
    """返回写进 meta.extra 的字段：watermark_free（全部图干净才 True）和原因。"""
    urls = [u for u in images or [] if u]
    if not urls:
        return {}
    verdicts = [judge_url(u) for u in urls]
    free = all(ok for ok, _ in verdicts)
    reasons = sorted({why for ok, why in verdicts if ok == free})
    return {"watermark_free": free, "watermark_reason": "；".join(reasons)}
