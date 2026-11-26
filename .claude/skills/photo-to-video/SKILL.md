---
name: photo-to-video
description: 让照片动起来、把照片做成视频：单张照片加镜头运动（推近/拉远/左右上下平移）生成短视频；多张照片做成带转场的影片，可配背景音乐。本地 ffmpeg，免费、稳定、不需要任何密钥。用户发来照片说"让它动起来""做成视频""照片转视频""做个相册视频/卡点视频"时使用。
---

# 照片 → 视频（免费本地版）

照做，不问用户。默认竖屏 9:16（适合抖音 / 小红书），做完直接用 SendUserFile（`display: "render"`）发给用户。

```bash
python3 -I .claude/skills/photo-to-video/scripts/photo2video.py <图1> [图2 ...] --out <scratchpad>/p2v [选项]
```

最后一行输出 JSON：`{"file": "...mp4", "duration": 秒, "width", "height", "photos"}`，把 `file` 发给用户。

## 选项（按用户话里的意思挑，没说就用默认）

| 选项 | 默认 | 说明 |
|---|---|---|
| `--ratio` | `9:16` | `16:9` 横屏、`1:1`、`3:4`（小红书图文比例）、`4:3`、`original`（跟第一张照片一致） |
| `--duration` | 单张 6 秒，多张每张 4 秒 | 每张停留秒数 |
| `--motion` | `auto` | `auto` 每张轮换；`zoom-in` 推近、`zoom-out` 拉远、`pan-left/right/up/down` 平移、`none` 不动 |
| `--zoom` | `0.15` | 运动幅度；"轻微一点" 0.08，"动感强" 0.25 |
| `--transition` | `fade` | `dissolve`、`slideleft`、`smoothleft`、`circleopen`、`zoomin`、`fadeblack`、`wipeleft` 等 |
| `--trans-dur` | `0.8` | 转场秒数 |
| `--music` | 无 | 本地音频/视频文件；音乐短会自动循环，结尾 1.5 秒淡出 |
| `--name` | 自动 | 输出文件名（不覆盖已有文件） |

- 照片顺序 = 命令行顺序，按用户发图的顺序传。
- 照片比例跟画面差得多时，自动用模糊放大的原图做背景，完整照片居中，不裁人脸。
- 用户给的是抖音/小红书链接当配乐：先用 `open-social-link` 技能下载，再把下载的文件传给 `--music`（视频文件也行，会取音轨）。
- 用户发的是小红书/抖音图文链接说"做成视频"：先下载图片，再把所有图片传进来。

## 回复格式

```
✅ 已生成：N 张照片，共 X 秒（9:16）
```

## 说明（用户问起再说）

这是镜头运动效果（像纪录片里推拉摇移照片），不是 AI 让人物自己动。真·AI 动起来（人眨眼、头发飘）的技能在 ClawHub 上都要付费 API 密钥（例如 runware/animate-image、free-image-to-video 实际需付费套餐），云端也没有 GPU 跑本地模型。用户明确要 AI 动态效果时，告诉他需要哪家的密钥和大概费用，由他决定。
