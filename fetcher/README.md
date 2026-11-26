# fetcher：公开链接 → 文案 + 数据 + 最高清原片

日常用 `sucai get` / `sucai batch`。这里是实现说明。只用免费公开方法：不读 cookie，不登录，不用付费接口。

```sh
fetcher/.venv/bin/python get.py "<链接>" --with-media --out <目录> [--transcribe] [--with-comments] [--max-height 1080]
fetcher/.venv/bin/python batch.py links.txt --out <目录> [--no-dewm] [--dewm-force] [--gif] [--audio]
```

输出 `content.md`（给人看）和 `meta.json`（给程序看，含 `unavailable` = 免费方法拿不到的字段，如实告诉用户即可）。
`extra.watermark_free=true` 表示平台给的就是无水印原图（规则在 `policy.py`），不用再去水印。
批量：每条一个子目录，根目录有 `汇总.md`、`失败链接.txt`；并发 4，同平台最多 2，失败重试 1 次。

## 站点（`sites/`）

| 站点 | 方法 | 验证情况 |
|---|---|---|
| 抖音 | iesdouyin 分享页（游客 ttwid + 安卓 UA）：无水印视频、图集原图、图文 BGM；无评论 | 真实链接测过：1080p 视频 |
| X / 推特 | syndication → fxtwitter → yt-dlp：全部图、视频、GIF 取最高码率；无评论 | 真实链接测过：1080p 视频 |
| B 站 | 官方接口游客模式（DASH 合并），含热门评论 | 真实链接测过：1080p |
| 微博 | 官方匿名访客流程：长文、转发原博、视频（8 段并行下载）、评论 | 真实链接测过：视频、图、评论 |
| YouTube | yt-dlp（需 node）：1080p、字幕、评论 | 真实链接测过 |
| 小红书 | 手机分享页 + 链接里的 `xsec_token`：作者原片、原图；必须是新鲜的完整分享链接 | 页面数据到成品的转换有离线测试；这一版没有拿真实链接联网验证 |
| 其他 | 交给 yt-dlp（上千个站点） | TikTok、Facebook 视频、Telegram 测过；Reddit、Bluesky、Threads、微信公众号拿不到 |

## 口播转写

`--transcribe`：faster-whisper small，CPU int8，输出带时间戳的 `transcript.txt`。中文可能出繁体，交付前按用户习惯转换。

## 测试

`for t in tests/test_*.py; do .venv/bin/python $t; done`（离线，`sucai selftest` 会跑）。
