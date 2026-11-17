#!/usr/bin/env python3
"""Tkinter GUI for the DTCP-IP rescue tool (stdlib only, Win/Linux/macOS).

Features (kept minimal on purpose):
  - list recordings on the recorder (no credentials needed)
  - fetch selected recordings via pydtcpip `stream` (see rescue.py)
  - progress bar (watches the .partial file size) and a log pane
  - manifest view with SHA-256 re-verification
  - credentials.env path display and placement status
  - manual recorder address (skips SSDP discovery, for routed paths
    such as VPN / subnet routing); the value is kept between runs

The GUI follows the same rule as the CLI: it NEVER reads, prints, or
verifies credential values. Placement status is inferred from file
metadata only (existence and size compared with the bundled empty
template); the credentials file itself is never opened here.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rescue  # noqa: E402

TOOL_DIR = Path(__file__).resolve().parent
TEMPLATE = TOOL_DIR / 'credentials.env.example'
SETTINGS_FILE = 'gui_settings.json'


def load_saved_host(config: rescue.Config) -> str | None:
    """Recorder address saved by a previous GUI run.

    The settings file is runtime state kept in the data directory
    (next to pydtcpip's srm.bin); it holds no credentials.
    """
    try:
        data = json.loads((config.data_dir / SETTINGS_FILE).read_text(encoding='utf-8'))
    except Exception:
        return None
    host = data.get('host')
    return host if isinstance(host, str) and host else None


def save_host(config: rescue.Config, host: str | None) -> None:
    """Persist the manual recorder address for the next run."""
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        (config.data_dir / SETTINGS_FILE).write_text(
            json.dumps({'host': host or ''}, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
    except Exception:
        pass  # persistence is a convenience; never block the workflow


def credentials_status(config: rescue.Config) -> str:
    """Placement status from metadata only (the file is never opened)."""
    path = config.credentials
    if not path.exists():
        return '未配置 (ファイルがありません)'
    size = path.stat().st_size
    template_size = TEMPLATE.stat().st_size if TEMPLATE.exists() else 0
    if size <= template_size:
        return '未配置 (空テンプレートのまま)'
    return '配置済み (ファイルサイズからの推定のみ。値は読んでいません)'


def format_bytes(size: int | None) -> str:
    if size is None:
        return '-'
    value = float(size)
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if value < 1024 or unit == 'GiB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} B'
        value /= 1024
    return f'{value:.1f} GiB'


def original_size(recording: dict) -> int | None:
    for resource in recording.get('resources', []):
        if resource.get('is_original'):
            return resource.get('cleartext_size') or resource.get('size')
    return None


class RescueApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title('DTCP-IP 録画救出ツール')
        self.geometry('980x680')
        self.config = rescue.resolve_config()
        if self.config.host is None:
            saved_host = load_saved_host(self.config)
            if saved_host:
                self.config = rescue.resolve_config(host=saved_host)
        self.events: queue.Queue = queue.Queue()
        self.listing: dict | None = None
        self.recordings: dict[str, dict] = {}
        self.fetching = False
        self.active_partial: Path | None = None
        self.active_expected: int | None = None

        self._build_widgets()
        self._refresh_credentials_status()
        self._refresh_manifest()
        self.after(120, self._drain_events)
        self.after(300, self._poll_progress)

    # ------------------------------------------------------------------
    # widgets
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill='x')

        ttk.Label(top, text='資格情報ファイル (credentials.env):').grid(
            row=0, column=0, sticky='w'
        )
        self.credentials_var = tk.StringVar(value=str(self.config.credentials))
        entry = ttk.Entry(top, textvariable=self.credentials_var, width=80)
        entry.grid(row=0, column=1, sticky='ew', padx=4)
        ttk.Button(top, text='変更…', command=self._choose_credentials).grid(
            row=0, column=2
        )
        ttk.Button(top, text='フォルダを開く', command=self._open_credentials_folder).grid(
            row=0, column=3, padx=(4, 0)
        )
        ttk.Label(top, text='nasne アドレス (手動指定):').grid(
            row=1, column=0, sticky='w', pady=(4, 0)
        )
        self.host_var = tk.StringVar(value=self.config.host or '')
        host_entry = ttk.Entry(top, textvariable=self.host_var, width=80)
        host_entry.grid(row=1, column=1, sticky='ew', padx=4, pady=(4, 0))
        ttk.Label(top, text='空欄 = SSDP で自動発見').grid(
            row=1, column=2, columnspan=2, sticky='w', pady=(4, 0)
        )
        self.status_var = tk.StringVar()
        ttk.Label(top, textvariable=self.status_var).grid(
            row=2, column=0, columnspan=4, sticky='w', pady=(2, 0)
        )
        top.columnconfigure(1, weight=1)

        buttons = ttk.Frame(self, padding=(8, 0, 8, 4))
        buttons.pack(fill='x')
        self.list_button = ttk.Button(
            buttons, text='録画一覧を取得', command=self._start_listing
        )
        self.list_button.pack(side='left')
        self.fetch_button = ttk.Button(
            buttons, text='選択した録画を救出', command=self._start_fetch
        )
        self.fetch_button.pack(side='left', padx=(6, 0))
        self.server_var = tk.StringVar(value='サーバー: 未接続')
        ttk.Label(buttons, textvariable=self.server_var).pack(side='left', padx=(12, 0))

        columns = ('title', 'date', 'channel', 'duration', 'size', 'copies')
        self.tree = ttk.Treeview(self, columns=columns, show='headings', height=10)
        for column, text, width in (
            ('title', 'タイトル', 380),
            ('date', '日時', 150),
            ('channel', 'チャンネル', 150),
            ('duration', '長さ', 70),
            ('size', 'サイズ', 90),
            ('copies', '残コピー', 60),
        ):
            self.tree.heading(column, text=text)
            self.tree.column(column, width=width, anchor='w')
        self.tree.pack(fill='both', expand=True, padx=8)

        progress_frame = ttk.Frame(self, padding=(8, 4))
        progress_frame.pack(fill='x')
        self.progress = ttk.Progressbar(progress_frame, mode='determinate', maximum=100)
        self.progress.pack(side='left', fill='x', expand=True)
        self.progress_var = tk.StringVar(value='')
        ttk.Label(progress_frame, textvariable=self.progress_var).pack(
            side='left', padx=(8, 0)
        )

        manifest_frame = ttk.LabelFrame(self, text='救出済み (manifest)', padding=4)
        manifest_frame.pack(fill='both', expand=True, padx=8, pady=(2, 4))
        m_columns = ('mtitle', 'mfile', 'mbytes', 'msha', 'mverify')
        self.mtree = ttk.Treeview(
            manifest_frame, columns=m_columns, show='headings', height=6
        )
        for column, text, width in (
            ('mtitle', 'タイトル', 300),
            ('mfile', 'ファイル', 260),
            ('mbytes', 'サイズ', 90),
            ('msha', 'SHA-256 (先頭16桁)', 130),
            ('mverify', '検証', 60),
        ):
            self.mtree.heading(column, text=text)
            self.mtree.column(column, width=width, anchor='w')
        self.mtree.pack(side='left', fill='both', expand=True)
        ttk.Button(
            manifest_frame, text='ハッシュ検証', command=self._start_verify
        ).pack(side='left', padx=(6, 0), anchor='n')

        log_frame = ttk.LabelFrame(self, text='ログ', padding=4)
        log_frame.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.log_text = tk.Text(log_frame, height=8, wrap='word')
        self.log_text.pack(fill='both', expand=True)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _log(self, message: str) -> None:
        self.log_text.insert('end', message + '\n')
        self.log_text.see('end')

    def _current_config(self) -> rescue.Config:
        path = self.credentials_var.get().strip()
        host = self.host_var.get().strip() or None
        credentials_changed = bool(path) and Path(path) != self.config.credentials
        if credentials_changed or host != self.config.host:
            self.config = rescue.resolve_config(
                credentials=path if path else None, host=host
            )
            save_host(self.config, host)
            self._refresh_credentials_status()
        return self.config

    def _refresh_credentials_status(self) -> None:
        self.status_var.set(
            f"配置状態: {credentials_status(self.config)}"
            '  (状態はファイルの有無とサイズだけから判定し、値は読みません)'
        )

    def _choose_credentials(self) -> None:
        chosen = filedialog.askopenfilename(
            title='credentials.env を選択',
            initialdir=str(self.config.credentials.parent),
            filetypes=[('env file', 'credentials.env'), ('all files', '*.*')],
        )
        if chosen:
            self.credentials_var.set(chosen)
            self.config = rescue.resolve_config(
                credentials=chosen, host=self.host_var.get().strip() or None
            )
            self._refresh_credentials_status()
            self._log(f'資格情報ファイルのパスを変更: {chosen}')

    def _open_credentials_folder(self) -> None:
        folder = self._current_config().credentials.parent
        try:
            if sys.platform == 'win32':
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(folder)])
            else:
                subprocess.Popen(['xdg-open', str(folder)])
        except Exception as error:  # opening a folder is a nicety, not core
            self._log(f'フォルダを開けませんでした: {error}')

    # ------------------------------------------------------------------
    # listing
    # ------------------------------------------------------------------
    def _start_listing(self) -> None:
        if self.fetching:
            return
        self.list_button.config(state='disabled')
        self._log('録画一覧を取得しています…')
        config = self._current_config()

        def worker() -> None:
            try:
                listing = rescue.run_listing(config)
                self.events.put(('listing', listing))
            except SystemExit as error:
                self.events.put(('error', f'一覧取得に失敗しました: {error}'))
            except Exception as error:  # surface anything unexpected
                self.events.put(('error', f'一覧取得に失敗しました: {error!r}'))

        threading.Thread(target=worker, daemon=True).start()

    def _show_listing(self, listing: dict) -> None:
        self.listing = listing
        server = listing.get('server', {})
        self.server_var.set(
            f"サーバー: {server.get('friendly_name', '?')} "
            f"({server.get('location', '')})"
        )
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.recordings.clear()
        for recording in listing.get('recordings', []):
            content_id = recording.get('content_id') or recording['id']
            self.recordings[content_id] = recording
            copies = recording.get('remaining_copy_count', {})
            copies_text = (
                str(copies.get('value')) if copies.get('status') == 'known' else '?'
            )
            date = (recording.get('date') or '').replace('T', ' ')[:16]
            self.tree.insert(
                '',
                'end',
                iid=content_id,
                values=(
                    recording.get('title', ''),
                    date,
                    recording.get('channel_name', ''),
                    recording.get('duration', ''),
                    format_bytes(original_size(recording)),
                    copies_text,
                ),
            )
        self._log(f"録画 {len(self.recordings)} 件を取得しました")

    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------
    def _start_fetch(self) -> None:
        if self.fetching:
            return
        if self.listing is None:
            messagebox.showinfo('録画救出', '先に「録画一覧を取得」を実行してください')
            return
        selected = [self.recordings[iid] for iid in self.tree.selection()]
        if not selected:
            messagebox.showinfo('録画救出', '救出する録画を選択してください')
            return
        config = self._current_config()
        listing = self.listing
        self.fetching = True
        self.fetch_button.config(state='disabled')
        self.list_button.config(state='disabled')

        def emit(message: str) -> None:
            self.events.put(('log', message))

        def worker() -> None:
            succeeded = 0
            for recording in selected:
                filename = rescue.recording_filename(recording)
                self.events.put(
                    (
                        'fetch_begin',
                        (
                            config.out_dir / f'.{filename}.partial',
                            original_size(recording),
                            recording.get('title', ''),
                        ),
                    )
                )
                try:
                    ok = rescue.fetch_one(
                        config, listing, recording, force=False, timeout=0, emit=emit
                    )
                except Exception as error:
                    emit(f'FAILED: {recording.get("title")} ({error!r})')
                    ok = False
                self.events.put(('fetch_end', None))
                succeeded += 1 if ok else 0
            self.events.put(('fetch_all_done', (succeeded, len(selected))))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_progress(self) -> None:
        if self.active_partial is not None and self.active_expected:
            try:
                size = self.active_partial.stat().st_size
            except OSError:
                size = 0
            percent = min(100.0, 100.0 * size / self.active_expected)
            self.progress['value'] = percent
            self.progress_var.set(
                f'{format_bytes(size)} / {format_bytes(self.active_expected)}'
                f' ({percent:.0f}%)'
            )
        self.after(300, self._poll_progress)

    # ------------------------------------------------------------------
    # manifest / verify
    # ------------------------------------------------------------------
    def _refresh_manifest(self, verify_results: dict[str, str] | None = None) -> None:
        for item in self.mtree.get_children():
            self.mtree.delete(item)
        try:
            entries = rescue.read_manifest(self.config)
        except Exception as error:
            self._log(f'manifest を読めませんでした: {error!r}')
            return
        for entry in entries:
            result = (verify_results or {}).get(entry['id'], '')
            self.mtree.insert(
                '',
                'end',
                iid=entry['id'],
                values=(
                    entry.get('title', ''),
                    entry.get('file', ''),
                    format_bytes(entry.get('bytes')),
                    entry.get('sha256', '')[:16],
                    result,
                ),
            )

    def _start_verify(self) -> None:
        config = self.config

        def worker() -> None:
            results: dict[str, str] = {}
            for entry in rescue.read_manifest(config):
                path = config.out_dir / entry['file']
                if not path.exists():
                    results[entry['id']] = 'ファイルなし'
                else:
                    results[entry['id']] = (
                        'OK' if rescue.sha256_of(path) == entry['sha256'] else '不一致'
                    )
            self.events.put(('verified', results))

        threading.Thread(target=worker, daemon=True).start()
        self._log('manifest のハッシュを検証しています…')

    # ------------------------------------------------------------------
    # event loop glue
    # ------------------------------------------------------------------
    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == 'log':
                    self._log(payload)
                elif kind == 'listing':
                    self._show_listing(payload)
                    self.list_button.config(state='normal')
                elif kind == 'error':
                    self._log(payload)
                    self.list_button.config(state='normal')
                    messagebox.showerror('録画救出', payload)
                elif kind == 'fetch_begin':
                    partial, expected, title = payload
                    self.active_partial = partial
                    self.active_expected = expected
                    self.progress['value'] = 0
                    self.progress_var.set(f'救出中: {title}')
                elif kind == 'fetch_end':
                    self.active_partial = None
                    self.active_expected = None
                elif kind == 'fetch_all_done':
                    succeeded, total = payload
                    self.fetching = False
                    self.fetch_button.config(state='normal')
                    self.list_button.config(state='normal')
                    self.progress['value'] = 100 if succeeded == total else 0
                    self.progress_var.set('')
                    self._log(f'救出完了: {succeeded}/{total} 件成功')
                    self._refresh_credentials_status()
                    self._refresh_manifest()
                elif kind == 'verified':
                    self._refresh_manifest(payload)
                    self._log('ハッシュ検証が終わりました')
        except queue.Empty:
            pass
        self.after(120, self._drain_events)


def main() -> int:
    app = RescueApp()
    app.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
