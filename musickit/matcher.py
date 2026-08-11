"""匹配与置信度打分：在 QQ 搜索候选里挑出最优，并判定 成功/待确认/失败。"""
from . import conf, filenames
from .models import Match


def tokens(s):
    return filenames.normalize(s).split()


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score(cand, title, artist, duration, versions) -> float:
    """对单条候选打分，范围约 [0, 1]。"""
    s = 0.0

    # 歌名：精确 +50，否则按词交集相似度
    n_title = filenames.normalize(title)
    n_cname = filenames.normalize(cand.get('songname', ''))
    if n_title and n_cname:
        if n_cname == n_title:
            s += 50
        else:
            s += 30 * jaccard(tokens(n_title), tokens(n_cname))

    # 歌手：一致 +20，明显不一致 -15
    n_artist = filenames.normalize(artist)
    singers = cand.get('singer') or []
    c_artist = singers[0].get('name', '') if singers else ''
    n_cartist = filenames.normalize(c_artist)
    if n_artist:
        if n_cartist:
            if n_cartist == n_artist:
                s += 20
            elif jaccard(tokens(n_cartist), tokens(n_artist)) < 0.5:
                s -= 15
        else:
            s -= 10

    # 时长：interval 单位秒，与本地文件时长比对
    interval = cand.get('interval') or 0
    if duration and interval:
        diff = abs(interval - duration)
        if diff <= 3:
            s += 20
        elif diff <= 10:
            s += 10
        elif diff > 30:
            s -= 20

    # 版本标注冲突（Live/伴奏/Remix…）：候选版本与文件名版本不一致则重罚
    cand_versions = filenames.extract_versions(cand.get('songname', ''))
    if versions and cand_versions and not (versions & cand_versions):
        s -= 30

    return max(0.0, min(1.0, s / 80.0))


def best_match(cands, title, artist, duration):
    """返回 (Match | None, 置信度)。"""
    versions = filenames.extract_versions(title)
    best, best_s = None, -1.0
    for c in cands:
        sc = score(c, title, artist, duration, versions)
        if sc > best_s:
            best, best_s = c, sc
    if best is None:
        return None, 0.0
    return Match(
        songmid=best.get('songmid', ''),
        songname=best.get('songname', ''),
        singer=(best.get('singer') or [{}])[0].get('name', ''),
        albumname=best.get('albumname', ''),
        albummid=best.get('albummid', ''),
        interval=best.get('interval'),
        confidence=best_s,
    ), best_s


def classify(confidence: float, has_artist: bool) -> str:
    """按置信度分档：success / pending / failed。"""
    if not has_artist:
        return 'pending'   # 无歌手只靠歌名搜，歧义大，强制人工确认
    if confidence >= conf.MIN_CONFIDENCE:
        return 'success'
    if confidence >= conf.PENDING_CONFIDENCE:
        return 'pending'
    return 'failed'
