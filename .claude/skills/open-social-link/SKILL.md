---
name: open-social-link
description: 打开并读取用户发来的小红书 / 抖音链接（含 xhslink.com、v.douyin.com 短链或整段"复制打开"分享文字），提取标题、正文、作者、点赞收藏评论数、话题标签、图片和视频地址。用户发来这类链接、或让你"看看/总结/分析这篇笔记/这个视频"时使用。
---

# 打开小红书 / 抖音链接

1. 把用户发来的整段文字（可以带"复制打开小红书"之类的废话）原样传给脚本：

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
