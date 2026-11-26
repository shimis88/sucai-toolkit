"""站点模块。每个模块提供 NAME、MATCH（链接正则）和 run(post, opts)。
没有专用模块的链接交给 ytdlp_site（yt-dlp 支持的上千个站点：YouTube、TikTok、Instagram、Reddit…）。"""
import re

from . import bilibili, douyin, weibo, x, xiaohongshu, youtube, ytdlp_site

DEDICATED = [weibo, douyin, xiaohongshu, bilibili, x, youtube]


def detect(url):
    for module in DEDICATED:
        if re.search(module.MATCH, url, re.I):
            return module
    return ytdlp_site
