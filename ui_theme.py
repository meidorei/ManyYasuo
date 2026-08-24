"""Shared semantic UI tokens and small helpers for the ManyYasuo desktop app."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

APP_FONT = "Microsoft YaHei UI"

# Surfaces
BG = "#F6F8FC"
SURFACE = "#FFFFFF"
SURFACE_2 = "#FBFCFE"
SURFACE_3 = "#EEF2F7"
SURFACE_ALT = "#F4F7FB"

# Text and borders
TEXT = "#172033"
MUTED = "#526178"
BORDER = "#D9E2EC"

# Brand and interaction
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
FOCUS = "#2563EB"

# Feedback
SUCCESS = "#15803D"
WARNING = "#B45309"
DANGER = "#DC2626"
SUCCESS_BG = "#DCFCE7"
WARNING_BG = "#FEF3C7"
WARNING_HOVER = "#FDE68A"
DANGER_BG = "#FEE2E2"
DANGER_HOVER = "#FECACA"

# Secondary controls
SECONDARY_BG = "#E8EEF6"
SECONDARY_HOVER = "#DCE6F1"
SECONDARY_TEXT = "#334155"

# Navigation
NAV_BG = "#F8FAFC"
NAV_HOVER = "#EEF3F8"
NAV_TEXT = MUTED
NAV_ACTIVE_BG = "#E8F0FE"
NAV_ACTIVE_TEXT = PRIMARY_HOVER
NAV_BORDER = BORDER
WORKSPACE = BG
ACCENT = PRIMARY


class ToolTip:
    """Lightweight hover tooltip for controls that need a descriptive label."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)
        widget.bind("<ButtonPress>", self.hide)

    def show(self, _event=None):
        if self.tip is not None or not self.text:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty() - 26}")
        label = ctk.CTkLabel(
            tip,
            text=self.text,
            fg_color=TEXT,
            text_color=SURFACE,
            corner_radius=6,
            font=ctk.CTkFont(family=APP_FONT, size=12),
        )
        label.pack(padx=1, pady=1)
        self.tip = tip

    def hide(self, _event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def apply_focus_style(button: ctk.CTkButton, border_width: int = 2):
    """Add a visible keyboard focus ring to a button without changing its default look."""
    try:
        default_width = int(button.cget("border_width"))
    except Exception:
        default_width = 0
    button.configure(border_width=default_width)
    button.bind(
        "<FocusIn>",
        lambda _event: button.configure(border_width=border_width, border_color=FOCUS),
    )
    button.bind(
        "<FocusOut>",
        lambda _event: button.configure(border_width=default_width),
    )


def secondary_button(parent, text, command, width=88, height=40):
    button = ctk.CTkButton(
        parent,
        text=text,
        command=command,
        width=width,
        height=height,
        corner_radius=9,
        fg_color=SECONDARY_BG,
        hover_color=SECONDARY_HOVER,
        text_color=SECONDARY_TEXT,
        font=ctk.CTkFont(family=APP_FONT, size=13, weight="bold"),
    )
    apply_focus_style(button)
    return button


def remove_button(parent, command, tooltip: str = "移除", width: int = 44, height: int = 44):
    button = ctk.CTkButton(
        parent,
        text="×",
        command=command,
        width=width,
        height=height,
        corner_radius=9,
        fg_color="transparent",
        hover_color=DANGER_BG,
        text_color=MUTED,
        font=ctk.CTkFont(family=APP_FONT, size=17),
    )
    ToolTip(button, tooltip)
    apply_focus_style(button)
    return button