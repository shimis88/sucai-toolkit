"""微博博文：文案（含长文全文）、作者、时间、数据、话题、原图、最高清视频、转发原博、评论。

只用微博官方的匿名访客流程（passport genvisitor2 发的游客 cookie，跟没登录打开网页一样），
不读用户/浏览器 cookie，不用付费接口。主接口 weibo.com/ajax，失败再退回 m.weibo.cn。
"""
import datetime as dt
import html
import json
import re
from urllib.parse import parse_qs, unquote, urlparse

from net import UA_PC as UA_DESKTOP, new_session as session
from post import Unreachable as Fail
from util import plain_text as strip_html, try_each as attempt

NAME, MATCH = "weibo", r"(?:^|//|\.)(?:weibo\.com|weibo\.cn|t\.cn)/"
REFERER = "https://weibo.com/"
VIDEO_OID = re.compile(r"(1034:\d{10,20})")
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


# ---------- 链接解析（离线可测） ----------

def bid_to_mid(bid: str) -> str:
    """微博短 ID（mblogid，如 RsnMuf2kM）转数字 mid：从右往左每 4 位 base62 转成 7 位十进制。"""
    out, s = "", bid
    while s:
        chunk, s = s[-4:], s[:-4]
        n = 0
        for c in chunk:
            n = n * 62 + ALPHABET.index(c)
        out = (str(n).zfill(7) if s else str(n)) + out
    return out.lstrip("0") or "0"


def parse_url(url: str):
    """返回 ("status", id) / ("video", "1034:xxx") / ("short", url) / (None, None)。id 可能是数字 mid 或 mblogid。"""
    u = (url or "").strip()
    p = urlparse(u if "://" in u else "https://" + u)
    host, path, q = (p.hostname or "").lower(), p.path or "", parse_qs(p.query)
    if host.startswith("passport.weibo.") and q.get("url"):  # 没 cookie 时跳到访客页，真实地址在 url= 里
        return parse_url(unquote(q["url"][0]))
    if host.endswith("weibo.cn") and path.startswith("/sinaurl"):  # 外链跳转页 weibo.cn/sinaurl?u=...
        target = (q.get("u") or q.get("toasturl") or [""])[0]
        return parse_url(unquote(target)) if target else (None, None)
    m = VIDEO_OID.search(unquote(u))
    if m and ("video" in host or "/tv/" in path or "fid=" in u):
        return "video", m.group(1)
    if host == "t.cn" or host.endswith(".t.cn"):
        return "short", u
    for key in ("weibo_id", "mid", "id"):
        v = (q.get(key) or [""])[0]
        if re.fullmatch(r"\d{15,20}", v):
            return "status", v
    m = re.search(r",(\d{15,20})(?:\.html)?$", path)  # share.api.weibo.cn/share/123,5367...html
    if m:
        return "status", m.group(1)
    m = re.search(r"/(?:detail|status|statuses)/(\d{15,20}|[0-9A-Za-z]{8,10})(?:$|[/?#])", path + "/")
    if m:
        return "status", m.group(1)
    m = re.fullmatch(r"/(?:u/)?\d{5,12}/(\d{15,20}|[0-9A-Za-z]{8,10})/?", path)  # weibo.com/<uid>/<mblogid>
    if m:
        return "status", m.group(1)
    return None, None


def canonical_mid(id_: str) -> str:
    return id_ if id_.isdigit() else bid_to_mid(id_)


# ---------- 取数 ----------

def visitor():
    """微博官方匿名访客 cookie（SUB/SUBP），weibo.com 和 m.weibo.cn 都认。"""
    s = session(UA_DESKTOP, referer=REFERER)
    s.post("https://passport.weibo.com/visitor/genvisitor2",
           data={"cb": "visitor_gray_callback", "tid": "", "from": "weibo"}, timeout=20)
    if not s.cookies.get("SUB"):
        raise Fail("visitor cookie not issued")
    return s


def ajax(s, path, **params):
    r = s.get("https://weibo.com/ajax/" + path, params=params, timeout=20)
    try:
        j = r.json()
    except ValueError:
        raise Fail(f"HTTP {r.status_code} non-JSON (login wall?)")
    if j.get("ok") not in (1, None) or (not j.get("id") and "data" not in j):
        raise Fail(f"HTTP {r.status_code} {str(j)[:120]}")
    return j


def resolve_short(s, url):
    url = re.sub(r"^http://", "https://", url)  # http://t.cn 常返回 500
    r = s.get(url, timeout=20, allow_redirects=True)
    kind, val = parse_url(r.url)
    if not kind:  # 有的短链落到中间页，页面里带真实地址
        m = re.search(r"https?://(?:m\.)?weibo\.(?:com|cn)/[^\"'<>\s]+", r.text)
        kind, val = parse_url(html.unescape(m.group(0))) if m else (None, None)
    if not kind or kind == "short":
        raise Fail(f"short link did not resolve to a weibo post: {r.url[:120]}")
    return kind, val


def tv_playinfo(s, oid):
    """视频页组件接口：给出 1080P/720P/480P 全部清晰度（博文接口里常只有 720P）。"""
    r = s.post(f"https://weibo.com/tv/api/component?page=/tv/show/{oid}",
               data={"data": json.dumps({"Component_Play_Playinfo": {"oid": oid}})},
               headers={"Referer": f"https://weibo.com/tv/show/{oid}"}, timeout=20)
    return ((r.json().get("data") or {}).get("Component_Play_Playinfo")) or {}


def _area(url):
    m = re.search(r"template=(\d+)x(\d+)", url or "")
    return int(m.group(1)) * int(m.group(2)) if m else 0


def best_video(s, page_info):
    """返回 (url, label)。先问视频组件要最高清，再退回博文里的 playback_list / mp4_* 字段。"""
    oid = page_info.get("object_id") or ""
    cands = []
    if VIDEO_OID.fullmatch(oid):
        try:
            cands += [(("https:" + u) if u.startswith("//") else u, k) for k, u in (tv_playinfo(s, oid).get("urls") or {}).items() if u]
        except Exception:
            pass
    mi = page_info.get("media_info") or {}
    for p in mi.get("playback_list") or []:
        u = (p.get("play_info") or {}).get("url") or ""
        if "video.weibocdn.com" in u:
            cands.append((u, (p.get("meta") or {}).get("label", "")))
    for k in ("mp4_1080p_mp4", "mp4_720p_mp4", "stream_url_hd", "mp4_hd_url", "mp4_sd_url", "stream_url"):
        if mi.get(k):
            cands.append((mi[k], k))
    for k, u in (page_info.get("urls") or {}).items():  # m.weibo.cn 格式
        cands.append((u, k))
    cands = [(u.replace("http://", "https://"), k) for u, k in cands if u]
    return max(cands, key=lambda c: _area(c[0])) if cands else (None, None)


def large(url):
    """sinaimg 任意尺寸 -> large（原图）。"""
    return re.sub(r"(sinaimg\.cn)/[a-z0-9_]+/", r"\1/large/", (url or "").replace("http://", "https://"))


def _pic_url(d):
    for k in ("largest", "mw2000", "original", "large", "bmiddle"):
        v = d.get(k)
        u = v.get("url") if isinstance(v, dict) else v
        if u:
            return large(u)
    return large(d.get("url") or "")


def add_pic(res, d):
    res.images.append(_pic_url(d))


def add_video(res, s, page_info):
    u, label = best_video(s, page_info)
    if u and any(v.split("?")[0] == u.split("?")[0] for v in res.videos):
        return  # 转发博文外层的 page_info 就是原博的视频，别下两遍
    if u:
        res.videos.append(u)
        res.extra.setdefault("video_quality", []).append(label)
    cover = (page_info.get("page_pic") or {}).get("url") if isinstance(page_info.get("page_pic"), dict) else page_info.get("page_pic")
    if cover:
        res.extra.setdefault("video_covers", []).append(large(cover))


def add_media(res, s, st):
    """按博文里的顺序收图和视频；混排博文（图+视频）走 mix_media_info。"""
    mix = (st.get("mix_media_info") or {}).get("items") or []
    if mix:
        for it in mix:
            d = it.get("data") or {}
            if it.get("type") == "video":
                add_video(res, s, d)
            else:
                add_pic(res, d)
        return
    infos = st.get("pic_infos") or {}
    for pid in st.get("pic_ids") or []:
        if pid in infos:
            add_pic(res, infos[pid])
    for p in st.get("pics") or []:  # m.weibo.cn 格式
        res.images.append(large((p.get("large") or {}).get("url") or p.get("url")))
    pi = st.get("page_info") or {}
    if str(pi.get("type")) in ("video", "11") or pi.get("object_type") == "video":
        add_video(res, s, pi)


def when(created_at):
    try:
        t = dt.datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
        return t.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M UTC+8")
    except Exception:
        return created_at or ""


def full_text(s, st):
    txt = st.get("text_raw") or strip_html(st.get("text") or "")
    if st.get("isLongText"):
        try:
            lt = (ajax(s, "statuses/longtext", id=st.get("mblogid") or st.get("bid") or st["id"]).get("data") or {})
            txt = lt.get("longTextContent") or txt
        except Exception:
            try:
                r = s.get("https://m.weibo.cn/statuses/extend", params={"id": st["id"]},
                          headers={"Referer": "https://m.weibo.cn/", "MWeibo-Pwa": "1"}, timeout=20).json()
                txt = strip_html((r.get("data") or {}).get("longTextContent") or "") or txt
            except Exception:
                pass
    return txt.replace("\u200b", "").strip()


def topics(st, text):
    t = [x.get("topic_title") for x in st.get("topic_struct") or [] if x.get("topic_title")]
    t += [x for x in re.findall(r"#([^#\n]{1,40})#", text) if x not in t]
    return list(dict.fromkeys(t))


def post_url(st):
    uid = (st.get("user") or {}).get("idstr") or (st.get("user") or {}).get("id")
    return f"https://weibo.com/{uid}/{st.get('mblogid') or st.get('bid') or st.get('id')}"


def fill(res, s, st):
    u = st.get("user") or {}
    res.author = u.get("screen_name", "")
    res.published = when(st.get("created_at"))
    res.text = full_text(s, st)
    res.title = (res.text.splitlines() or [""])[0][:60]
    res.stats = {"likes": st.get("attitudes_count"), "comments": st.get("comments_count"), "reposts": st.get("reposts_count")}
    res.extra.update({"mid": str(st.get("id")), "mblogid": st.get("mblogid") or st.get("bid"), "uid": u.get("idstr") or u.get("id"),
                      "tags": topics(st, res.text), "region": (st.get("region_name") or "").replace("发布于 ", "")})
    res.url = post_url(st)
    add_media(res, s, st)
    rt = st.get("retweeted_status")
    if rt and rt.get("user"):
        rt_text = full_text(s, rt)
        res.extra["retweet"] = {"author": rt["user"].get("screen_name"), "text": rt_text, "url": post_url(rt),
                                "published": when(rt.get("created_at")),
                                "stats": {"likes": rt.get("attitudes_count"), "comments": rt.get("comments_count"), "reposts": rt.get("reposts_count")}}
        res.text += f"\n\n//转发自 @{rt['user'].get('screen_name')}：\n{rt_text}"
        add_media(res, s, rt)
    elif rt:
        res.extra["retweet"] = {"note": "原博已删除或不可见"}
    covers = res.extra.get("video_covers") or []
    if covers and not res.images:  # 纯视频博文：封面也存一张
        res.images.append(covers[0])


def comments(s, res, n=20):
    j = ajax(s, "statuses/buildComments", is_reload=1, id=res.extra["mid"], is_show_bulletin=2, is_mix=0,
             count=n, uid=res.extra.get("uid"), fetch_level=0, locale="zh-CN")
    res.comments = [{"author": (c.get("user") or {}).get("screen_name"), "text": c.get("text_raw") or strip_html(c.get("text")),
                     "likes": c.get("like_counts"), "time": when(c.get("created_at"))} for c in j.get("data") or []]


def run(res, o):
    g = {}

    def get_session():
        g["s"] = visitor()

    if not attempt(res, "session", [("weibo visitor cookie (passport genvisitor2, anonymous)", get_session)]):
        return
    s = g["s"]
    kind, val = parse_url(res.url)
    if kind == "short":
        kind, val = resolve_short(s, res.url)
    if kind == "video":
        info = tv_playinfo(s, val)
        if not info.get("mid"):
            raise Fail("video page has no post id")
        kind, val = "status", str(info["mid"])
    if kind != "status":
        raise Fail("not a weibo post URL (profile/search pages are not supported)")

    def desktop():
        fill(res, s, ajax(s, "statuses/show", id=val, locale="zh-CN", isGetLongText="true"))

    def mobile():
        r = s.get("https://m.weibo.cn/statuses/show", params={"id": val},
                  headers={"Referer": "https://m.weibo.cn/", "MWeibo-Pwa": "1", "X-Requested-With": "XMLHttpRequest"}, timeout=20)
        d = r.json().get("data")
        if not d:
            raise Fail(f"HTTP {r.status_code} no data (deleted or private)")
        d["mblogid"] = d.get("bid")
        fill(res, s, d)

    attempt(res, "content", [("weibo.com/ajax/statuses/show", desktop), ("m.weibo.cn/statuses/show", mobile)])
    if getattr(o, "with_comments", False) and res.extra.get("mid"):
        attempt(res, "comments", [("weibo.com/ajax/statuses/buildComments (top 20)", lambda: comments(s, res))])
