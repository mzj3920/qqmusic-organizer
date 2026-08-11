"""文件名解析：清洗脏标记、拆歌手/歌名、归一化、版本标注提取。"""
import os
import re

from . import conf

# 重名编号 (1) / (2)，注意别误伤 (Live)
DUPE_NUM_RE = re.compile(r'\s*\(\d+\)\s*$')

# --------------------------------------------------------------------------
# 清洗
# --------------------------------------------------------------------------

def clean_stem(name: str) -> str:
    """把 `歌手 - 歌名 [mqms2].mflac0.flac` 之类的名字清洗成干净 stem。

    顺序：剥扩展名 → 剥 QMC 双扩展名 → 剥重名编号 `(1)` → 反复剥脏标记。
    编号必须先剥，否则 `Memory_EM (1)` 里的 `_EM` 会因不在尾部而漏剥。
    """
    stem = os.path.splitext(name)[0]

    # 剥 QMC 双扩展名（如 .mflac0、.qmcflac），按长度降序避免半截误剥
    for q in sorted(conf.QE_SUFFIXES, key=len, reverse=True):
        if stem.endswith('.' + q):
            stem = stem[:-(len(q) + 1)]
            break

    # 剥重名编号 (1) / (2)，注意别误伤 (Live)
    stem = DUPE_NUM_RE.sub('', stem)

    # 反复剥尾部脏标记，直到稳定
    changed = True
    while changed:
        changed = False
        for s in conf.DIRTY_SUFFIXES:
            if stem.endswith(s):
                stem = stem[:len(stem) - len(s)]
                changed = True

    return stem.strip()


def parse_path(path) -> tuple:
    """从文件路径解析出 (artist, title)。"""
    name = os.path.basename(str(path))
    cleaned = clean_stem(name)
    return split_artist_title(cleaned)


def split_artist_title(cleaned: str) -> tuple:
    """按第一个 ` - ` 拆歌手/歌名；无分隔符则整段作歌名（歌手为空）。"""
    m = re.match(r'^(.*?)\s+-\s+(.*)$', cleaned)
    if m:
        artist = m.group(1).strip()
        title = m.group(2).strip()
        # “6 - Billie Jean”的 6 是曲号前缀不是歌手 → 丢弃，保留歌名
        if re.fullmatch(r'\d{1,3}', artist):
            artist = ''
        else:
            # 歌手侧剥掉括号内容（如“各种(群星)”），歌名侧的 (Live) 等版本标注保留
            artist = re.sub(r'[\(（\[【].*?[\)）\]】]', '', artist).strip()
        return artist, title
    return '', cleaned.strip()


def is_well_named(artist: str, title: str) -> bool:
    """命名是否规范（有歌手且歌名），用于去重时决定保留哪个文件。"""
    return bool(artist and title)


# --------------------------------------------------------------------------
# 归一化 / 版本标注（匹配与搜索用）
# --------------------------------------------------------------------------

def normalize(s: str) -> str:
    """归一化用于比较：小写、全角转半角、去书名号、标点变空格。"""
    s = (s or '').lower().strip()
    s = s.replace('（', '(').replace('）', ')')
    s = s.replace('·', ' ').replace('　', ' ').replace('　', ' ')
    s = re.sub(r'[《》「」【】『』“”‘’]', '', s)
    s = re.sub(r'[^a-z0-9一-鿿]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# 版本标注：括号以版本词开头即可，后面允许跟更多文字，
# 如 (Live)、 (Live at the Royal Albert Hall, 2011)、 (伴奏)、 (Remix Extended)
_VERSION_RE = re.compile(
    r'[（(](?:live|remix|remastered|acoustic|伴奏|instrumental|piano|solo|clean|'
    r'原版|现场|demo|unplugged|dj|karaoke|版)[^）)]*[）)]',
    re.IGNORECASE,
)
_VERSION_KW = re.compile(
    r'(live|remix|remastered|acoustic|伴奏|instrumental|piano|solo|clean|'
    r'原版|现场|demo|unplugged|dj|karaoke|版)',
    re.IGNORECASE,
)


def extract_versions(s: str) -> set:
    """提取文件名里的版本标注，统一成规范词（Live/伴奏/Remix…）。

    `(Live)` 和 `(Live at the Royal Albert Hall, 2011)` 都归一成 {'live'}，
    匹配打分时用于保证版本一致。
    """
    versions = set()
    for m in _VERSION_RE.finditer(s or ''):
        inside = m.group(0)[1:-1]
        kw = _VERSION_KW.match(inside)
        if kw:
            versions.add(kw.group(1).lower())
    return versions
