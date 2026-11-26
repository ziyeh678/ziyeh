# ziyeh

## 在手机上让 Claude 打开小红书 / 抖音链接

本仓库带了一个 Claude Code 技能：`.claude/skills/open-social-link`。

使用方法（手机 Claude App → Code）：
1. 新建会话时选仓库 **ziyeh678/ziyeh**，环境选 **ziyeh**（已放行小红书、抖音域名）。
2. 直接把分享链接或"复制打开"的整段文字发给 Claude。

现状：
- 小红书：✅ 可读标题、正文、作者、点赞/收藏/评论数、标签、图片、视频地址（链接需带 `xsec_token`，App 里"复制链接"得到的完整链接或 xhslink 短链都行）。
- 抖音：⚠️ 抖音不给海外云服务器返回视频数据，只能从分享文字里读文案。想要完整功能，需要在自己电脑上运行 Claude Code，再用手机 Remote Control 遥控。
