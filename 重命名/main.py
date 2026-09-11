"""Folder Renamer - preview and apply extractor-compatible folder names."""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import DND_FILES
from tkinterdnd2.TkinterDnD import DnDWrapper, _require

from config_store import RENAMER_DEFAULTS as DEFAULT_CONFIG, load_config, save_config
from rename_core import (
    ALREADY_NAMED,
    FAILED,
    INVALID,
    NO_TAG,
    PROTECTED,
    READY,
    RENAMED,
    RENAMED_MARKER_KEPT,
    RenameOptions,
    analyze_folders,
    execute_rename,
    path_sort_key,
)


APP_NAME = "标签提取工作台"
CONFIG_FILE = Path(sys.executable if getattr(sys, "frozen", False) else __file__).with_name("config.json")

from ui_theme import (
    SoftCard, SoftButton, SoftEntry, SoftProgressBar, SoftScrollableFrame,
    SCROLLBAR, SCROLLBAR_HOVER,
    APP_FONT,
    BG,
    BORDER,
    DANGER,
    DANGER_BG,
    DANGER_HOVER,
    MUTED,
    PRIMARY,
    PRIMARY_HOVER,
    SECONDARY_BG,
    SECONDARY_HOVER,
    SECONDARY_TEXT,
    SUCCESS,
    SURFACE,
    SURFACE_2,
    SURFACE_3,
    TEXT,
    WARNING,
    ToolTip,
    apply_focus_style,
    secondary_button as theme_secondary_button,
)

STATUS_COLORS = {
    READY: PRIMARY,
    PROTECTED: WARNING,
    NO_TAG: WARNING,
    ALREADY_NAMED: SUCCESS,
    INVALID: DANGER,
    RENAMED: SUCCESS,
    RENAMED_MARKER_KEPT: WARNING,
    FAILED: DANGER,
}


class ModernDnDWindow(ctk.CTk, DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = _require(self)


class RenamerApp:
    def __init__(self, root: ModernDnDWindow, config_backend=None):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1040x720")
        self.root.minsize(840, 600)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.rows: list[dict] = []
        self.is_running = False
        self.cancel_requested = False
        self.ui_events: queue.Queue = queue.Queue(maxsize=512)
        self.config_backend = config_backend
        self.config = config_backend.section("renaming") if config_backend else load_config(CONFIG_FILE)
        self.preview_generation = 0
        self.preview_running = False
        self.preview_options: RenameOptions | None = None

        self.setup_ui()
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.handle_drop)
        self.poll_ui_events()

    @staticmethod
    def card(parent, **kwargs):
        return SoftCard(
            parent,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            corner_radius=14,
            **kwargs,
        )

    @staticmethod
    def secondary_button(parent, text, command, width=90):
        return theme_secondary_button(parent, text, command, width=width, height=40)

    @staticmethod
    def entry(parent, width=None):
        kwargs = {
            "height": 38,
            "corner_radius": 9,
            "fg_color": SURFACE_2,
            "border_color": BORDER,
            "text_color": TEXT,
            "font": ctk.CTkFont(size=13, weight="bold"),
        }
        if width is not None:
            kwargs["width"] = width
        return SoftEntry(parent, **kwargs)

    def setup_ui(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self.build_settings_card()
        self.build_queue_card()
        self.build_action_dock()

    def build_settings_card(self):
        card = self.card(self.root)
        card.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        card.grid_columnconfigure(3, weight=1)

        heading = ctk.CTkFrame(card, fg_color="transparent")
        heading.grid(row=0, column=0, columnspan=5, sticky="ew", padx=18, pady=(14, 10))
        ctk.CTkLabel(
            heading,
            text="提取标签规则",
            text_color=TEXT,
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(side="left")
        self.btn_save = self.secondary_button(heading, "保存设置", self.save_settings, 92)
        self.btn_save.pack(side="right")

        ctk.CTkLabel(
            card,
            text="标签前缀",
            text_color=MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=0, padx=(18, 8), pady=(0, 16))
        self.entry_tag_prefix = self.entry(card, 160)
        self.entry_tag_prefix.grid(row=1, column=1, sticky="w", pady=(0, 16))
        self.entry_tag_prefix.insert(0, self.config.get("tag_prefix", DEFAULT_CONFIG["tag_prefix"]))

        ctk.CTkLabel(
            card,
            text="保护检测词",
            text_color=MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=2, padx=(24, 8), pady=(0, 16))
        self.entry_block_terms = self.entry(card)
        self.entry_block_terms.grid(row=1, column=3, columnspan=2, sticky="ew", padx=(0, 18), pady=(0, 16))
        self.entry_block_terms.insert(0, self.config.get("block_terms", DEFAULT_CONFIG["block_terms"]))

        self.entry_tag_prefix.bind("<KeyRelease>", self.schedule_preview_refresh)
        self.entry_block_terms.bind("<KeyRelease>", self.schedule_preview_refresh)
        self.preview_refresh_job = None

    def build_queue_card(self):
        card = self.card(self.root)
        card.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(15, 10))
        ctk.CTkLabel(
            header,
            text="提取标签预览",
            text_color=TEXT,
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(side="left")
        self.queue_count = ctk.StringVar(value="队列为空")
        ctk.CTkLabel(
            header,
            textvariable=self.queue_count,
            text_color=MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(12, 0))
        self.btn_clear = self.secondary_button(header, "清空", self.clear_queue, 68)
        self.btn_clear.pack(side="right")
        self.btn_choose = self.secondary_button(header, "选择文件夹", self.choose_folder, 108)
        self.btn_choose.pack(side="right", padx=(0, 8))

        self.queue_frame = SoftScrollableFrame(
            card,
            fg_color=SURFACE_2,
            corner_radius=10,
            scrollbar_button_color=SCROLLBAR,
            scrollbar_button_hover_color=SCROLLBAR_HOVER,
        )
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.empty_label = ctk.CTkLabel(
            self.queue_frame,
            text="拖入文件夹，或点击“选择文件夹”",
            text_color=MUTED,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.empty_label.pack(expand=True, pady=105)

    def build_action_dock(self):
        dock = SoftCard(
            self.root,
            height=78,
            corner_radius=0,
            fg_color=SURFACE,
            border_width=1,
            border_color=BORDER,
        )
        dock.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        dock.grid_columnconfigure(0, weight=1)

        progress_box = ctk.CTkFrame(dock, fg_color="transparent")
        progress_box.grid(row=0, column=0, sticky="ew", padx=(22, 20), pady=13)
        progress_box.grid_columnconfigure(0, weight=1)
        self.status_var = ctk.StringVar(value="等待添加文件夹")
        ctk.CTkLabel(
            progress_box,
            textvariable=self.status_var,
            text_color=MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self.total_label = ctk.CTkLabel(
            progress_box,
            text="0%",
            text_color=PRIMARY,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.total_label.grid(row=0, column=1, sticky="e")
        self.total_progress = SoftProgressBar(
            progress_box,
            height=26,
            corner_radius=13,
            fg_color=SURFACE,
            progress_color=PRIMARY,
        )
        self.total_progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        self.total_progress.set(0)

        self.btn_start = SoftButton(
            dock,
            text="提取标签",
            command=self.start_rename,
            width=178,
            height=48,
            corner_radius=12,
            fg_color=SURFACE,
            hover_color=SECONDARY_HOVER,
            text_color=PRIMARY,
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        apply_focus_style(self.btn_start)
        self.btn_start.grid(row=0, column=1, padx=(0, 22))

    def current_options(self) -> RenameOptions:
        return RenameOptions(
            tag_prefix=self.entry_tag_prefix.get().strip(),
            block_terms=self.entry_block_terms.get().strip(),
        )

    def save_settings(self, notify=True):
        options = self.current_options()
        try:
            if self.config_backend:
                self.config_backend.update_section(
                    "renaming",
                    {"tag_prefix": options.tag_prefix, "block_terms": options.block_terms},
                )
            else:
                save_config(CONFIG_FILE, options.tag_prefix, options.block_terms)
            if notify:
                messagebox.showinfo("已保存", f"配置已保存至\n{CONFIG_FILE}")
        except OSError as error:
            messagebox.showerror("无法保存配置", str(error))

    def schedule_preview_refresh(self, _event=None):
        if self.is_running:
            return
        self.preview_options = None
        if self.preview_refresh_job is not None:
            self.root.after_cancel(self.preview_refresh_job)
        self.preview_refresh_job = self.root.after(180, self.refresh_previews)

    def choose_folder(self):
        path = filedialog.askdirectory(title="选择一个文件夹（可继续添加）")
        if path:
            self.add_folders([path])

    def handle_drop(self, event):
        if not self.is_running:
            self.add_folders(self.root.tk.splitlist(event.data))
        return "break"

    def add_folders(self, paths):
        if self.is_running:
            return
        known = {os.path.normcase(os.path.abspath(row["source"])) for row in self.rows}
        for raw_path in paths:
            path = os.path.abspath(raw_path)
            key = os.path.normcase(path)
            if not os.path.isdir(path) or key in known:
                continue
            self.add_row(path)
            known.add(key)
        self._sort_rows()
        self.refresh_previews()

    def add_row(self, path: str):
        self.empty_label.pack_forget()
        frame = ctk.CTkFrame(
            self.queue_frame,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            corner_radius=10,
        )
        frame.pack(fill="x", pady=(0, 8))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(2, weight=1)

        source_label = ctk.CTkLabel(
            frame,
            text=os.path.basename(path),
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        source_label.grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=(11, 2))
        ctk.CTkLabel(
            frame,
            text="→",
            text_color=PRIMARY,
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=1, padx=6, pady=(9, 0))
        target_label = ctk.CTkLabel(
            frame,
            text="正在分析…",
            text_color=PRIMARY,
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        target_label.grid(row=0, column=2, sticky="ew", padx=(8, 10), pady=(11, 2))
        remove = SoftButton(
            frame,
            text="×",
            width=44,
            height=44,
            corner_radius=9,
            fg_color="transparent",
            hover_color=DANGER_BG,
            text_color=MUTED,
            font=ctk.CTkFont(size=17),
        )
        ToolTip(remove, "移除")
        apply_focus_style(remove)
        remove.grid(row=0, column=3, rowspan=2, padx=(2, 10))

        path_label = ctk.CTkLabel(
            frame,
            text=os.path.dirname(path),
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        path_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(14, 8), pady=(0, 10))
        status_label = ctk.CTkLabel(
            frame,
            text="正在分析…",
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        status_label.grid(row=1, column=2, sticky="ew", padx=(8, 10), pady=(0, 10))

        row = {
            "frame": frame,
            "source": path,
            "source_label": source_label,
            "target_label": target_label,
            "path_label": path_label,
            "status_label": status_label,
            "remove": remove,
            "preview": None,
            "finished": False,
            "last_status": None,
        }
        remove.configure(command=lambda current=row: self.remove_row(current))
        self.rows.append(row)

    def _sort_rows(self):
        if not self.rows:
            return
        self.rows.sort(key=lambda row: path_sort_key(row["source"]))
        for row in self.rows:
            row["frame"].pack_forget()
        for row in self.rows:
            row["frame"].pack(fill="x", pady=(0, 8))

    def remove_row(self, row):
        if self.is_running:
            return
        row["frame"].destroy()
        if row in self.rows:
            self.rows.remove(row)
        self.update_queue_count()

    def clear_queue(self):
        if self.is_running:
            return
        for row in self.rows:
            row["frame"].destroy()
        self.rows.clear()
        self.update_queue_count()
        self.total_progress.set(0)
        self.total_label.configure(text="0%")
        self.status_var.set("等待添加文件夹")

    def refresh_previews(self):
        self.preview_refresh_job = None
        if self.is_running:
            return
        active_rows = [row for row in self.rows if not row["finished"]]
        if not active_rows:
            self.preview_running = False
            self.preview_options = self.current_options()
            self.update_queue_count()
            return
        self.preview_generation += 1
        generation = self.preview_generation
        options = self.current_options()
        self.preview_running = True
        self.preview_options = None
        for row in active_rows:
            row["preview"] = None
            row["target_label"].configure(text="正在分析…", text_color=PRIMARY)
            row["status_label"].configure(text="后台读取标签", text_color=MUTED)
        self.status_var.set("正在后台分析文件夹")
        threading.Thread(
            target=self._preview_worker,
            args=(generation, active_rows, options),
            daemon=True,
        ).start()

    def _preview_worker(self, generation, active_rows, options):
        previews = analyze_folders((row["source"] for row in active_rows), options)
        self.ui_events.put(("previews", generation, active_rows, previews, options))

    def update_queue_count(self):
        if not self.rows:
            self.queue_count.set("队列为空")
            if self.empty_label.winfo_exists():
                self.empty_label.pack(expand=True, pady=105)
            return
        ready = sum(
            row["preview"] is not None and row["preview"].status == READY
            for row in self.rows
            if not row["finished"]
        )
        self.queue_count.set(f"{len(self.rows)} 个文件夹 · {ready} 个可提取标签")

    def set_running_state(self, running: bool):
        state = "disabled" if running else "normal"
        self.entry_tag_prefix.configure(state=state)
        self.entry_block_terms.configure(state=state)
        self.btn_save.configure(state=state)
        self.btn_choose.configure(state=state)
        self.btn_clear.configure(state=state)
        for row in self.rows:
            row["remove"].configure(state=state)
        self.btn_start.configure(
            state="disabled" if running else "normal",
            text="正在提取标签…" if running else "提取标签",
        )

    def start_rename(self):
        if self.is_running:
            return
        options = self.current_options()
        if self.preview_running:
            self.status_var.set("文件夹仍在后台分析")
            messagebox.showinfo("正在分析", "文件夹仍在后台分析，请稍后再开始提取标签。")
            return
        if self.preview_options != options or any(
            row["preview"] is None for row in self.rows if not row["finished"]
        ):
            self.status_var.set("正在更新预览")
            self.refresh_previews()
            messagebox.showinfo("正在更新预览", "设置或队列已经变化，预览更新后即可开始。")
            return
        tasks = [
            (row, row["preview"])
            for row in self.rows
            if not row["finished"] and row["preview"] is not None and row["preview"].status == READY
        ]
        if not tasks:
            self.status_var.set("没有可处理项目")
            messagebox.showinfo("没有可处理项目", "当前队列中没有可提取标签的文件夹。")
            return

        for row in self.rows:
            row["last_status"] = None

        self.save_settings(notify=False)
        self.is_running = True
        self.cancel_requested = False
        self.set_running_state(True)
        self.total_progress.set(0)
        self.total_label.configure(text="0%")
        self.status_var.set(f"正在处理 {len(tasks)} 个文件夹")
        threading.Thread(
            target=self.rename_worker,
            args=(tasks, self.current_options()),
            daemon=True,
        ).start()

    def rename_worker(self, tasks, options: RenameOptions):
        total = len(tasks)
        for index, (row, preview) in enumerate(tasks):
            if self.cancel_requested:
                break
            self.ui_events.put(("working", row))
            result = execute_rename(preview.source, options)
            self.ui_events.put(("result", row, result, index + 1, total))
        self.ui_events.put(("finished", total))

    def poll_ui_events(self):
        processed = 0
        deadline = time.perf_counter() + 0.008
        try:
            while processed < 32 and time.perf_counter() < deadline:
                event = self.ui_events.get_nowait()
                processed += 1
                if event[0] == "working":
                    _, row = event
                    row["status_label"].configure(text="正在提取标签…", text_color=PRIMARY)
                elif event[0] == "result":
                    _, row, result, completed, total = event
                    color = STATUS_COLORS.get(result.status, MUTED)
                    row["last_status"] = result.status
                    row["status_label"].configure(text=result.message, text_color=color)
                    if result.target is not None:
                        row["target_label"].configure(text=result.target.name, text_color=color)
                    if result.succeeded:
                        row["source"] = str(result.target)
                        row["path_label"].configure(text=str(result.target.parent))
                        row["finished"] = True
                    progress = completed / total
                    self.total_progress.set(progress)
                    self.total_label.configure(text=f"{progress * 100:.0f}%")
                elif event[0] == "finished":
                    self.finish_rename()
                elif event[0] == "previews":
                    _, generation, active_rows, previews, options = event
                    if generation != self.preview_generation:
                        continue
                    self.preview_running = False
                    self.preview_options = options
                    for row, preview in zip(active_rows, previews):
                        if row not in self.rows or row["finished"]:
                            continue
                        row["preview"] = preview
                        color = STATUS_COLORS.get(preview.status, MUTED)
                        row["target_label"].configure(
                            text=preview.target.name if preview.target is not None else "— 保留原名",
                            text_color=color,
                        )
                        row["status_label"].configure(text=preview.message, text_color=color)
                    self.update_queue_count()
                    if self.rows:
                        self.status_var.set("预览已更新")
        except queue.Empty:
            pass
        self.root.after(20 if not self.ui_events.empty() else 50, self.poll_ui_events)

    def finish_rename(self):
        self.is_running = False
        self.set_running_state(False)
        attempted = sum(row["last_status"] is not None for row in self.rows)
        succeeded = sum(
            row["last_status"] in {RENAMED, RENAMED_MARKER_KEPT} for row in self.rows
        )
        failed = attempted - succeeded
        self.update_queue_count()
        self.status_var.set(f"处理完成 · 成功 {succeeded} 个 · 失败 {failed} 个")
        messagebox.showinfo("提取标签完成", f"成功：{succeeded} 个\n失败：{failed} 个")

    def on_close(self):
        if self.is_running and not messagebox.askyesno(
            "退出程序", "当前正在提取标签。退出后会停止处理剩余文件夹，确定吗？"
        ):
            return
        self.cancel_requested = True
        self.root.destroy()
