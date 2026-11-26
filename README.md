# ziyeh

在手机上让 Claude 打开小红书 / 抖音链接、下载和搬运视频。

| 用法 | 打开小红书 | 打开抖音 | 下载无水印视频 | 自动发布 |
|---|---|---|---|---|
| **手机 → 云端会话（仓库 `ziyeh678/ziyeh` + 环境 `ziyeh`）** | ✅ | ✅（TikHub） | ✅ 直接发到手机 | ❌ 在 App 里自己发 |
| 手机 → 遥控自己电脑 | ✅ | ✅ | ✅ | ✅ |

云端方案用 [TikHub](https://tikhub.io) 解析抖音（按次计费，密钥存在 `ziyeh` 环境的网络密钥里，由代理注入）；小红书优先走免费网页解析。

- 推荐方案的一次性安装：[docs/本地电脑安装.md](docs/本地电脑安装.md)
- 技能：`.claude/skills/open-social-link`（打开链接）、`.claude/skills/repost-video`（搬运）
