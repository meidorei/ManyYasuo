"""Batch folder preprocessing page for the unified desktop app."""

from __future__ import annotations

import os
import queue
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config_store import ConfigStore
from core import (
    CANCELLED,
    FAILED,
    INVALID,
    PREPROCESSED,
    PreprocessOptions,
    analyze_explicit_preprocess_batch,
    analyze_preprocess_batch,
    detect_compression_tag,
    execute_explicit_preprocess_batch,
    resolve_preprocess_targets,
    folder_size,
    format_size,
    path_sort_key,
)
from job_coordinator import JobCoordinator


from ui_theme import (
    SoftCard, SoftButton, SoftEntry, SoftProgressBar, SoftScrollableFrame,
    SCROLLBAR, SCROLLBAR_HOVER,
    BG,
    BORDER,
    DANGER,
    DANGER_BG,
    FOCUS,
    MUTED,
    PRIMARY,
    PRIMARY_HOVER,
    SECONDARY_BG,
    SECONDARY_HOVER,
    SECONDARY_TEXT,
    SUCCESS,
    SUCCESS_BG,
    SURFACE,
    SURFACE_2,
    SURFACE_3,
    SURFACE_ALT,
    TEXT,
    WARNING,
    WARNING_BG,
    WARNING_HOVER,
    ToolTip,
    apply_focus_style,
    secondary_button as theme_secondary_button,
)


class PreprocessApp:
    owner_name = "preprocessing"

    def __init__(self, root, store: ConfigStore, coordinator: JobCoordinator):
        self.root = root
        self.store = store
        self.coordinator = coordinator
        self.config = store.section("preprocessing")
        self.rows: list[dict] = []
        self.row_by_id: dict[int, dict] = {}
        self.next_row_id = 1
        self.pending_render: set[int] = set()
        self.render_after_id = None
        self.pending_paths: list[str] = []
        self.pending_keys: set[str] = set()
        self.adding_paths = False
        self.ui_events: queue.Queue = queue.Queue(maxsize=512)
        self.scan_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="folder-size")
        self.scan_futures: list[Future] = []
        self.tag_scan_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preprocess-tag")
        self.tag_scan_tokens: set[int] = set()
        self.next_tag_scan_token = 1
        self.tag_rescan_after = None
        self.scan_generation = 0
        self.is_running = False
        self.cancel_requested = False
        self.mutation_started = False
        self.current_process = None
        self._build_ui()
        self._poll_ui_events()

    @staticmethod
    def _card(parent, **kwargs):
        return SoftCard(
            parent,
            fg_color=SURFACE,
            border_width=1,
            border_color=BORDER,
            corner_radius=12,
            **kwargs,
        )

    @staticmethod
    def _secondary_button(parent, text, command, width=88):
        return theme_secondary_button(parent, text, command, width=width, height=40)

    def _build_ui(self):
        self.root.configure(fg_color=BG)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        settings = self._card(self.root)
        settings.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        settings.grid_columnconfigure(1, weight=1)

        title_row = ctk.CTkFrame(settings, fg_color="transparent")
        title_row.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(15, 10))
        ctk.CTkLabel(title_row, text="加入标签", text_color=TEXT, font=ctk.CTkFont(size=17, weight="bold")).pack(side="left")
        self._secondary_button(title_row, "选择文件夹", self.choose_folder, 104).pack(side="right", padx=(0, 8))

        controls = ctk.CTkFrame(settings, fg_color=SURFACE_2, corner_radius=10)
        controls.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 16))

        ctk.CTkLabel(controls, text="起始编号", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(14, 7), pady=11)
        self.counter_var = ctk.StringVar(value="0001")
        self.counter_var.trace_add("write", self.revalidate)
        self.entry_counter = SoftEntry(
            controls,
            textvariable=self.counter_var,
            width=88,
            height=36,
            justify="center",
            fg_color=SURFACE_3,
            border_color=BORDER,
        )
        self.entry_counter.pack(side="left", pady=9)
        self.btn_detect_number = self._secondary_button(controls, "提取最小编号", self.detect_min_number, 112)
        self.btn_detect_number.pack(side="left", padx=8, pady=9)

        ctk.CTkLabel(controls, text="文件名前缀", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(12, 7))
        self.entry_prefix = SoftEntry(controls, width=140, height=36, fg_color=SURFACE_3, border_color=BORDER)
        self.entry_prefix.pack(side="left")
        self.entry_prefix.insert(0, self.config.get("prefix", "HGLIST-"))
        self.entry_prefix.bind("<KeyRelease>", self.revalidate)

        ctk.CTkLabel(controls, text="标签前缀", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(12, 7))
        self.entry_tag_prefix = SoftEntry(controls, width=120, height=36, fg_color=SURFACE_3, border_color=BORDER)
        self.entry_tag_prefix.pack(side="left")
        self.entry_tag_prefix.insert(0, self.config.get("tag_prefix", "AAA_"))
        self.entry_tag_prefix.bind("<KeyRelease>", self.schedule_tag_rescan)
        self._secondary_button(controls, "保存设置", self.save_config, 88).pack(side="right", padx=10, pady=9)

        listing = self._card(self.root)
        listing.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        listing.grid_columnconfigure(0, weight=1)
        listing.grid_rowconfigure(2, weight=1)

        heading = ctk.CTkFrame(listing, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        ctk.CTkLabel(heading, text="文件夹列表", text_color=TEXT, font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        self.count_label = ctk.CTkLabel(heading, text="0 个文件夹", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold"))
        self.count_label.pack(side="right")
        self._secondary_button(heading, "清空", self.clear_rows, 66).pack(side="right", padx=(0, 8))

        columns = ctk.CTkFrame(listing, fg_color="transparent")
        columns.grid(row=1, column=0, sticky="ew", padx=29, pady=(0, 5))
        columns.grid_columnconfigure(0, weight=3)
        columns.grid_columnconfigure(1, weight=3)
        for column, text, width in ((0, "当前名称", 0), (1, "目标名称", 0), (2, "编号", 112), (3, "大小（点击复制）", 104), (4, "标签", 150), (5, "状态", 106)):
            ctk.CTkLabel(columns, text=text, width=width, anchor="w", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=column, sticky="ew", padx=6)

        self.list_frame = SoftScrollableFrame(
            listing,
            fg_color=SURFACE_ALT,
            corner_radius=10,
            scrollbar_button_color=SCROLLBAR,
            scrollbar_button_hover_color=SCROLLBAR_HOVER,
        )
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.empty_label = ctk.CTkLabel(self.list_frame, text="拖入文件夹，或点击“选择文件夹”", text_color=MUTED, font=ctk.CTkFont(size=14, weight="bold"))
        self.empty_label.pack(expand=True, pady=90)

        dock = self._card(self.root, height=78)
        dock.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        dock.grid_columnconfigure(0, weight=1)
        progress_box = ctk.CTkFrame(dock, fg_color="transparent")
        progress_box.grid(row=0, column=0, sticky="ew", padx=18, pady=14)
        progress_box.grid_columnconfigure(0, weight=1)
        status_row = ctk.CTkFrame(progress_box, fg_color="transparent")
        status_row.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.status_var = ctk.StringVar(value="等待开始")
        ctk.CTkLabel(status_row, textvariable=self.status_var, text_color=TEXT, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.total_label = ctk.CTkLabel(status_row, text="0%", text_color=PRIMARY, font=ctk.CTkFont(size=12, weight="bold"))
        self.total_label.pack(side="right")
        self.total_progress = SoftProgressBar(progress_box, height=26, corner_radius=13, fg_color=SURFACE, progress_color=PRIMARY)
        self.total_progress.grid(row=1, column=0, sticky="ew")
        self.total_progress.set(0)

        self.btn_cancel = SoftButton(
            dock,
            text="取消",
            command=self.cancel,
            state="disabled",
            width=112,
            height=46,
            corner_radius=11,
            fg_color=SURFACE,
            hover_color=SECONDARY_HOVER,
            text_color=DANGER,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.btn_cancel.grid(row=0, column=1, padx=(8, 10), pady=14)
        self.btn_start = SoftButton(
            dock,
            text="加入标签",
            command=self.start,
            width=168,
            height=46,
            corner_radius=11,
            fg_color=SURFACE,
            hover_color=SECONDARY_HOVER,
            text_color=PRIMARY,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.btn_start.grid(row=0, column=2, padx=(0, 18), pady=14)
        self._update_empty_state()

    def options(self) -> PreprocessOptions:
        return PreprocessOptions(
            file_prefix=self.entry_prefix.get(),
            tag_prefix=self.entry_tag_prefix.get().strip(),
            start_number=self.counter_var.get(),
            unwrap_nested=True,
        )

    def _analyze_current_batch(self):
        sources = [row["path"] for row in self.rows]
        tags = [row["tag_var"].get() for row in self.rows]
        targets = resolve_preprocess_targets(sources, sources, tags)
        return analyze_explicit_preprocess_batch(sources, targets)

    def save_config(self):
        try:
            self.store.update_section(
                "preprocessing",
                {"prefix": self.entry_prefix.get(), "tag_prefix": self.entry_tag_prefix.get().strip()},
            )
            messagebox.showinfo("已保存", "预处理设置已保存")
        except OSError as error:
            messagebox.showerror("无法保存", str(error))

    def choose_folder(self):
        path = filedialog.askdirectory(title="选择一个文件夹（可继续添加）")
        if path:
            self.add_paths([path])

    def handle_drop(self, event):
        self.add_paths(self.root.tk.splitlist(event.data))

    def add_paths(self, paths):
        if self.is_running:
            return
        known = {os.path.normcase(row["path"]) for row in self.rows} | self.pending_keys
        for raw in paths:
            path = os.path.abspath(os.path.normpath(raw))
            key = os.path.normcase(path)
            if key in known or not os.path.isdir(path):
                continue
            known.add(key)
            self.pending_keys.add(key)
            self.pending_paths.append(path)
        if self.pending_paths and not self.adding_paths:
            self.adding_paths = True
            self.btn_start.configure(state="disabled")
            self.status_var.set("正在添加文件夹")
            self.root.after(1, self._drain_pending_paths)

    def _drain_pending_paths(self):
        deadline = time.perf_counter() + 0.008
        added = 0
        while self.pending_paths and (added == 0 or (added < 4 and time.perf_counter() < deadline)):
            path = self.pending_paths.pop(0)
            self.pending_keys.discard(os.path.normcase(path))
            if os.path.isdir(path) and not any(os.path.normcase(row["path"]) == os.path.normcase(path) for row in self.rows):
                self._add_row(path)
                added += 1
        if self.pending_paths:
            self.root.after(2, self._drain_pending_paths)
        else:
            self.adding_paths = False
            self._sort_rows()
            self._schedule_render()
            self.revalidate()
            self._update_empty_state()
            self.status_var.set("等待开始")
            self._refresh_start_state()

    def _schedule_render(self):
        if self.render_after_id is not None:
            return
        self.render_after_id = self.root.after(500, self._render_pending_chunk)

    def _render_pending_chunk(self):
        self.render_after_id = None
        try:
            alive = bool(self.root.winfo_exists())
        except Exception:
            alive = False
        if not alive:
            return
        batch = [row for row in self.rows if row["id"] in self.pending_render and "frame" not in row][:2]
        for row in batch:
            self.pending_render.discard(row["id"])
            self._render_row(row)
        if any(row["id"] in self.pending_render for row in self.rows):
            self.render_after_id = self.root.after(500, self._render_pending_chunk)

    def _sort_rows(self):
        if not self.rows:
            return
        self.rows.sort(key=lambda row: path_sort_key(row["path"]))
        rendered = [row for row in self.rows if "frame" in row]
        for row in rendered:
            row["frame"].pack_forget()
        for row in rendered:
            row["frame"].pack(fill="x", pady=(0, 8))
        if self.pending_render:
            self._schedule_render()

    def _add_row(self, path: str):
        row_id = self.next_row_id
        self.next_row_id += 1
        row = {
            "id": row_id,
            "path": path,
            "original_name": Path(path).name,
            "target_name": "—",
            "target_color": MUTED,
            "size_text": "计算中…",
            "size_bytes": None,
            "tag_var": ctk.StringVar(master=self.root, value=""),
            "status_text": "待处理",
            "status_color": MUTED,
            "result_status": None,
            "expected_number_name": "",
            "tag_edited": False,
            "detected_tag": "",
            "preserved_name": "",
            "scan_token": 0,
        }
        self.rows.append(row)
        self.row_by_id[row_id] = row
        self._schedule_size(row)
        self.schedule_tag_detection(row)
        if len(self.rows) <= 3:
            self._render_row(row)
        else:
            self.pending_render.add(row_id)

    def _render_row(self, row: dict):
        frame = ctk.CTkFrame(
            self.list_frame,
            fg_color=SURFACE,
            border_width=1,
            border_color=BORDER,
            corner_radius=9,
        )
        frame.pack(fill="x", pady=(0, 8))
        frame.grid_columnconfigure(0, weight=3)
        frame.grid_columnconfigure(1, weight=3)
        current = ctk.CTkLabel(frame, text=row["original_name"], anchor="w", text_color=TEXT, font=ctk.CTkFont(size=13, weight="bold"))
        current.grid(row=0, column=0, sticky="ew", padx=(12, 6), pady=10)
        target = ctk.CTkLabel(frame, text=row["target_name"], anchor="w", text_color=row["target_color"], font=ctk.CTkFont(size=13, weight="bold"))
        target.grid(row=0, column=1, sticky="ew", padx=6)
        number = SoftButton(
            frame,
            text="检查编号",
            width=112,
            height=40,
            command=lambda item=row["id"]: self._do_fix_number(item),
            fg_color=WARNING_BG,
            hover_color=WARNING_HOVER,
            text_color=WARNING,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        apply_focus_style(number)
        number.grid(row=0, column=2, padx=6, pady=8)
        size_ready = row["size_bytes"] is not None
        size = SoftButton(
            frame,
            text=row["size_text"],
            width=104,
            height=40,
            anchor="w",
            command=lambda item=row["id"]: self.copy_size(item),
            state="normal" if size_ready else "disabled",
            fg_color="transparent",
            hover_color=SECONDARY_BG,
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        )
        ToolTip(size, "点击复制")
        apply_focus_style(size)
        size.grid(row=0, column=3, padx=6, pady=8)
        tag = SoftEntry(frame, textvariable=row["tag_var"], width=150, height=36, placeholder_text="可选", fg_color=SURFACE, border_color=BORDER)
        tag.grid(row=0, column=4, padx=6, pady=8)
        tag.bind("<KeyRelease>", lambda _event, item=row["id"]: self._mark_tag_edited(item))
        status = ctk.CTkLabel(frame, text=row["status_text"], width=106, anchor="w", text_color=row["status_color"], font=ctk.CTkFont(size=12, weight="bold"))
        status.grid(row=0, column=5, padx=6, pady=8)
        remove = SoftButton(
            frame,
            text="×",
            width=44,
            height=44,
            command=lambda item=row["id"]: self.remove_row(item),
            fg_color="transparent",
            hover_color=DANGER_BG,
            text_color=MUTED,
            font=ctk.CTkFont(size=17),
        )
        ToolTip(remove, "移除")
        apply_focus_style(remove)
        remove.grid(row=0, column=6, padx=(2, 9), pady=6)
        if self.is_running:
            number.configure(state="disabled")
            remove.configure(state="disabled")
        self.empty_label.pack_forget()
        row.update({
            "frame": frame,
            "current_label": current,
            "target_label": target,
            "number_button": number,
            "size_label": size,
            "tag_entry": tag,
            "status_label": status,
            "remove_button": remove,
        })

    def _update_empty_state(self):
        self.count_label.configure(text=f"{len(self.rows)} 个文件夹")
        if self.rows:
            self.empty_label.pack_forget()
        else:
            self.empty_label.pack(expand=True, pady=90)

    def remove_row(self, row_id: int):
        if self.is_running:
            return
        row = self.row_by_id.pop(row_id, None)
        if not row:
            return
        self.tag_scan_tokens.discard(row.get("scan_token", 0))
        self.pending_render.discard(row_id)
        frame = row.get("frame")
        if frame is not None:
            frame.destroy()
        self.rows.remove(row)
        self.revalidate()
        self._update_empty_state()

    def clear_rows(self):
        if self.is_running:
            return
        self.scan_generation += 1
        self.pending_paths.clear()
        self.pending_keys.clear()
        self.adding_paths = False
        self.pending_render.clear()
        if self.render_after_id is not None:
            try:
                self.root.after_cancel(self.render_after_id)
            except Exception:
                pass
            self.render_after_id = None
        for row in self.rows:
            frame = row.get("frame")
            if frame is not None:
                frame.destroy()
        self.rows.clear()
        self.row_by_id.clear()
        self.tag_scan_tokens.clear()
        self.revalidate()
        self._update_empty_state()

    def detect_min_number(self):
        matches = [numbers[-1] for row in self.rows if (numbers := re.findall(r"\d+", row["original_name"]))]
        if matches:
            self.counter_var.set(min(matches, key=int))

    def _do_fix_number(self, row_id: int):
        if self.is_running or self.adding_paths:
            return
        row = self.row_by_id.get(row_id)
        if not row:
            return
        target_name = row.get("expected_number_name", "")
        if not target_name or row["original_name"] == target_name:
            return
        target = os.path.join(os.path.dirname(row["path"]), target_name)
        if os.path.exists(target):
            self.status_var.set(f"编号冲突：{target_name}")
            messagebox.showerror("名称冲突", f"目标文件夹已存在：\n{target}")
            return
        try:
            os.rename(row["path"], target)
        except OSError as error:
            self.status_var.set(f"修改编号失败：{error}")
            messagebox.showerror("修改编号失败", str(error))
            return
        row["path"] = target
        row["original_name"] = target_name
        if "current_label" in row:
            row["current_label"].configure(text=target_name)
        self.status_var.set(f"已改为 {target_name}")
        self.revalidate()

    def copy_size(self, row_id: int):
        row = self.row_by_id.get(row_id)
        if not row or row["size_bytes"] is None:
            return
        value = row["size_text"]
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self.root.update_idletasks()
        except Exception:
            return
        self.status_var.set(f"已复制大小：{value}")
        button = row.get("size_label")
        if button is not None:
            button.configure(text="已复制", text_color=SUCCESS, fg_color=SUCCESS_BG)

            def restore():
                current = self.row_by_id.get(row_id)
                if current and current.get("size_label") is button:
                    button.configure(text=current["size_text"], text_color=MUTED, fg_color="transparent")

            self.root.after(1200, restore)

    def revalidate(self, *_):
        if not hasattr(self, "entry_prefix"):
            return
        batch = self._analyze_current_batch()
        try:
            raw = self.counter_var.get()
            start = int(raw)
            padding = len(raw)
        except ValueError:
            start = None
            padding = 0
        prefix = self.entry_prefix.get()
        for index, (row, preview) in enumerate(zip(self.rows, batch.previews)):
            row["target_name"] = preview.target.name if preview.target else "—"
            if start is not None:
                expected = f"{prefix}{str(start + index).zfill(padding)}"
                row["expected_number_name"] = expected
                if "number_button" in row:
                    correct = row["original_name"] == expected
                    row["number_button"].configure(
                        text="✓ 编号正确" if correct else f"改为 {expected}",
                        state="disabled" if correct else "normal",
                        fg_color=SUCCESS_BG if correct else WARNING_BG,
                        text_color=SUCCESS if correct else WARNING,
                    )
            if preview.status == INVALID:
                row["status_text"] = "需检查"
                row["status_color"] = DANGER
                row["target_color"] = DANGER
            elif not self.is_running:
                if row["result_status"] is None:
                    row["status_text"] = "待处理"
                    row["status_color"] = MUTED
                row["target_color"] = TEXT
            if "target_label" in row:
                row["target_label"].configure(text=row["target_name"], text_color=row["target_color"])
            if "status_label" in row:
                row["status_label"].configure(text=row["status_text"], text_color=row["status_color"])
        self.count_label.configure(text=f"{len(self.rows)} 个文件夹")
        self._refresh_start_state()

    def _schedule_size(self, row: dict):
        generation = self.scan_generation
        row_id = row["id"]
        path = row["path"]

        def cancelled():
            return generation != self.scan_generation

        def scan():
            try:
                value = folder_size(path, cancelled)
            except InterruptedError:
                return
            except OSError:
                self._put_event(("size", row_id, generation, None))
            else:
                self._put_event(("size", row_id, generation, value))

        self.scan_futures.append(self.scan_executor.submit(scan))

    def _refresh_start_state(self):
        if not hasattr(self, "btn_start"):
            return
        disabled = (
            self.adding_paths
            or self.is_running
            or bool(self.tag_scan_tokens)
            or bool(self.coordinator.owner)
        )
        self.btn_start.configure(state="disabled" if disabled else "normal")

    def schedule_tag_detection(self, row):
        if self.is_running or row.get("id") not in self.row_by_id:
            return
        if not row.get("tag_edited") and row.get("detected_tag") and row["tag_var"].get() == row["detected_tag"]:
            row["tag_var"].set("")
        row["detected_tag"] = ""
        row["preserved_name"] = ""
        token = self.next_tag_scan_token
        self.next_tag_scan_token += 1
        row["scan_token"] = token
        self.tag_scan_tokens.add(token)
        self._refresh_start_state()
        path = row["path"]
        prefix = self.entry_tag_prefix.get().strip()
        row_id = row["id"]

        def scan():
            try:
                detection = detect_compression_tag(path, prefix)
            except OSError:
                detection = None
            try:
                self.ui_events.put(("tag_detected", row_id, token, detection), timeout=0.5)
            except queue.Full:
                self.tag_scan_tokens.discard(token)

        self.tag_scan_executor.submit(scan)

    def schedule_tag_rescan(self, *_):
        if self.tag_rescan_after is not None:
            try:
                self.root.after_cancel(self.tag_rescan_after)
            except Exception:
                pass
        self.tag_rescan_after = self.root.after(300, self.rescan_tags)

    def rescan_tags(self):
        self.tag_rescan_after = None
        for row in list(self.rows):
            self.schedule_tag_detection(row)

    def _mark_tag_edited(self, row_id):
        row = self.row_by_id.get(row_id)
        if not row:
            return
        if row.get("scan_token"):
            self.tag_scan_tokens.discard(row["scan_token"])
            row["scan_token"] = 0
        row["tag_edited"] = True
        row["detected_tag"] = ""
        row["preserved_name"] = ""
        self.revalidate()
        self._refresh_start_state()

    def _put_event(self, event):
        try:
            self.ui_events.put(event, timeout=0.5)
        except queue.Full:
            pass

    def start(self):
        if self.adding_paths:
            self.status_var.set("正在添加文件夹，请稍候")
            messagebox.showinfo("正在添加", "请等待文件夹添加完成。")
            return
        if self.tag_scan_tokens:
            self.status_var.set("正在识别标签，请稍候")
            messagebox.showinfo("正在识别", "请等待标签识别完成。")
            return
        batch = self._analyze_current_batch()
        if not batch.valid:
            message = batch.error or "请检查文件夹列表"
            self.status_var.set(message)
            messagebox.showerror("无法开始", message)
            self.revalidate()
            return
        if not self.coordinator.try_acquire(self.owner_name):
            self.status_var.set("已有任务运行，请稍候")
            messagebox.showinfo("已有任务运行", "请等待当前模块完成或取消后再开始加入标签。")
            return
        self.is_running = True
        self.cancel_requested = False
        self.mutation_started = False
        self.scan_generation += 1
        self.btn_start.configure(state="disabled", text="正在加入标签…")
        self.btn_cancel.configure(state="normal")
        self.status_var.set("正在停止大小扫描")
        self.total_progress.set(0)
        self.total_label.configure(text="0%")
        for row in self.rows:
            row["result_status"] = None
            row["status_text"] = "等待开始"
            row["status_color"] = MUTED
            if "remove_button" in row:
                row["remove_button"].configure(state="disabled")
            if "number_button" in row:
                row["number_button"].configure(state="disabled")
            if "status_label" in row:
                row["status_label"].configure(text="等待开始", text_color=MUTED)
        snapshot_rows = list(self.rows)
        sources = [row["path"] for row in snapshot_rows]
        targets = [str(preview.target) for preview in batch.previews if preview.target is not None]
        tags = [row["tag_var"].get() for row in snapshot_rows]
        options = self.options()
        futures = list(self.scan_futures)
        threading.Thread(
            target=self._worker,
            args=(snapshot_rows, sources, targets, tags, options, futures),
            daemon=True,
        ).start()

    def _worker(self, rows, sources, targets, tags, options, futures):
        wait(futures)
        if self.cancel_requested:
            results = execute_explicit_preprocess_batch(
                sources, targets, tags, options.tag_prefix, unwrap_nested=options.unwrap_nested, cancelled=lambda: True
            )
        else:
            self.mutation_started = True
            self._put_event(("phase", "正在加入标签"))
            results = execute_explicit_preprocess_batch(
                sources, targets, tags, options.tag_prefix, unwrap_nested=options.unwrap_nested
            )
        total = max(1, len(results))
        for index, (row, result) in enumerate(zip(rows, results), start=1):
            self._put_event(("result", row["id"], result))
            self._put_event(("progress", index / total))
        self._put_event(("finished",))

    def cancel(self):
        if not self.is_running:
            return
        if self.mutation_started:
            self.status_var.set("正在安全完成文件操作")
            self.btn_cancel.configure(state="disabled")
            return
        self.cancel_requested = True
        self.scan_generation += 1
        self.status_var.set("正在取消…")
        self.btn_cancel.configure(state="disabled")

    def _poll_ui_events(self):
        processed = 0
        deadline = time.perf_counter() + 0.008
        try:
            while processed < 32 and time.perf_counter() < deadline:
                event = self.ui_events.get_nowait()
                processed += 1
                kind = event[0]
                if kind == "tag_detected":
                    _, row_id, token, detection = event
                    self.tag_scan_tokens.discard(token)
                    row = self.row_by_id.get(row_id)
                    if row and row.get("scan_token") == token and not row.get("tag_edited"):
                        if detection is not None and detection.found:
                            chosen = detection.marker_tag.strip() or detection.name_tag.strip()
                            row["tag_var"].set(chosen)
                            row["detected_tag"] = chosen
                            row["preserved_name"] = detection.preserved_name
                        else:
                            row["detected_tag"] = ""
                            row["preserved_name"] = ""
                        self.revalidate()
                    self._refresh_start_state()
                elif kind == "size":
                    _, row_id, generation, value = event
                    row = self.row_by_id.get(row_id)
                    if row and generation == self.scan_generation:
                        row["size_bytes"] = value
                        row["size_text"] = format_size(value) if value is not None else "无法读取"
                        if "size_label" in row:
                            row["size_label"].configure(
                                text=row["size_text"],
                                state="normal" if value is not None else "disabled",
                            )
                elif kind == "phase":
                    self.status_var.set(event[1])
                elif kind == "progress":
                    value = event[1]
                    self.total_progress.set(value)
                    self.total_label.configure(text=f"{value * 100:.0f}%")
                elif kind == "result":
                    _, row_id, result = event
                    row = self.row_by_id.get(row_id)
                    if row:
                        row["result_status"] = result.status
                        color = SUCCESS if result.status == PREPROCESSED else MUTED if result.status == CANCELLED else DANGER
                        row["status_text"] = result.message
                        row["status_color"] = color
                        if "status_label" in row:
                            row["status_label"].configure(text=result.message, text_color=color)
                        if result.target and result.target.exists():
                            row["path"] = str(result.target)
                            row["original_name"] = result.target.name
                            if "current_label" in row:
                                row["current_label"].configure(text=result.target.name)
                elif kind == "finished":
                    self.finish()
        except queue.Empty:
            pass
        try:
            self.root.after(20 if not self.ui_events.empty() else 50, self._poll_ui_events)
        except Exception:
            pass

    def finish(self):
        was_cancelled = self.cancel_requested and not self.mutation_started
        self.is_running = False
        self.mutation_started = False
        self.btn_start.configure(text="加入标签")
        self.btn_cancel.configure(state="disabled")
        self.status_var.set("已取消" if was_cancelled else "加入标签完成")
        for row in self.rows:
            if "remove_button" in row:
                row["remove_button"].configure(state="normal")
        self.coordinator.release(self.owner_name)
        self.revalidate()
        self.scan_generation += 1
        self.scan_futures = [future for future in self.scan_futures if not future.done()]
        for row in self.rows:
            row["size_text"] = "计算中…"
            row["size_bytes"] = None
            if "size_label" in row:
                row["size_label"].configure(text="计算中…", state="disabled")
            self._schedule_size(row)
        self.rescan_tags()

    def shutdown(self):
        self.cancel_requested = True
        self.scan_generation += 1
        self.tag_scan_tokens.clear()
        if self.tag_rescan_after is not None:
            try:
                self.root.after_cancel(self.tag_rescan_after)
            except Exception:
                pass
            self.tag_rescan_after = None
        if self.render_after_id is not None:
            try:
                self.root.after_cancel(self.render_after_id)
            except Exception:
                pass
            self.render_after_id = None
        self.pending_render.clear()
        self.scan_executor.shutdown(wait=False, cancel_futures=True)
        self.tag_scan_executor.shutdown(wait=False, cancel_futures=True)


__all__ = ["PreprocessApp"]
