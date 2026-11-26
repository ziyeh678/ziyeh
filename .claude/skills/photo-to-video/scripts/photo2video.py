#!/usr/bin/env python3
"""照片 → 视频（本地 ffmpeg，免费、稳定、无需密钥）。

一张照片：加镜头运动（推近 / 拉远 / 左右上下平移），生成几秒短视频。
多张照片：每张带镜头运动，之间交叉转场，可配背景音乐。

用法：
  python3 -I photo2video.py 图1.jpg [图2.jpg ...] --out 输出目录
      [--ratio 9:16|16:9|1:1|3:4|4:3|original] [--duration 秒/张]
      [--motion auto|zoom-in|zoom-out|pan-left|pan-right|pan-up|pan-down|none]
      [--zoom 0.15] [--transition fade|...] [--trans-dur 0.8]
      [--music 音频文件] [--fps 30] [--name 文件名]
最后一行打印 JSON：{"file": ..., "duration": ..., "width": ..., "height": ...}
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

RATIOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080),
          "3:4": (1080, 1440), "4:3": (1440, 1080)}
AUTO_CYCLE = ["zoom-in", "pan-right", "zoom-out", "pan-left", "pan-up", "pan-down"]
TRANSITIONS = {"fade", "fadeblack", "fadewhite", "dissolve", "slideleft", "slideright",
               "slideup", "slidedown", "smoothleft", "smoothright", "circleopen",
               "circleclose", "radial", "zoomin", "wipeleft", "wiperight", "pixelize"}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr[-3000:])
        raise SystemExit(f"ffmpeg 失败：{' '.join(cmd[:6])} …")
    return p.stdout


def probe_size(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height:stream_side_data=rotation", "-of", "json", path])
    s = json.loads(out)["streams"][0]
    w, h = int(s["width"]), int(s["height"])
    for sd in s.get("side_data_list", []) or []:
        if abs(int(sd.get("rotation", 0))) in (90, 270):
            w, h = h, w
    return w, h


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", path])
    return float(out.strip())


def even(n):
    return int(n) // 2 * 2


def motion_expr(motion, A, D):
    """返回 zoompan 的 z / x / y 表达式。用 smoothstep 缓动，起止更柔和。"""
    p = f"(on/{max(D - 1, 1)})"
    e = f"({p}*{p}*(3-2*{p}))"
    cx, cy = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    if motion == "zoom-in":
        return f"1+{A}*{e}", cx, cy
    if motion == "zoom-out":
        return f"1+{A}*(1-{e})", cx, cy
    z = f"1+{A}"
    if motion == "pan-right":   # 镜头向右移
        return z, f"(iw-iw/zoom)*{e}", cy
    if motion == "pan-left":
        return z, f"(iw-iw/zoom)*(1-{e})", cy
    if motion == "pan-down":
        return z, cx, f"(ih-ih/zoom)*{e}"
    if motion == "pan-up":
        return z, cx, f"(ih-ih/zoom)*(1-{e})"
    return "1", "0", "0"  # none


def make_clip(img, out, W, H, dur, fps, motion, A):
    D = max(int(round(dur * fps)), 2)
    iw, ih = probe_size(img)
    # 比例差不多就裁满画面，差得多就模糊背景 + 完整照片居中
    close = abs((iw / ih) / (W / H) - 1) < 0.18
    S = 3  # 先放大 3 倍再做 zoompan，避免抖动
    BW, BH = W * S, H * S
    if close:
        canvas = (f"[0:v]scale={BW}:{BH}:force_original_aspect_ratio=increase:flags=lanczos,"
                  f"crop={BW}:{BH},setsar=1[c]")
    else:
        canvas = (f"[0:v]split[a][b];"
                  f"[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,"
                  f"crop={W // 4}:{H // 4},gblur=sigma=12,eq=brightness=-0.08,"
                  f"scale={BW}:{BH}[bg];"
                  f"[b]scale={BW}:{BH}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
                  f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[c]")
    z, x, y = motion_expr(motion, A, D)
    vf = (f"{canvas};[c]zoompan=z='{z}':x='{x}':y='{y}':d={D}:s={W}x{H}:fps={fps},"
          f"format=yuv420p[v]")
    run(["ffmpeg", "-y", "-v", "error", "-i", img, "-filter_complex", vf, "-map", "[v]",
         "-frames:v", str(D), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-r", str(fps), out])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ratio", default="9:16")
    ap.add_argument("--duration", type=float, default=None, help="每张秒数")
    ap.add_argument("--motion", default="auto")
    ap.add_argument("--zoom", type=float, default=0.15, help="运动幅度，0.1 轻 / 0.25 强")
    ap.add_argument("--transition", default="fade")
    ap.add_argument("--trans-dur", type=float, default=0.8)
    ap.add_argument("--music", default=None)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--name", default=None)
    a = ap.parse_args()

    imgs = [os.path.abspath(i) for i in a.images]
    for i in imgs:
        if not os.path.isfile(i):
            raise SystemExit(f"找不到文件：{i}")
    n = len(imgs)
    dur = a.duration or (6.0 if n == 1 else 4.0)
    if a.transition not in TRANSITIONS:
        raise SystemExit(f"不支持的转场 {a.transition}，可选：{', '.join(sorted(TRANSITIONS))}")
    if a.ratio == "original":
        w0, h0 = probe_size(imgs[0])
        k = 1920 / max(w0, h0)
        W, H = even(w0 * k), even(h0 * k)
    elif a.ratio in RATIOS:
        W, H = RATIOS[a.ratio]
    else:
        raise SystemExit(f"不支持的比例 {a.ratio}")
    T = min(a.trans_dur, dur / 2) if n > 1 else 0

    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    name = a.name or os.path.splitext(os.path.basename(imgs[0]))[0] + ("_动起来" if n == 1 else f"_等{n}张")
    final = os.path.join(a.out, name + ".mp4")
    k = 2
    while os.path.exists(final):  # 不覆盖
        final = os.path.join(a.out, f"{name}_{k}.mp4")
        k += 1

    tmp = tempfile.mkdtemp(prefix="p2v_")
    try:
        clips = []
        for idx, img in enumerate(imgs):
            m = AUTO_CYCLE[idx % len(AUTO_CYCLE)] if a.motion == "auto" else a.motion
            c = os.path.join(tmp, f"c{idx:03d}.mp4")
            make_clip(img, c, W, H, dur, a.fps, m, a.zoom)
            clips.append(c)
            print(f"[{idx + 1}/{n}] {os.path.basename(img)} → {m}", file=sys.stderr)

        total = n * dur - (n - 1) * T
        cmd = ["ffmpeg", "-y", "-v", "error"]
        for c in clips:
            cmd += ["-i", c]
        music_idx = None
        if a.music:
            cmd += ["-stream_loop", "-1", "-i", os.path.abspath(a.music)]
            music_idx = n
        fg, last = [], "0:v"
        for i in range(1, n):
            off = i * (dur - T)
            fg.append(f"[{last}][{i}:v]xfade=transition={a.transition}:duration={T}:offset={off:.3f}[x{i}]")
            last = f"x{i}"
        fo = max(total - 0.6, 0)
        fg.append(f"[{last}]fade=t=in:st=0:d=0.4,fade=t=out:st={fo:.3f}:d=0.6,format=yuv420p[v]")
        maps = ["-map", "[v]"]
        if music_idx is not None:
            afo = max(total - 1.5, 0)
            fg.append(f"[{music_idx}:a]atrim=0:{total:.3f},asetpts=N/SR/TB,"
                      f"afade=t=in:st=0:d=0.5,afade=t=out:st={afo:.3f}:d=1.5[a]")
            maps += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-filter_complex", ";".join(fg)] + maps + [
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", str(a.fps),
            "-t", f"{total:.3f}", "-movflags", "+faststart", final]
        run(cmd)
        print(json.dumps({"file": final, "duration": round(probe_duration(final), 2),
                          "width": W, "height": H, "photos": n}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
