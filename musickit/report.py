"""生成整理报告：Markdown + CSV 双份，UTF-8 编码。"""
import csv
from pathlib import Path

_STATUS_CN = {
    'success': '✅成功',
    'pending': '⚠️待确认',
    'failed': '❌失败',
    'duplicate': '🗂重复',
    'error': '⚠️错误',
}


def _row(item):
    m = item.match
    conf_v = f'{m.confidence:.2f}' if m else ''
    return {
        '状态': _STATUS_CN.get(item.status, item.status),
        '源文件': str(item.src),
        '目标路径': str(item.target or ''),
        '歌手': effective(item, 'artist'),
        '歌名': effective(item, 'title'),
        '专辑': effective(item, 'album'),
        '曲号': item.en_track,
        '发行年': item.en_year,
        '流派': item.en_genre,
        '封面': '有' if item.cover else ('已有' if item.has_cover else ''),
        '歌词': '有' if item.lyrics else '',
        '置信度': conf_v,
        '备注': item.note,
    }


def effective(item, which):
    return (getattr(item, 'en_' + which) or
            getattr(item, 'emb_' + which) or
            getattr(item, which, '') or '')


def write_report(items, out_md: str, dry_run=False):
    """写 Markdown 报告，并顺带写同名 .csv。"""
    out_md = Path(out_md)
    rows = [_row(it) for it in items]

    cols = ['状态', '源文件', '目标路径', '歌手', '歌名', '专辑', '曲号',
            '发行年', '流派', '封面', '歌词', '置信度', '备注']
    counts = {}
    for it in items:
        counts[it.status] = counts.get(it.status, 0) + 1

    tag = ' [DRY-RUN]' if dry_run else ''
    lines = [
        f'# MusicKit 曲库整理报告{tag}',
        '',
        f'- 扫描文件数：{len(items)}',
        f'- 成功：{counts.get("success", 0)} ｜ 待确认：{counts.get("pending", 0)} ｜ '
        f'失败：{counts.get("failed", 0)} ｜ 重复：{counts.get("duplicate", 0)} ｜ '
        f'错误：{counts.get("error", 0)}',
        '',
        '| ' + ' | '.join(cols) + ' |',
        '|' + '|'.join(['---'] * len(cols)) + '|',
    ]
    for r in rows:
        lines.append('| ' + ' | '.join(r.get(c, '') for c in cols) + ' |')

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text('\n'.join(lines), encoding='utf-8')

    out_csv = out_md.with_suffix('.csv')
    with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    return out_md, out_csv
