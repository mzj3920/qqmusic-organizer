"""全局常量。

QQ 音乐接口端点集中在这里，接口调整时只改这一处。
"""

# --------------------------------------------------------------------------
# QQ 音乐 Web 接口（2026-08 实测：无需登录、无需签名，固定 header 即可）
# --------------------------------------------------------------------------
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'),
    'Referer': 'https://y.qq.com/',
    'Origin': 'https://y.qq.com',
}

ENDPOINTS = {
    'search': 'https://c.y.qq.com/soso/fcgi-bin/client_search_cp',
    'lyric': 'https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg',
    'album': 'https://c.y.qq.com/v8/fcg-bin/fcg_v8_album_info_cp.fcg',
}

# 封面：albummid -> 图床 URL（R800 失败自动降级 R500）
COVER_TEMPLATE = 'https://y.gtimg.cn/music/photo_new/T002R800x800M000{mid}.jpg'
COVER_FALLBACK = 'https://y.gtimg.cn/music/photo_new/T002R500x500M000{mid}.jpg'

# 请求限速 / 重试
RATE_DELAY = 0.3          # 相邻请求最小间隔（秒）
RETRIES = 3
TIMEOUT = 10

# --------------------------------------------------------------------------
# 文件识别
# --------------------------------------------------------------------------
AUDIO_EXTS = {'flac', 'ogg', 'opus', 'mp3', 'm4a', 'mp4'}

# 文件名里的脏标记（QQ 音乐音质标签等），按出现先后逐个剥除
DIRTY_SUFFIXES = [
    ' [mqms2]', '[mqms2]', ' [mqms0]', '[mqms0]',
    '_EM', '_hires', '_hq', '_SQ', '_SQFlac',
    '_flac', '_ogg', '_m4a', '_mp3',
]

# QMC 加密格式的双扩展名（解密后残留，如 xxx.mflac0.flac 里的 .mflac0）
QE_SUFFIXES = [
    'mflac0', 'mflac2', 'mflac', 'mgg0', 'mgg1', 'mggl', 'mgg', 'mmp4',
    'qmcflac', 'qmcogg', 'qmc0', 'qmc2', 'qmc3', 'qmc4', 'qmc6', 'qmc8',
    'tkm', 'bkcmp3', 'bkcm4a', 'bkcflac', 'bkcwav', 'bkcape', 'bkcogg', 'bkcwma',
]

# --------------------------------------------------------------------------
# 匹配 / 目录规整
# --------------------------------------------------------------------------
MIN_CONFIDENCE = 0.7      # ≥ 自动接受
PENDING_CONFIDENCE = 0.4  # ≥ 待人工确认，< 匹配失败

# 目录规整
DEFAULT_OUT = 'music_lib'
UNKNOWN_ARTIST_DIR = 'Unknown Artists'
SINGLE_DIR = 'Single'
DUPLICATE_DIR = '_duplicates'
MAX_NAME_LEN = 120
