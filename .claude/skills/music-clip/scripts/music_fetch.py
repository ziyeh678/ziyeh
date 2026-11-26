#!/usr/bin/env python3
"""按歌名在 QQ 音乐搜歌、自动挑原唱版本、下载完整 MP3（拒绝试听片段）。

  python3 music_fetch.py search "歌名 歌手"
  python3 music_fetch.py get "歌名" [--artist 歌手] [--version live/翻唱/伴奏/...] --out <目录>   # 先网易云，后 QQ
  python3 music_fetch.py login --qr <二维码保存路径>      # 用手机 QQ 扫码登录（会员歌需要）
  python3 music_fetch.py status                           # 看登录状态

网易云需先扫码登录（netease.py login），用户账号是黑胶会员；QQ 账号目前非会员，只能下免费歌。
依赖：pip install --target <dir> -r ../requirements.txt，并把 ../vendor/qqmusic 加进 sys.path（脚本会自动加）。
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "vendor" / "qqmusic"), os.environ.get("MUSIC_PYLIB", str(Path.home() / ".cache" / "ziyeh-music" / "pylib"))]
AUTH = Path(os.environ.get("MUSIC_AUTH_DIR", str(Path.home() / ".config" / "ziyeh-music")))
CRED = AUTH / "qq-credential.json"

try:
    import requests
    from qqmusic_api import Client, Credential
    from qqmusic_api.modules.song import SongFileInfo, SongFileType
except ImportError:
    print(json.dumps({"error": "缺依赖", "fix": f"pip install -q --target {sys.path[1]} -r {HERE.parent / 'requirements.txt'}"}, ensure_ascii=False))
    sys.exit(3)

ALT_WORDS = ["live", "现场", "翻唱", "cover", "伴奏", "纯音乐", "inst", "remix", "dj", "钢琴", "吉他", "铃声", "女声版", "男声版", "加速", "降速", "0.8x", "1.2x", "片段", "演唱会", "八音盒", "改编"]


def emit(o, code=0):
    print(json.dumps(o, ensure_ascii=False, indent=2))
    sys.exit(code)


def client():
    AUTH.mkdir(parents=True, exist_ok=True)
    cred = Credential.model_validate(json.loads(CRED.read_text())) if CRED.exists() else None
    return Client(cred, device_path=str(AUTH / "device.json"), max_concurrency=2)


def norm(s):
    return re.sub(r"[\s\(\)（）\[\]【】《》'\"·・,，.。!！?？\-—_]", "", str(s or "").lower())


def to_dict(s):
    return {"mid": s.mid, "title": s.name, "subtitle": getattr(s, "subtitle", "") or "", "artists": [a.name for a in s.singer],
            "album": s.album.name, "duration": s.interval}


async def search(q, n=15):
    async with client() as c:
        r = await c.search.search_by_type(q, num=n, highlight=False)
        return [to_dict(s) for s in r.song]


def score(c, title, artist, version):
    t, full = norm(c["title"]), norm(c["title"] + c["subtitle"] + c["album"])
    s = 0
    if t == norm(title):
        s += 50
    elif norm(title) in t:
        s += 25
    if artist:
        if any(norm(artist) == norm(a) for a in c["artists"]):
            s += 40
        elif any(norm(artist) in norm(a) or norm(a) in norm(artist) for a in c["artists"]):
            s += 20
    alt = [w for w in ALT_WORDS if w in full]
    if version:
        s += 30 if norm(version) in full else -20
    else:
        s -= 30 * len(alt)
    if c["duration"] < 60:
        s -= 40
    return s


async def song_url(c, mid):
    for ft in (SongFileType.MP3_320, SongFileType.MP3_128):
        try:
            r = await c.song.get_song_urls([SongFileInfo(mid=mid)], file_type=ft)
        except Exception:  # noqa
            continue
        d = r.data[0] if r.data else None
        if d and d.result == 0 and d.purl:
            return d.purl, ft.name
    return None, None


def netease_first(title, artist, version, out):
    """先走网易云（用户是黑胶会员），成功就直接输出。"""
    args = [sys.executable, "-I", str(HERE / "netease.py"), "find", title, "--out", str(out)]
    if artist:
        args += ["--artist", artist]
    if version:
        args += ["--version", version]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": (r.stdout or r.stderr)[-300:]}
    if data.get("status") == "ok":
        emit(data)
    return data


async def get(title, artist, version, out):
    ne = netease_first(title, artist, version, out)
    cands = await search(f"{title} {artist or ''}".strip())
    if not cands:
        emit({"error": f"QQ 音乐搜不到：{title} {artist or ''}"}, 1)
    ranked = sorted(cands, key=lambda c: -score(c, title, artist, version))
    tried = []
    async with client() as c:
        dispatch = await c.song.get_cdn_dispatch()
        for cand in ranked[:5]:
            if score(cand, title, artist, version) < 40:
                break
            if norm(title) not in norm(cand["title"]):
                continue  # 歌名必须对得上
            if artist and not any(norm(artist) == norm(a) for a in cand["artists"]):
                continue  # 指定了歌手就只要原唱
            purl, quality = await song_url(c, cand["mid"])
            if not purl:
                tried.append({**cand, "reason": "无下载权限（会员/版权）"})
                continue
            out.mkdir(parents=True, exist_ok=True)
            path = out / (re.sub(r'[<>:"/\\|?*]', "_", f"{cand['title']} - {'、'.join(cand['artists'])}") + ".mp3")
            for sip in dispatch.sip:
                url = urljoin(sip, purl).replace("http://", "https://", 1)
                try:
                    r = requests.get(url, headers={"Referer": "https://y.qq.com"}, timeout=120)
                except Exception:  # noqa
                    continue
                if r.status_code == 200 and len(r.content) > 50000:
                    path.write_bytes(r.content)
                    break
            else:
                tried.append({**cand, "reason": "下载服务器拒绝（可能需放行新的 CDN 主机）", "cdn": dispatch.sip})
                continue
            dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                       capture_output=True, text=True).stdout.strip() or 0)
            if abs(dur - cand["duration"]) > 3:
                path.unlink()
                tried.append({**cand, "reason": f"只拿到试听片段（{dur:.0f}s / 原曲 {cand['duration']}s）"})
                continue
            emit({"status": "ok", "platform": "qq", "path": str(path), "quality": quality, "duration": round(dur, 2), **cand,
                  "logged_in": CRED.exists(), "skipped": tried, "netease_outcome": ne.get("error")})
    emit({"error": "网易云和 QQ 都没下到", "netease": ne, "qq_logged_in": CRED.exists(), "qq_tried": tried,
          "hint": "多半是会员/版权歌：先用 login 扫码登录（需 QQ 音乐会员），或让用户直接上传音频"}, 1)


async def login(qr_path):
    from qqmusic_api.models.login import QRLoginType
    from qqmusic_api.modules.login_utils import QRCodeLoginSession
    async with client() as c:
        sess = QRCodeLoginSession(c.login, QRLoginType.QQ, interval=2, timeout_seconds=180)
        qr = await sess.get_qrcode()
        p = qr.save(str(Path(qr_path).parent))
        os.replace(p, qr_path)
        print(json.dumps({"status": "awaiting_scan", "qr": str(qr_path)}, ensure_ascii=False), flush=True)
        async for ev in sess.iter_events():
            name = ev.event.name
            if name == "DONE":
                CRED.write_text(ev.credential.model_dump_json())
                os.chmod(CRED, 0o600)
                emit({"status": "logged_in"})
            print(json.dumps({"status": name}, ensure_ascii=False), flush=True)
            if name in ("TIMEOUT", "REFUSE"):
                emit({"status": name.lower()}, 1)


async def status():
    if not CRED.exists():
        emit({"logged_in": False})
    async with client() as c:
        expired = await c.login.check_expired(c.credential)
        emit({"logged_in": not expired, "expired": expired})


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("query")
    g = sub.add_parser("get"); g.add_argument("title"); g.add_argument("--artist"); g.add_argument("--version"); g.add_argument("--out", required=True)
    l = sub.add_parser("login"); l.add_argument("--qr", required=True)
    sub.add_parser("status")
    a = p.parse_args()
    if a.cmd == "search":
        emit({"candidates": asyncio.run(search(a.query))})
    elif a.cmd == "get":
        asyncio.run(get(a.title, a.artist, a.version, Path(a.out)))
    elif a.cmd == "login":
        asyncio.run(login(a.qr))
    else:
        asyncio.run(status())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa
        emit({"error": f"{type(e).__name__}: {str(e)[:300]}"}, 2)
