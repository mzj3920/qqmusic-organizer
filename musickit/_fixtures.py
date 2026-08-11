"""测试夹具生成：构造最小合法音频文件（仅用于 --self-test，无真实音频流）。

fixture 目标是能被 mutagen 正常打开/读取/写入标签，体积小、可离线构造。
"""
import struct
from pathlib import Path

# --------------------------------------------------------------------------
# FLAC
# --------------------------------------------------------------------------

def _flac_block(type_, data, last):
    return struct.pack('>I', (1 << 31 if last else 0) | (type_ << 24) | len(data)) + data


def make_flac(path, title='', artist='', album=''):
    path = Path(path)
    field = (44100 << 44) | ((2 - 1) << 41) | ((16 - 1) << 36) | 44100
    streaminfo = (struct.pack('>HH', 4096, 4096) + b'\x00\x00\x00' + b'\x00\x00\x00'
                  + struct.pack('>Q', field) + b'\x00' * 16)

    kv = [f'{k}={v}'.encode('utf-8') for k, v in
          (('TITLE', title), ('ARTIST', artist), ('ALBUM', album)) if v]
    vendor = b'reference libFLAC 1.3.1 20141125'
    vc = struct.pack('<I', len(vendor)) + vendor + struct.pack('<I', len(kv))
    for it in kv:
        vc += struct.pack('<I', len(it)) + it

    path.write_bytes(b'fLaC' + _flac_block(0, streaminfo, False) + _flac_block(4, vc, True))


# --------------------------------------------------------------------------
# OGG / Vorbis
# --------------------------------------------------------------------------

_OGG_CRC_TABLE = None


def _ogg_crc_table():
    global _OGG_CRC_TABLE
    if _OGG_CRC_TABLE is None:
        table = []
        for i in range(256):
            r = i << 24
            for _ in range(8):
                r = ((r << 1) ^ 0x04c11db7) & 0xFFFFFFFF if (r & 0x80000000) else (r << 1) & 0xFFFFFFFF
            table.append(r)
        _OGG_CRC_TABLE = table
    return _OGG_CRC_TABLE


def _ogg_page(packet, serial, seq, header_type, granule=0):
    # 单包 < 255 字节：page_segments=1，lacing value=包长
    seg = bytes([1, len(packet)])
    pre = (b'OggS' + bytes([0, header_type]) + struct.pack('<Q', granule)
           + struct.pack('<I', serial) + struct.pack('<I', seq))
    page = pre + b'\x00\x00\x00\x00' + seg + packet
    crc = 0
    for b in page:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _ogg_crc_table()[((crc >> 24) & 0xFF) ^ b]
    return pre + struct.pack('<I', crc) + seg + packet


def _vorbis_ident():
    return (b'\x01vorbis' + struct.pack('<I', 0) + bytes([2]) + struct.pack('<I', 44100)
            + struct.pack('<I', 0) + struct.pack('<I', 128000) + struct.pack('<I', 0)
            + bytes([0xB8, 0x01]))


def _vorbis_comment(title, artist, album):
    kv = [f'{k}={v}'.encode('utf-8') for k, v in
          (('TITLE', title), ('ARTIST', artist), ('ALBUM', album)) if v]
    vendor = b'musickit fixture'
    p = b'\x03vorbis' + struct.pack('<I', len(vendor)) + vendor + struct.pack('<I', len(kv))
    for it in kv:
        p += struct.pack('<I', len(it)) + it
    return p + b'\x01'


def make_ogg(path, title='', artist='', album=''):
    path = Path(path)
    serial = 0x12345678
    data = (_ogg_page(_vorbis_ident(), serial, 0, 0x02)
            + _ogg_page(_vorbis_comment(title, artist, album), serial, 1, 0x00))
    path.write_bytes(data)


# --------------------------------------------------------------------------
# MP3（ID3v2.3 + 一个 MPEG1 Layer III 帧头）
# --------------------------------------------------------------------------

def _id3_frame(tag, text):
    body = b'\x03' + text.encode('utf-8') + b'\x00'
    sz = len(body)
    return (tag.encode() + bytes([(sz >> 21) & 0x7f, (sz >> 14) & 0x7f,
                                  (sz >> 7) & 0x7f, sz & 0x7f])
            + b'\x00\x00' + body)


def make_mp3(path, title='', artist='', album=''):
    path = Path(path)
    frames = b''
    if title:
        frames += _id3_frame('TIT2', title)
    if artist:
        frames += _id3_frame('TPE1', artist)
    if album:
        frames += _id3_frame('TALB', album)
    size = len(frames)
    id3 = (b'ID3' + b'\x03\x00' + b'\x00'
           + bytes([(size >> 21) & 0x7f, (size >> 14) & 0x7f, (size >> 7) & 0x7f, size & 0x7f]))
    # 20 个 128kbps / 44100Hz MPEG1 Layer III 帧（各 417 字节，含 4 字节头），
    # 让 mutagen 的帧同步校验能前后帧互相确认
    frame = bytes([0xFF, 0xFB, 0x90, 0xC0]) + bytes(417 - 4)
    path.write_bytes(id3 + frames + frame * 20)


# --------------------------------------------------------------------------
# M4A（最小 MP4：ftyp + mdat + moov，含 stsd 音频样例）
# --------------------------------------------------------------------------

def _atom(t, payload):
    if isinstance(t, str):
        t = t.encode('ascii')
    return struct.pack('>I', 8 + len(payload)) + t + payload


def _full(t, version, flags, payload):
    return _atom(t, bytes([version]) + flags.to_bytes(3, 'big') + payload)


def _esds():
    """AudioSpecificConfig(1.0) 的 ES_Descriptor，供 mutagen 识别 mp4a。"""
    asc = bytes([0x11, 0x90])          # AAC-LC 44100 双声道
    dec_config = (b'\x04' + bytes([len(asc) + 13]) + b'\x40' + b'\x15'
                  + (0x2000 + len(asc) + 5).to_bytes(2, 'big') + b'\x00\x00\x00\x00'
                  + asc)
    sl = b'\x05' + bytes([2]) + b'\x12\x00'
    body = (b'\x03' + bytes([len(dec_config) + len(sl) + 3]) + b'\x00\x01'
            + dec_config + sl)
    return _atom('esds', bytes([0, 0, 0, 0]) + body)


def _stsd_entry():
    mp4a = (b'\x00\x00\x00\x00' + b'\x00\x00' + b'\x00\x01' + b'\x00\x00\x00\x00'
            + b'\x00\x10\x00\x00' + b'\x00\x00\x00\x00' + b'\x00\x00\x00\x00'
            + b'\x00\x00\x00\x00' + b'\x00\x00\x00\x00' + _esds())
    return _atom('mp4a', mp4a)


def make_m4a(path, title='', artist='', album=''):
    path = Path(path)
    ftyp = _atom('ftyp', b'M4A \x00\x00\x00\x00M4A mp42isom')
    mdat = _atom('mdat', b'\x00')

    mvhd = _full('mvhd', 0, 0, (struct.pack('>IIII', 0, 0, 1000, 1000)
                                + struct.pack('>H', 0x0100) + b'\x00\x00'
                                + b'\x00' * 10 + struct.pack('>9I', *([0] * 9))
                                + struct.pack('>6I', *([0] * 6)) + struct.pack('>I', 2)))
    tkhd = _full('tkhd', 0, 7, (struct.pack('>IIII', 0, 0, 1, 1000)
                                + b'\x00' * 8 + struct.pack('>HHHH', 0, 0, 0, 0)
                                + struct.pack('>9I', *([0] * 9)) + struct.pack('>II', 0, 0)))
    mdhd = _full('mdhd', 0, 0, struct.pack('>IIII', 0, 0, 44100, 44100)
                 + struct.pack('>H', 0x55c4) + b'\x00\x00')
    hdlr = _full('hdlr', 0, 0, b'\x00\x00\x00\x00soun\x00\x00\x00\x00\x00\x00\x00\x00'
                 + b'SoundHandler\x00')
    smhd = _full('smhd', 0, 0, b'\x00\x00\x00\x00')
    dref = _full('dref', 0, 0, struct.pack('>I', 1) + _atom('url ', b'\x00\x00\x00\x01'))
    dinf = _atom('dinf', dref)

    stsd = _full('stsd', 0, 0, struct.pack('>I', 1) + _stsd_entry())
    stts = _full('stts', 0, 0, struct.pack('>II', 1, 44100))
    stsc = _full('stsc', 0, 0, struct.pack('>IIIII', 1, 1, 1, 1, 0))
    stsz = _full('stsz', 0, 0, struct.pack('>II', 0, 0))
    stco = _full('stco', 0, 0, struct.pack('>I', 0))
    stbl = _atom('stbl', stsd + stts + stsc + stsz + stco)
    minf = _atom('minf', smhd + dinf + stbl)
    mdia = _atom('mdia', mdhd + hdlr + minf)
    trak = _atom('trak', tkhd + mdia)
    moov = _atom('moov', mvhd + trak)

    path.write_bytes(ftyp + mdat + moov)


# --------------------------------------------------------------------------
# 统一入口
# --------------------------------------------------------------------------

def make(path, title='', artist='', album=''):
    """按扩展名生成对应格式的最小音频文件。"""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == '.flac':
        make_flac(path, title, artist, album)
    elif ext == '.ogg':
        make_ogg(path, title, artist, album)
    elif ext == '.mp3':
        make_mp3(path, title, artist, album)
    elif ext in ('.m4a', '.mp4'):
        make_m4a(path, title, artist, album)
    else:
        raise ValueError(f'不支持的夹具格式: {ext}')
