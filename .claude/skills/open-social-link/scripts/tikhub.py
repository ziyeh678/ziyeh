#!/usr/bin/env python3
"""通过 TikHub API 完整读取抖音 / 小红书链接，并可下载无水印视频/图片。

用法: python3 tikhub.py "<链接或整段分享文字>" [--download 目录] [--raw]
密钥: 云端会话由网络代理自动注入（api.tikhub.io 的网络密钥）；本地电脑用环境变量 TIKHUB_API_KEY。
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("TIKHUB_BASE", "https://api.tikhub.io")
KEY = os.environ.get("TIKHUB_API_KEY", "proxy-injected")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"


def api(path, **params):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}", "User-Agent": "tikhub-skill/1.0"})
    import time
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            # 400/5xx 多为 TikHub 上游临时失败（不扣费），重试；401/402/403/429 直接报错
            if e.code in (400, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise SystemExit(json.dumps({"error": f"TikHub HTTP {e.code}", "detail": body}, ensure_ascii=False))


def first(lst):
    return lst[0] if isinstance(lst, list) and lst else None


def douyin(text):
    d = api("/api/v1/douyin/app/v3/fetch_one_video_by_share_url", share_url=text)
    a = ((d.get("data") or {}).get("aweme_detail")) or {}
    v = a.get("video") or {}
    play = first((v.get("play_addr") or {}).get("url_list")) or first((v.get("download_addr") or {}).get("url_list"))
    br = v.get("bit_rate") or []
    if br:
        best = max(br, key=lambda b: b.get("bit_rate") or 0)
        play = first((best.get("play_addr") or {}).get("url_list")) or play
    cands = []
    for b in sorted(br, key=lambda b: -(b.get("bit_rate") or 0)):
        cands += (b.get("play_addr") or {}).get("url_list") or []
    cands += (v.get("play_addr") or {}).get("url_list") or []
    cands += (v.get("download_addr") or {}).get("url_list") or []
    st = a.get("statistics") or {}
    return d, {
        "platform": "douyin",
        "id": a.get("aweme_id"),
        "url": f"https://www.douyin.com/video/{a.get('aweme_id')}",
        "desc": a.get("desc"),
        "author": (a.get("author") or {}).get("nickname"),
        "create_time": a.get("create_time"),
        "duration_ms": v.get("duration"),
        "stats": {k: st.get(k) for k in ("digg_count", "comment_count", "collect_count", "share_count")},
        "cover": first((v.get("cover") or {}).get("url_list")),
        "images": [first(i.get("url_list")) for i in (a.get("images") or [])],
        "video_url": None if a.get("images") else play,
        "video_backup_urls": [] if a.get("images") else [u for u in dict.fromkeys(cands) if u != play],
        "music": (a.get("music") or {}).get("title"),
    }


def find_note(obj):
    """在返回里递归找到像笔记的那个对象。"""
    if isinstance(obj, dict):
        if ("title" in obj or "desc" in obj) and ("images_list" in obj or "video" in obj or "image_list" in obj or "imageList" in obj):
            return obj
        for v in obj.values():
            r = find_note(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_note(v)
            if r:
                return r
    return None


def find_video_url(obj):
    if isinstance(obj, dict):
        for k in ("master_url", "masterUrl", "url"):
            u = obj.get(k)
            if isinstance(u, str) and ".mp4" in u:
                return u
        for v in obj.values():
            r = find_video_url(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_video_url(v)
            if r:
                return r
    return None


def xiaohongshu(text):
    m = re.search(r"(?:explore|item|discovery/item|note)/([0-9a-f]{24})", text)
    q = {"note_id": m.group(1)} if m else {"share_text": re.search(r"https?://\S+", text).group(0)}
    want = q.get("note_id")

    def nid(n):
        return n.get("id") or n.get("note_id") or n.get("noteId")

    def ok(n):
        return n and (not want or nid(n) == want)

    d = api("/api/v1/xiaohongshu/app_v2/get_video_note_detail", **q)
    n = find_note(d)
    if not ok(n) or not (n.get("video") or find_video_url(n)):
        d = api("/api/v1/xiaohongshu/app_v2/get_image_note_detail", **q)
        n = find_note(d)
    if not ok(n):
        sys.exit(json.dumps({"error": f"TikHub 没返回请求的笔记 {want}（返回了 {nid(n or {})}）", "hint": "可改用 fetch_social.py"}, ensure_ascii=False))
    imgs = []
    for i in n.get("images_list") or n.get("image_list") or n.get("imageList") or []:
        imgs.append(i.get("original") or i.get("url_size_large") or i.get("url") or i.get("urlDefault"))
    user = n.get("user") or {}
    return d, {
        "platform": "xiaohongshu",
        "id": n.get("id") or n.get("note_id") or n.get("noteId"),
        "type": n.get("type"),
        "title": n.get("title"),
        "desc": n.get("desc"),
        "author": user.get("nickname") or user.get("name"),
        "stats": {k: n.get(k) for k in ("liked_count", "collected_count", "comments_count", "shared_count") if k in n},
        "tags": [t.get("name") for t in n.get("hash_tag") or n.get("tagList") or [] if isinstance(t, dict)],
        "images": [u for u in imgs if u],
        "video_url": find_video_url(n.get("video") or {}) or find_video_url(n),
    }


def download(out, folder):
    os.makedirs(folder, exist_ok=True)
    base = f"{out['platform']}_{out.get('id')}"
    if out.get("video_url"):
        targets = [([out["video_url"]] + (out.get("video_backup_urls") or []), ".mp4")]
    else:
        targets = [([u], ".jpg") for u in out.get("images") or []]
    files = []
    for i, (urls, ext) in enumerate(targets):
        path = os.path.join(folder, base + (f"_{i}" if len(targets) > 1 else "") + ext)
        last = None
        for u in urls:  # CDN 主机每次可能不同，逐个尝试备用地址
            if u.startswith("http://"):
                u = "https://" + u[len("http://"):]
            try:
                req = urllib.request.Request(u, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=180) as r, open(path, "wb") as f:
                    while chunk := r.read(1 << 16):
                        f.write(chunk)
                if os.path.getsize(path) > 0:
                    files.append({"path": os.path.abspath(path), "bytes": os.path.getsize(path)})
                    last = None
                    break
            except Exception as e:  # noqa
                last = e
        if last:
            raise last
    return files


def main():
    args = sys.argv[1:]
    folder, raw = None, "--raw" in args
    args = [a for a in args if a != "--raw"]
    if "--download" in args:
        i = args.index("--download")
        folder = args[i + 1] if i + 1 < len(args) else "downloads"
        del args[i:i + 2]
    if not args:
        print(__doc__)
        sys.exit(1)
    text = " ".join(args)
    if re.search(r"douyin\.com|iesdouyin", text):
        d, out = douyin(text)
    elif re.search(r"xhslink\.(?:com|cn)|xiaohongshu\.com|rednote\.com", text):
        # 小红书先走免费网页解析（能拿到完整视频流），失败再用 TikHub
        out = None
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("fetch_social", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_social.py"))
            fs = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fs)
            out = fs.xiaohongshu(fs.extract_url(text))
            d = None
        except Exception:  # noqa
            out = None
        if not out or out.get("error"):
            d, out = xiaohongshu(text)
            out["source"] = "tikhub"
        else:
            out["source"] = "web"
    else:
        sys.exit(json.dumps({"error": "不是抖音/小红书链接"}, ensure_ascii=False))
    if folder:
        try:
            out["files"] = download(out, folder)
        except Exception as e:  # noqa
            out["download_error"] = f"{type(e).__name__}: {e}"
    if raw:
        out["raw"] = d
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
