"""命令行入口与流水线编排：扫描→去重→匹配→补全→写标签→移动→报告。"""
import argparse
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

from tqdm import tqdm

from . import __version__, conf, dedupe, filenames, matcher, organiser, qqapi, report, scanner, tags
from .models import Track


# --------------------------------------------------------------------------
# 参数
# --------------------------------------------------------------------------

def parse_args(argv=None) -> Namespace:
    p = argparse.ArgumentParser(
        prog='musickit',
        description='QQ 音乐解密后的曲库整理管道：去重、抓封面/歌词/标签、整理目录、生成报告。',
    )
    p.add_argument('input', nargs='?', help='要整理的目录（递归扫描 flac/ogg/mp3/m4a）')
    p.add_argument('--out', default=conf.DEFAULT_OUT, help=f'输出根目录（默认 {conf.DEFAULT_OUT}/）')
    p.add_argument('--dry-run', action='store_true', help='只打印将要做的操作，不落盘不移动')
    p.add_argument('--verbose', action='store_true', help='逐条打印匹配过程与得分')
    p.add_argument('--report', default='musickit_report.md', help='报告路径（自动同时写同名 .csv）')

    g = p.add_argument_group('网络补全')
    g.add_argument('--offline', action='store_true', help='完全离线：只用内嵌标签/文件名，不发网络请求')
    g.add_argument('--no-fetch-cover', action='store_true', help='跳过封面下载')
    g.add_argument('--no-fetch-lyric', action='store_true', help='跳过歌词抓取')
    g.add_argument('--no-fetch-tags', action='store_true', help='跳过专辑详情补全（曲号/发行年/流派）')
    g.add_argument('--workers', type=int, default=1, help='并发预留（当前为顺序处理）')

    p.add_argument('--force', action='store_true', help='覆盖已存在的目标文件')
    p.add_argument('--no-dedupe', action='store_true', help='关闭去重')
    p.add_argument('--min-confidence', type=float, default=conf.MIN_CONFIDENCE,
                   help=f'自动接受阈值（默认 {conf.MIN_CONFIDENCE}，低于则标待确认）')
    p.add_argument('--self-test', action='store_true', help='生成夹具跑通全流程后退出')
    p.add_argument('--version', action='version', version=f'musickit {__version__}')
    return p.parse_args(argv)


# --------------------------------------------------------------------------
# 匹配与补全
# --------------------------------------------------------------------------

def _match_and_enrich(it: Track, ns: Namespace):
    # 内嵌标签优先（QQ 解密文件里已写好），文件名解析作兜底
    title = it.emb_title or it.title
    artist = it.emb_artist or it.artist
    if not title:
        it.status = 'error'
        it.note = '无法从文件名/标签解析歌名'
        return

    try:
        cands = qqapi.search(title, artist)
    except Exception:
        it.status = 'error'
        it.note = '网络请求失败（可加 --offline 离线整理）'
        return

    m, conf_v = matcher.best_match(cands, title, artist, it.duration)
    status = matcher.classify(conf_v, bool(artist))
    it.match = m

    if status != 'success' or m is None:
        it.status = status
        it.note = ('无歌手，需人工确认' if not artist and conf_v else
                   '置信度不足' if status == 'pending' else '匹配失败')
        return

    # 成功匹配 → 网络补全（只补空字段）
    it.en_title = m.songname
    it.en_artist = m.singer or artist
    it.en_album = m.albumname

    if not ns.no_fetch_tags and m.albummid:
        album = qqapi.get_album(m.albummid)
        it.en_year = (album.get('aDate') or '')[:4]
        it.en_genre = album.get('genre', '')
        it.en_track = qqapi.album_track_number(m.albummid, m.songmid)

    if not ns.no_fetch_lyric:
        lrc, trans = qqapi.get_lyric(m.songmid)
        it.lyrics = lrc or trans

    if not ns.no_fetch_cover:
        it.cover = qqapi.download_cover(m.albummid)

    it.status = 'success'


# --------------------------------------------------------------------------
# 流水线
# --------------------------------------------------------------------------

def _run(ns: Namespace) -> int:
    if ns.verbose:
        print(f'[scan] 目录: {ns.input}')

    paths = scanner.scan(ns.input)
    if not paths:
        print(f'未在 {ns.input} 找到音频文件')
        return 1
    print(f'扫描到 {len(paths)} 个音频文件')

    # 1) 读取内嵌标签 / 解析文件名
    items = []
    for p in tqdm(paths, desc='读取内嵌标签', unit='个', disable=not ns.verbose):
        it = Track(src=p, size=p.stat().st_size)
        info = tags.read_embedded(p)
        it.duration = info['duration']
        it.emb_title, it.emb_artist, it.emb_album = info['title'], info['artist'], info['album']
        it.has_cover = info['has_cover']
        it.artist, it.title = filenames.parse_path(p)
        items.append(it)

    # 2) 去重
    dup_keep = {}
    if not ns.no_dedupe:
        groups = dedupe.group_duplicates(paths)
        for g in groups:
            k, rest = dedupe.pick_keep(g)
            for r in rest:
                dup_keep[str(r)] = k
        for it in items:
            if str(it.src) in dup_keep:
                it.keep = False
                it.status = 'duplicate'
                it.note = f'内容与 [{dup_keep[str(it.src)].name}] 重复'
        if dup_keep:
            print(f'去重：{len(dup_keep)} 个重复文件')

    # 3) 匹配与补全（仅对保留件）
    keep_items = [it for it in items if it.keep]
    if ns.offline:
        for it in keep_items:
            it.en_title = it.emb_title or it.title
            it.en_artist = it.emb_artist or it.artist
            it.en_album = it.emb_album
            it.status = 'success' if (it.en_artist and it.en_title) else 'pending'
            if it.status == 'pending':
                it.note = '无歌手，离线模式'
    else:
        for it in tqdm(keep_items, desc='匹配与补全', unit='个', disable=not ns.verbose):
            _match_and_enrich(it, ns)
            if ns.verbose:
                m = it.match
                cv = f'{m.confidence:.2f}' if m else '-'
                print(f'  [{it.status}] {it.src.name} → {cv} | {it.en_title} - {it.en_artist}')

    # 4) 写标签 + 移动
    out_root = ns.out
    for it in items:
        if it.status == 'duplicate':
            organiser.move_duplicate(it, out_root, dry_run=ns.dry_run)
        elif it.keep:
            if not ns.dry_run:
                ok = tags.write_tags(it.src, it)
                if not ok and it.status == 'success':
                    it.note = (it.note + '；' if it.note else '') + '标签写入失败'
            organiser.move_file(it, out_root, dry_run=ns.dry_run)

    # 5) 报告
    md, csv = report.write_report(items, ns.report, dry_run=ns.dry_run)
    counts = {}
    for it in items:
        counts[it.status] = counts.get(it.status, 0) + 1
    mode = '[DRY-RUN] ' if ns.dry_run else ''
    print(f"\n{mode}完成：成功 {counts.get('success', 0)} / 待确认 {counts.get('pending', 0)}"
          f" / 失败 {counts.get('failed', 0)} / 重复 {counts.get('duplicate', 0)}"
          f" / 错误 {counts.get('error', 0)}")
    print(f'报告：{md}  数据：{csv}')
    return 0


# --------------------------------------------------------------------------
# 自检：生成最小 flac 夹具，跑通离线全流程 + 标签写入回读
# --------------------------------------------------------------------------

def self_test() -> int:
    from . import _fixtures
    base = Path(tempfile.mkdtemp(prefix='musickit_selftest_'))
    src, out, rep = base / 'in', base / 'out', base / 'report.md'
    src.mkdir()

    # 1) 离线流水线：flac 夹具 + 去重 + dry-run + 报告
    _fixtures.make(src / '陶喆 - 太美丽.flac', '太美丽', '陶喆', '黑色柳丁')
    _fixtures.make(src / '陶喆 - 太美丽 (1).flac', '太美丽', '陶喆', '黑色柳丁')  # 字节重复
    _fixtures.make(src / 'Memory.flac', 'Memory', '')
    _fixtures.make(src / '孙楠 - 拯救 (Live)_EM.flac', '拯救 (Live)', '孙楠')

    ns = Namespace(input=src, out=str(out), dry_run=True, verbose=False,
                   report=str(rep), offline=True, force=False, no_dedupe=False,
                   min_confidence=conf.MIN_CONFIDENCE,
                   no_fetch_cover=True, no_fetch_lyric=True, no_fetch_tags=True,
                   workers=1, self_test=False)
    _run(ns)

    md = rep.read_text(encoding='utf-8')
    csv = rep.with_suffix('.csv')
    assert '重复：1' in md, f'应识别 1 个重复，实际:\n{md}'
    assert csv.exists()
    print('[1/3] 离线 dry-run 全流程 OK（4 文件 → 去重 1 → 报告生成）')

    # 2) 多格式标签/封面/歌词 写入 + 回读
    for fmt in ('flac', 'ogg', 'mp3', 'm4a'):
        p = base / f'roundtrip.{fmt}'
        _fixtures.make(p, '测试歌', '测试歌手', '测试专辑')
        item = Track(src=p)
        item.en_title = '新标题'
        item.en_artist = '新歌手'
        item.en_album = '新专辑'
        item.en_track = '7'
        item.en_year = '2024'
        item.en_genre = 'Pop'
        item.lyrics = '[ti:新标题]\n[00:01.00]test\n'
        item.cover = b'\xff\xd8\xff\xe0' + b'\x00' * 64  # 占位 JPEG
        assert tags.write_tags(p, item), f'{fmt} 标签写入失败'
        info = tags.read_embedded(p)
        assert (info['title'] == '新标题' and info['artist'] == '新歌手'
                and info['album'] == '新专辑' and info['has_cover']), f'{fmt} 回读不符'
    print('[2/3] 多格式标签/封面/歌词写入+回读 OK（flac/ogg/mp3/m4a）')

    # 3) 版本标注识别（长格式 / 全角 / 无标注）
    from . import filenames
    assert filenames.extract_versions('Think of Me (Live at the Royal Albert Hall, 2011)') == {'live'}
    assert filenames.extract_versions('普通朋友（现场版）') == {'现场'}
    assert filenames.extract_versions('太美丽') == set()
    print('[3/3] 版本标注识别 OK（长格式/全角/无标注）')

    print(f'夹具目录（可删）：{base}')
    return 0


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------

def _fix_console():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def main(argv=None) -> int:
    ns = parse_args(argv)
    _fix_console()
    if ns.self_test:
        return self_test()
    if not ns.input:
        print('用法：python -m musickit <输入目录> [--dry-run] [--offline] …（--help 查看全部）')
        return 2
    return _run(ns)


if __name__ == '__main__':
    sys.exit(main())
