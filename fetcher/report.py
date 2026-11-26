"""把 Post 写成 content.md（人看）和 meta.json（程序看）。"""
import json
import os

from post import Post

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


def write(post: Post, outdir):
    os.makedirs(outdir, exist_ok=True)
    stats = " / ".join(f"{k} {v}" for k, v in post.stats.items() if v not in (None, ""))
    lines = [f"# {post.title or '(无标题)'}", "",
             f"- Platform: {post.site}", f"- Author: {post.author}", f"- Published: {post.published}",
             f"- Stats: {stats}", f"- URL: {post.url}", ""]
    if post.text:
        lines += ["## Text", "", post.text, ""]
    if post.comments:
        lines += ["## Comments", ""] + [
            f"- **{c.get('author', '')}** ({c.get('likes', '')}): {str(c.get('text', '')).strip()[:500]}"
            for c in post.comments] + [""]
    if post.files:
        lines += ["## Media", ""] + [f"- {os.path.basename(p)}" for p in post.files]
        covers = [p for p in post.files if p.lower().endswith(IMAGE_EXT)]
        if covers:
            lines += ["", f"![cover]({os.path.basename(covers[0])})"]
    if post.unavailable:
        lines += ["", "## 免费方法拿不到", ""] + [f"- {name}" for name in post.unavailable]
    with open(os.path.join(outdir, "content.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(outdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(post.meta(), f, ensure_ascii=False, indent=2, default=str)
