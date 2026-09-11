"""Jieya - batch extractor for archives created by ManyYasuo."""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import DND_FILES
from tkinterdnd2.TkinterDnD import DnDWrapper, _require

from extraction_core import finalize_extraction, path_sort_key, preserve_partial, sanitize_name
from process_utils import iter_decoded_chunks


APP_NAME = "批量解压工作台"
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


class ModernDnDWindow(ctk.CTk, DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = _require(self)


class ExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1120x760")
        self.root.minsize(920, 640)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.rows = []
        self.is_running = False
        self.cancel_requested = False
        self.current_process = None
        self.current_row = None
        self.ui_events = queue.Queue(maxsize=512)
        self.config = self.load_config()

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
    def find_default_7z():
        candidates = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
        ]
        return next((path for path in candidates if os.path.isfile(path)), "")

    def load_config(self):
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save_config(self, notify=True):
        data = {
            "7z_path": self.entry_7z.get().strip(),
            "password": self.entry_password.get(),
            "tag_prefix": self.entry_tag_prefix.get(),
            "block_terms": self.entry_block_terms.get(),
            "output_dir": self.entry_output.get().strip(),
        }
        try:
            CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            if notify:
                messagebox.showinfo("已保存", f"配置已保存至\n{CONFIG_FILE}")
        except OSError as error:
            messagebox.showerror("无法保存配置", str(error))

    def setup_ui(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self.build_config_card()
        self.build_queue_card()
        self.build_action_dock()

    def build_config_card(self):
        card = self.card(self.root)
        card.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        card.grid_columnconfigure(1, weight=1)

        title = ctk.CTkFrame(card, fg_color="transparent")
        title.grid(row=0, column=0, columnspan=8, sticky="ew", padx=18, pady=(14, 8))
        ctk.CTkLabel(title, text="解压配置", text_color=TEXT, font=ctk.CTkFont(size=17, weight="bold")).pack(side="left")
        self.secondary_button(title, "保存设置", self.save_config, 92).pack(side="right")

        ctk.CTkLabel(card, text="7-Zip 路径", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).grid(row=1, column=0, padx=(18, 8), pady=6)
        self.entry_7z = self.entry(card, placeholder="请选择控制台版 7z.exe")
        self.entry_7z.grid(row=1, column=1, columnspan=5, sticky="ew", pady=6)
        self.entry_7z.insert(0, self.config.get("7z_path") or self.find_default_7z())
        self.secondary_button(card, "浏览", self.choose_7z, 72).grid(row=1, column=6, padx=(8, 18), pady=6)

        ctk.CTkLabel(card, text="解压密码", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=0, padx=(18, 8), pady=6)
        self.entry_password = self.entry(card, width=210, show="●")
        self.entry_password.grid(row=2, column=1, sticky="w", pady=6)
        self.entry_password.insert(0, self.config.get("password", ""))
        self.show_password = False
        self.btn_show_password = self.secondary_button(card, "显示", self.toggle_password, 64)
        self.btn_show_password.grid(row=2, column=2, padx=(6, 18), pady=6)

        ctk.CTkLabel(card, text="标签前缀", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=3, padx=(0, 8), pady=6)
        self.entry_tag_prefix = self.entry(card, width=140)
        self.entry_tag_prefix.grid(row=2, column=4, sticky="w", pady=6)
        self.entry_tag_prefix.insert(0, self.config.get("tag_prefix", "AAA_"))

        ctk.CTkLabel(card, text="保护检测词", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=5, padx=(18, 8), pady=6)
        self.entry_block_terms = self.entry(card, width=180)
        self.entry_block_terms.grid(row=2, column=6, sticky="w", padx=(0, 18), pady=6)
        saved_terms = self.config.get("block_terms")
        if not saved_terms:
            legacy_keyword = self.config.get("block_keyword", "")
            saved_terms = "路径, 中文" if "路径" in legacy_keyword and "中文" in legacy_keyword else legacy_keyword
        self.entry_block_terms.insert(0, saved_terms or "路径, 中文")

        ctk.CTkLabel(card, text="统一输出目录", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).grid(row=3, column=0, padx=(18, 8), pady=(6, 16))
        self.entry_output = self.entry(card, placeholder="留空表示解压到每个压缩包所在目录")
        self.entry_output.grid(row=3, column=1, columnspan=5, sticky="ew", pady=(6, 16))
        self.entry_output.insert(0, self.config.get("output_dir", ""))
        self.secondary_button(card, "选择目录", self.choose_output, 92).grid(row=3, column=6, padx=(8, 18), pady=(6, 16))

    @staticmethod
    def entry(parent, width=None, placeholder="", show=""):
        kwargs = {
            "height": 38,
            "corner_radius": 9,
            "fg_color": SURFACE_2,
            "border_color": BORDER,
            "text_color": TEXT,
            "font": ctk.CTkFont(size=13, weight="bold"),
            "placeholder_text": placeholder,
            "show": show,
        }
        if width is not None:
            kwargs["width"] = width
        return SoftEntry(parent, **kwargs)

    def build_queue_card(self):
        card = self.card(self.root)
        card.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(15, 10))
        ctk.CTkLabel(header, text="解压队列", text_color=TEXT, font=ctk.CTkFont(size=17, weight="bold")).pack(side="left")
        self.queue_count = ctk.StringVar(value="队列为空")
        ctk.CTkLabel(header, textvariable=self.queue_count, text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(12, 0))
        self.secondary_button(header, "清空", self.clear_queue, 68).pack(side="right")
        self.secondary_button(header, "选择压缩文件", self.choose_archives, 120).pack(side="right", padx=(0, 8))

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
            text="拖入压缩文件，或点击“选择压缩文件”",
            text_color=MUTED,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.empty_label.pack(expand=True, pady=110)

    def build_action_dock(self):
        dock = SoftCard(self.root, fg_color=SURFACE)
        dock.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        dock.grid_columnconfigure(0, weight=1)

        progress_box = ctk.CTkFrame(dock, fg_color="transparent")
        progress_box.grid(row=0, column=0, sticky="ew", padx=(22, 20), pady=13)
        progress_box.grid_columnconfigure(0, weight=1)
        self.status_var = ctk.StringVar(value="")
        title = ctk.CTkFrame(progress_box, fg_color="transparent")
        title.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title, text="队列总进度", text_color=TEXT, font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkLabel(title, textvariable=self.status_var, text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(10, 0))
        self.total_label = ctk.CTkLabel(progress_box, text="0%", text_color=PRIMARY, font=ctk.CTkFont(size=13, weight="bold"))
        self.total_label.grid(row=0, column=1, sticky="e")
        self.total_progress = SoftProgressBar(progress_box, height=26, corner_radius=13, fg_color=SURFACE, progress_color=PRIMARY)
        self.total_progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        self.total_progress.set(0)

        self.btn_cancel = SoftButton(
            dock,
            text="取消任务",
            command=self.cancel_all,
            state="disabled",
            width=108,
            height=44,
            corner_radius=11,
            fg_color=DANGER_BG,
            hover_color=DANGER_HOVER,
            text_color=DANGER,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        apply_focus_style(self.btn_cancel)
        self.btn_cancel.grid(row=0, column=1, padx=(0, 10))
        self.btn_start = SoftButton(
            dock,
            text="开始解压",
            command=self.start_extract,
            width=170,
            height=48,
            corner_radius=12,
            fg_color=SURFACE,
            hover_color=SECONDARY_HOVER,
            text_color=PRIMARY,
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        apply_focus_style(self.btn_start)
        self.btn_start.grid(row=0, column=2, padx=(0, 22))

    def choose_7z(self):
        path = filedialog.askopenfilename(title="选择 7z.exe", filetypes=[("7-Zip 控制台程序", "7z.exe"), ("可执行文件", "*.exe")])
        if path:
            self.set_entry(self.entry_7z, path)

    def choose_output(self):
        path = filedialog.askdirectory(title="选择统一输出目录")
        if path:
            self.set_entry(self.entry_output, path)

    @staticmethod
    def set_entry(entry, value):
        entry.delete(0, "end")
        entry.insert(0, value)

    def toggle_password(self):
        self.show_password = not self.show_password
        self.entry_password.configure(show="" if self.show_password else "●")
        self.btn_show_password.configure(text="隐藏" if self.show_password else "显示")

    def choose_archives(self):
        paths = filedialog.askopenfilenames(title="选择压缩文件", filetypes=[("所有文件", "*.*")])
        self.add_archives(paths)

    def handle_drop(self, event):
        self.add_archives(self.root.tk.splitlist(event.data))

    def add_archives(self, paths):
        known = {os.path.normcase(row["path"]) for row in self.rows}
        for raw_path in paths:
            path = os.path.abspath(raw_path)
            key = os.path.normcase(path)
            if not os.path.isfile(path) or key in known:
                continue
            self.add_row(path)
            known.add(key)
        self._sort_rows()
        self.update_queue_count()

    def add_row(self, path):
        self.empty_label.pack_forget()
        frame = ctk.CTkFrame(self.queue_frame, fg_color=SURFACE, border_color=BORDER, border_width=1, corner_radius=10)
        frame.pack(fill="x", pady=(0, 8))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text=os.path.basename(path), text_color=TEXT, anchor="w", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=(10, 2))
        ctk.CTkLabel(frame, text=os.path.dirname(path), text_color=MUTED, anchor="w", font=ctk.CTkFont(size=11, weight="bold")).grid(row=1, column=0, sticky="ew", padx=(14, 8), pady=(0, 8))
        status = ctk.CTkLabel(frame, text="等待解压", text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold"))
        status.grid(row=0, column=1, rowspan=2, padx=8)
        remove = SoftButton(frame, text="×", width=44, height=44, corner_radius=9, fg_color="transparent", hover_color=DANGER_BG, text_color=MUTED, font=ctk.CTkFont(size=17))
        ToolTip(remove, "移除")
        apply_focus_style(remove)
        remove.grid(row=0, column=2, rowspan=2, padx=(2, 10))
        progress = ctk.CTkProgressBar(frame, height=7, corner_radius=4, fg_color=SURFACE_3, progress_color=PRIMARY)
        progress.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 11))
        progress.set(0)

        row = {
            "frame": frame,
            "path": path,
            "status": "pending",
            "status_label": status,
            "progress": progress,
            "destination": "",
        }
        remove.configure(command=lambda current=row: self.remove_row(current))
        self.rows.append(row)

    def _sort_rows(self):
        if not self.rows:
            return
        self.rows.sort(key=lambda row: path_sort_key(row["path"]))
        for row in self.rows:
            row["frame"].pack_forget()
        for row in self.rows:
            row["frame"].pack(fill="x", pady=(0, 8))

    def remove_row(self, row):
        if self.is_running and row is self.current_row:
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

    def update_queue_count(self):
        pending = sum(row["status"] in {"pending", "failed"} for row in self.rows)
        self.queue_count.set(f"{len(self.rows)} 个文件 · {pending} 个待处理" if self.rows else "队列为空")
        if not self.rows:
            self.empty_label.pack(expand=True, pady=110)

    def start_extract(self):
        sevenz = self.entry_7z.get().strip()
        if not sevenz or not os.path.isfile(sevenz) or os.path.basename(sevenz).lower() != "7z.exe":
            self.status_var.set("7-Zip 路径错误")
            messagebox.showerror("7-Zip 路径错误", "请选择控制台版 7z.exe，不能使用 7zG.exe。")
            return
        tasks = [row for row in self.rows if row["status"] in {"pending", "failed"}]
        if not tasks:
            self.status_var.set("解压队列为空")
            messagebox.showinfo("队列为空", "请先拖入或选择压缩文件。")
            return

        output = self.entry_output.get().strip()
        if output:
            try:
                Path(output).mkdir(parents=True, exist_ok=True)
            except OSError as error:
                self.status_var.set(f"输出目录不可用：{error}")
                messagebox.showerror("输出目录不可用", str(error))
                return

        self.save_config(notify=False)
        options = {
            "password": self.entry_password.get(),
            "tag_prefix": self.entry_tag_prefix.get(),
            "block_terms": self.entry_block_terms.get().strip(),
            "output_dir": output,
        }
        self.is_running = True
        self.cancel_requested = False
        self.btn_start.configure(state="disabled", text="正在解压…")
        self.btn_cancel.configure(state="normal")
        self.status_var.set("正在处理队列")
        threading.Thread(target=self.extract_worker, args=(tasks, sevenz, options), daemon=True).start()

    def cancel_all(self):
        if self.is_running and messagebox.askyesno("取消队列", "停止当前解压并取消剩余任务吗？已解压的文件不会被删除。"):
            self.cancel_requested = True
            process = self.current_process
            if process and process.poll() is None:
                process.terminate()
            self.status_var.set("正在取消…")

    def extract_worker(self, tasks, sevenz, options):
        total = len(tasks)
        for index, row in enumerate(tasks):
            if self.cancel_requested:
                break
            self.current_row = row
            row["status"] = "running"
            self.ui_events.put(("status", row, "正在解压", PRIMARY, 0))
            archive = Path(row["path"])
            output_parent = Path(options["output_dir"]) if options["output_dir"] else archive.parent
            staging = output_parent / f".jieya_{sanitize_name(archive.stem)}_{uuid.uuid4().hex[:8]}"
            command = [sevenz, "x", str(archive), f"-o{staging}", "-y", "-bsp1", "-bso1", "-bse1"]
            if options["password"]:
                command.append(f"-p{options['password']}")

            output_tail = ""
            try:
                # Keep directory creation inside the task boundary. Otherwise an invalid or
                # read-only output path would terminate the worker and leave the UI "running".
                staging.mkdir(parents=True, exist_ok=False)
                self.current_process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,
                    startupinfo=self.hidden_startupinfo(),
                    creationflags=self.compression_creation_flags(),
                )
                progress_buffer = ""
                last_progress = -1
                last_emit_at = 0.0

                def emit_progress(text):
                    nonlocal last_progress, last_emit_at
                    matches = re.findall(r"(\d{1,3})%", text)
                    if not matches:
                        return
                    value = min(100, int(matches[-1]))
                    now = time.monotonic()
                    if value == last_progress or (value not in {0, 100} and now - last_emit_at < 0.1):
                        return
                    last_progress = value
                    last_emit_at = now
                    self.ui_events.put(("progress", row, value, index, total))

                for chunk in iter_decoded_chunks(self.current_process.stdout):
                    output_tail = (output_tail + chunk)[-1200:]
                    progress_buffer = (progress_buffer + chunk)[-512:]
                    emit_progress(progress_buffer)
                emit_progress(progress_buffer)
                result = self.current_process.wait()

                if self.cancel_requested:
                    row["status"] = "cancelled"
                    kept = preserve_partial(staging, output_parent, archive.stem)
                    text = "已取消" if kept is None else f"已取消 · 部分文件保存在 {kept.name}"
                    self.ui_events.put(("status", row, text, MUTED, 0))
                    break
                if result != 0:
                    row["status"] = "failed"
                    kept = preserve_partial(staging, output_parent, archive.stem)
                    hint = "密码错误或压缩文件损坏"
                    if kept is not None:
                        hint += f" · 部分文件保存在 {kept.name}"
                    self.ui_events.put(("status", row, hint, DANGER, 0))
                else:
                    destination, message = finalize_extraction(staging, output_parent, archive, options)
                    row["destination"] = str(destination)
                    row["status"] = "done"
                    self.ui_events.put(("status", row, message, SUCCESS if "已按标签改名" in message else WARNING, 100))
            except Exception as error:
                row["status"] = "failed"
                kept = preserve_partial(staging, output_parent, archive.stem)
                suffix = "" if kept is None else f" · 部分文件保存在 {kept.name}"
                self.ui_events.put(("status", row, f"失败：{error}{suffix}", DANGER, 0))
            finally:
                self.current_process = None
                self.ui_events.put(("task_done", index + 1, total))

        if self.cancel_requested:
            for row in tasks:
                if row["status"] == "pending":
                    row["status"] = "cancelled"
                    self.ui_events.put(("status", row, "已取消", MUTED, 0))
        self.ui_events.put(("finished",))

    @staticmethod
    def hidden_startupinfo():
        if os.name != "nt":
            return None
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return info

    @staticmethod
    def compression_creation_flags():
        return subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0

    def poll_ui_events(self):
        processed = 0
        deadline = time.perf_counter() + 0.008
        try:
            while processed < 32 and time.perf_counter() < deadline:
                event = self.ui_events.get_nowait()
                processed += 1
                if event[0] == "progress":
                    _, row, value, index, total = event
                    row["progress"].set(value / 100)
                    row["status_label"].configure(text=f"正在解压 {value}%", text_color=PRIMARY)
                    overall = (index + value / 100) / total
                    self.total_progress.set(overall)
                    self.total_label.configure(text=f"{overall * 100:.0f}%")
                elif event[0] == "status":
                    _, row, text, color, value = event
                    row["status_label"].configure(text=text, text_color=color)
                    row["progress"].set(value / 100)
                elif event[0] == "task_done":
                    _, completed, total = event
                    overall = completed / total
                    self.total_progress.set(overall)
                    self.total_label.configure(text=f"{overall * 100:.0f}%")
                elif event[0] == "finished":
                    self.finish_extract()
        except queue.Empty:
            pass
        self.root.after(20 if not self.ui_events.empty() else 50, self.poll_ui_events)

    def finish_extract(self):
        self.is_running = False
        self.current_row = None
        self.btn_start.configure(state="normal", text="开始解压")
        self.btn_cancel.configure(state="disabled")
        done = sum(row["status"] == "done" for row in self.rows)
        failed = sum(row["status"] == "failed" for row in self.rows)
        self.status_var.set("已取消" if self.cancel_requested else "队列已完成")
        self.update_queue_count()
        if not self.cancel_requested:
            messagebox.showinfo("任务结束", f"成功：{done} 个\n失败：{failed} 个")

    def on_close(self):
        if self.is_running and not messagebox.askyesno("退出程序", "当前仍在解压。退出会终止当前任务，确定吗？"):
            return
        self.cancel_requested = True
        process = self.current_process
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        self.root.destroy()


__all__ = ["ExtractorApp"]
