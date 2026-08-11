"""内容去重：size 分组 + sha1 分块哈希确认。

重复文件几乎必同 size，先按 size 分组，组内再用内容哈希确认，
避免对每个文件都全量读一遍。保留优先级见 keep_priority()。
"""
import hashlib
from pathlib import Path

from . import conf, filenames, tags

CHUNK = 1 << 20  # 1 MiB


def content_hash(path) -> str:
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def group_duplicates(paths) -> list:
    """返回重复组列表，每组是一个内容完全相同但文件不同的列表。"""
    by_size = {}
    for p in paths:
        by_size.setdefault(p.stat().st_size, []).append(p)

    groups = []
    for size, group in by_size.items():
        if len(group) < 2:
            continue
        by_hash = {}
        for p in group:
            by_hash.setdefault(content_hash(p), []).append(p)
        for files in by_hash.values():
            if len(files) > 1:
                groups.append(files)
    return groups


def keep_priority(path) -> tuple:
    """决定去重时保留哪个文件（分数高的保留）。

    优先级：有内嵌封面 > 命名规范（歌手 - 歌名）> 无脏标记 > 名字更短。
    """
    score = 0
    if tags.has_cover(path):
        score += 10
    artist, title = filenames.parse_path(path)
    if artist and title:
        score += 4
    if not any(d in path.name for d in conf.DIRTY_SUFFIXES):
        score += 2
    if filenames.DUPE_NUM_RE.search(Path(path).stem):
        score -= 5          # 带重名编号 (1) 的是较差的保留对象
    if len(path.name) < 60:
        score += 1
    return score


def pick_keep(paths) -> tuple:
    """从重复组里挑出 (保留文件, [淘汰文件...])。"""
    keep = max(paths, key=keep_priority)
    return keep, [p for p in paths if p is not keep]
