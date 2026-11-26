# 素材工具 sucai-toolkit

> **使用、安装即视为同意[免责声明](DISCLAIMER.md)。禁止将本工具用于任何违法犯罪用途，后果由使用者自行承担。**
> **By installing or using this software you agree to the [Disclaimer](DISCLAIMER.md). Illegal use is prohibited; you bear all consequences.**

**发一个链接，拿回最高清、无水印的原片 + 文案 + 数据。** 给 AI 助手用的免费开源素材工具，作者 **shimis**（X：[@shimis_88](https://x.com/shimis_88)）。

- 抖音、X/推特、B 站、微博、YouTube、小红书 → 原片或全部原图、文案、点赞评论转发、发布时间
- 压成适合发 X 的视频（自动画质自检）、转 GIF、图片去水印、提取 BGM、分离人声和伴奏、口播转文字、批量下载并打包
- 不用付费接口，不读浏览器 cookie，不用登录，不需要显卡

## 一句话使用：把这句发给你的 AI

```
请把 https://github.com/shimis88/sucai-toolkit 克隆到你自己的云电脑上，按仓库里的 AGENTS.md 装好这套素材工具，自测通过后当我的素材专家。
```

## 三步

1. 把上面这句话发给能运行命令行的 AI（Grok Bot、Claude、Cursor、Codex 等）。
2. AI 自己安装（约 2GB、几分钟）并自测，然后问你称呼、语言、时区。
3. 之后把链接发给它：「压成发 X 的」「转 GIF」「去水印」「要背景音乐」「要口播文字」直接说。

## 自己装

```bash
git clone --depth 1 https://github.com/shimis88/sucai-toolkit ~/tools/sucai
bash ~/tools/sucai/install.sh        # 可重复运行；--full 多装 Florence-2（+2GB）、--no-gifski 不装 AGPL 组件
sucai doctor && sucai selftest
sucai get "https://x.com/…/status/…" # sucai help 看全部命令
```

要求：Linux x86_64（Debian/Ubuntu 最省事）、≥4GB 内存、≥5GB 磁盘。全部装在仓库目录里，删掉目录即卸载。

## 实际能做到什么（如实）

| | 情况 |
|---|---|
| 真实链接测过原片（1080p H.264） | 抖音、X、B 站、微博、YouTube |
| 其他能下的 | TikTok、Facebook 视频、Telegram（yt-dlp） |
| 小红书 | 需要新鲜完整的分享链接；转换逻辑有离线测试，这一版没拿真实链接验证 |
| 拿不到 | 抖音/X 的评论、需要登录的内容、Reddit/Bluesky/Threads/公众号；平台本身只给 720p 就是 720p |
| 不做 | 视频里烧进画面的水印、录网页动画（没有显卡）、实况图 |

## 目录

| 路径 | 作用 |
|---|---|
| `AGENTS.md` | 给 AI 的安装和使用说明（入口） |
| `skills/` | AI 的操作手册：`getting-started`、`media-workflow` |
| `sucai`、`install.sh` | 命令入口、一键安装 |
| `fetcher/` | 链接抓取、批量、口播转写 |
| `media-convert/` | 转码、压 X 版、GIF、抽音轨、`m3u8` 下载 |
| `img-dewatermark/` | 图片去水印（CPU） |
| `stem-split/` | 人声/伴奏分离（Demucs，CPU） |
| `tests/` | `sucai doctor`、`sucai selftest` |

## 许可证

MIT，© shimis（@shimis_88）。使用前请阅读并同意 [免责声明](DISCLAIMER.md)。安装时下载的第三方软件各自遵循原许可证，其中 gifski 为 AGPL-3.0（可 `--no-gifski`），见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
去水印仅可用于您有权处理的内容，且只适合个人自用，请尊重原作者版权。

---

**English** — sucai-toolkit by shimis ([@shimis_88](https://x.com/shimis_88)): a free, open-source media toolkit for AI agents. Send a public link (Douyin, X, Bilibili, Weibo, YouTube, Xiaohongshu…), get the highest-quality watermark-free original, caption and stats; plus X-ready compression, GIF, image watermark removal, vocal separation and transcription. No paid APIs, no cookies, no login, no GPU. Use constitutes agreement to the Disclaimer (DISCLAIMER.md). Tell your agent: *"Clone https://github.com/shimis88/sucai-toolkit and follow AGENTS.md to install it, then act as my media assistant."*
