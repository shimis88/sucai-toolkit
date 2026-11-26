"""Xiaohongshu / rednote public share page (mobile H5) — no signing, no cookies, no login.

From a datacenter IP the signed web API returns 461 and the desktop note page redirects to
login, but the mobile share page (iPhone UA + the share link's xsec_token) is served with the
full note in window.__INITIAL_STATE__.noteData. Verified 2026-11-21.
"""
import re, json
import requests

from net import UA_IPHONE
# Hosts that serve the creator's original upload by key (no platform/author watermark).
VIDEO_HOSTS = ("sns-video-bd.xhscdn.com", "sns-video-hw.xhscdn.com", "sns-video-al.xhscdn.com")
IMAGE_HOSTS = ("sns-img-bd.xhscdn.com", "sns-img-qc.xhscdn.com")
WATERMARKED_STREAMS = (259, 309)  # MINI_APP streams: "小红书 + author" overlay burned in


class Blocked(Exception):
    pass


def resolve_short(url):
    """xhslink short link -> full note URL. Must be https (http answers 500); don't follow further."""
    url = re.sub(r"^http://", "https://", url.strip())
    r = requests.get(url, allow_redirects=False, timeout=20)
    loc = r.headers.get("Location")
    if not loc:
        raise Blocked(f"short link HTTP {r.status_code}, no redirect (expired?)")
    return loc


def fetch_state(url):
    r = requests.get(url, headers={"User-Agent": UA_IPHONE, "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=25)
    if "/404" in r.url or "/login" in r.url or "website-login" in r.url:
        raise Blocked(f"redirected to {r.url.split('?')[0]} (xsec_token missing/expired, or note deleted: copy a fresh share link)")
    m = re.search(r"__INITIAL_STATE__=(\{.*?\})</script>", r.text, re.S)
    if not m:
        raise Blocked(f"HTTP {r.status_code}, no __INITIAL_STATE__")
    return json.loads(re.sub(r"\bundefined\b", "null", m.group(1)))


def _alive(url):
    try:
        r = requests.get(url, headers={"Range": "bytes=0-0"}, timeout=15, stream=True)
        r.close()
        return r.status_code in (200, 206) and "video" in r.headers.get("Content-Type", "")
    except requests.RequestException:
        return False


def best_video(n):
    """Return (url, label). Order: creator's original upload > clean stream > watermarked mini-app stream."""
    v = n.get("video") or {}
    key = (v.get("consumer") or {}).get("originVideoKey")
    if key:
        for h in VIDEO_HOSTS:
            u = f"https://{h}/{key}"
            if _alive(u):
                return u, "original upload (no watermark)"
    st = ((v.get("media") or {}).get("stream")) or {}
    clean, marked = [], []
    for codec in ("h264", "h265", "av1"):
        for s in st.get(codec) or []:
            u = s.get("masterUrl") or (s.get("backupUrls") or [None])[0]
            if u:
                (marked if s.get("streamType") in WATERMARKED_STREAMS else clean).append(((s.get("height") or 0), u, codec))
    for lst, tag in ((clean, "clean stream"), (marked, "MINI_APP stream (has 小红书 watermark)")):
        if lst:
            h, u, codec = max(lst)
            return u.replace("http://", "https://"), f"{tag} {codec} {h}p"
    return None, None


def image_url(i):
    """Original image by fileId (full size, no re-encode); fall back to the page URL."""
    fid = i.get("fileId") or ""
    return f"https://{IMAGE_HOSTS[0]}/{fid}" if fid else (i.get("url") or i.get("urlDefault") or "").replace("http://", "https://")


def parse(st):
    d = ((st.get("noteData") or {}).get("data")) or {}
    n = d.get("noteData")
    if not n:
        raise Blocked("page has no noteData")
    return n, ((d.get("commentData") or {}).get("comments")) or []
