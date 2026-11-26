#!/usr/bin/env python3
"""读取抖音 / 小红书分享链接的公开内容，输出 JSON。

用法: python3 fetch_social.py "<链接或整段分享文字>"
只依赖 Python 标准库。
"""
import json
import re
import sys
import urllib.request
import urllib.parse

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.geturl(), r.read().decode("utf-8", "replace")


def extract_url(text):
    m = re.search(r"https?://[^\s，。！!“”\"'<>]+", text)
    return m.group(0) if m else text.strip()


def js_obj(html, marker):
    m = re.search(re.escape(marker) + r"\s*=\s*(\{.*?\})\s*</script>", html, re.S)
    if not m:
        return None
    s = re.sub(r"\bundefined\b", "null", m.group(1))
    return json.loads(s)


# ---------------- 抖音 ----------------
def douyin(url):
    final, html = get(url)
    m = re.search(r"/(?:video|note|share/video|share/note)/(\d{15,})", final) or re.search(r"modal_id=(\d{15,})", final)
    if not m:
        return {"platform": "douyin", "error": "无法从链接解析视频 ID", "final_url": final}
    vid = m.group(1)
    if "iesdouyin.com/share/" not in final:
        final, html = get(f"https://www.iesdouyin.com/share/video/{vid}/")
    data = js_obj(html, "window._ROUTER_DATA")
    item = None
    if data:
        for v in (data.get("loaderData") or {}).values():
            if isinstance(v, dict) and v.get("videoInfoRes"):
                items = v["videoInfoRes"].get("item_list") or []
                item = items[0] if items else None
    if not item:
        return {"platform": "douyin", "id": vid, "error": "页面没有返回视频数据（可能已删除、私密或被风控）", "final_url": final}
    st = item.get("statistics") or {}
    video = item.get("video") or {}
    play = ((video.get("play_addr") or {}).get("url_list") or [None])[0]
    if play:
        play = play.replace("playwm", "play")
    return {
        "platform": "douyin",
        "id": vid,
        "url": f"https://www.douyin.com/video/{vid}",
        "desc": item.get("desc"),
        "author": (item.get("author") or {}).get("nickname"),
        "create_time": item.get("create_time"),
        "duration_ms": video.get("duration"),
        "stats": {k: st.get(k) for k in ("digg_count", "comment_count", "collect_count", "share_count") if k in st},
        "hashtags": [t.get("hashtag_name") for t in (item.get("text_extra") or []) if t.get("hashtag_name")],
        "cover": ((video.get("cover") or {}).get("url_list") or [None])[0],
        "images": [((i.get("url_list") or [None])[0]) for i in (item.get("images") or [])],
        "video_url": play,
        "music": (item.get("music") or {}).get("title"),
    }


# ---------------- 小红书 ----------------
def xiaohongshu(url):
    final, html = get(url)
    data = js_obj(html, "window.__INITIAL_STATE__")
    if not data:
        return {"platform": "xiaohongshu", "error": "页面没有返回数据", "final_url": final}
    note = None
    nd = (data.get("noteData") or {}).get("data") or {}
    if nd.get("noteData"):
        note = nd["noteData"]
    else:
        for v in ((data.get("note") or {}).get("noteDetailMap") or {}).values():
            if (v or {}).get("note"):
                note = v["note"]
                break
    if not note or not (note.get("title") or note.get("desc")):
        return {"platform": "xiaohongshu", "error": "没拿到笔记内容（链接可能缺少 xsec_token、笔记已删除，或需要登录）", "final_url": final}
    ii = note.get("interactInfo") or {}
    imgs = []
    for i in note.get("imageList") or []:
        imgs.append(i.get("urlDefault") or i.get("url") or ((i.get("infoList") or [{}])[-1]).get("url"))
    vurl = None
    try:
        streams = note["video"]["media"]["stream"]
        for k in ("h264", "h265", "av1"):
            if streams.get(k):
                vurl = streams[k][0].get("masterUrl")
                break
    except (KeyError, TypeError, IndexError):
        pass
    nid = note.get("noteId") or (re.search(r"/([0-9a-f]{24})", final) or [None, None])[1]
    return {
        "platform": "xiaohongshu",
        "id": nid,
        "url": final,
        "type": note.get("type"),
        "title": note.get("title"),
        "desc": note.get("desc"),
        "author": (note.get("user") or {}).get("nickname") or (note.get("user") or {}).get("nickName"),
        "time": note.get("time"),
        "ip_location": note.get("ipLocation"),
        "stats": {k: ii.get(k) for k in ("likedCount", "collectedCount", "commentCount", "shareCount") if k in ii},
        "tags": [t.get("name") for t in note.get("tagList") or []],
        "images": [u for u in imgs if u],
        "video_url": vurl,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    url = extract_url(" ".join(sys.argv[1:]))
    host = urllib.parse.urlparse(url).netloc
    try:
        if "douyin" in host:
            out = douyin(url)
        elif "xhslink" in host or "xiaohongshu" in host or "rednote" in host:
            out = xiaohongshu(url)
        else:
            out = {"error": f"不支持的链接: {url}"}
    except Exception as e:  # noqa
        out = {"error": f"{type(e).__name__}: {e}", "url": url}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
