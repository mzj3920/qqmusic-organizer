# MusicKit — QQ音乐解密后的曲库整理管道

> 解密的下半场：把 `QQMusicDecryptor` 解出来的一堆无封面、无歌词、命名混乱的 flac，
> 自动整理成「**歌手 / 专辑 / 曲号 - 歌名.flac**」的规范曲库。

> ## ⚠️ 法律声明 / Legal Disclaimer
>
> **本工具仅用于整理你「自己合法下载、有权使用」的音频文件。** 请勿将其用于任何侵权或未经授权的用途。封面/歌词/元数据均来自 QQ 音乐公开 Web 接口，仅作本地整理用途。
>
> **This tool is intended *solely* for organizing audio files that you have legally downloaded and have the right to use.**

## 它能做什么

对解密出的音乐文件夹一键完成：

| 步骤 | 说明 |
| --- | --- |
| **扫描** | 递归识别 `.flac / .ogg / .opus / .mp3 / .m4a / .mp4` |
| **去重** | 按内容哈希识别字节级重复文件（含 `song (1).flac` 这种重名副本），保留命名规范/带封面的那份，其余移入 `_duplicates/` |
| **清洗文件名** | 剥掉 `_EM`、`_hires`、`[mqms2]`、`.mflac0` 双扩展名、`(1)` 重名编号等 QQ 音乐脏标记 |
| **匹配** | 用 歌名+歌手+时长 打置信度分，从 QQ 音乐搜索候选里选最优；低置信度标「待人工确认」，不瞎抓 |
| **补全** | 抓 封面图 + LRC 歌词 + 专辑名/曲号/发行年/流派（QQ 音乐公开接口，无需登录/签名） |
| **写标签** | flac/ogg 写 VorbisComment + 内嵌封面 + LYRICS；mp3 写 ID3 + APIC + USLT；m4a 写 MP4 atom |
| **规整目录** | 移动成 `歌手/专辑/曲号 - 歌名.flac`，自动处理非法字符/Windows 保留名/重名冲突 |
| **报告** | 生成 Markdown + CSV 报告：成功/待确认/失败/重复一目了然 |

## 安装

```bash
pip install -r requirements.txt   # 仅新增 mutagen（requests/tqdm 大多数环境已有）
```

## 用法

```bash
python -m musickit <输入目录> [选项]
```

常用示例：

```bash
# 1) 先 dry-run 预览（推荐）：只打印计划，不落盘不移动
python -m musickit decrypted --out music_lib --dry-run

# 2) 离线整理（不联网，只用内嵌标签/文件名，适合已匹配好的库）
python -m musickit decrypted --out music_lib --offline --dry-run

# 3) 真实落地：匹配 + 抓封面歌词 + 写标签 + 移动
python -m musickit decrypted --out music_lib --report music_lib_report.md

# 4) 内置自检（生成最小 flac 夹具，跑通全流程后退出）
python -m musickit --self-test
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `输入目录` | 必填 | 递归扫描源 |
| `--out` | `music_lib/` | 输出根目录 |
| `--dry-run` | 关 | 只打印将要做的 写标签/移动，不落盘 |
| `--offline` | 关 | 完全离线：只用内嵌标签/文件名 |
| `--no-fetch-cover` / `--no-fetch-lyric` / `--no-fetch-tags` | 关 | 分别跳过 封面/歌词/专辑补全 |
| `--force` | 关 | 覆盖已存在的目标文件 |
| `--no-dedupe` | 关 | 关闭去重 |
| `--min-confidence` | `0.7` | 自动接受阈值，低于则标待确认 |
| `--report` | `musickit_report.md` | 报告路径（自动同时写同名 `.csv`） |
| `--verbose` | 关 | 逐条打印匹配过程与得分 |

## 匹配与置信度

- 打分维度：歌名精确/相似 + 歌手一致 + 时长差（秒）+ 版本标注一致（`(Live)`/`(伴奏)`/`(Remix)` 冲突会重罚）
- `≥0.7` 自动接受；`0.4–0.7` 标「待人工确认」（报告里找 `⚠️`）；`<0.4` 匹配失败（仍按文件名进目录，不加网络补全）
- **只有歌名没有歌手的文件强制标「待确认」**——只靠歌名搜歧义太大，不硬猜歌手
- 已匹配成功后才抓歌词/封面/专辑，避免无谓请求；专辑/歌词按 songmid/albummid 缓存，跨文件去重命中

## 已知限制

- 无 ffmpeg 依赖，不做音频指纹（AcoustID）匹配；封面/歌词全靠 QQ 音乐公开接口
- QQ 音乐接口可能调整；端点集中在 [`musickit/conf.py`](musickit/conf.py)，改一处即可
- 高频请求可能被限流：内置 0.3s 限速 + 指数退避重试 + `--offline` 兜底
- 封面下载失败自动降级 `R500x500`，再失败跳过该封面，不中断整批

## 目录结构

```
musickit/
├── musickit.py  (入口见下)
└── musickit/
    ├── cli.py        # 参数解析 + 流水线编排 + 内置自检
    ├── scanner.py    # 递归扫描音频文件
    ├── filenames.py  # 文件名清洗 / 歌手歌名拆分 / 归一化
    ├── dedupe.py     # 内容哈希去重 + 保留策略
    ├── matcher.py    # 置信度打分 / 分档
    ├── qqapi.py      # QQ 音乐搜索/歌词/专辑/封面封装（限速+重试+缓存）
    ├── tags.py       # mutagen 读写 flac/ogg/mp3/m4a 标签+封面+歌词
    ├── organiser.py  # 目录规划 / 非法字符 / 冲突 / move
    ├── report.py     # Markdown + CSV 报告
    ├── models.py     # Track / Match 数据结构
    └── conf.py       # 端点 / 阈值 / 目录规则常量
```

## 依赖

- `requests` — QQ 音乐接口
- `mutagen` — 标签读写（flac/ogg/mp3/m4a）
- `tqdm` — 进度条

## 致谢

元数据来自 [QQ 音乐](https://y.qq.com/) 公开 Web 接口；标签写入基于 [mutagen](https://mutagen.readthedocs.io/)。本工具不包含任何 QQ 音乐私钥或破解逻辑，仅做元数据补全与文件整理。
