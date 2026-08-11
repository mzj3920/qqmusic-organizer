"""MusicKit 图形界面版（Tkinter）。

启动：python -m musickit --gui
可选拖拽依赖：pip install tkinterdnd2（不装也能用"浏览…"按钮选目录）。
"""
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import __version__, conf
from .cli import _run

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # noqa: F401
    HAS_DND = True
except ImportError:
    HAS_DND = False


class _QueueStream:
    """把 print/tqdm 输出重定向到线程安全队列，主线程轮询显示到日志框。"""

    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s and s.strip():
            self.q.put(s)

    def flush(self):
        pass


class GuiApp:
    def __init__(self, root):
        self.root = root
        self.root.title('MusicKit 曲库整理')
        self.root.geometry('880x680')
        self.root.minsize(720, 560)

        self.q = queue.Queue()
        self.worker = None
        self.running = False

        self._build_ui()
        if self._setup_dnd():
            self._log('拖拽已启用：把文件夹拖进输入目录即可。')
        self._log(f'MusicKit v{__version__} 就绪。选好目录和选项后点「开始整理」。')

    # --------------------------------------------------------------- UI
    def _build_ui(self):
        pad = {'padx': 12, 'pady': 4}
        root = self.root

        # 输入 / 输出目录
        frm = ttk.LabelFrame(root, text='目录')
        frm.pack(fill='x', padx=12, pady=8)
        self.var_in = tk.StringVar()
        self.var_out = tk.StringVar(value=str(Path.cwd() / conf.DEFAULT_OUT))
        ttk.Label(frm, text='输入目录').grid(row=0, column=0, sticky='w', padx=8, pady=4)
        self._in_entry = ttk.Entry(frm, textvariable=self.var_in)
        self._in_entry.grid(row=0, column=1, sticky='ew', padx=4, pady=4)
        ttk.Button(frm, text='浏览…', command=lambda: self._browse('in')).grid(row=0, column=2, padx=4)
        ttk.Label(frm, text='输出目录').grid(row=1, column=0, sticky='w', padx=8, pady=4)
        ttk.Entry(frm, textvariable=self.var_out).grid(row=1, column=1, sticky='ew', padx=4, pady=4)
        ttk.Button(frm, text='浏览…', command=lambda: self._browse('out')).grid(row=1, column=2, padx=4)
        frm.columnconfigure(1, weight=1)

        # 选项
        frm2 = ttk.LabelFrame(root, text='选项')
        frm2.pack(fill='x', padx=12, pady=8)
        self.opt = {}
        for i, (key, text) in enumerate([
            ('dry_run', '仅预览（dry-run，不落盘）'),
            ('offline', '离线（不联网）'),
            ('fetch_cover', '抓封面'),
            ('fetch_lyric', '抓歌词'),
            ('fetch_tags', '补全标签'),
            ('dedupe', '去重'),
        ]):
            self.opt[key] = tk.BooleanVar(value=key in ('fetch_cover', 'fetch_lyric', 'fetch_tags', 'dedupe'))
            ttk.Checkbutton(frm2, text=text, variable=self.opt[key]).grid(
                row=i // 3, column=i % 3, sticky='w', padx=8, pady=2)

        # 按钮
        bar = ttk.Frame(root)
        bar.pack(fill='x', padx=12, pady=4)
        self.btn_run = ttk.Button(bar, text='开始整理', command=self._on_run)
        self.btn_run.pack(side='left')
        self.btn_cancel = ttk.Button(bar, text='取消', command=self._on_cancel, state='disabled')
        self.btn_cancel.pack(side='left', padx=8)
        self.progress = ttk.Progressbar(bar, mode='indeterminate')
        self.progress.pack(side='left', fill='x', expand=True, padx=12)

        # 日志
        lbl = ttk.LabelFrame(root, text='日志')
        lbl.pack(fill='both', expand=True, padx=12, pady=8)
        self.txt = tk.Text(lbl, wrap='word', height=16, font=('Consolas', 9))
        self.txt.pack(fill='both', expand=True, padx=6, pady=6)

    def _setup_dnd(self):
        """绑定输入框为拖拽目标；根窗口不支持 tkdnd 时静默跳过。返回是否启用。"""
        if not HAS_DND:
            return False
        try:
            self._in_entry.drop_target_register(DND_FILES)
            self._in_entry.dnd_bind('<<Drop>>', self._on_drop)
            return True
        except tk.TclError:
            return False

    # ------------------------------------------------------------- 行为
    def _browse(self, which):
        d = filedialog.askdirectory(title='选择目录')
        if d:
            (self.var_in if which == 'in' else self.var_out).set(d)

    def _on_drop(self, event):
        path = event.data.strip().strip('{}').replace('\\', '/')
        if os.path.isdir(path):
            self.var_in.set(path)
            self._log(f'拖入目录：{path}')

    def _log(self, s):
        self.txt.insert('end', s.rstrip() + '\n')
        self.txt.see('end')

    def _build_ns(self):
        from argparse import Namespace
        report = os.path.join(self.var_out.get(), 'musickit_report.md') if self.var_out.get() else 'musickit_report.md'
        o = self.opt
        return Namespace(
            input=self.var_in.get(),
            out=self.var_out.get(),
            dry_run=o['dry_run'].get(),
            verbose=True,
            report=report,
            offline=o['offline'].get(),
            no_fetch_cover=not o['fetch_cover'].get(),
            no_fetch_lyric=not o['fetch_lyric'].get(),
            no_fetch_tags=not o['fetch_tags'].get(),
            force=False,
            no_dedupe=not o['dedupe'].get(),
            min_confidence=conf.MIN_CONFIDENCE,
            workers=1,
            self_test=False,
        )

    def _on_run(self):
        if self.running:
            return
        ns = self._build_ns()
        if not ns.input or not os.path.isdir(ns.input):
            self._log('请输入有效的输入目录。')
            return
        self.running = True
        self.btn_run.config(state='disabled')
        self.btn_cancel.config(state='normal')
        self.progress.start(12)
        self._log(f"\n===== 开始整理：{ns.input} → {ns.out} =====\n")

        # 在子线程跑流水线，stdout/stderr 重定向进队列
        def job():
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = _QueueStream(self.q)
            sys.stderr = _QueueStream(self.q)
            try:
                try:
                    _run(ns)
                except Exception as e:
                    self.q.put(f'\n[出错] {type(e).__name__}: {e}')
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                self.q.put('__DONE__')

        self.worker = threading.Thread(target=job, daemon=True)
        self.worker.start()
        self.root.after(100, self._poll)

    def _on_cancel(self):
        self._log('\n[取消] 本版支持结束后再停止（流水线未设中断点）。')
        self.btn_cancel.config(state='disabled')

    def _poll(self):
        try:
            while True:
                s = self.q.get_nowait()
                if s == '__DONE__':
                    raise StopIteration
                self._log(s)
        except queue.Empty:
            pass
        except StopIteration:
            self.progress.stop()
            self.btn_run.config(state='normal')
            self.btn_cancel.config(state='disabled')
            self.running = False
            self._log('===== 完成 =====')
            return
        if self.running:
            self.root.after(100, self._poll)


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    cls = TkinterDnD.Tk if HAS_DND else tk.Tk
    root = cls()
    GuiApp(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
