"""ManyYasuo unified compression, extraction and renaming workstation."""

from __future__ import annotations

import os
import sys
from tkinter import messagebox

import customtkinter as ctk
from tkinterdnd2 import COPY, DND_FILES, REFUSE_DROP
from tkinterdnd2.TkinterDnD import DnDWrapper, _require

from config_store import ConfigStore
from job_coordinator import JobCoordinator
from main import PipelineApp
from preprocessing import PreprocessApp
from 批量解压.main import ExtractorApp
from 重命名.main import RenamerApp


APP_NAME = "压缩"

from ui_theme import (
    APP_FONT,
    SoftButton, SoftCard, TEXT, SURFACE,
    ACCENT,
    NAV_ACTIVE_BG,
    NAV_ACTIVE_TEXT,
    NAV_BG,
    NAV_BORDER,
    NAV_HOVER,
    NAV_TEXT,
    SUCCESS,
    WORKSPACE,
    apply_focus_style,
    style_window_caption, MUTED,
)


class UnifiedWindow(ctk.CTk, DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = _require(self)


class PageHost(ctk.CTkFrame):
    """A frame that exposes harmless window methods expected by legacy pages."""

    def title(self, _value=None):
        return self.winfo_toplevel().title() if _value is None else None

    def geometry(self, _value=None):
        return ""

    def minsize(self, *_args):
        return None

    def protocol(self, *_args):
        return None

    def drop_target_register(self, *_args):
        return None

    def dnd_bind(self, *_args):
        return None


class CoordinatedCompression(PipelineApp):
    owner_name = "compression"

    def __init__(self, root, store: ConfigStore, coordinator: JobCoordinator):
        self.store = store
        self.coordinator = coordinator
        super().__init__(root)

    def load_config(self):
        return self.store.section("compression")

    def do_restructure(self):
        if not self.coordinator.try_acquire(self.owner_name):
            messagebox.showinfo("已有任务运行", "请等待当前任务完成后再加入队列。")
            return
        try:
            super().do_restructure()
        except Exception as error:
            self.preparing_queue = False
            self._restore_enqueue_controls()
            messagebox.showerror("无法加入队列", str(error))
        finally:
            if not self.preparing_queue:
                self.coordinator.release(self.owner_name)
                self.refresh_enqueue_state()

    def _restore_enqueue_controls(self):
        for row in self.left_rows:
            for key in ("btn_fix", "btn_remove", "entry"):
                row[key].configure(state="normal")

    def finish_enqueue(self, rows, results, tags):
        try:
            super().finish_enqueue(rows, results, tags)
        finally:
            self.preparing_queue = False
            try:
                self._restore_enqueue_controls()
            finally:
                self.coordinator.release(self.owner_name)
                self.refresh_enqueue_state()

    def save_config(self):
        data = {
            "7z_path": self.entry_7z.get().strip(),
            "prefix": self.entry_prefix.get(),
            "tag_prefix": self.entry_tag_prefix.get(),
            "extension": self.entry_ext.get(),
            "lvl": self.combo_lvl.get(),
            "dict": self.combo_dict.get(),
            "word": self.combo_word.get(),
            "solid": self.combo_solid.get(),
            "threads": self.combo_threads.get(),
            "pwd": self.entry_pwd.get(),
            "hide_name": bool(self.var_hide.get()),
        }
        try:
            self.store.update_section("compression", data)
            messagebox.showinfo("已保存", f"压缩设置已保存至\n{self.store.path}")
        except OSError as error:
            messagebox.showerror("无法保存", str(error))

    def do_compress(self):
        if not self.coordinator.try_acquire(self.owner_name):
            messagebox.showinfo("已有任务运行", "请等待当前模块完成或取消后再开始压缩。")
            return
        super().do_compress()
        if not self.is_running:
            self.coordinator.release(self.owner_name)

    def finish_compression(self):
        try:
            super().finish_compression()
        finally:
            self.coordinator.release(self.owner_name)


class CoordinatedExtractor(ExtractorApp):
    owner_name = "extraction"

    def __init__(self, root, store: ConfigStore, coordinator: JobCoordinator):
        self.store = store
        self.coordinator = coordinator
        super().__init__(root)

    def load_config(self):
        return self.store.section("extraction")

    def save_config(self, notify=True):
        data = {
            "7z_path": self.entry_7z.get().strip(),
            "password": self.entry_password.get(),
            "tag_prefix": self.entry_tag_prefix.get(),
            "block_terms": self.entry_block_terms.get(),
            "output_dir": self.entry_output.get().strip(),
        }
        try:
            self.store.update_section("extraction", data)
            if notify:
                messagebox.showinfo("已保存", f"解压设置已保存至\n{self.store.path}")
        except OSError as error:
            messagebox.showerror("无法保存配置", str(error))

    def start_extract(self):
        if not self.coordinator.try_acquire(self.owner_name):
            messagebox.showinfo("已有任务运行", "请等待当前模块完成或取消后再开始解压。")
            return
        super().start_extract()
        if not self.is_running:
            self.coordinator.release(self.owner_name)

    def finish_extract(self):
        try:
            super().finish_extract()
        finally:
            self.coordinator.release(self.owner_name)


class CoordinatedRenamer(RenamerApp):
    owner_name = "renaming"

    def __init__(self, root, store: ConfigStore, coordinator: JobCoordinator):
        self.coordinator = coordinator
        super().__init__(root, config_backend=store)

    def start_rename(self):
        if not self.coordinator.try_acquire(self.owner_name):
            messagebox.showinfo("已有任务运行", "请等待当前模块完成或取消后再开始重命名。")
            return
        super().start_rename()
        if not self.is_running:
            self.coordinator.release(self.owner_name)

    def finish_rename(self):
        try:
            super().finish_rename()
        finally:
            self.coordinator.release(self.owner_name)


class WorkstationApp:
    def __init__(self, root: UnifiedWindow):
        self.root = root
        ctk.set_appearance_mode("light")
        ctk.ThemeManager.theme["CTkFont"]["family"] = APP_FONT
        self.root.title(APP_NAME)
        self.root.geometry("1360x820")
        self.root.minsize(1080, 680)
        self.root.configure(fg_color=WORKSPACE)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        self.store = ConfigStore()
        self.coordinator = JobCoordinator()
        self.current_page = "compression"
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.hosts: dict[str, PageHost] = {}
        self.pages = {}

        self._build_header()
        self._build_navigation()
        self._build_pages()
        self.coordinator.subscribe(self._on_job_change)
        self.show_page("compression")

        self._register_drop_targets()
        self.root.bind("<Map>", self._on_window_map, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(300, lambda: style_window_caption(self.root))

    def _on_window_map(self, event):
        if event.widget is self.root:
            self.root.after_idle(self._register_drop_targets)

    def _register_drop_targets(self):
        # CTk scroll areas have their own native frames/canvases. Register the
        # actual content windows, including after the toplevel is remapped.
        targets = [self.root]
        for page in self.pages.values():
            for attribute in ("frame_left", "frame_right", "list_frame", "queue_frame"):
                area = getattr(page, attribute, None)
                if area is not None:
                    targets.extend((area._parent_frame, area._parent_canvas, area))
        for target in targets:
            target.drop_target_register(DND_FILES)
            # Avoid accumulating registered Tcl callbacks on remapping.
            if not getattr(target, "_workstation_drop_bound", False):
                target.dnd_bind("<<DropEnter>>", lambda event: COPY)
                target.dnd_bind("<<DropPosition>>", lambda event: COPY)
                target.dnd_bind("<<Drop>>", self.handle_drop)
                target._workstation_drop_bound = True

    def _build_header(self):
        header = ctk.CTkFrame(self.root, fg_color=WORKSPACE, corner_radius=0)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=24, pady=(14, 0))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="文件工作台", text_color=TEXT,
                     font=ctk.CTkFont(size=21, weight="bold")).grid(row=0, column=0, padx=(0, 30))
        self.page_heading = ctk.CTkLabel(header, text="批量压缩", text_color=TEXT,
                                        font=ctk.CTkFont(size=18, weight="bold"))
        self.page_heading.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(header, text="批量处理 · 本地执行", text_color=MUTED,
                     font=ctk.CTkFont(size=13)).grid(row=0, column=2)

    def _build_navigation(self):
        rail = ctk.CTkFrame(
            self.root,
            width=172,
            corner_radius=0,
            fg_color=NAV_BG,
            border_width=0,
            border_color=NAV_BORDER,
        )
        rail.grid(row=1, column=0, sticky="nsew")
        rail.grid_propagate(False)
        rail.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            rail,
            text="处理模块",
            text_color=MUTED,
            font=ctk.CTkFont(size=13),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(24, 22))

        items = [
            ("compression", "压缩"),
            ("preprocessing", "加入标签"),
            ("extraction", "解压"),
            ("renaming", "提取标签"),
        ]
        for index, (key, title) in enumerate(items, start=1):
            button = SoftButton(
                rail,
                text=title,
                command=lambda name=key: self.show_page(name),
                height=52,
                corner_radius=9,
                anchor="w",
                fg_color=NAV_BG,
                hover_color=NAV_HOVER,
                text_color=NAV_TEXT,
                font=ctk.CTkFont(size=14, weight="bold"),
            )
            apply_focus_style(button)
            button.grid(row=index, column=0, sticky="ew", padx=12, pady=6)
            self.nav_buttons[key] = button

        status = SoftCard(
            rail,
            fg_color=SURFACE,
            border_width=0,
            border_color=NAV_BORDER,
            corner_radius=10,
        )
        status.grid(row=6, column=0, sticky="ew", padx=12, pady=(12, 16))
        self.activity_dot = ctk.CTkLabel(
            status,
            text="●",
            width=16,
            text_color=SUCCESS,
            font=ctk.CTkFont(size=10),
        )
        self.activity_dot.pack(side="left", padx=(12, 2), pady=10)
        self.activity_text = ctk.CTkLabel(
            status,
            text="空闲",
            text_color=NAV_TEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.activity_text.pack(side="left", pady=10)

    def _build_pages(self):
        for key in ("compression", "preprocessing", "extraction", "renaming"):
            host = PageHost(self.root, fg_color=WORKSPACE, corner_radius=0)
            host.grid(row=1, column=1, sticky="nsew")
            self.hosts[key] = host

        self.pages = {
            "compression": CoordinatedCompression(self.hosts["compression"], self.store, self.coordinator),
            "preprocessing": PreprocessApp(self.hosts["preprocessing"], self.store, self.coordinator),
            "extraction": CoordinatedExtractor(self.hosts["extraction"], self.store, self.coordinator),
            "renaming": CoordinatedRenamer(self.hosts["renaming"], self.store, self.coordinator),
        }

    def show_page(self, name: str):
        self.current_page = name
        labels = {"compression": "批量压缩", "preprocessing": "加入标签",
                  "extraction": "批量解压", "renaming": "提取标签"}
        self.page_heading.configure(text=labels[name])
        self.root.title(f"{labels[name]} · 文件工作台")
        for key, host in self.hosts.items():
            if key == name:
                host.grid()
                host.tkraise()
            else:
                host.grid_remove()
        for key, button in self.nav_buttons.items():
            active = key == name
            button.set_selected(active)
            button.configure(
                fg_color=NAV_ACTIVE_BG if active else NAV_BG,
                text_color=NAV_ACTIVE_TEXT if active else NAV_TEXT,
            )

    def handle_drop(self, event):
        if not getattr(event, "data", None):
            return REFUSE_DROP
        page = self.pages[self.current_page]
        page.handle_drop(event)
        return COPY

    def _on_job_change(self, owner: str | None):
        buttons = {
            "compression": self.pages["compression"].btn_compress,
            "preprocessing": self.pages["preprocessing"].btn_start,
            "extraction": self.pages["extraction"].btn_start,
            "renaming": self.pages["renaming"].btn_start,
        }
        for button in buttons.values():
            button.configure(state="disabled" if owner else "normal")
        self.pages["compression"].refresh_enqueue_state()
        if self.pages["preprocessing"].adding_paths:
            self.pages["preprocessing"].btn_start.configure(state="disabled")

        labels = {"compression": "压缩", "preprocessing": "加入标签", "extraction": "解压", "renaming": "提取标签"}
        if owner:
            self.activity_dot.configure(text_color=ACCENT)
            self.activity_text.configure(text=f"{labels[owner]}中")
        else:
            self.activity_dot.configure(text_color=SUCCESS)
            self.activity_text.configure(text="空闲")

    def on_close(self):
        owner = self.coordinator.owner
        if owner and not messagebox.askyesno("退出程序", "当前仍有任务运行。退出会终止当前任务，确定吗？"):
            return
        for page in self.pages.values():
            page.cancel_requested = True
            shutdown = getattr(page, "shutdown", None)
            if shutdown:
                shutdown()
            process = getattr(page, "current_process", None)
            if process and process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        self.root.destroy()


def run():
    if getattr(sys, "frozen", False):
        os.environ["TKDND_LIBRARY"] = os.path.join(sys._MEIPASS, "tkinterdnd2", "tkdnd")
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    ctk.ThemeManager.theme["CTkFont"]["family"] = APP_FONT
    window = UnifiedWindow()
    WorkstationApp(window)
    window.mainloop()


if __name__ == "__main__":
    run()
