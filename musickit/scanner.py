"""递归扫描音频文件。"""
from pathlib import Path

from . import conf


def scan(root) -> list:
    """递归扫描 root 下所有支持的音频文件，返回 Path 列表。"""
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f'输入目录不存在: {root}')
    out = []
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower().lstrip('.') in conf.AUDIO_EXTS:
            out.append(p)
    return sorted(out)
