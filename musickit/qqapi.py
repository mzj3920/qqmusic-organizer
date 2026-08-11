"""QQ 音乐 Web 接口封装：搜索 / 歌词 / 专辑详情 / 封面。

2026-08 实测：四个端点无需登录、无需签名，固定 header 即可稳定调用。
内置限速 + 指数退避重试 + album/lyric 缓存（跨文件命中避免重复请求）。
"""
import base64
import threading
import time

import requests

from . import conf

_session = requests.Session()
_session.headers.update(conf.HEADERS)

_lock = threading.Lock()
_last_req = [0.0]

_album_cache = {}
_lyric_cache = {}


def _rate_limit():
    """限速：保证相邻请求间隔不小于 RATE_DELAY。"""
    with _lock:
        wait = conf.RATE_DELAY - (time.time() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.time()


def _get(url, params=None):
    for i in range(conf.RETRIES):
        _rate_limit()
        try:
            r = _session.get(url, params=params, timeout=conf.TIMEOUT)
            r.raise_for_status()
            r.encoding = 'utf-8'  # 关键：防止 requests 把 UTF-8 误判成其他编码
            return r
        except (requests.RequestException, ValueError):
            if i == conf.RETRIES - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError('unreachable')


def search(title, artist=None):
    """按歌名+歌手搜索，返回候选列表（每条含 songmid/songname/singer/albummid/...）。"""
    w = f'{title} {artist}'.strip() if artist else title
    r = _get(conf.ENDPOINTS['search'], params={'w': w, 'p': 1, 'n': 20, 'format': 'json', 't': 0})
    try:
        data = r.json()
    except ValueError:
        return []
    if data.get('code') != 0:
        return []
    return data.get('data', {}).get('song', {}).get('list', []) or []


def get_lyric(songmid):
    """返回 (lrc, trans)。lrc 含 [ti:][ar:][al:] 头部；失败返回 ('', '')。"""
    if songmid in _lyric_cache:
        return _lyric_cache[songmid]
    val = ('', '')
    try:
        r = _get(conf.ENDPOINTS['lyric'], params={'songmid': songmid, 'format': 'json'})
        j = r.json()
        val = (_b64dec(j.get('lyric')), _b64dec(j.get('trans')))
    except (requests.RequestException, ValueError):
        pass
    _lyric_cache[songmid] = val
    return val


def get_album(albummid):
    """返回专辑详情 dict（含 aDate/genre/songlist）。失败返回 {}。"""
    if albummid in _album_cache:
        return _album_cache[albummid]
    val = {}
    try:
        r = _get(conf.ENDPOINTS['album'], params={'albummid': albummid, 'format': 'json'})
        val = r.json().get('data') or {}
    except (requests.RequestException, ValueError):
        pass
    _album_cache[albummid] = val
    return val


def album_track_number(albummid, songmid):
    """在专辑曲目表里找 songmid 的曲号（下标+1）；找不到返回空串。"""
    data = get_album(albummid)
    songlist = data.get('list') or []   # 实测键是 'list' 不是 'songlist'
    for i, s in enumerate(songlist):
        if s.get('songmid') == songmid:
            return str(i + 1)
    return ''


def download_cover(albummid):
    """按 albummid 下载封面 JPEG；R800 失败自动降级 R500；都失败返回 None。"""
    if not albummid:
        return None
    for url in (conf.COVER_TEMPLATE.format(mid=albummid),
                conf.COVER_FALLBACK.format(mid=albummid)):
        _rate_limit()
        try:
            r = _session.get(url, headers=conf.HEADERS, timeout=conf.TIMEOUT)
            if r.status_code == 200 and r.content and not r.content[:4].lstrip().startswith(b'<'):
                return r.content
        except requests.RequestException:
            continue
    return None


def _b64dec(s):
    try:
        return base64.b64decode(s or '').decode('utf-8', 'replace')
    except Exception:
        return ''
