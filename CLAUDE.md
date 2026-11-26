# 项目说明（给新会话的 Claude）

用户主要在**手机**上用 Claude App 发小红书 / 抖音链接，让你打开、总结、下载无水印视频/图片。用中文回复，简洁。

## 怎么做
- 打开 / 下载链接：用技能 `open-social-link`（脚本 `.claude/skills/open-social-link/scripts/tikhub.py`）。
- 下载好的文件用 SendUserFile 发给用户，他在手机上保存到相册。
- 搬运：技能 `repost-video`。云端只负责下载 + 改写文案；发布由用户在 App 里自己发（云端登录账号易被封）。只搬运用户自己的或已授权的内容。

## 环境
- 会话应使用云环境 **ziyeh**：已放行小红书/抖音域名和部分视频 CDN；api.tikhub.io 的 API Key 存在环境网络密钥里，由代理自动注入（脚本里 `TIKHUB_API_KEY` 用占位值即可，不要找用户要密钥）。
- 如果用户在别的环境里，提醒他新建会话时选 ziyeh 环境。
- 视频 CDN 主机名会变，下载被拦（`no rule ... allows this host`）时，用 update_environment 把具体主机名加进 ziyeh 的放行列表再重试；同时可先把 `video_url` 发给用户在浏览器打开。

## 费用（TikHub，按次扣用户余额）
- 抖音解析 0.001 美元/次；小红书 TikHub 通道 0.01 美元/次（小红书默认走免费网页解析，失败才用）；400 失败不扣费。
- 查余额：`curl -s -H "Authorization: Bearer proxy-injected" https://api.tikhub.io/api/v1/tikhub/user/get_user_info`
- 批量操作前先告诉用户大概花费。

## 已知情况
- 抖音不给海外 IP 返回网页数据，只能走 TikHub。
- 小红书 `video_url` 优先是无水印原始文件（sns-video-bd.xhscdn.com），备用流带水印。
- TikHub 小红书 app_v2 接口偶尔返回错的笔记，脚本已校验 note_id。
