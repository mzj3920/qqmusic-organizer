"""流水线各阶段共享的数据结构。"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Match:
    """QQ 音乐 API 返回的最优匹配结果。"""
    songmid: str
    songname: str
    singer: str = ''
    albumname: str = ''
    albummid: str = ''
    interval: Optional[int] = None
    confidence: float = 0.0


@dataclass
class Track:
    """一条待整理的音乐文件，贯穿扫描→去重→匹配→整理→报告。"""
    src: Path
    size: int = 0
    file_hash: str = ''
    duration: float = 0.0

    # 文件名解析结果
    artist: str = ''
    title: str = ''

    # 内嵌标签
    emb_title: str = ''
    emb_artist: str = ''
    emb_album: str = ''
    has_cover: bool = False

    # 最优匹配
    match: Optional[Match] = None

    # 网络补全结果
    en_title: str = ''
    en_artist: str = ''
    en_album: str = ''
    en_track: str = ''
    en_year: str = ''
    en_genre: str = ''
    cover: Optional[bytes] = None
    lyrics: str = ''

    # 处理结果
    status: str = 'new'   # success / pending / failed / duplicate / error
    target: Optional[Path] = None
    keep: bool = True     # False 表示是去重淘汰件
    note: str = ''
