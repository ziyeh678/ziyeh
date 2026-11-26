#!/usr/bin/env python3
"""网易云：扫码登录 / 搜歌 / 下载（用用户自己的账号）。

  python3 netease.py login --qr <二维码保存路径>   # 生成二维码并等待扫码（3 分钟）
  python3 netease.py status
  python3 netease.py search "歌名 歌手"
  python3 netease.py get <歌曲id> --out <目录>
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


def get(sid, out):
    s = session()
    d = s.get("https://music.163.com/api/song/detail/", params={"ids": json.dumps([int(sid)])}, timeout=30).json()["songs"][0]
    dur = d.get("duration", 0) / 1000
    for level in ("exhigh", "standard"):
        r = s.post("https://music.163.com/weapi/song/enhance/player/url/v1",
                   data=ncm.encrypted_request({"ids": [int(sid)], "level": level, "encodeType": "mp3", "csrf_token": s.cookies.get("__csrf", "")}), timeout=30).json()
        it = (r.get("data") or [{}])[0]
        if it.get("url") and not it.get("freeTrialInfo"):
            break
    else:
        emit({"error": "拿不到完整下载地址", "code": it.get("code"), "trial": bool(it.get("freeTrialInfo")), "logged_in": CRED.exists(),
              "hint": "code 404 多为海外 IP 版权地区限制；trial 表示只给试听"}, 1)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{d['name']} - {'、'.join(a['name'] for a in d['artists'])}.mp3".replace("/", "_")
    resp = requests.get(it["url"].replace("http://", "https://", 1), headers={"Referer": "https://music.163.com"}, timeout=120)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    real = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout or 0)
    if abs(real - dur) > 3:
        path.unlink(); emit({"error": f"只拿到片段 {real:.0f}s / 原曲 {dur:.0f}s"}, 1)
    emit({"status": "ok", "path": str(path), "duration": round(real, 2), "title": d["name"], "album": d["album"]["name"]})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("login"); l.add_argument("--qr", required=True)
    sub.add_parser("status")
    q = sub.add_parser("search"); q.add_argument("query")
    g = sub.add_parser("get"); g.add_argument("id"); g.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    try:
        {"login": lambda: login(a.qr), "status": status, "search": lambda: search(a.query), "get": lambda: get(a.id, a.out)}[a.cmd]()
    except SystemExit:
        raise
    except Exception as e:  # noqa
        emit({"error": f"{type(e).__name__}: {str(e)[:300]}"}, 2)
