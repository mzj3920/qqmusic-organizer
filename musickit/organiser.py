"""目录规整：规划 `歌手/专辑/曲号 - 歌名.ext`，处理非法字符/冲突，执行 move。"""
import os
import re
import shutil
from pathlib import Path

from . import conf

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {'CON', 'PRN', 'AUX', 'NUL',
             'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
             'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}


def sanitize(name: str) -> str:
    """清理目录/文件名的非法字符与 Windows 保留名。"""
    name = _ILLEGAL.sub('_', name).strip(' .')
    if not name:
        name = '_'
    if name.upper() in _RESERVED:
        name = '_' + name
    return name[:conf.MAX_NAME_LEN]


def effective_artist(item) -> str:
    """取歌手：网络补全 > 内嵌 > 文件名，都没有归入 Unknown Artists。"""
    return (item.en_artist or item.emb_artist or item.artist
            or conf.UNKNOWN_ARTIST_DIR)


def effective_album(item) -> str:
    """取专辑：网络补全 > 内嵌，都没有归入 Single。"""
    return item.en_album or item.emb_album or conf.SINGLE_DIR


def effective_title(item) -> str:
    """取歌名：网络补全 > 文件名 > 内嵌。"""
    return item.en_title or item.title or item.emb_title or Path(item.src).stem


def plan_target(item, out_root) -> Path:
    """规划目标路径：<out>/<歌手>/<专辑>/[曲号 - ]歌名.ext。"""
    artist = sanitize(effective_artist(item))
    album = sanitize(effective_album(item))
    title = sanitize(effective_title(item))
    ext = Path(item.src).suffix.lower()
    stem = f'{item.en_track} - {title}' if item.en_track else title
    return Path(out_root) / artist / album / (stem + ext)


def resolve_conflict(target: Path, force: bool) -> Path:
    """目标已存在时：force 直接覆盖；否则追加 ` (2)`/` (3)`…。"""
    if force or not target.exists():
        return target
    parent, name = target.parent, target.stem + target.suffix
    for n in range(2, 1000):
        cand = parent / f'{target.stem} ({n}){target.suffix}'
        if not cand.exists():
            return cand
    return parent / f'{target.stem} ({999}){target.suffix}'


def move_file(item, out_root, dry_run=False) -> Path:
    """规划并执行移动；dry_run 只返回目标不落盘。返回最终目标路径。"""
    target = resolve_conflict(plan_target(item, out_root), force=False)
    if dry_run:
        item.target = target
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.path.exists(target) and os.path.samefile(target, item.src):
        item.target = target
        return target
    shutil.move(str(item.src), str(target))
    item.target = target
    return target


def move_duplicate(item, out_root, dry_run=False) -> Path:
    """把去重淘汰件移到 <out>/_duplicates/。"""
    target = Path(out_root) / conf.DUPLICATE_DIR / item.src.name
    target = resolve_conflict(target, force=False)
    if dry_run:
        item.target = target
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(item.src), str(target))
    item.target = target
    return target
