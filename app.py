"""ManyYasuo unified compression, extraction and renaming workstation."""

from __future__ import annotations

import os
import sys
from tkinter import messagebox

import customtkinter as ctk
from tkinterdnd2 import DND_FILES
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
        self.root.title(APP_NAME)
        self.root.geometry("1360x820")
        self.root.minsize(1080, 680)
        self.root.configure(fg_color=WORKSPACE)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        self.store = ConfigStore()
        self.coordinator = JobCoordinator()
        self.current_page = "compression"
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.hosts: dict[str, PageHost] = {}
        self.pages = {}

        self._build_navigation()
        self._build_pages()
        self.coordinator.subscribe(self._on_job_change)
        self.show_page("compression")

        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.handle_drop)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_navigation(self):
        rail = ctk.CTkFrame(
            self.root,
            width=156,
            corner_radius=0,
            fg_color=NAV_BG,
            border_width=1,
            border_color=NAV_BORDER,
        )
        rail.grid(row=0, column=0, sticky="nsew")
        rail.grid_propagate(False)
        rail.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            rail,
            text="压缩",
            text_color="#172033",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(24, 22))

        items = [
            ("compression", "压缩"),
            ("preprocessing", "加入标签"),
            ("extraction", "解压"),
            ("renaming", "提取标签"),
        ]
        for index, (key, title) in enumerate(items, start=1):
            button = ctk.CTkButton(
                rail,
                text=title,
                command=lambda name=key: self.show_page(name),
                height=44,
                corner_radius=9,
                anchor="w",
                fg_color="transparent",
                hover_color=NAV_HOVER,
                text_color=NAV_TEXT,
                font=ctk.CTkFont(size=14, weight="bold"),
            )
            apply_focus_style(button)
            button.grid(row=index, column=0, sticky="ew", padx=12, pady=3)
            self.nav_buttons[key] = button

        status = ctk.CTkFrame(
            rail,
            fg_color="#FFFFFF",
            border_width=1,
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
            host.grid(row=0, column=1, sticky="nsew")
            self.hosts[key] = host

        self.pages = {
            "compression": CoordinatedCompression(self.hosts["compression"], self.store, self.coordinator),
            "preprocessing": PreprocessApp(self.hosts["preprocessing"], self.store, self.coordinator),
            "extraction": CoordinatedExtractor(self.hosts["extraction"], self.store, self.coordinator),
            "renaming": CoordinatedRenamer(self.hosts["renaming"], self.store, self.coordinator),
        }

    def show_page(self, name: str):
        self.current_page = name
        for key, host in self.hosts.items():
            if key == name:
                host.grid()
                host.tkraise()
            else:
                host.grid_remove()
        for key, button in self.nav_buttons.items():
            active = key == name
            button.configure(
                fg_color=NAV_ACTIVE_BG if active else "transparent",
                text_color=NAV_ACTIVE_TEXT if active else NAV_TEXT,
            )

    def handle_drop(self, event):
        page = self.pages[self.current_page]
        page.handle_drop(event)
        return "break"

    def _on_job_change(self, owner: str | None):
        buttons = {
            "compression": self.pages["compression"].btn_compress,
            "preprocessing": self.pages["preprocessing"].btn_start,
            "extraction": self.pages["extraction"].btn_start,
            "renaming": self.pages["renaming"].btn_start,
        }
        for button in buttons.values():
            button.configure(state="disabled" if owner else "normal")
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
