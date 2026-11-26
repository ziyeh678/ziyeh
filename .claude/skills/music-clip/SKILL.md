---
name: music-clip
description: 音乐找歌 + 剪辑 + 去人声：用户只给歌名/歌手或一份歌单（文字/截图/Word），自动去网易云（优先）/QQ 音乐下载原唱完整版，按原曲时间裁剪、默认 0.5 秒淡入、编号命名、解码校验、逐首 mp3 发到手机；用户明确要求时去人声做伴奏。也接受上传的音频/视频或抖音小红书链接当来源。
---

# 音乐：找歌 → 剪辑 → （可选）伴奏 → 发给用户

**不要问用户任何问题**，按下面直接做，做完一句话汇报。

## 0. 每个新会话先准备（几秒）
```bash
bash .claude/skills/music-clip/scripts/setup.sh            # 搜歌下载依赖
bash .claude/skills/music-clip/scripts/setup.sh vocal      # 只有要伴奏时再装（3-5 分钟，后台跑）
```

## 1. 登录（新会话里第一次下歌时）
先查：
```bash
python3 -I .claude/skills/music-clip/scripts/netease.py status        # logged_in / vipType（用户网易云是黑胶会员）
python3 -I .claude/skills/music-clip/scripts/music_fetch.py status    # QQ（账号目前非会员，只能下免费歌）
```
没登录就**直接**生成二维码发给用户（不用先问）：
```bash
# 后台运行（run_in_background），它会等用户扫码 3 分钟
python3 -I .claude/skills/music-clip/scripts/netease.py login --qr <scratchpad>/netease-login.png
```
等 png 生成后用 SendUserFile 发出，配一句：「网易云扫码：保存图片 → 网易云 App 扫一扫 → 相册 → 确认」。
QQ 同理：`music_fetch.py login --qr <scratchpad>/qq-login.png`，「手机 QQ → 扫一扫 → 相册 → 确认」。
网易云能下就不用登 QQ。登录信息只在本会话机器上，新会话要重扫。

## 2. 整理歌单 → JSON
```json
{"event": "张三李四婚礼",
 "entries": [
   {"position": "新人入场", "title": "如果我们不曾相遇", "artist": "五月天", "start": "1:02", "end": "2:30"},
   {"position": "交换戒指", "title": "Marry You", "artist": "Bruno Mars"},
   {"position": "敬酒", "title": "小幸运", "artist": "田馥甄", "instrumental": "敬酒用伴奏"},
   {"position": "退场", "title": "如果我们不曾相遇", "artist": "五月天", "start": "2:10", "fade_out": 3}
 ]}
```
- **不写 source** → 自动按歌名+歌手去网易云（优先）/QQ 下原唱完整版；原曲存在 `<event>/原曲/`。
- 有上传文件 / 抖音小红书链接就填 `source`。
- 用户指定版本（live、某专辑）→ `"version": "live"`。没指定就要录音室原唱；**歌名和歌手必须完全对上，不拿翻唱凑数**。
- 保留原顺序和重复条目；取消的写 `"cancelled": true`；用户没给的字段不编。
- `instrumental`：**只有用户明确说要伴奏/去人声**才填，值写用户原话。

## 3. 运行并发送
```bash
python3 -I .claude/skills/music-clip/scripts/music_clip.py batch <歌单.json> --out <scratchpad>/music
```
用 SendUserFile 把成品 mp3 **逐首单独**发（一次调用可传多个文件，`display: "render"`）。**不要发 zip**——用户手机上的 Claude App 打不开 zip，大文件也容易打不开。回复一句：成功几首（各来自网易云/QQ/上传）、失败几首及原因。
单首也可以：`music_clip.py one "song:歌名|歌手" --start 1:02 --end 2:30 --out <目录>`

## 剪辑规则（来自婚礼音乐工作流，照做）
- 时间按**原曲**计；支持 `62`、`1:02`、`1:02.5`、`1分2秒`、`1：02`。
- 裁剪过的片段默认开头 **0.5 秒淡入**；整首不加。「不要淡入」→ `"fade_in": false`；「淡入 2 秒」→ `"fade_in": 2`。
- **淡出默认不加**，用户说了才加。
- 文件名 `001 - 环节 - 歌名 - 歌手.mp3`（伴奏加 ` - 伴奏`）。
- 永不覆盖：改了时间重剪，把 `event` 改成 `xxx-v2`。
- 每个成品做时长核对 + 完整解码校验，记录在 `report.json`。

## 出错自己处理
| 情况 | 做法 |
|---|---|
| 网易云 `-460` 限流 | 脚本会自动等待重试；仍失败就隔几分钟再跑 |
| 网易云/QQ 都没下到（版权/QQ 非会员） | 告诉用户一句："《xx》两个平台都下不了，发我这首歌的文件"，其余照常交付 |
| 下载报 `no rule or network setting allows this host` | 把主机名（如 `m9.music.126.net`、`xx.stream.qqmusic.qq.com`）用 update_environment 加进 ziyeh 环境，重试 |
| 去人声组件没装 | 后台跑 `setup.sh vocal`，装好再继续 |
| 没登录 | 按第 1 步直接发二维码 |

## 已知情况
- 网易云：不登录时海外服务器拿不到下载地址；登录黑胶会员后会员歌能下完整版（实测《如果我们不曾相遇》《Marry You》）。部分歌网易云没版权（如田馥甄《小幸运》）。
- QQ 音乐：登录后搜索不再被风控；账号非会员时只能下免费歌。
- 去人声：UVR-MDX-NET-Inst_HQ_3 模型，CPU 处理一首约 2 分钟，不保证完美，提醒用户试听。
- 第三方代码：QQMusicApi（GPL-3.0）、ncm-cli（MIT），来自用户提供的婚礼音乐工作流安装包，见 `vendor/`。
