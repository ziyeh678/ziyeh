#!/usr/bin/env python3
"""婚礼/活动音乐剪辑：按原曲时间裁剪、默认 0.5 秒淡入、编号命名、解码校验、打包。

两种用法：
  单首： python3 music_clip.py one <音频/视频文件或抖音小红书链接> --start 1:02 [--end 2:30] [--fade-in 0.5] [--fade-out 3] --out <目录> [--name "001 - 入场 - 歌名"]
  整场： python3 music_clip.py batch <歌单.json> --out <目录> [--zip]

歌单 JSON：
{
  "event": "张三李四婚礼",
  "entries": [
    {"position": "新人入场", "title": "如果我们不曾相遇", "artist": "五月天",
     "source": "/path/song.mp3 或 抖音/小红书链接（不填就按歌名+歌手去网易云/QQ 下原唱）",
     "version": null, "start": "1:02", "end": "2:30",
     "fade_in": null, "fade_out": null, "instrumental": false, "cancelled": false}
  ]
}
instrumental：用户明确要求这首用伴奏时，填用户原话（字符串）或 true，会先去人声再剪。
规则（来自婚礼音乐工作流）：
- 时间都按原曲计；start 默认 0，end 默认到结尾。支持 62、1:02、1:02.5、1分2秒。
- 实际裁剪的片段默认开头 0.5 秒淡入（最多片段长度一半）；整首不加；fade_in=0/false 关闭，给了秒数就用给的。
- 淡出默认不加，只有给了 fade_out 才加。
- 保留歌单顺序和重复条目，每条独立编号；cancelled=true 的跳过。
- 不覆盖已有文件；每个成品都做时长检查 + 完整解码校验，记 sha256 到 report.json。
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TIKHUB = HERE.parents[1] / "open-social-link" / "scripts" / "tikhub.py"
DEFAULT_FADE_IN = 0.5
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".amr"}


def sh(args):
    p = subprocess.run([str(a) for a in args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout)[-1500:] or "ffmpeg 失败")
    return p.stdout


def seconds(v):
    if v is None or v == "":
        return None
    if v is False:
        return 0.0
    if v is True:
        raise ValueError("时间不能是 true")
    s = str(v).strip().replace("：", ":")
    if re.fullmatch(r"\d+(\.\d+)?", s):
        r = float(s)
    elif re.fullmatch(r"\d+(:\d{1,2}){1,2}(\.\d+)?", s):
        parts = [float(x) for x in s.split(":")]
        if any(x >= 60 for x in parts[1:]):
            raise ValueError(f"分/秒必须小于 60：{s}")
        r = 0.0
        for x in parts:
            r = r * 60 + x
    else:
        m = re.fullmatch(r"(?:(\d+)\s*(?:小时|h))?\s*(?:(\d+)\s*(?:分钟?|m|min))?\s*(?:(\d+(?:\.\d+)?)\s*(?:秒|s))?", s)
        if not m or not any(m.groups()):
            raise ValueError(f"看不懂的时间：{s}")
        r = float(m[1] or 0) * 3600 + float(m[2] or 0) * 60 + float(m[3] or 0)
    if not math.isfinite(r) or r < 0:
        raise ValueError(f"时间必须是非负数：{s}")
    return r


def fmt(t):
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:05.2f}"


def probe(path):
    d = json.loads(sh(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]))
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if not a:
        raise ValueError(f"文件里没有音轨：{Path(path).name}")
    dur = float(d["format"]["duration"])
    if not math.isfinite(dur) or dur <= 0:
        raise ValueError("时长无效")
    return dur, a["codec_name"]


def verify(path):
    dur, codec = probe(path)
    sh(["ffmpeg", "-v", "error", "-xerror", "-i", path, "-map", "0:a:0", "-f", "null", "-"])
    return dur, codec


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def safe(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(s)).strip(" .")[:55] or "未命名"


FETCH = HERE / "music_fetch.py"
VOCAL = HERE / "vocal_remove.py"
VOCAL_PY = Path.home() / ".cache" / "ziyeh-music" / "vocal" / "bin" / "python"


def song_key(e):
    """歌单条目的来源键：有 source 用 source，没有就用 song:歌名|歌手|版本 去网易云/QQ 找。"""
    if e.get("source"):
        return str(e["source"])
    if not e.get("title"):
        raise ValueError("条目既没有 source 也没有歌名")
    return f"song:{e['title']}|{e.get('artist') or ''}|{e.get('version') or ''}"


def instrumental(src, outdir, request):
    if not VOCAL_PY.exists():
        raise RuntimeError("去人声组件没装：按 vocal_remove.py 顶部说明安装")
    r = subprocess.run([str(VOCAL_PY), str(VOCAL), str(src), "--out", str(outdir), "--request", request],
                       capture_output=True, text=True, encoding="utf-8")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("去人声失败：" + (r.stdout or r.stderr)[-500:])
    if data.get("status") not in ("ok", "reused"):
        raise RuntimeError("去人声失败：" + str(data.get("error")))
    return Path(data["output"]), {"instrumental": True, "instrumental_model": data.get("model")}


def fetch_source(src, workdir):
    """本地文件直接用；抖音/小红书链接先下载视频（再从中取音轨）；song:歌名|歌手|版本 去网易云（优先）/QQ 下载原唱。"""
    if str(src).startswith("song:"):
        title, artist, version = (str(src)[5:].split("|") + ["", ""])[:3]
        args = [sys.executable, "-I", str(FETCH), "get", title, "--out", str(workdir)]
        if artist:
            args += ["--artist", artist]
        if version:
            args += ["--version", version]
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            raise RuntimeError("找歌失败：" + (r.stdout or r.stderr)[-500:])
        if data.get("status") != "ok":
            raise RuntimeError(f"网易云/QQ 都没下到《{title}》" + (f"（{artist}）" if artist else "") + "，请上传这首歌的文件")
        c = data.get("candidate") or data
        return Path(data["path"]), {"song_platform": data.get("platform"), "song_title": c.get("title"),
                                    "song_artists": c.get("artists"), "song_album": c.get("album")}
    if re.search(r"https?://", str(src)):
        out = subprocess.run([sys.executable, "-I", str(TIKHUB), str(src), "--download", str(workdir)],
                             capture_output=True, text=True, encoding="utf-8")
        try:
            data = json.loads(out.stdout)
        except json.JSONDecodeError:
            raise RuntimeError("链接下载失败：" + (out.stdout or out.stderr)[-500:])
        files = [f["path"] for f in data.get("files") or [] if f["path"].endswith(".mp4")]
        if not files:
            raise RuntimeError("链接没下载到视频：" + str(data.get("download_error") or data.get("error") or "无视频"))
        return Path(files[0]), {"from_link": src, "link_title": data.get("title") or data.get("desc")}
    p = Path(src).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"找不到文件：{src}")
    return p, {}


def clip(source, out_path, start=None, end=None, fade_in=None, fade_out=None):
    out_path = Path(out_path)
    if out_path.exists():
        raise FileExistsError(f"已存在，不覆盖：{out_path.name}")
    full, codec = probe(source)
    st = seconds(start) or 0.0
    en = seconds(end)
    en = full if en is None else en
    if en > full and en - full < 1:
        en = full  # 给的结尾比原曲稍长，按原曲结尾
    if not (0 <= st < en <= full):
        raise ValueError(f"裁剪范围 {fmt(st)}–{fmt(en)} 超出原曲 0:00–{fmt(full)}")
    length = en - st
    trimmed = st > 0.05 or en < full - 0.05
    if fade_in is not None and fade_in != "":
        fi = seconds(fade_in) or 0.0
        fi_basis = "指定"
    else:
        fi = min(DEFAULT_FADE_IN, length / 2) if trimmed else 0.0
        fi_basis = "裁剪默认" if trimmed else "整首不加"
    fo = seconds(fade_out) or 0.0
    if max(fi, fo) > length:
        raise ValueError("淡入/淡出比片段还长")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(".tmp-" + out_path.name)
    if not trimmed and not fi and not fo and codec == "mp3" and source.suffix.lower() == ".mp3":
        shutil.copy2(source, tmp)
    else:
        filt = [f"atrim=start={st}:end={en}", "asetpts=PTS-STARTPTS"]
        if fi:
            filt.append(f"afade=t=in:d={fi}")
        if fo:
            filt.append(f"afade=t=out:st={length - fo}:d={fo}")
        sh(["ffmpeg", "-v", "error", "-y", "-i", source, "-map", "0:a:0", "-vn", "-af", ",".join(filt),
            "-c:a", "libmp3lame", "-q:a", "2", "-f", "mp3", tmp])
    dur, ocodec = verify(tmp)
    if abs(dur - length) > 0.5:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"成品时长 {dur:.2f}s 与预期 {length:.2f}s 不符")
    os.replace(tmp, out_path)
    return {
        "output": str(out_path), "bytes": out_path.stat().st_size, "sha256": sha256(out_path),
        "original_duration": round(full, 2), "start": fmt(st), "end": fmt(en),
        "clip_duration": round(dur, 2), "fade_in": fi, "fade_in_basis": fi_basis, "fade_out": fo,
        "codec": ocodec, "decode": "通过",
    }


def cmd_one(a):
    out = Path(a.out)
    with tempfile.TemporaryDirectory() as w:
        src, meta = fetch_source(a.source, Path(w))
        name = a.name or f"{safe(Path(src).stem)}-剪辑"
        r = clip(src, out / (safe(name) + ".mp3"), a.start, a.end, a.fade_in, a.fade_out)
    r.update(meta)
    print(json.dumps(r, ensure_ascii=False, indent=2))


def cmd_batch(a):
    plan = json.loads(Path(a.playlist).read_text(encoding="utf-8-sig"))
    event = safe(plan.get("event") or Path(a.playlist).stem)
    out = Path(a.out) / event
    out.mkdir(parents=True, exist_ok=True)
    rp = out / "report.json"
    prior = {}
    if rp.exists():  # 重跑：已校验通过且文件没变的条目直接复用，不重做也不覆盖
        for r in json.loads(rp.read_text(encoding="utf-8")).get("entries", []):
            if r.get("status") == "成功" and r.get("output"):
                prior[r["output"]] = r
    report = {"event": plan.get("event"), "entries": []}
    n = 0
    with tempfile.TemporaryDirectory() as w:
        cache = {}
        for i, e in enumerate(plan["entries"], 1):
            row = {"order": i, "position": e.get("position"), "title": e.get("title"), "artist": e.get("artist")}
            report["entries"].append(row)
            if e.get("cancelled"):
                row["status"] = "已取消，跳过"
                continue
            n += 1
            inst = e.get("instrumental")
            parts = [f"{n:03d}", e.get("position"), e.get("title"), e.get("artist"), "伴奏" if inst else None]
            name = " - ".join(safe(p) for p in parts if p)
            target = str(out / (name + ".mp3"))
            old = prior.get(target)
            try:
                key = song_key(e)
            except ValueError as ex:
                row.update(status="失败", error=str(ex))
                continue
            if old and Path(target).exists() and sha256(target) == old.get("sha256") \
                    and old.get("start") == fmt(seconds(e.get("start")) or 0.0) and old.get("source_key") == key:
                row.update(old); row["reused"] = True
                continue
            try:
                if key not in cache:
                    # 按歌名下载的原曲留在「原曲」目录，原件不改动
                    workdir = out / "原曲" if key.startswith("song:") else Path(w) / f"src{i}"
                    cache[key] = fetch_source(key, workdir)
                src, meta = cache[key]
                if inst:
                    ikey = key + "#伴奏"
                    if ikey not in cache:
                        req = inst if isinstance(inst, str) else "用户在歌单里要求这首用伴奏"
                        cache[ikey] = instrumental(src, out / "伴奏", req)
                    src, imeta = cache[ikey]
                    meta = {**meta, **imeta}
                r = clip(src, target, e.get("start"), e.get("end"), e.get("fade_in"), e.get("fade_out"))
                row.update(r); row.update(meta); row["source_key"] = key; row["status"] = "成功"
            except Exception as ex:  # noqa
                row.update(status="失败", error=f"{type(ex).__name__}: {ex}")
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = [r for r in report["entries"] if r.get("status") == "成功"]
    bad = [r for r in report["entries"] if r.get("status") == "失败"]
    summary = {"folder": str(out), "report": str(rp), "success": len(ok), "failed": len(bad),
               "files": [r["output"] for r in ok], "failures": [{"order": r["order"], "title": r["title"], "error": r["error"]} for r in bad]}
    if a.zip and ok:
        zp = Path(a.out) / f"{event}.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
            for r in ok:
                z.write(r["output"], Path(r["output"]).name)
            z.write(rp, "report.json")
        summary["zip"] = str(zp)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.exit(0 if not bad else 1)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("one")
    o.add_argument("source"); o.add_argument("--start"); o.add_argument("--end")
    o.add_argument("--fade-in"); o.add_argument("--fade-out"); o.add_argument("--out", required=True); o.add_argument("--name")
    b = sub.add_parser("batch")
    b.add_argument("playlist"); b.add_argument("--out", required=True); b.add_argument("--zip", action="store_true")
    a = p.parse_args()
    try:
        cmd_one(a) if a.cmd == "one" else cmd_batch(a)
    except SystemExit:
        raise
    except Exception as ex:  # noqa
        print(json.dumps({"error": f"{type(ex).__name__}: {ex}"}, ensure_ascii=False)); sys.exit(2)


if __name__ == "__main__":
    main()
