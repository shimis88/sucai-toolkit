"""一条帖子抓取结果的数据结构。各站点模块往里填，report.py 负责写成文件。"""
from dataclasses import dataclass, field


@dataclass
class Post:
    site: str
    url: str
    title: str = ""
    author: str = ""
    published: str = ""
    text: str = ""
    stats: dict = field(default_factory=dict)      # likes / comments / shares / collects / views ...
    images: list = field(default_factory=list)     # 图片地址，最清晰的在前
    videos: list = field(default_factory=list)     # 直链，或 YtdlpVideo(链接)
    comments: list = field(default_factory=list)   # [{author, text, likes, time}]
    extra: dict = field(default_factory=dict)      # 站点专有字段（music、tags、video_source …）
    steps: list = field(default_factory=list)      # 每一步用了什么方法、成没成功
    unavailable: list = field(default_factory=list)  # 免费方法拿不到的字段名
    files: list = field(default_factory=list)      # 已保存到磁盘的媒体文件

    def note(self, what, how, ok, detail=""):
        """记一笔：做了 what，用的方法 how，ok 表示成败。失败时把原因打印出来。"""
        self.steps.append({"capability": what, "method": how, "ok": ok, "note": str(detail)[:300]})
        line = f"  [{'OK ' if ok else 'FAIL'}] {what:<9} via {how}"
        print(line + (f" -- {detail}" if detail and not ok else ""))

    def missing(self, what):
        if what not in self.unavailable:
            self.unavailable.append(what)

    def meta(self):
        d = dict(self.__dict__)
        d["videos"] = [v.url if isinstance(v, YtdlpVideo) else v for v in self.videos]
        d["site"] = self.site
        return d


class YtdlpVideo:
    """标记：这个视频要交给 yt-dlp 下载，而不是直链。"""
    def __init__(self, url):
        self.url = url


class Unreachable(Exception):
    """某个免费方法没成功；消息写明原因。"""
