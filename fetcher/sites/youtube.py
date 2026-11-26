"""YouTube：和通用站点同一套 yt-dlp 流程（含字幕），单独成模块是为了批量去重认得出同一个视频。"""
from sites import ytdlp_site

NAME = "youtube"
MATCH = r"(youtube\.com|youtu\.be)/"
run = ytdlp_site.run
