---
name: open-social-link
description: 打开并读取用户发来的小红书 / 抖音链接（含 xhslink.com、v.douyin.com 短链或整段"复制打开"分享文字），提取标题、正文、作者、点赞收藏评论数、话题标签、图片和视频地址。用户发来这类链接、或让你"看看/总结/分析这篇笔记/这个视频"时使用。
---

# 打开小红书 / 抖音链接

1. **首选 TikHub（完整内容 + 无水印视频地址，抖音也能用）**，把用户发来的整段文字原样传进去：

   ```bash
   python3 -I .claude/skills/open-social-link/scripts/tikhub.py "<用户发来的原文>"
   # 要下载视频/图片：加 --download <目录>（云端用 scratchpad 目录）；字段不全时加 --raw 看原始返回
   ```
   云端会话的 TikHub 密钥由网络代理自动注入（`ziyeh` 环境里 api.tikhub.io 的网络密钥），不需要环境变量；本地电脑用 `export TIKHUB_API_KEY=...`。每次调用会扣 TikHub 余额，批量操作前先告诉用户。

   **下载后交给用户**：在手机上用时，用 SendUserFile 把下载好的 mp4/jpg 发给用户；如果云端下载被拦（`download_error`），就把 `video_url` 直接发给用户，让他在手机浏览器里点开保存。

   TikHub 出错（401 密钥无效、402 余额不足）时，退回免费脚本：

   ```bash
   python3 -I .claude/skills/open-social-link/scripts/fetch_social.py "<用户发来的原文>"
   ```

2. 脚本输出 JSON。根据用户需求用中文回答：默认给出标题、作者、正文要点、互动数据和标签；用户要总结/分析就基于 `desc` 做。
3. 图片 / 视频地址是临时 CDN 链接，可以列给用户，但不要承诺长期有效。

## 出错时

- `CONNECT tunnel failed, response 403`：当前云环境没放行这些域名。需要用名为 **ziyeh** 的云环境开会话（已放行 www.xiaohongshu.com、xhslink.com、edith.xiaohongshu.com、www.rednote.com、v.douyin.com、www.douyin.com、www.iesdouyin.com）。
- 小红书"没拿到笔记内容"：链接里通常缺 `xsec_token`。让用户在 App 里点"分享 → 复制链接"发完整链接（xhslink.com 短链也行）。
- 抖音"页面没有返回视频数据"：抖音对海外云服务器 IP 不返回视频数据，这是已知限制。不要伪装爬虫 UA 或绕过风控。改为：
  - 抖音"复制分享"的文字本身就包含视频文案，直接从用户发来的原文读取；
  - 或请用户截图 / 粘贴文案。
- 只读取公开内容，不登录、不批量抓取。
