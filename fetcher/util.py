"""小工具：时间格式、HTML 文本提取、依次尝试多个方法。"""
import datetime as dt
import html
import re

from post import Unreachable

USER_TZ_NOTE = "UTC"


def utc_text(value):
    """时间戳（秒）/ ISO 字符串 → 'YYYY-MM-DD HH:MM UTC'。解析不了就原样返回。"""
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            moment = dt.datetime.fromtimestamp(int(value), dt.timezone.utc)
        else:
            moment = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, OSError, OverflowError):
        return str(value or "")


def og_tag(page, prop):
    m = re.search(r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]*)"' % re.escape(prop), page)
    return html.unescape(m.group(1)) if m else ""


def plain_text(fragment):
    fragment = re.sub(r"<br\s*/?>|</p>", "\n", fragment or "")
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def try_each(post, what, methods):
    """按顺序试 [(名字, 函数)]，第一个不抛错的算成功。全失败就把 what 记进 post.unavailable。"""
    for name, fn in methods:
        try:
            fn()
        except Exception as e:  # 站点方法千奇百怪，失败原因只记录、不中断
            post.note(what, name, False, f"{type(e).__name__}: {e}")
        else:
            post.note(what, name, True)
            return True
    post.missing(what)
    return False


def require(condition, message):
    if not condition:
        raise Unreachable(message)
