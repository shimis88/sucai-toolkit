"""把 Post 里的图片、视频、音轨存到磁盘；可选口播转写。"""
import os
import shutil
import subprocess

import net
import ytdl
from post import Post, YtdlpVideo

REFERERS = {"bilibili": "https://www.bilibili.com/", "weibo": "https://weibo.com/"}
HEIC_BRANDS = (b"heic", b"heix", b"mif1", b"msf1", b"heim", b"heis")


def _ffmpeg(*args):
    return subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", *args], capture_output=True)


def _heic_to_jpg(path):
    """有的 CDN 把 HEIC 装成 .jpg 发出来，转成真 JPEG（q95，原尺寸），所有设备都能打开。"""
    with open(path, "rb") as f:
        head = f.read(12)
    if head[4:8] != b"ftyp" or head[8:12] not in HEIC_BRANDS or not shutil.which("heif-convert"):
        return path
    backup = path + ".heic"
    os.replace(path, backup)
    ok = subprocess.run(["heif-convert", "-q", "95", backup, path], capture_output=True).returncode == 0
    if ok and os.path.exists(path):
        os.remove(backup)
    else:
        os.replace(backup, path)
    return path


def _image_ext(url):
    path = url.split("?")[0].lower()
    if ".webp" in path:
        return ".webp"
    return next((e for e in (".gif", ".png") if path.endswith(e)), ".jpg")


def _save_images(post, outdir, opts, ua, referer):
    for i, url in enumerate([u for u in post.images if u][:opts.max_images]):
        target = os.path.join(outdir, f"image_{i:02d}{_image_ext(url)}")
        try:
            post.files.append(_heic_to_jpg(net.save(url, target, ua, referer)))
            post.note("image", f"download #{i}", True)
        except Exception as e:
            post.note("image", f"download #{i}", False, e)


def _save_bilibili(post, outdir, opts, ua, referer):
    limit = opts.max_mb << 20
    audio = net.save_first(post.extra["dash_audio"], os.path.join(outdir, "audio.m4s"), ua=ua, referer=referer, max_bytes=limit)
    video = net.save_first(post.extra["dash_video"], os.path.join(outdir, "video.m4s"), ua=ua, referer=referer, max_bytes=limit)
    if not ytdl.HAS_FFMPEG:
        post.files += [audio, video]
        return
    merged = os.path.join(outdir, "video.mp4")
    _ffmpeg("-i", video, "-i", audio, "-c", "copy", merged)
    post.files.append(merged)
    os.remove(video)
    mp3 = os.path.join(outdir, "audio.mp3")
    _ffmpeg("-i", audio, "-vn", "-c:a", "libmp3lame", mp3)
    os.remove(audio)
    post.files.append(mp3)


def _save_videos(post, outdir, opts, ua, referer):
    videos = [v for v in post.videos if v]
    for i, v in enumerate(videos):
        label = "download" if len(videos) == 1 else f"download #{i + 1}"
        try:
            if post.site == "bilibili":
                if i == 0:
                    _save_bilibili(post, outdir, opts, ua, referer)
                else:
                    break
            elif isinstance(v, YtdlpVideo):
                post.files += ytdl.download(v.url, outdir, max_height=opts.max_height)
            else:
                name = "video.mp4" if len(videos) == 1 else f"video_{i + 1}.mp4"
                saver = net.save_parallel if post.site == "weibo" else net.save
                post.files.append(saver(v, os.path.join(outdir, name), ua, referer, max_bytes=opts.max_mb << 20))
            post.note("video", label, True)
        except Exception as e:
            post.note("video", label, False, e)
            post.missing("video")


def _extras(post, outdir, opts, ua, referer):
    music = post.extra.get("music")  # 抖音图文的背景音乐
    if music:
        try:
            post.files.append(net.save(music, os.path.join(outdir, "music.mp3"), ua, referer, max_bytes=opts.max_mb << 20))
            post.note("music", "download", True)
        except Exception as e:
            post.note("music", "download", False, e)
    clips = [p for p in post.files if p.endswith((".mp4", ".webm", ".mkv"))]
    if clips and ytdl.HAS_FFMPEG:
        if not any(p.endswith(".mp3") for p in post.files):
            mp3 = os.path.join(outdir, "audio.mp3")
            _ffmpeg("-i", clips[0], "-vn", "-c:a", "libmp3lame", mp3)
            if os.path.exists(mp3):
                post.files.append(mp3)
        if not any(p.lower().endswith(".jpg") or p.lower().endswith((".webp", ".png")) for p in post.files):
            frame = os.path.join(outdir, "frame.jpg")
            _ffmpeg("-ss", "1", "-i", clips[0], "-frames:v", "1", frame)
            if os.path.exists(frame):
                post.files.append(frame)
    sub_url = post.extra.get("subtitle_url")
    if sub_url:
        try:
            post.files.append(net.save(sub_url, os.path.join(outdir, f"subtitle.{post.extra['subtitle_lang']}.vtt")))
        except Exception as e:
            post.note("subtitles", "download", False, e)
            post.missing("subtitles")


def transcribe(audio, model="small"):
    """faster-whisper（CPU int8）。每行前面带起始秒数。"""
    import numpy as np
    from faster_whisper import WhisperModel
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", audio, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    wave = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    segments, _ = WhisperModel(model, device="cpu", compute_type="int8").transcribe(wave)
    return "\n".join(f"[{s.start:.1f}s] {s.text.strip()}" for s in segments)


def _transcribe(post, outdir, opts):
    audio = next((p for p in post.files if p.endswith(".mp3")), None)
    if not audio:
        return
    try:
        path = os.path.join(outdir, "transcript.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(transcribe(audio, opts.whisper_model))
        post.files.append(path)
        post.note("transcript", "faster-whisper", True)
    except Exception as e:
        post.note("transcript", "faster-whisper", False, e)


def save_all(post: Post, outdir, opts):
    os.makedirs(outdir, exist_ok=True)
    referer = REFERERS.get(post.site)
    ua = net.UA_ANDROID if post.site == "douyin" else net.UA_PC
    _save_images(post, outdir, opts, ua, referer)
    _save_videos(post, outdir, opts, ua, referer)
    _extras(post, outdir, opts, ua, referer)
    if opts.transcribe:
        _transcribe(post, outdir, opts)
