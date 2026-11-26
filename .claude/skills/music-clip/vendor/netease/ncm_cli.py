#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ncm-dl - 网易云音乐下载器 (v2.0, 2026-08 升级版)
支持搜索、下载 FLAC/MP3、嵌入封面/元数据、双语歌词、VIP cookie、并发下载

用法:
  ncm-dl "歌名"                    # 搜索并下载
  ncm-dl "歌名" "另一首歌"         # 批量下载
  ncm-dl -s 123456                # 按歌曲 ID 下载
  ncm-dl -a 789012                # 下载整张专辑 (ID)
  ncm-dl -A "专辑名"               # 按名字搜索专辑并下载
  ncm-dl -p 345678                # 下载歌单
  ncm-dl -c "MUSIC_U=xxx; NMTID=yyy"   # 带登录 cookie (解锁 VIP/无损)
  ncm-dl -c zen                   # 自动从 zen 浏览器提取网易云 cookie
  ncm-dl -w 4 "歌名"              # 4 线程并发下载
"""

import sys
import os
import re
import json
import base64
import binascii
import argparse
import random
import string
import sqlite3
import shutil
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from Cryptodome.Cipher import AES

# ── 网易云 API 加密 ──────────────────────────────────────────────

MODULUS = '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7'
NONCE = '0CoJUm6Qyw8W8jud'
PUB_KEY = '010001'

BASE_HEADERS = {
    'Accept': '*/*',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://music.163.com',
}
COOKIE_BASE = 'appver=2.0.2; os=pc; _ntes_nuid={}; NMTID={}'.format(
    ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
    ''.join(random.choices(string.ascii_letters + string.digits, k=32)))

MUSIC_DIR = Path.home() / 'Music'
_print_lock = None  # 并发打印锁（惰性初始化）


def get_print_lock():
    global _print_lock
    if _print_lock is None:
        import threading
        _print_lock = threading.Lock()
    return _print_lock


def locked_print(msg='', end='\n'):
    with get_print_lock():
        print(msg, end=end, flush=True)


# ── 加密 ─────────────────────────────────────────────────────────

def aes_encrypt(text, key):
    pad = 16 - len(text) % 16
    text = text + chr(pad) * pad
    encryptor = AES.new(key.encode(), AES.MODE_CBC, b'0102030405060708')
    return base64.b64encode(encryptor.encrypt(text.encode())).decode()


def rsa_encrypt(text):
    text = text[::-1]
    rs = pow(int(binascii.hexlify(text), 16), int(PUB_KEY, 16), int(MODULUS, 16))
    return format(rs, 'x').zfill(256)


def encrypted_request(params):
    text = json.dumps(params)
    sec_key = binascii.hexlify(os.urandom(16))[:16]
    enc_text = aes_encrypt(aes_encrypt(text, NONCE), sec_key.decode())
    enc_sec_key = rsa_encrypt(sec_key)
    return {'params': enc_text, 'encSecKey': enc_sec_key}


# ── Cookie 支持 ─────────────────────────────────────────────────

def extract_zen_cookie():
    """从 zen 浏览器提取 music.163.com 的登录 cookie"""
    zen_dir = Path.home() / '.config' / 'zen'
    if not zen_dir.exists():
        return None
    for db in zen_dir.glob('*/cookies.sqlite'):
        tmp = Path('/tmp') / f'zen_cookies_{db.parent.name.replace(" ", "_")}.sqlite'
        try:
            shutil.copy2(db, tmp)
            conn = sqlite3.connect(tmp)
            rows = conn.execute(
                "SELECT name, value FROM moz_cookies WHERE host LIKE '%music.163.com%'"
            ).fetchall()
            conn.close()
            tmp.unlink(missing_ok=True)
            if rows:
                return '; '.join(f'{n}={v}' for n, v in rows)
        except Exception:
            continue
    return None


def build_headers(cookie=None):
    h = dict(BASE_HEADERS)
    if cookie:
        h['Cookie'] = cookie
    else:
        h['Cookie'] = COOKIE_BASE
    return h


def api_post(url, params, encrypted=True):
    resp = requests.post(url,
                         data=encrypted_request(params) if encrypted else params,
                         headers=build_headers(), timeout=30)
    return resp.json()


def api_get(url, cookie=None):
    resp = requests.get(url, headers=build_headers(cookie), timeout=30)
    return resp.json()


# ── 搜索 ─────────────────────────────────────────────────────────

def search(keyword, limit=10):
    """搜索歌曲 (type=1)，统一字段名为 artists/album"""
    url = 'https://music.163.com/api/cloudsearch/pc'
    resp = requests.post(url, data={'s': keyword, 'type': 1, 'limit': limit, 'offset': 0},
                         headers=build_headers(), timeout=30)
    raw_songs = resp.json().get('result', {}).get('songs', [])
    songs = []
    for s in raw_songs:
        s['artists'] = [{'name': a['name'], 'id': a['id']} for a in s.get('ar', [])]
        s['album'] = {'name': s.get('al', {}).get('name', ''),
                      'picUrl': s.get('al', {}).get('picUrl', ''),
                      'id': s.get('al', {}).get('id', 0),
                      'publishTime': s.get('al', {}).get('publishTime', 0)}
        songs.append(s)
    return songs


def search_albums(keyword, limit=10):
    """搜索专辑 (type=10)"""
    url = 'https://music.163.com/api/cloudsearch/pc'
    resp = requests.post(url, data={'s': keyword, 'type': 10, 'limit': limit, 'offset': 0},
                         headers=build_headers(), timeout=30)
    raw = resp.json().get('result', {}).get('albums', [])
    albums = []
    for a in raw:
        albums.append({'id': a.get('id'), 'name': a.get('name'),
                       'artist': a.get('artist', {}).get('name', ''),
                       'size': a.get('size', 0), 'publishTime': a.get('publishTime', 0)})
    return albums


def get_song_detail(song_id):
    result = api_get(f'https://music.163.com/api/song/detail/?ids=[{song_id}]')
    if result.get('songs'):
        return result['songs'][0]
    return None


def get_album_songs(album_id):
    result = api_get(f'https://music.163.com/api/album/{album_id}/')
    return result.get('album', {}).get('songs', [])


def get_playlist_songs(playlist_id):
    result = api_get(f'https://music.163.com/api/v6/playlist/detail?id={playlist_id}')
    playlist = result.get('playlist', {})
    track_ids = [t['id'] for t in playlist.get('trackIds', [])]
    songs = []
    for i in range(0, len(track_ids), 1000):
        batch = track_ids[i:i + 1000]
        ids = ','.join(str(x) for x in batch)
        detail = api_get(f'https://music.163.com/api/song/detail/?ids=[{ids}]')
        songs.extend(detail.get('songs', []))
    return songs, playlist.get('name', 'Unknown')


# ── 音源 ─────────────────────────────────────────────────────────

def get_song_url(song_id):
    """获取下载链接，按 lossless→exhigh→standard 降级。
    返回 (url, ext, is_trial)：url 已转 https，ext 按 URL 后缀判断，
    is_trial=True 表示 VIP 试听片段。"""
    url = 'https://music.163.com/weapi/song/enhance/player/url/v1?csrf_token='
    for level in ['lossless', 'exhigh', 'standard']:
        params = {'ids': [song_id], 'level': level, 'encodeType': 'flac', 'csrf_token': ''}
        data = api_post(url, params).get('data', [{}])[0]
        song_url = data.get('url')
        if song_url:
            song_url = song_url.replace('http://', 'https://')
            ext = 'flac' if song_url.rsplit('.', 1)[-1].lower() == 'flac' else 'mp3'
            trial = data.get('freeTrialInfo') is not None and data.get('freeTrialInfo') != {}
            return song_url, ext, trial
    return None, 'mp3', False


def get_lyrics(song_id):
    """返回 (原词, 翻译)，失败返回 ('', '')"""
    try:
        result = api_get(f'https://music.163.com/api/song/lyric?id={song_id}&lv=1&tv=1')
        lrc = result.get('lrc', {}).get('lyric', '')
        tlyric = result.get('tlyric', {}).get('lyric', '')
        return lrc, tlyric
    except Exception:
        return '', ''


def get_cover_url(song):
    album = song.get('album', {})
    pic_url = album.get('picUrl', '')
    if pic_url:
        return pic_url.replace('http://', 'https://') + '?param=1024y1024'
    return None


def merge_lrc(lrc, tlyric):
    """把翻译合并进主歌词：翻译行跟在同时间戳的原文行后面（双语 LRC）"""
    if not tlyric:
        return lrc
    trans = {}
    for line in tlyric.splitlines():
        m = re.match(r'\[(\d+:\d+[.:]\d+)\](.*)', line)
        if m:
            trans[m.group(1)] = m.group(2)
    if not trans:
        return lrc
    out = []
    for line in lrc.splitlines():
        m = re.match(r'\[(\d+:\d+[.:]\d+)\](.*)', line)
        if m and m.group(1) in trans and trans[m.group(1)] and trans[m.group(1)] != m.group(2):
            out.append(line)
            out.append(f'[{m.group(1)}]{trans[m.group(1)]}')
        else:
            out.append(line)
    return '\n'.join(out)


# ── 文件名 ───────────────────────────────────────────────────────

def safe_name(s):
    """文件名清理：路径分隔符/Windows 保留字符换成顿号，保留空格"""
    s = re.sub(r'[/\\:*?"<>|\t]+', '、', s)
    s = re.sub(r'\s*、\s*', '、', s)
    s = re.sub(r'、+', '、', s).strip('、 ')
    return s


def artist_str(song):
    """多艺人用 / 连接"""
    artists = song.get('artists') or []
    return ' / '.join(a['name'] for a in artists if a.get('name')) if artists else '未知歌手'


# ── 下载 ─────────────────────────────────────────────────────────

def download_file(url, path, retries=3):
    """带 Referer + 重试的下载"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = {'Referer': 'https://music.163.com', 'User-Agent': BASE_HEADERS['User-Agent']}
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=60)
            if resp.status_code != 200:
                raise RuntimeError(f'HTTP {resp.status_code}')
            total = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            with open(path, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded / total * 100
                            locked_print(f'\r  ↓ {pct:5.1f}%  {downloaded // 1024}KB', end='')
            locked_print()
            return path
        except Exception as e:
            locked_print(f'\r  ⚠️  第 {attempt}/{retries} 次下载失败: {e}')
            if attempt < retries:
                time.sleep(1.5 * attempt)
            path.unlink(missing_ok=True)
    return None


def _song_meta(song):
    """提取通用元数据字典"""
    artists = [a['name'] for a in song.get('artists', []) if a.get('name')]
    artist = ' / '.join(artists) if artists else '未知歌手'
    album = song.get('album', {}).get('name', '')
    album_artist = song.get('album', {}).get('artist', {}).get('name', '') or (artists[0] if artists else '')
    track = str(song.get('no', ''))
    date = ''
    pt = song.get('album', {}).get('publishTime', 0) or song.get('publishTime', 0)
    if pt:
        import datetime
        date = datetime.datetime.fromtimestamp(pt / 1000).strftime('%Y-%m-%d')
    return {'name': song.get('name', ''), 'artist': artist, 'album': album,
            'album_artist': album_artist, 'track': track, 'date': date}


def tag_flac(path, meta, cover_data):
    from mutagen.flac import FLAC, Picture
    audio = FLAC(str(path))
    audio['title'] = meta['name']
    audio['artist'] = meta['artist']
    audio['album'] = meta['album']
    if meta['album_artist']:
        audio['albumartist'] = meta['album_artist']
    if meta['track']:
        audio['tracknumber'] = meta['track']
    if meta['date']:
        audio['date'] = meta['date']
    if cover_data:
        pic = Picture()
        pic.type = 3
        pic.mime = 'image/jpeg'
        pic.data = cover_data
        audio.clear_pictures()
        audio.add_picture(pic)
    audio.save()


def tag_mp3(path, meta, cover_data):
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TPE2, TALB, TRCK, TDRC
    try:
        audio = MP3(str(path), ID3=ID3)
    except Exception:
        return
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=meta['name']))
    audio.tags.add(TPE1(encoding=3, text=meta['artist']))
    audio.tags.add(TALB(encoding=3, text=meta['album']))
    if meta['album_artist']:
        audio.tags.add(TPE2(encoding=3, text=meta['album_artist']))
    if meta['track']:
        audio.tags.add(TRCK(encoding=3, text=meta['track']))
    if meta['date']:
        audio.tags.add(TDRC(encoding=3, text=meta['date']))
    if cover_data:
        audio.tags.delall('APIC')
        audio.tags.add(APIC(encoding=0, mime='image/jpeg', type=3, data=cover_data))
    audio.save(v2_version=3)


def tag_audio(path, song, cover_data=None):
    """写元数据：多艺人、ALBUMARTIST、DATE、TRACKNUMBER、封面"""
    meta = _song_meta(song)
    if Path(path).suffix.lower() == '.flac':
        tag_flac(path, meta, cover_data)
    else:
        tag_mp3(path, meta, cover_data)


def download_song(song, no_print=False, cookie=None, force=False, no_trial=False, tlrc=False):
    """下载单首歌：音频 + 封面 + 元数据 + 双语歌词"""
    song_id = song['id']
    name = safe_name(song.get('name', ''))
    artist = safe_name(artist_str(song))
    album = safe_name(song.get('album', {}).get('name', ''))

    folder = MUSIC_DIR / artist / album
    folder.mkdir(parents=True, exist_ok=True)

    track_no = song.get('no', 0)
    track_prefix = f'{track_no:02d} - ' if track_no else ''

    audio_url, ext, is_trial = get_song_url(song_id)
    if not audio_url:
        locked_print(f'   ❌ 版权限制，无法下载')
        return False

    if is_trial and no_trial:
        locked_print(f'   ⏭️  试听片段 (VIP)，--no-trial 跳过')
        return False

    audio_path = folder / f'{track_prefix}{name} - {artist}.{ext}'
    mp3_path = folder / f'{track_prefix}{name} - {artist}.mp3'
    flac_path = folder / f'{track_prefix}{name} - {artist}.flac'

    if (audio_path.exists() or mp3_path.exists() or flac_path.exists()) and not force:
        locked_print(f'   ⏭️  已存在，跳过')
        return True

    if not no_print:
        locked_print(f'\n🎵 {artist} - {name}')
        locked_print(f'   专辑: {album}')
        if is_trial:
            locked_print(f'   ⚠️  VIP 试听片段 — 用 --cookie 登录可下完整版')

    locked_print(f'   ↓ 下载中 ({ext.upper()})...')
    result = download_file(audio_url, audio_path)
    if result is None:
        locked_print(f'   ❌ 下载失败')
        return False

    # 下载封面
    cover_data = None
    cover_url = get_cover_url(song)
    if cover_url:
        try:
            resp = requests.get(cover_url, headers={'Referer': 'https://music.163.com',
                                                    'User-Agent': BASE_HEADERS['User-Agent']},
                                timeout=30)
            if resp.ok:
                cover_data = resp.content
        except Exception:
            pass

    # 元数据
    try:
        tag_audio(audio_path, song, cover_data)
        locked_print(f'   ✅ 元数据 + 封面已写入')
    except Exception as e:
        locked_print(f'   ⚠️  元数据写入失败: {e}')

    # 歌词（翻译合并进主 lrc）
    lrc, tlyric = get_lyrics(song_id)
    if lrc:
        lrc_path = folder / f'{track_prefix}{name} - {artist}.lrc'
        with open(lrc_path, 'w', encoding='utf-8') as f:
            f.write(merge_lrc(lrc, tlyric) if not tlrc else lrc)
        if tlrc and tlyric:
            tlrc_path = folder / f'{track_prefix}{name} - {artist}.tlrc'
            with open(tlrc_path, 'w', encoding='utf-8') as f:
                f.write(tlyric)
        locked_print(f'   📝 歌词已下载' + (' (双语)' if tlyric and not tlrc else ''))
    return True


def download_many(songs, workers=1, no_print=False, cookie=None, force=False,
                  no_trial=False, tlrc=False):
    """并发下载一批歌曲"""
    failed = 0
    if workers <= 1 or len(songs) <= 1:
        for s in songs:
            if not download_song(s, no_print=no_print, cookie=cookie, force=force,
                                 no_trial=no_trial, tlrc=tlrc):
                failed += 1
        return failed
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(download_song, s, no_print, cookie, force, no_trial, tlrc): s
                   for s in songs}
        for fut in as_completed(futures):
            try:
                if not fut.result():
                    failed += 1
            except Exception as e:
                failed += 1
                locked_print(f'   ❌ 任务异常: {e}')
    return failed


# ── 交互 ─────────────────────────────────────────────────────────

def interactive_search(keyword):
    songs = search(keyword)
    if not songs:
        print('❌ 没有找到相关歌曲')
        return None

    print(f'\n搜索 "{keyword}" 的结果:\n')
    for i, s in enumerate(songs):
        artists = ', '.join(a['name'] for a in s.get('artists', []))
        album = s.get('album', {}).get('name', '')
        duration = s.get('duration', 0) // 1000
        m, sec = divmod(duration, 60)
        fee = s.get('fee', 0)
        vip = ' [VIP]' if fee in (1, 8) else ''
        print(f'  [{i + 1}] {artists} - {s["name"]}{vip}')
        print(f'      专辑: {album}  时长: {m}:{sec:02d}')

    print('\n  [0] 取消')
    print()

    while True:
        try:
            choice = input('选择序号 (多个用空格分隔): ').strip()
            if not choice or choice == '0':
                return None
            indices = [int(x) - 1 for x in choice.split()]
            selected = [songs[i] for i in indices if 0 <= i < len(songs)]
            if selected:
                return selected
        except (ValueError, IndexError):
            pass
        print('无效输入，请重试')


def interactive_album_search(keyword):
    albums = search_albums(keyword)
    if not albums:
        print('❌ 没有找到相关专辑')
        return None

    print(f'\n搜索专辑 "{keyword}" 的结果:\n')
    for i, a in enumerate(albums):
        import datetime
        date = datetime.datetime.fromtimestamp(a['publishTime'] / 1000).strftime('%Y') if a['publishTime'] else '?'
        print(f'  [{i + 1}] {a["artist"]} - {a["name"]}  ({a["size"]}首, {date})')

    print('\n  [0] 取消')
    print()

    while True:
        try:
            choice = input('选择序号: ').strip()
            if not choice or choice == '0':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(albums):
                return albums[idx]
        except (ValueError, IndexError):
            pass
        print('无效输入，请重试')


# ── 主程序 ───────────────────────────────────────────────────────

def main():
    global MUSIC_DIR
    parser = argparse.ArgumentParser(
        description='🎵 网易云音乐下载器 v2.0 - 搜索/FLAC/封面/双语歌词/VIP cookie/并发')
    parser.add_argument('keywords', nargs='*', help='搜索关键词（歌名）')
    parser.add_argument('-s', '--song', type=int, action='append', help='按歌曲 ID 下载')
    parser.add_argument('-a', '--album', type=int, help='下载整张专辑 (专辑 ID)')
    parser.add_argument('-A', '--album-search', type=str, help='按名字搜索专辑并下载')
    parser.add_argument('-p', '--playlist', type=int, help='下载歌单')
    parser.add_argument('-d', '--dir', type=str, default=None, help='下载目录 (默认 ~/Music)')
    parser.add_argument('-y', '--yes', action='store_true', help='自动选择第一个结果')
    parser.add_argument('-c', '--cookie', type=str, default=None,
                        help='登录 cookie 字符串，或 "zen" 自动从 zen 浏览器提取')
    parser.add_argument('-w', '--workers', type=int, default=1, help='并发下载线程数 (默认 1)')
    parser.add_argument('-f', '--force', action='store_true', help='已存在也重新下载')
    parser.add_argument('--no-trial', action='store_true', help='跳过 VIP 试听片段')
    parser.add_argument('--tlrc', action='store_true', help='翻译歌词单独存 .tlrc (默认合并进 lrc)')
    args = parser.parse_args()

    if args.dir:
        MUSIC_DIR = Path(args.dir)

    if not any([args.keywords, args.song, args.album, args.album_search, args.playlist]):
        parser.print_help()
        sys.exit(1)

    cookie = None
    if args.cookie:
        if args.cookie == 'zen':
            cookie = extract_zen_cookie()
            if cookie:
                print('🍪 已从 zen 浏览器提取网易云 cookie')
            else:
                print('⚠️  zen 浏览器里没找到 music.163.com 的 cookie（先登录一次网页版网易云）')
        else:
            cookie = args.cookie

    failed = 0

    # 按 ID 下载
    if args.song:
        for sid in args.song:
            song = get_song_detail(sid)
            if song:
                if not download_song(song, cookie=cookie, force=args.force,
                                     no_trial=args.no_trial, tlrc=args.tlrc):
                    failed += 1
            else:
                print(f'❌ 找不到歌曲 ID: {sid}')
                failed += 1

    # 下载专辑（ID）
    if args.album:
        songs = get_album_songs(args.album)
        print(f'📀 专辑共 {len(songs)} 首')
        failed += download_many(songs, workers=args.workers, cookie=cookie,
                                force=args.force, no_trial=args.no_trial, tlrc=args.tlrc)

    # 按名字搜索专辑
    if args.album_search:
        sel = interactive_album_search(args.album_search)
        if sel:
            songs = get_album_songs(sel['id'])
            print(f'📀 {sel["artist"]} - {sel["name"]} 共 {len(songs)} 首')
            failed += download_many(songs, workers=args.workers, cookie=cookie,
                                    force=args.force, no_trial=args.no_trial, tlrc=args.tlrc)

    # 下载歌单
    if args.playlist:
        songs, pl_name = get_playlist_songs(args.playlist)
        print(f'📋 歌单 "{pl_name}" 共 {len(songs)} 首')
        failed += download_many(songs, workers=args.workers, cookie=cookie,
                                force=args.force, no_trial=args.no_trial, tlrc=args.tlrc)

    # 搜索下载
    for kw in args.keywords:
        if args.yes:
            songs = search(kw, limit=1)
            if songs:
                if not download_song(songs[0], cookie=cookie, force=args.force,
                                     no_trial=args.no_trial, tlrc=args.tlrc):
                    failed += 1
            else:
                print(f'❌ 没有找到: {kw}')
                failed += 1
        else:
            selected = interactive_search(kw)
            if selected:
                failed += download_many(selected, workers=args.workers, cookie=cookie,
                                        force=args.force, no_trial=args.no_trial, tlrc=args.tlrc)

    print(f'\n✨ 完成! 文件在: {MUSIC_DIR}' + (f'  (失败 {failed} 首)' if failed else ''))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
