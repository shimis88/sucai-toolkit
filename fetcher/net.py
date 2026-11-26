"""网络层：请求头、会话、下载（整文件 / 多段并行 / 多个镜像依次试）。"""
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import requests

from post import Unreachable

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/126.0.0.0 Safari/537.36")
UA_ANDROID = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0.0.0 Mobile Safari/537.36")
UA_IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
UA_SEARCH_BOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
TIMEOUT = 25
MIN_FILE = 500  # 小于这个字节数的下载结果当作失败（多半是错误页）


def https(url):
    return "https://" + url[7:] if url.startswith("http://") else url


def new_session(ua=UA_PC, referer=None, cookies=None):
    s = requests.Session()
    s.headers["User-Agent"] = ua
    if referer:
        s.headers["Referer"] = referer
    if cookies:
        s.cookies.update(cookies)
    return s


def fetch(url, ua=UA_PC, session=None, **kw):
    """GET，带统一超时。返回 requests.Response。"""
    return (session or new_session(ua)).get(url, timeout=TIMEOUT, **kw)


def _headers(ua, referer):
    h = {"User-Agent": ua}
    if referer:
        h["Referer"] = referer
    return h


def save(url, path, ua=UA_PC, referer=None, max_bytes=None):
    """把整个文件存到 path。超过 max_bytes 直接报错，绝不存半截。"""
    size = 0
    with requests.get(https(url), headers=_headers(ua, referer), timeout=60, stream=True) as r:
        if r.status_code not in (200, 206):
            raise Unreachable(f"HTTP {r.status_code}")
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                size += len(chunk)
                if max_bytes and size > max_bytes:
                    f.close()
                    os.remove(path)
                    raise Unreachable(f"超过 --max-mb 上限（{max_bytes >> 20} MB）")
                f.write(chunk)
    if size < MIN_FILE:
        raise Unreachable("文件太小，多半是错误页")
    return path


def save_parallel(url, path, ua=UA_PC, referer=None, max_bytes=None, parts=8, min_size=8 << 20):
    """大文件分段并行下载（CDN 支持 Range 时），否则回到 save()。微博视频冷缓存时单连接很慢。"""
    url, headers = https(url), _headers(ua, referer)
    try:
        probe = requests.get(url, headers={**headers, "Range": "bytes=0-0"}, timeout=30)
        total = int((probe.headers.get("Content-Range") or "/0").rsplit("/", 1)[-1] or 0)
        ranged = probe.status_code == 206
    except (requests.RequestException, ValueError):
        return save(url, path, ua, referer, max_bytes)
    if not ranged or total < min_size:
        return save(url, path, ua, referer, max_bytes)
    if max_bytes and total > max_bytes:
        raise Unreachable(f"超过 --max-mb 上限（{max_bytes >> 20} MB）")
    step = -(-total // parts)
    with open(path, "wb") as f:
        f.truncate(total)
    fd = os.open(path, os.O_WRONLY)

    def part(i):
        lo, hi = i * step, min(total, (i + 1) * step) - 1
        for _ in range(3):
            try:
                pos = lo
                with requests.get(url, headers={**headers, "Range": f"bytes={lo}-{hi}"}, timeout=120, stream=True) as r:
                    if r.status_code != 206:
                        continue
                    for chunk in r.iter_content(1 << 20):
                        os.pwrite(fd, chunk, pos)
                        pos += len(chunk)
                if pos == hi + 1:
                    return
            except requests.RequestException:
                pass
        raise Unreachable(f"第 {i} 段下载失败")

    try:
        with ThreadPoolExecutor(parts) as pool:
            list(pool.map(part, range(parts)))
    except Unreachable:
        os.close(fd)
        return save(url, path, ua, referer, max_bytes)
    os.close(fd)
    return path


def save_first(urls, path, **kw):
    """多个镜像地址依次试，全失败就抛最后一个错。"""
    last = Unreachable("没有可用地址")
    for u in urls:
        try:
            return save(u, path, **kw)
        except (Unreachable, requests.RequestException) as e:
            last = e
    raise last
