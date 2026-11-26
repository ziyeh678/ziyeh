# 必读：用户发链接 = 直接下载并发给他

用户在**手机**上用。他的沟通成本要降到最低：**不要提问、不要确认、不要解释方案、不要列选项**。看到链接就直接干活，干完用中文一两句话回报。

## 默认动作（用户只发了链接或分享文字时）

用户发来任何包含小红书 / 抖音链接的消息（`xhslink.com`、`xiaohongshu.com`、`rednote.com`、`v.douyin.com`、`douyin.com`，或整段"复制打开…"分享文字），**立刻**执行：

```bash
D=<你的 scratchpad 目录>/dl
python3 -I .claude/skills/open-social-link/scripts/tikhub.py "<用户发来的整段原文>" --download "$D"
```

然后：
1. 用 **SendUserFile**（`display: "render"`, `status: "normal"`）把 `files` 里的所有文件发给用户（视频或全部图片）。
2. 回复格式（就这么短）：
   ```
   ✅ 已下载：<标题或文案前 20 字>（作者 xxx，赞 x / 藏 x / 评 x）
   ```
   - 小红书如果最后用的是带水印的备用流，加一句"⚠️ 原片下载失败，这份带水印"。
3. 一条消息里有多个链接：逐个处理，每个下载完就发。

用户如果说了别的要求（总结、写文案、只看不下载等），按他说的做，但同样**不要反问**，按最合理的理解直接做。

## 音乐剪辑（婚礼/活动歌单）

用户发来音频/视频文件、或一份带时间点的歌单（"入场 1:02 开始""退场整首"之类），或说"剪一下这首歌"：直接用技能 `music-clip`，整理歌单 → 批量剪辑 → 把 zip 发给用户。规则（0.5 秒淡入、按原曲时间、编号命名、不覆盖）都写在 `.claude/skills/music-clip/SKILL.md`，照做不问。

## 照片做成视频 / 让照片动起来

用户发来照片说"让它动起来""做成视频""做个相册视频"：直接用技能 `photo-to-video`（本地 ffmpeg，免费），默认竖屏 9:16，做完把 mp4 发给用户。规则写在 `.claude/skills/photo-to-video/SKILL.md`，照做不问。

## 出错时自己处理，别问用户

| 情况 | 你自己做 |
|---|---|
| `download_error` 含 `no rule or network setting allows this host` | 从 `video_url` / `video_backup_urls` 里找到被拦的主机名，用 update_environment 加进 **ziyeh** 环境的放行列表（只加具体主机名），等 30 秒重试。仍失败就把 `video_url` 发给用户："点开链接长按保存"。 |
| TikHub `HTTP 400` | 脚本已自动重试 3 次；仍失败就再跑一次脚本。 |
| TikHub `HTTP 401` | 密钥失效。告诉用户一句："TikHub 密钥失效了，回我'换密钥'"，然后用 request_credential（host `api.tikhub.io`）弹框。 |
| TikHub `HTTP 402` / 余额不足 | 告诉用户一句："TikHub 余额不足，去 user.tikhub.io 充值"。小红书链接改用 `fetch_social.py`（同目录，参数相同，免费）继续。 |
| 小红书"没拿到笔记内容" | 让用户在 App 里"分享 → 复制链接"重新发（缺 xsec_token）。只说这一句。 |
| 小红书 / 抖音主域名报 `CONNECT tunnel failed, response 403` | 当前会话不在 ziyeh 环境。告诉用户一句："请新建会话时环境选 ziyeh"。 |

## 背景（需要时再看）

- **环境**：云环境 `ziyeh` 已放行小红书 / 抖音域名和部分视频 CDN；`api.tikhub.io` 的 API Key 存在环境网络密钥里，代理自动注入，**不要找用户要密钥**，脚本里也不用设变量。
- **抖音**：只能走 TikHub（抖音不给海外 IP 返回网页数据），返回无水印地址。
- **小红书**：脚本先走免费网页解析，`video_url` 优先是无水印原始文件 `sns-video-bd.xhscdn.com/<originVideoKey>`（原画质，可能是 4K），失败才用 TikHub。
- **费用**（扣用户 TikHub 余额）：抖音 0.001 美元/次，小红书 TikHub 通道 0.01 美元/次，400 不扣费。一次超过 20 个链接时先说一句大概花费再做。
  查余额：`curl -s -H "Authorization: Bearer proxy-injected" https://api.tikhub.io/api/v1/tikhub/user/get_user_info`
- **搬运**（用户说"搬运 / 发到小红书 / 发到抖音"）：下载 + 按目标平台改写标题（小红书 ≤20 字）、正文、话题标签，一次性给出可直接复制的文案；发布由用户在 App 里自己发（云端登录账号易封号）。只搬运用户自己的或已授权的内容，不确定时在文案后附一句提醒，不要反问。
- 技能细节：`.claude/skills/open-social-link/SKILL.md`、`.claude/skills/repost-video/SKILL.md`。
