"""mutagen 标签读写：flac/ogg/opus/mp3/m4a 的 标签+封面+歌词。

写标签时只写入补全的非空字段，不触碰文件里已有的 QMQuality 等其他字段。
"""
import base64
from pathlib import Path

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1, TRCK, USLT
from mutagen.id3 import ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------

def _vc_get(tags, key):
    """读 VorbisComment 标签（mutagen 键统一小写）。"""
    vals = tags.get(key) if tags else None
    return str(vals[0]) if vals else ''


def _id3_get(id3, key):
    frames = id3.getall(key) if id3 else []
    if frames and frames[0].text:
        return str(frames[0].text[0])
    return ''


def read_embedded(path) -> dict:
    """读内嵌标签与时长：{duration, title, artist, album, has_cover}。"""
    ext = Path(path).suffix.lower()
    info = {'duration': 0.0, 'title': '', 'artist': '', 'album': '', 'has_cover': False}
    try:
        if ext == '.flac':
            f = FLAC(path)
            info['duration'] = float(f.info.length or 0)
            tags = f.tags
            info['title'] = _vc_get(tags, 'title')
            info['artist'] = _vc_get(tags, 'artist')
            info['album'] = _vc_get(tags, 'album')
            info['has_cover'] = bool(f.pictures)
        elif ext in ('.ogg', '.opus'):
            f = OggVorbis(path) if ext == '.ogg' else OggOpus(path)
            info['duration'] = float(f.info.length or 0)
            tags = f.tags
            info['title'] = _vc_get(tags, 'title')
            info['artist'] = _vc_get(tags, 'artist')
            info['album'] = _vc_get(tags, 'album')
            info['has_cover'] = bool(tags and 'metadata_block_picture' in tags)
        elif ext == '.mp3':
            f = MP3(path)
            info['duration'] = float(f.info.length or 0)
            id3 = f.tags
            info['title'] = _id3_get(id3, 'TIT2')
            info['artist'] = _id3_get(id3, 'TPE1')
            info['album'] = _id3_get(id3, 'TALB')
            info['has_cover'] = bool(id3 and id3.getall('APIC'))
        elif ext in ('.m4a', '.mp4'):
            f = MP4(path)
            info['duration'] = float(f.info.length or 0)
            tags = f.tags or {}
            info['title'] = str(tags['\xa9nam'][0]) if tags.get('\xa9nam') else ''
            info['artist'] = str(tags['\xa9ART'][0]) if tags.get('\xa9ART') else ''
            info['album'] = str(tags['\xa9alb'][0]) if tags.get('\xa9alb') else ''
            info['has_cover'] = bool(tags.get('covr'))
    except Exception:
        pass
    return info


def has_cover(path) -> bool:
    return read_embedded(path)['has_cover']


# --------------------------------------------------------------------------
# 写入
# --------------------------------------------------------------------------

_VC_FIELDS = ('TITLE', 'ARTIST', 'ALBUM', 'TRACKNUMBER', 'DATE', 'GENRE', 'LYRICS')


def _enrich_values(item):
    return {
        'TITLE': item.en_title,
        'ARTIST': item.en_artist,
        'ALBUM': item.en_album,
        'TRACKNUMBER': item.en_track,
        'DATE': item.en_year,
        'GENRE': item.en_genre,
        'LYRICS': item.lyrics,
    }


def _make_picture(cover):
    pic = Picture()
    pic.type = 3
    pic.mime = 'image/jpeg'
    pic.desc = 'Cover'
    pic.data = cover
    return pic


def write_tags(path, item) -> bool:
    """写入补全的标签/封面/歌词。返回是否成功。"""
    try:
        ext = Path(path).suffix.lower()
        if ext == '.flac':
            _write_flac(path, item)
        elif ext == '.ogg':
            _write_vorbis(path, item, OggVorbis)
        elif ext == '.opus':
            _write_vorbis(path, item, OggOpus)
        elif ext == '.mp3':
            _write_mp3(path, item)
        elif ext in ('.m4a', '.mp4'):
            _write_mp4(path, item)
        else:
            return False
        return True
    except Exception:
        return False


def _write_flac(path, item):
    f = FLAC(path)
    for k, v in _enrich_values(item).items():
        if v:
            f[k] = v
    if item.cover:
        f.clear_pictures()
        f.add_picture(_make_picture(item.cover))
    f.save()


def _write_vorbis(path, item, cls):
    f = cls(path)
    for k, v in _enrich_values(item).items():
        if v:
            f[k] = v
    if item.cover:
        pic = _make_picture(item.cover)
        f['metadata_block_picture'] = [base64.b64encode(pic.write()).decode('ascii')]
    f.save()


def _write_mp3(path, item):
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        id3 = ID3()
    if item.en_title:
        id3.add(TIT2(encoding=3, text=[item.en_title]))
    if item.en_artist:
        id3.add(TPE1(encoding=3, text=[item.en_artist]))
    if item.en_album:
        id3.add(TALB(encoding=3, text=[item.en_album]))
    if item.en_track:
        id3.add(TRCK(encoding=3, text=[item.en_track]))
    if item.en_year:
        id3.add(TDRC(encoding=3, text=[item.en_year]))
    if item.en_genre:
        id3.add(TCON(encoding=3, text=[item.en_genre]))
    if item.lyrics:
        id3.add(USLT(encoding=3, lang='chi', desc='LRC', text=item.lyrics))
    if item.cover:
        id3.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=item.cover))
    id3.save(path)


def _write_mp4(path, item):
    f = MP4(path)
    if item.en_title:
        f['\xa9nam'] = [item.en_title]
    if item.en_artist:
        f['\xa9ART'] = [item.en_artist]
    if item.en_album:
        f['\xa9alb'] = [item.en_album]
    if item.en_track:
        try:
            f['trkn'] = [(int(item.en_track), 0)]
        except ValueError:
            pass
    if item.en_year:
        f['\xa9day'] = [item.en_year]
    if item.en_genre:
        f['\xa9gen'] = [item.en_genre]
    if item.lyrics:
        f['\xa9lyr'] = [item.lyrics]
    if item.cover:
        f['covr'] = [MP4Cover(item.cover, imageformat=MP4Cover.FORMAT_JPEG)]
    f.save()
