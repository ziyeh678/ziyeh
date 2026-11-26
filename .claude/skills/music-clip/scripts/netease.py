#!/usr/bin/env python3
"""网易云：扫码登录 / 搜歌 / 下载（用用户自己的账号）。

  python3 netease.py login --qr <二维码保存路径>   # 生成二维码并等待扫码（3 分钟）
  python3 netease.py status
  python3 netease.py search "歌名 歌手"
  python3 netease.py get <歌曲id> --out <目录>
  python3 netease.py find "歌名" [--artist 歌手] [--version live] --out <目录>   # 搜索+自动挑原唱+下载
登录 cookie 存在 ~/.config/ziyeh-music/netease-credential.json（只在本会话机器上）。
"""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "vendor" / "netease"), os.environ.get("MUSIC_PYLIB", str(Path.home() / ".cache/ziyeh-music/pylib"))]
import requests, qrcode
import ncm_cli as ncm
from Cryptodome.Cipher import AES

AUTH = Path(os.environ.get("MUSIC_AUTH_DIR", str(Path.home() / ".config/ziyeh-music")))
CRED = AUTH / "netease-credential.json"


def emit(o, code=0):
    print(json.dumps(o, ensure_ascii=False, indent=2), flush=True)
    if code is not None:
        sys.exit(code)


def session():
    s = requests.Session()
    s.headers.update(ncm.BASE_HEADERS)
    if CRED.exists():
        for k, v in json.loads(CRED.read_text()).items():
            s.cookies.set(k, v, domain=".music.163.com")
    return s


def eapi(s, endpoint, data):
    uri = "/api/" + endpoint
    header = {"os": "pc", "appver": "3.1.17.204416", "osver": "Microsoft-Windows-10-Professional-build-19045-64bit", "channel": "netease",
              "versioncode": "140", "buildver": str(int(time.time())), "resolution": "1920x1080", "__csrf": "", "requestId": str(int(time.time() * 1000))}
    for f in ("MUSIC_U", "NMTID"):
        if s.cookies.get(f):
            header[f] = s.cookies.get(f)
    text = json.dumps(dict(data, header=header), ensure_ascii=False, separators=(",", ":"))
    dg = hashlib.md5(("nobody" + uri + "use" + text + "md5forencrypt").encode()).hexdigest()
    plain = (uri + "-36cd479b6b5-" + text + "-36cd479b6b5-" + dg).encode()
    pad = 16 - len(plain) % 16
    enc = AES.new(b"e82ckenh8dichen8", AES.MODE_ECB).encrypt(plain + bytes([pad]) * pad).hex().upper()
    r = s.post("https://interfacepc.music.163.com/eapi/" + endpoint, data={"params": enc},
               headers={"Cookie": "; ".join(k + "=" + str(v) for k, v in header.items())}, timeout=25)
    r.raise_for_status()
    return r.json()


def login(qr_path):
    AUTH.mkdir(parents=True, exist_ok=True)
    s = session()
    r = eapi(s, "login/qrcode/unikey", {"type": 3})
    key = r.get("unikey") or (r.get("data") or {}).get("unikey")
    if not key:
        emit({"status": "qr_failed", "code": r.get("code")}, 1)
    qrcode.make("https://music.163.com/login?codekey=" + key).save(qr_path)
    emit({"status": "awaiting_scan", "qr": str(qr_path)}, None)
    last = None
    for _ in range(90):
        time.sleep(2)
        r = eapi(s, "login/qrcode/client/login", {"key": key, "type": 3})
        code = r.get("code")
        if code != last:
            emit({"status": {800: "expired", 801: "awaiting_scan", 802: "scanned_waiting_confirm", 803: "ok"}.get(code, code)}, None)
            last = code
        if code == 803:
            ck = s.cookies.get_dict()
            if not ck.get("MUSIC_U"):
                emit({"status": "no_music_session"}, 1)
            CRED.write_text(json.dumps(ck)); os.chmod(CRED, 0o600)
            emit({"status": "logged_in"})
        if code == 800:
            emit({"status": "expired"}, 1)
    emit({"status": "timeout"}, 1)


def status():
    s = session()
    r = s.get("https://music.163.com/api/nuser/account/get", timeout=20).json()
    prof = r.get("profile") or {}
    acc = r.get("account") or {}
    emit({"logged_in": bool(prof), "vipType": acc.get("vipType"), "nickname_set": bool(prof.get("nickname"))})


def search(q):
    s = session()
    r = s.post("https://music.163.com/api/cloudsearch/pc", data={"s": q, "type": 1, "limit": 10, "offset": 0}, timeout=30).json()
    emit({"candidates": [{"id": x["id"], "title": x["name"], "artists": [a["name"] for a in x["ar"]], "album": x["al"]["name"],
                          "duration": round(x["dt"] / 1000, 2), "fee": x.get("fee")} for x in (r.get("result") or {}).get("songs", [])]})


ALT_WORDS = ["live", "现场", "翻唱", "cover", "伴奏", "纯音乐", "inst", "remix", "dj", "钢琴", "吉他", "铃声", "女声版", "男声版",
             "加速", "降速", "0.8x", "1.2x", "片段", "演唱会", "八音盒", "改编", "(", "（"]


def _norm(x):
    import re
    return re.sub(r"[\s\(\)（）\[\]【】《》'\"·・,，.。!！?？\-—_]", "", str(x or "").lower())


def score(c, title, artist, version):
    t, full = _norm(c["title"]), (c["title"] + " " + c["album"]).lower()
    sc = 0
    if t == _norm(title):
        sc += 50
    elif _norm(title) in t:
        sc += 25
    if artist:
        if any(_norm(artist) == _norm(a) for a in c["artists"]):
            sc += 40
        elif any(_norm(artist) in _norm(a) or _norm(a) in _norm(artist) for a in c["artists"]):
            sc += 20
    alt = [w for w in ALT_WORDS if w in c["title"].lower()]
    if version:
        sc += 30 if version.lower() in full else -20
    else:
        sc -= 30 * len(alt)
    if c["duration"] < 60:
        sc -= 40
    return sc


def find(title, artist, version, out):
    s = session()
    q = f"{title} {artist or ''}".strip()
    r = s.post("https://music.163.com/api/cloudsearch/pc", data={"s": q, "type": 1, "limit": 15, "offset": 0}, timeout=30).json()
    cands = [{"id": x["id"], "title": x["name"], "artists": [a["name"] for a in x["ar"]], "album": x["al"]["name"],
              "duration": round(x["dt"] / 1000, 2)} for x in (r.get("result") or {}).get("songs", [])]
    ranked = sorted(cands, key=lambda c: -score(c, title, artist, version))
    tried = []
    for c in ranked[:4]:
        if score(c, title, artist, version) < 40:
            break
        if _norm(title) not in _norm(c["title"]):
            continue  # 歌名必须对得上
        if artist and not any(_norm(artist) == _norm(a) for a in c["artists"]):
            continue  # 指定了歌手就只要原唱，不拿翻唱凑数
        try:
            res = download(c["id"], out)
            res.update(candidate=c, platform="netease", skipped=tried)
            emit(res)
        except DownloadError as e:
            tried.append({**c, "reason": str(e)})
    emit({"error": "网易云没下到", "tried": tried, "candidates": ranked[:5]}, 1)


class DownloadError(Exception):
    pass


def download(sid, out):
    s = session()
    d = s.get("https://music.163.com/api/song/detail/", params={"ids": json.dumps([int(sid)])}, timeout=30).json()["songs"][0]
    dur = d.get("duration", 0) / 1000
    for level in ("exhigh", "standard"):
        for wait in (0, 20, 45, 90):  # -460 = 请求太频繁被限流，等一会儿再试
            time.sleep(wait)
            r = s.post("https://music.163.com/weapi/song/enhance/player/url/v1",
                       data=ncm.encrypted_request({"ids": [int(sid)], "level": level, "encodeType": "mp3", "csrf_token": s.cookies.get("__csrf", "")}), timeout=30).json()
            if r.get("code") != -460:
                break
        else:
            raise DownloadError("网易云限流（-460），过几分钟再试")
        it = (r.get("data") or [{}])[0]
        if it.get("url") and not it.get("freeTrialInfo"):
            break
    else:
        raise DownloadError(f"拿不到完整下载地址（code {it.get('code')}{'，只给试听' if it.get('freeTrialInfo') else ''}；未登录或非会员时常见）")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{d['name']} - {'、'.join(a['name'] for a in d['artists'])}.mp3".replace("/", "_")
    content, last = None, None
    for _ in range(4):  # 海外连接网易云 CDN 偶尔被重置，重试
        try:
            resp = requests.get(it["url"].replace("http://", "https://", 1), headers={"Referer": "https://music.163.com"}, timeout=120)
            resp.raise_for_status()
            content = resp.content
            break
        except requests.RequestException as e:
            last = e
            time.sleep(2)
    if content is None:
        raise DownloadError(f"下载失败：{type(last).__name__}: {str(last)[:150]}")
    path.write_bytes(content)
    real = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout or 0)
    if abs(real - dur) > 3:
        path.unlink()
        raise DownloadError(f"只拿到片段 {real:.0f}s / 原曲 {dur:.0f}s")
    return {"status": "ok", "path": str(path), "duration": round(real, 2), "title": d["name"],
            "artists": [a["name"] for a in d["artists"]], "album": d["album"]["name"]}


def get(sid, out):
    try:
        emit(download(sid, out))
    except DownloadError as e:
        emit({"error": str(e)}, 1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("login"); l.add_argument("--qr", required=True)
    sub.add_parser("status")
    q = sub.add_parser("search"); q.add_argument("query")
    g = sub.add_parser("get"); g.add_argument("id"); g.add_argument("--out", required=True, type=Path)
    f = sub.add_parser("find"); f.add_argument("title"); f.add_argument("--artist"); f.add_argument("--version"); f.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    try:
        {"login": lambda: login(a.qr), "status": status, "search": lambda: search(a.query), "get": lambda: get(a.id, a.out),
         "find": lambda: find(a.title, a.artist, a.version, a.out)}[a.cmd]()
    except SystemExit:
        raise
    except Exception as e:  # noqa
        emit({"error": f"{type(e).__name__}: {str(e)[:300]}"}, 2)
