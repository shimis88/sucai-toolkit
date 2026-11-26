#!/usr/bin/env python3
"""Batch scrape: pull every public link out of messy share text and process them together.

Usage:
  .venv/bin/python batch.py links.txt
  .venv/bin/python batch.py - < pasted.txt
  .venv/bin/python batch.py "6.10 复制打开抖音…… https://v.douyin.com/xxx/" "https://x.com/..."

No cookies, no paid APIs. Calls get.py as a subprocess.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from sites import detect  # noqa: E402

PY = ROOT / ".venv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)

CONVERT = ROOT.parent / "media-convert" / "convert.sh"
DEWM = ROOT.parent / "img-dewatermark" / "run.sh"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
try:  # 用户时区：环境变量 SUCAI_TZ（如 Asia/Shanghai、America/New_York），默认 Asia/Shanghai
    from zoneinfo import ZoneInfo
    USER_TZ = ZoneInfo(os.environ.get("SUCAI_TZ", "Asia/Shanghai"))
except Exception:
    USER_TZ = timezone(timedelta(hours=8))

# Short hosts that must be resolved before platform detection / dedupe.
SHORT_HOSTS = {
    "t.co",
    "v.douyin.com", "www.v.douyin.com",
    "xhslink.com", "www.xhslink.com", "xhslink.cn", "www.xhslink.cn",
    "b23.tv", "www.b23.tv",
    "t.cn",
    "youtu.be", "www.youtu.be",
    "pin.it", "vm.tiktok.com", "vt.tiktok.com",
    "fb.watch", "redd.it", "bit.ly", "tinyurl.com", "ow.ly",
}

TRACKING_KEYS = {
    "s", "t", "si", "feature", "pp", "ref_src", "ref_url", "twclid", "cxt", "cn-fr",
    "fbclid", "igshid", "src", "sref",
}

HOST_RE = (
    r"(?:(?:www|m|mobile|v)\.)?(?:"
    r"youtube\.com|youtu\.be|bilibili\.com|b23\.tv|"
    r"x\.com|twitter\.com|t\.co|"
    r"douyin\.com|iesdouyin\.com|"
    r"xiaohongshu\.com|rednote\.com|xhslink\.(?:com|cn)|"
    r"tiktok\.com|instagram\.com|facebook\.com|fb\.watch|"
    r"threads\.(?:net|com)|linkedin\.com|reddit\.com|redd\.it|"
    r"pinterest\.[a-z.]+|pin\.it|t\.me|telegram\.me|"
    r"medium\.com|bsky\.app|mp\.weixin\.qq\.com|"
    r"(?:share\.api\.|video\.|h5\.video\.)?weibo\.(?:com|cn)|t\.cn"
    r")"
)
URL_RE = re.compile(r"https?://[^\s<>\"'）)」】\]>，。；：！？、》]+", re.I)
BARE_RE = re.compile(r"(?<![\w./:@-])(" + HOST_RE + r"/[^\s<>\"'）)」】\]>，。；：！？、》]+)", re.I)
TRAIL_PUNCT = re.compile(r"[.,;:!?）)」】\]>\"'，。；：！？、》]+$")

STAT_ZH = {
    "likes": "赞",
    "comments": "评论",
    "replies": "评论",
    "shares": "转发",
    "reposts": "转发",
    "collects": "收藏",
    "favorites": "收藏",
    "coins": "投币",
    "views": "播放",
    "danmaku": "弹幕",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov"}
_DEWM_LOCK = threading.Lock()
_GIF_LOCK = threading.Lock()


def _clean_url(u: str) -> str:
    u = TRAIL_PUNCT.sub("", u.strip())
    while u.endswith(")") and u.count("(") < u.count(")"):
        u = u[:-1]
    while u.endswith("]") and u.count("[") < u.count("]"):
        u = u[:-1]
    return u


def extract_urls(text: str) -> list[str]:
    """Pull http(s) and bare known-host links out of arbitrary share text."""
    found: list[str] = []
    seen: set[str] = set()

    def add(u: str):
        u = _clean_url(u)
        if not u or u in seen:
            return
        seen.add(u)
        found.append(u)

    for m in URL_RE.finditer(text or ""):
        add(m.group(0))
    for m in BARE_RE.finditer(text or ""):
        start = m.start()
        prefix = (text or "")[max(0, start - 8) : start].lower()
        if prefix.endswith("://") or prefix.endswith("http://") or prefix.endswith("https://"):
            continue
        add("https://" + m.group(1))
    return found


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def expand_short(url: str, timeout: int = 15) -> str:
    """Follow redirects on short links. Leave already-canonical URLs alone."""
    raw = url
    host = _host(url)
    if url.startswith("http://") and ("xhslink" in host or host == "t.cn"):
        url = "https://" + url[7:]  # http xhslink / t.cn often return 500
        host = _host(url)
    if host not in SHORT_HOSTS:
        return url
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True, stream=True)
        final = r.url or url
        r.close()
        fp = urlparse(final)
        if (fp.hostname or "").startswith("passport.weibo."):  # t.cn 没 cookie 会落到微博访客页，真实地址在 url= 里
            inner = dict(parse_qsl(fp.query)).get("url")
            if inner:
                final = inner
        return final
    except Exception:
        return raw


def _query_without_tracking(query: str) -> str:
    q = []
    for k, v in parse_qsl(query, keep_blank_values=True):
        kl = k.lower()
        if kl in TRACKING_KEYS or kl.startswith("utm_"):
            continue
        q.append((k, v))
    return urlencode(q, doseq=True)


def for_scrape(url: str) -> str:
    """Light cleanup for the URL we actually hand to get.py. Keeps www."""
    p = urlparse((url or "").strip())
    host = (p.hostname or "").lower()
    if host in {"twitter.com", "www.twitter.com", "mobile.twitter.com", "mobile.x.com", "www.x.com"}:
        host = "x.com"
    if host in {"m.youtube.com", "music.youtube.com"}:
        host = "www.youtube.com"
    if host == "youtu.be" or host == "www.youtu.be":
        vid = (p.path or "").strip("/")
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return f"https://www.youtube.com/watch?v={vid}"
        host = "www.youtube.com"
    if host == "m.bilibili.com":
        host = "www.bilibili.com"
    if host == "youtube.com":
        host = "www.youtube.com"
    if host == "bilibili.com":
        host = "www.bilibili.com"
    if host == "douyin.com":
        host = "www.douyin.com"
    query = _query_without_tracking(p.query)
    return urlunparse(("https", host, p.path or "", "", query, ""))


def normalize_url(url: str) -> str:
    """Dedupe form: lowercase host, drop www, drop tracking params."""
    p = urlparse(for_scrape(url) if url else "")
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"twitter.com", "mobile.twitter.com", "mobile.x.com"}:
        host = "x.com"
    if host in {"m.youtube.com", "music.youtube.com", "youtu.be"}:
        host = "youtube.com"
    if host in {"m.bilibili.com"}:
        host = "bilibili.com"
    q = []
    for k, v in parse_qsl(p.query, keep_blank_values=True):
        kl = k.lower()
        if kl in TRACKING_KEYS or kl.startswith("utm_"):
            continue
        q.append((k, v))
    query = urlencode(q, doseq=True)
    path = p.path or ""
    # youtu.be/ID → youtube.com/watch?v=ID when we already rewrote the host
    if host == "youtube.com" and re.fullmatch(r"/[A-Za-z0-9_-]{11}/?", path) and not query:
        vid = path.strip("/")
        path, query = "/watch", f"v={vid}"
    return urlunparse(("https", host, path, "", query, ""))


def dedupe_key(url: str, platform: str) -> tuple[str, str]:
    if platform == "x":
        m = re.search(r"/status/(\d+)", url)
        if m:
            return ("x", m.group(1))
        m = re.search(r"x\.com/([A-Za-z0-9_]{1,15})/?$", url)
        if m:
            return ("x-profile", m.group(1).lower())
    if platform == "youtube":
        m = re.search(r"(?:v=|/shorts/|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url)
        if m:
            return ("youtube", m.group(1))
    if platform == "douyin":
        m = re.search(r"(?:video|note|modal_id=)/?(\d{15,20})", url)
        if m:
            return ("douyin", m.group(1))
    if platform == "bilibili":
        m = re.search(r"(BV[0-9A-Za-z]{10})", url, re.I)
        if m:
            return ("bilibili", m.group(1).upper())
    if platform == "xiaohongshu":
        m = re.search(r"/(?:explore|discovery/item|items)/([0-9a-f]+)", url, re.I)
        if m:
            return ("xiaohongshu", m.group(1).lower())
    if platform == "weibo":
        from sites.weibo import canonical_mid, parse_url
        kind, val = parse_url(url)
        if kind == "status":
            return ("weibo", canonical_mid(val))
        if kind == "video":
            return ("weibo-video", val)
    return ("url", normalize_url(url).rstrip("/").lower())


def collect_urls(text: str) -> list[tuple[str, str]]:
    """Extract, expand short links, normalize, dedupe. Returns [(url, platform), ...]."""
    raw = extract_urls(text)
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for u in raw:
        expanded = expand_short(u)
        scrape = for_scrape(expanded)
        platform = detect(scrape).NAME
        key = dedupe_key(normalize_url(scrape), platform)
        if key in seen:
            continue
        seen.add(key)
        out.append((scrape, platform))
    return out


def slug(title: str, n: int = 24) -> str:
    s = html.unescape(title or "")
    s = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > n:
        s = s[:n].rstrip()
    return s or "untitled"


def now_shanghai() -> datetime:
    return datetime.now(USER_TZ)


def read_input(inputs: list[str] | None) -> str:
    if not inputs or inputs == ["-"]:
        return sys.stdin.read()
    parts: list[str] = []
    for item in inputs:
        p = Path(item)
        if p.is_file() and not re.match(r"https?://", item, re.I):
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
        else:
            parts.append(item)
    return "\n".join(parts)


def _fail_reason(code: int, stdout: str, stderr: str) -> str:
    text = (stdout or "") + "\n" + (stderr or "")
    fails = [ln.strip() for ln in text.splitlines() if "[FAIL]" in ln or "ERROR:" in ln]
    if fails:
        return " | ".join(fails[-3:])[:400]
    if stderr.strip():
        return stderr.strip()[-400:]
    return f"get.py 退出码 {code}"


def _load_meta(outdir: Path) -> dict:
    meta = outdir / "meta.json"
    if not meta.exists():
        return {}
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_empty_result(meta: dict, outdir: Path) -> bool:
    """yt-dlp sometimes returns a stub title for a dead YouTube id and exit 0."""
    if not meta:
        return True
    needs = meta.get("unavailable") or []
    if any(c in needs for c in ("content", "profile", "list", "session")):
        return True
    if (meta.get("author") or "").strip():
        return False
    if (meta.get("text") or "").strip():
        return False
    if any(v not in (None, "", 0) for v in (meta.get("stats") or {}).values()):
        return False
    media = [
        p for p in outdir.iterdir()
        if p.is_file() and p.name not in {"meta.json", "content.md"} and not p.name.startswith(".")
    ]
    return not media


def _is_image(path: Path) -> bool:
    if path.suffix.lower() not in IMAGE_EXTS:
        return False
    stem = path.stem
    if stem.endswith("_mask") or stem.endswith("_orig") or stem == "frame":
        return False
    return True


def _is_video(path: Path) -> bool:
    if path.suffix.lower() not in VIDEO_EXTS:
        return False
    return True


def dewatermark_images(outdir: Path) -> tuple[list[str], float, str]:
    """Run img-dewatermark on still images. Serialized (model is heavy). Returns (files, seconds, note)."""
    images = [p for p in sorted(outdir.iterdir()) if p.is_file() and _is_image(p)]
    if not images or not DEWM.exists():
        note = "无图片" if not images else f"{DEWM} 不存在"
        return [], 0.0, note
    tmp = outdir / ".dewm_tmp"
    tmp.mkdir(exist_ok=True)
    # Copy into a staging dir so run.sh does not also pick up frame.jpg / masks
    staged = outdir / ".dewm_in"
    staged.mkdir(exist_ok=True)
    t_work = 0.0
    try:
        for img in images:
            dest = staged / img.name
            if dest.exists():
                dest.unlink()
            dest.write_bytes(img.read_bytes())
        with _DEWM_LOCK:
            t0 = time.time()
            proc = _run([str(DEWM), str(staged), "--out", str(tmp)], timeout=600)
            t_work = time.time() - t0
        note = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return [p.name for p in images], t_work, f"去水印失败: {note[-300:]}"
        done = []
        masks = {f.stem[:-5] for f in tmp.iterdir() if f.is_file() and f.stem.endswith("_mask")}
        for f in tmp.iterdir():
            if not f.is_file():
                continue
            target = outdir / f.name
            is_mask = f.stem.endswith("_mask")
            if not is_mask and f.stem in masks:
                # only keep *_orig when something was actually inpainted
                orig = outdir / f"{f.stem}_orig{f.suffix}"
                src = outdir / f.name
                if src.exists() and not orig.exists():
                    src.replace(orig)
            elif not is_mask:
                # skipped (no watermark): leave the original name, drop the identical copy
                f.unlink()
                done.append(f.name + "（无水印，跳过）")
                continue
            f.replace(target)
            done.append(f.name)
        extra = ""
        n_skip = note.count("[跳过]")
        n_do = len(masks)
        summary = f"处理 {n_do} 张，跳过 {n_skip} 张" if (n_do or n_skip) else "ok"
        return done, t_work, summary
    except Exception as e:
        return [], t_work, f"去水印异常: {type(e).__name__}: {e}"
    finally:
        for d in (tmp, staged):
            if d.exists():
                for f in d.iterdir():
                    try:
                        f.unlink()
                    except OSError:
                        pass
                try:
                    d.rmdir()
                except OSError:
                    pass


class _Proc:
    def __init__(self, returncode, stdout, stderr):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _run(cmd: list[str], timeout: int, env: dict | None = None) -> _Proc:
    import subprocess
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=str(ROOT))
    return _Proc(p.returncode, p.stdout or "", p.stderr or "")


def maybe_gif(outdir: Path) -> tuple[list[str], str]:
    if not CONVERT.exists():
        return [], "convert.sh 不存在"
    made, notes = [], []
    videos = [p for p in sorted(outdir.iterdir()) if p.is_file() and _is_video(p)]
    for v in videos:
        gif = outdir / (v.stem + ".gif")
        with _GIF_LOCK:
            try:
                # --no-optimize: media-convert 的 gifsicle 优化在缺二进制时会直接 die，
                # 不会走到“使用未优化版本”的回退。转 GIF 本身由 gifski 完成。
                p = _run([str(CONVERT), "to-gif", "--no-optimize", "-o", str(gif), str(v)], timeout=600)
            except Exception as e:
                notes.append(f"{v.name}: {e}")
                continue
        if p.returncode == 0 and gif.exists():
            made.append(gif.name)
            notes.append(f"{gif.name} {gif.stat().st_size / 1024 / 1024:.1f}MB")
        else:
            notes.append(f"{v.name}: {(p.stderr or p.stdout)[-200:]}")
    return made, "; ".join(notes)


def maybe_audio(outdir: Path) -> tuple[list[str], str]:
    if not CONVERT.exists():
        return [], "convert.sh 不存在"
    existing = [p for p in outdir.iterdir() if p.suffix.lower() in {".mp3", ".m4a", ".aac"}]
    if existing:
        return [p.name for p in existing], "已有音轨"
    videos = [p for p in sorted(outdir.iterdir()) if p.is_file() and _is_video(p)]
    made, notes = [], []
    for v in videos:
        mp3 = outdir / "audio.mp3"
        try:
            p = _run([str(CONVERT), "audio", "--format", "mp3", "-o", str(mp3), str(v)], timeout=180)
        except Exception as e:
            notes.append(f"{v.name}: {e}")
            continue
        if p.returncode == 0 and mp3.exists():
            made.append(mp3.name)
            break
        notes.append((p.stderr or p.stdout)[-200:])
    return made, "; ".join(notes)


def scrape_one(url: str, outdir: Path, timeout: int, max_height: int, max_mb: int) -> tuple[bool, str, str]:
    cmd = [str(PY), str(ROOT / "get.py"), url, "--with-media", "--out", str(outdir),
           "--max-height", str(max_height), "--max-mb", str(max_mb)]
    env = os.environ.copy()
    try:
        p = _run(cmd, timeout=timeout, env=env)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", ""
    log = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    meta = _load_meta(outdir) if (outdir / "meta.json").exists() else {}
    if _is_empty_result(meta, outdir):
        why = "链接无效或空结果：无作者、无文案、无媒体"
        detail = _fail_reason(p.returncode, p.stdout, p.stderr)
        if detail and not detail.startswith("get.py 退出码"):
            why = f"{why}（{detail}）"
        return False, why, log
    if p.returncode == 0 and meta:
        return True, "", log
    return False, _fail_reason(p.returncode, p.stdout, p.stderr), log


def process_item(idx: int, url: str, platform: str, batch_dir: Path, opts) -> dict:
    title_hint = url.rstrip("/").split("/")[-1][:20]
    # Temporary name; rename after we know the title
    outdir = batch_dir / f"{idx:02d}_{platform}_{title_hint}"
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    ok, reason, log = scrape_one(url, outdir, opts.timeout, opts.max_height, opts.max_mb)
    attempts = 1
    if not ok:
        time.sleep(1.5)
        ok, reason, log2 = scrape_one(url, outdir, opts.timeout, opts.max_height, opts.max_mb)
        log = (log or "") + "\n--- retry ---\n" + (log2 or "")
        attempts = 2
    meta = _load_meta(outdir)
    title = html.unescape(meta.get("title") or "")
    author = html.unescape(meta.get("author") or "")
    text = html.unescape(meta.get("text") or "")
    stats = meta.get("stats") or {}
    # Rename folder now that we have a title
    final_dir = batch_dir / f"{idx:02d}_{platform}_{slug(title)}"
    if final_dir != outdir:
        if final_dir.exists():
            final_dir = batch_dir / f"{idx:02d}_{platform}_{slug(title)}_{idx}"
        try:
            outdir.rename(final_dir)
            outdir = final_dir
        except OSError:
            pass
    dewm_s, dewm_note, gif_note, audio_note = 0.0, "", "", ""
    extra_files: list[str] = []
    if ok:
        if opts.dewm:
            ex = meta.get("extra") or {}
            if ex.get("watermark_free") and not opts.dewm_force:
                # 平台发的就是无水印原图：不跑模型，省时间也不会误伤画面
                dewm_note = f"平台原图无水印，跳过：{ex.get('watermark_reason', '')}"
            else:
                files, dewm_s, dewm_note = dewatermark_images(outdir)
                extra_files += files
        if opts.gif:
            files, gif_note = maybe_gif(outdir)
            extra_files += files
        if opts.audio:
            files, audio_note = maybe_audio(outdir)
            extra_files += files
    media = []
    if outdir.exists():
        skip = {".dewm_tmp", ".dewm_in", "meta.json", "content.md"}
        media = sorted(
            p.name for p in outdir.iterdir()
            if p.is_file() and p.name not in skip and not p.name.startswith(".")
        )
    elapsed = time.time() - t0
    return {
        "index": idx,
        "url": url,
        "platform": platform,
        "ok": ok,
        "reason": reason,
        "title": title,
        "author": author,
        "text": text,
        "stats": stats,
        "media": media,
        "outdir": str(outdir),
        "seconds": elapsed,
        "attempts": attempts,
        "dewm_seconds": dewm_s,
        "dewm_note": dewm_note,
        "gif_note": gif_note,
        "audio_note": audio_note,
    }


class PlatformPool:
    """Global concurrency plus a per-platform cap (to ease rate limits)."""

    def __init__(self, jobs: int, per_platform: int):
        self.global_sem = threading.Semaphore(jobs)
        self.per_platform = per_platform
        self._plat: dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()

    def slot(self, platform: str):
        with self._lock:
            sem = self._plat.get(platform)
            if sem is None:
                sem = self._plat[platform] = threading.Semaphore(self.per_platform)
        return _Slot(self.global_sem, sem)


class _Slot:
    def __init__(self, a, b):
        self.a, self.b = a, b

    def __enter__(self):
        self.a.acquire()
        self.b.acquire()
        return self

    def __exit__(self, *exc):
        self.b.release()
        self.a.release()
        return False


def format_stats(stats: dict) -> str:
    if not stats:
        return "—"
    parts = []
    for k, v in stats.items():
        if v in (None, ""):
            continue
        parts.append(f"{STAT_ZH.get(k, k)} {v}")
    return " / ".join(parts) or "—"


def _fence(text: str) -> str:
    body = (text or "").replace("```", "``\u200b`")
    return "```\n" + body + ("\n" if body and not body.endswith("\n") else "") + "```"


def write_summary(batch_dir: Path, items: list[dict], wall: float, opts) -> None:
    ok_n = sum(1 for i in items if i["ok"])
    fail_n = len(items) - ok_n
    seq = sum(i["seconds"] for i in items)
    dewm_total = sum(i.get("dewm_seconds") or 0 for i in items)
    started = now_shanghai().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# 批量抓取汇总",
        "",
        f"- 时间: {started}（{os.environ.get('SUCAI_TZ', 'Asia/Shanghai')}）",
        f"- 共 {len(items)} 条，成功 {ok_n}，失败 {fail_n}",
        f"- 并行总耗时 {wall:.1f} 秒（各条合计 {seq:.1f} 秒，约等于串行下限）",
        f"- 并发: 全局 {opts.jobs}，单平台最多 {opts.per_platform}；失败重试 1 次",
        f"- 图片去水印: {'开启' if opts.dewm else '关闭'}（合计 {dewm_total:.1f} 秒）",
        f"- 转 GIF: {'开启' if opts.gif else '关闭'}；抽音轨: {'开启' if opts.audio else '关闭'}",
        "",
    ]
    failed_lines = []
    for i in items:
        flag = "成功" if i["ok"] else "失败"
        header = f"## {i['index']:02d}. {flag}  {i['platform']}  {i['title'] or '(无标题)'}"
        lines += [header, ""]
        lines.append(f"- 链接: {i['url']}")
        if i["ok"]:
            lines.append(f"- 作者: {i['author'] or '—'}")
            lines.append(f"- 数据: {format_stats(i['stats'])}")
            lines.append(f"- 耗时: {i['seconds']:.1f} 秒（尝试 {i['attempts']} 次）")
            if opts.dewm:
                extra = f"（{i['dewm_note']}）" if i.get("dewm_note") and i["dewm_note"] not in {"ok", ""} else ""
                lines.append(f"- 去水印: {i['dewm_seconds']:.1f} 秒{extra}")
            if opts.gif and i.get("gif_note"):
                lines.append(f"- GIF: {i['gif_note']}")
            if opts.audio and i.get("audio_note"):
                lines.append(f"- 音轨: {i['audio_note']}")
            if i["text"]:
                lines += ["- 文案:", _fence(i["text"])]
            else:
                lines.append("- 文案: （无）")
            if i["media"]:
                lines.append("- 文件: " + ", ".join(i["media"]))
            else:
                lines.append("- 文件: （无）")
        else:
            lines.append(f"- 原因: {i['reason'] or '未知错误'}")
            lines.append(f"- 耗时: {i['seconds']:.1f} 秒（尝试 {i['attempts']} 次）")
            failed_lines.append(f"{i['url']}\t{i['reason']}")
        lines.append("")
    (batch_dir / "汇总.md").write_text("\n".join(lines), encoding="utf-8")
    (batch_dir / "失败链接.txt").write_text(
        ("\n".join(failed_lines) + "\n") if failed_lines else "（无失败链接）\n",
        encoding="utf-8",
    )


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="从一段分享文案里抽出全部链接，并行抓取并汇总。不使用 cookie，不调用付费接口。"
    )
    ap.add_argument("inputs", nargs="*", help="文本文件、链接，或直接粘贴分享文案。无参数或 - 表示读标准输入。")
    ap.add_argument("--out", help="输出根目录。默认 output/batch_<时间戳>/")
    ap.add_argument("--jobs", type=int, default=4, help="全局并发，默认 4")
    ap.add_argument("--per-platform", type=int, default=2, help="同一平台最多同时几个，默认 2")
    ap.add_argument("--timeout", type=int, default=600, help="单条 scrape 超时秒数，默认 600")
    ap.add_argument("--max-height", type=int, default=1080)
    ap.add_argument("--max-mb", type=int, default=2000)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dewm", dest="dewm", action="store_true", help="图片去水印（默认开启）")
    g.add_argument("--no-dewm", dest="dewm", action="store_false", help="跳过图片去水印")
    ap.set_defaults(dewm=True)
    ap.add_argument("--dewm-force", action="store_true",
                    help="平台原图也跑去水印（默认跳过 X/小红书/抖音等无水印原图；作者自己加的签名才需要）")
    ap.add_argument("--gif", action="store_true", help="把视频再转成 GIF（调用 media-convert to-gif）")
    ap.add_argument("--audio", action="store_true", help="若还没有音轨，再抽一条 MP3")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    opts = parse_args(argv)
    text = read_input(opts.inputs)
    if not text.strip():
        print("没有输入。把分享文案存成文件，或通过管道/参数传进来。", file=sys.stderr)
        return 2
    t_all = time.time()
    links = collect_urls(text)
    if not links:
        print("没有从输入里解析到链接。", file=sys.stderr)
        return 2
    stamp = now_shanghai().strftime("%Y%m%d_%H%M%S")
    batch_dir = Path(opts.out) if opts.out else ROOT / "output" / f"batch_{stamp}"
    if not batch_dir.is_absolute():
        batch_dir = (Path.cwd() / batch_dir).resolve()
    batch_dir.mkdir(parents=True, exist_ok=True)
    print(f"解析到 {len(links)} 条链接，输出目录 {batch_dir}")
    for i, (u, p) in enumerate(links, 1):
        print(f"  {i:02d}. {p:12} {u}")

    pool = PlatformPool(max(1, opts.jobs), max(1, opts.per_platform))
    items: list[dict] = []

    def worker(idx, url, platform):
        with pool.slot(platform):
            print(f"[{idx:02d}/{len(links)}] 开始 {platform}  {url}")
            rec = process_item(idx, url, platform, batch_dir, opts)
            flag = "成功" if rec["ok"] else "失败"
            print(f"[{idx:02d}/{len(links)}] {flag} {platform}  {rec['seconds']:.1f}s  {rec['title'][:40] or rec['reason'][:80]}")
            return rec

    with ThreadPoolExecutor(max_workers=max(1, opts.jobs)) as ex:
        futs = [ex.submit(worker, i, u, p) for i, (u, p) in enumerate(links, 1)]
        for f in as_completed(futs):
            items.append(f.result())
    items.sort(key=lambda r: r["index"])
    wall = time.time() - t_all
    write_summary(batch_dir, items, wall, opts)
    ok_n = sum(1 for i in items if i["ok"])
    print(f"完成: 成功 {ok_n}/{len(items)}，并行 {wall:.1f}s，各条合计 {sum(i['seconds'] for i in items):.1f}s")
    print(f"  汇总: {batch_dir}/汇总.md")
    if any(not i["ok"] for i in items):
        print(f"  失败链接: {batch_dir}/失败链接.txt")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
