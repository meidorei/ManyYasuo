"""Shared semantic UI tokens and small helpers for the ManyYasuo desktop app."""
from __future__ import annotations

import tkinter as tk
import sys
from functools import lru_cache
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

import customtkinter as ctk

APP_FONT = "Microsoft YaHei UI"

# Surfaces
BG = "#F4F1EA"
SURFACE = "#F4F1EA"
SURFACE_2 = SURFACE
SURFACE_3 = SURFACE
SURFACE_ALT = SURFACE
SHADOW = "#D1CABE"
HIGHLIGHT = "#FFFFFF"

# Text and borders
TEXT = "#2E3A4B"
MUTED = "#4D5D70"
BORDER = "#B6AFA3"
CONTROL_BORDER = "#737E8E"

# Brand and interaction
PRIMARY = "#406592"
PRIMARY_HOVER = "#365980"
FOCUS = "#456D9E"

# Feedback
SUCCESS = "#15803D"
WARNING = "#B45309"
DANGER = "#AD403C"
SUCCESS_BG = SURFACE
WARNING_BG = SURFACE
WARNING_HOVER = SURFACE
DANGER_BG = SURFACE
DANGER_HOVER = SURFACE

# Secondary controls
SECONDARY_BG = SURFACE
SECONDARY_HOVER = SURFACE
SECONDARY_TEXT = TEXT

# Navigation
NAV_BG = SURFACE
NAV_HOVER = SECONDARY_HOVER
NAV_TEXT = MUTED
NAV_ACTIVE_BG = SURFACE
NAV_ACTIVE_TEXT = PRIMARY_HOVER
NAV_BORDER = BORDER
WORKSPACE = BG
ACCENT = PRIMARY
SCROLLBAR = "#B6AFA3"
SCROLLBAR_HOVER = "#807A70"


def style_window_caption(window):
    """Tint Windows 11 native chrome without replacing its accessible controls."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class HighContrast(ctypes.Structure):
        _fields_ = [("size", wintypes.UINT), ("flags", wintypes.DWORD),
                    ("scheme", wintypes.LPWSTR)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    contrast = HighContrast()
    contrast.size = ctypes.sizeof(contrast)
    if user32.SystemParametersInfoW(0x0042, contrast.size, ctypes.byref(contrast), 0) and contrast.flags & 1:
        return False
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    hwnd = user32.GetAncestor(window.winfo_id(), 2)
    set_attribute = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute
    set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    set_attribute.restype = ctypes.c_long
    results = []
    for attribute, color in ((35, BG), (36, TEXT), (34, BORDER)):
        value = wintypes.DWORD(int(color[1:3], 16) | int(color[3:5], 16) << 8 | int(color[5:7], 16) << 16)
        results.append(set_attribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0)
    return all(results)


@lru_cache(maxsize=32)
def _surface_image(width, height, radius, background, face, sunken, scale):
    """Supersample curved edges; retain the final image at physical DPI size."""
    tile = max(24, round(radius + 12 * scale))
    if width > tile * 2 and height > tile * 2:
        # Nine-slice the constant centre and straight edges. Blurring an entire
        # tall list at 3x resolution would monopolise Tk during bulk inserts.
        source = _surface_image(tile * 2, tile * 2, radius, background, face, sunken, scale)
        result = Image.new("RGB", (width, height), face)
        for x, sx in ((0, 0), (width - tile, tile)):
            for y, sy in ((0, 0), (height - tile, tile)):
                result.paste(source.crop((sx, sy, sx + tile, sy + tile)), (x, y))
        for y, sy in ((0, 0), (height - tile, tile)):
            result.paste(source.crop((tile, sy, tile + 1, sy + tile)).resize((width - 2 * tile, tile)), (tile, y))
        for x, sx in ((0, 0), (width - tile, tile)):
            result.paste(source.crop((sx, tile, sx + tile, tile + 1)).resize((tile, height - 2 * tile)), (x, tile))
        return result
    quality = 3
    return _render_surface(width * quality, height * quality, radius * quality,
                           background, face, sunken, scale * quality).resize(
                               (width, height), Image.Resampling.LANCZOS)


def _render_surface(width, height, radius, background, face, sunken, scale):
    """Rasterize real blurred light/shadow masks, rather than bevel outlines."""
    size = (width, height)
    pad = max(3, round(6 * scale))
    radius = max(4, radius - pad)
    box = (pad, pad, width-pad-1, height-pad-1)
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius, fill=255)
    result = Image.new("RGB", size, background)
    blur = max(1, 3 * scale)
    shift = max(1, round(3 * scale))
    def shifted(dx, dy):
        layer = Image.new("L", size)
        layer.paste(mask, (dx, dy))
        return layer
    if not sunken:
        for dx, color in ((-shift, HIGHLIGHT), (shift, SHADOW)):
            shade = shifted(dx, dx).filter(ImageFilter.GaussianBlur(blur))
            result.paste(color, (0, 0), shade)
        result.paste(face, (0, 0), mask)
    else:
        result.paste(face, (0, 0), mask)
        for dx, color in ((shift, SHADOW), (-shift, HIGHLIGHT)):
            shade = ImageChops.subtract(mask, shifted(dx, dx))
            shade = shade.filter(ImageFilter.GaussianBlur(blur))
            shade = ImageChops.multiply(shade, mask)
            result.paste(color, (0, 0), shade)
        # Native text widgets cannot be transparent. Keep the recessed centre
        # flat, with the shadow confined to the rim instead of under the text.
        inner = pad + max(2, round(4 * scale))
        if width > 2 * inner and height > 2 * inner:
            ImageDraw.Draw(result).rounded_rectangle(
                (inner, inner, width - inner - 1, height - inner - 1),
                radius=max(2, radius - (inner - pad)), fill=face,
            )
    return result


class _SoftEdges:
    """DPI-aware soft surfaces, keeping native controls and their events."""

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        self._canvas.delete("soft_surface")
        face = self._apply_appearance_mode(self._surface_color())
        if face == "transparent":
            if not getattr(self, "_soft_focused", False):
                return
            face = self._apply_appearance_mode(self._bg_color)
        w = max(20, round(self._apply_widget_scaling(self._current_width)))
        h = max(20, round(self._apply_widget_scaling(self._current_height)))
        background = self._apply_appearance_mode(self._bg_color)
        rendered = _surface_image(w, h, round(self._apply_widget_scaling(self._corner_radius)),
                                  background, face, getattr(self, "_sunken", False),
                                  self._apply_widget_scaling(1))
        # Draw boundaries on the final surface: CTk's underlying border is
        # otherwise covered by the raster, including the keyboard focus ring.
        focused = getattr(self, "_soft_focused", False)
        hovered = (getattr(self, "_mouse_inside", False) and
                   getattr(self, "_hover", False) and getattr(self, "_state", None) == "normal")
        outlined = isinstance(self, SoftEntry) or getattr(self, "_selected", False) or hovered
        if focused or outlined:
            rendered = rendered.copy()
            inset = max(3, round(self._apply_widget_scaling(6)))
            ImageDraw.Draw(rendered).rounded_rectangle(
                (inset, inset, w - inset - 1, h - inset - 1),
                radius=max(4, round(self._apply_widget_scaling(self._corner_radius)) - inset),
                outline=FOCUS if focused else CONTROL_BORDER,
                width=max(1, round(self._apply_widget_scaling(2 if focused else 1))),
            )
        self._soft_photo = ImageTk.PhotoImage(rendered, master=self)
        self._canvas.create_image(0, 0, anchor="nw", image=self._soft_photo, tags="soft_surface")
        # Keep the native focus ring above the background image.
        if getattr(self, "_border_width", 0) > 0 and getattr(self, "_border_color", None) == FOCUS:
            self._canvas.tag_raise("border_parts")

    def _surface_color(self):
        return self._fg_color


class SoftCard(_SoftEdges, ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        kwargs.update(corner_radius=24, border_width=0)
        super().__init__(master, **kwargs)


class SoftEntry(_SoftEdges, ctk.CTkEntry):
    _sunken = True

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        if hasattr(self, "_entry"):
            self._entry.grid_configure(padx=round(self._apply_widget_scaling(14)),
                                       pady=round(self._apply_widget_scaling(12)))
            face = self._apply_appearance_mode(self._fg_color)
            self._entry.configure(bg=face, readonlybackground=face, disabledbackground=face)

    def __init__(self, master, **kwargs):
        kwargs.update(corner_radius=14, border_color=CONTROL_BORDER, border_width=0)
        kwargs["height"] = max(44, kwargs.get("height", 44))
        kwargs.setdefault("fg_color", SURFACE_2)
        kwargs.setdefault("text_color", TEXT)
        kwargs.setdefault("placeholder_text_color", MUTED)
        super().__init__(master, **kwargs)
        self.bind("<FocusIn>", lambda event: self._set_focus(True))
        self.bind("<FocusOut>", lambda event: self._set_focus(False))

    def _set_focus(self, focused):
        self._soft_focused = focused
        self._draw()


class SoftProgressBar(ctk.CTkProgressBar):
    """A recessed horizontal determinate track; zero has no phantom fill."""

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        self._canvas.delete("soft_progress")
        if self._mode != "determinate" or self._orientation != "horizontal":
            return
        scale = self._apply_widget_scaling(1)
        w = max(24, round(self._apply_widget_scaling(self._current_width)))
        h = max(24, round(self._apply_widget_scaling(self._current_height)))
        face = self._apply_appearance_mode(self._fg_color)
        background = self._apply_appearance_mode(self._bg_color)
        rendered = _surface_image(w, h, h // 2, background, face, True, scale).copy()
        inset = max(7, round(8 * scale))
        draw = ImageDraw.Draw(rendered)
        if self._determinate_value > 0:
            right = inset + max(1, round((w - 2 * inset - 1) * self._determinate_value))
            draw.rounded_rectangle((inset, inset, right, h - inset - 1),
                                   radius=min((right - inset) // 2, (h - 2 * inset) // 2),
                                   fill=self._apply_appearance_mode(self._progress_color))
        self._soft_photo = ImageTk.PhotoImage(rendered, master=self)
        self._canvas.create_image(0, 0, anchor="nw", image=self._soft_photo, tags="soft_progress")


class SoftScrollbar(ctk.CTkScrollbar):
    """Keep CTk scroll geometry and input handling, replace only the surface."""

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        self._canvas.delete("soft_scroll")
        scale = self._apply_widget_scaling(1)
        w = max(24, round(self._apply_widget_scaling(self._current_width)))
        h = max(24, round(self._apply_widget_scaling(self._current_height)))
        vertical = self._orientation == "vertical"
        background = self._apply_appearance_mode(self._bg_color)
        track = _surface_image(w, h, 12 * scale, background, SURFACE, True, scale)
        self._track_photo = ImageTk.PhotoImage(track, master=self)
        self._canvas.create_image(0, 0, anchor="nw", image=self._track_photo,
                                  tags=("soft_scroll", "soft_track"))
        self._canvas.tag_bind("soft_track", "<Button-1>", self._clicked)
        if self._end_value - self._start_value >= .999:
            return
        first, last = self._get_scrollbar_values_for_minimum_pixel_size()
        length = h if vertical else w
        spacing = round(self._apply_widget_scaling(self._border_spacing))
        start = round(spacing + (length - 2 * spacing) * first)
        end = round(spacing + (length - 2 * spacing) * last)
        tw, th = (w, max(24, end - start)) if vertical else (max(24, end - start), h)
        face = SECONDARY_HOVER if self._hover_state else SURFACE
        thumb = _surface_image(tw, th, 12 * scale, SURFACE, face, False, scale).copy()
        # A small, high-contrast grip identifies the movable surface.
        draw = ImageDraw.Draw(thumb)
        for offset in (-3, 0, 3):
            if vertical:
                draw.line((tw // 2 - 2, th // 2 + offset, tw // 2 + 2, th // 2 + offset), fill=CONTROL_BORDER)
            else:
                draw.line((tw // 2 + offset, th // 2 - 2, tw // 2 + offset, th // 2 + 2), fill=CONTROL_BORDER)
        self._thumb_photo = ImageTk.PhotoImage(thumb, master=self)
        self._canvas.create_image(0 if vertical else start, start if vertical else 0,
                                  anchor="nw", image=self._thumb_photo,
                                  tags=("soft_scroll", "soft_thumb"))
        self._canvas.tag_bind("soft_thumb", "<Button-1>", self._clicked_scrollbar)

    def _on_enter(self, event=None):
        super()._on_enter(event)
        self._draw()

    def _on_leave(self, event=None):
        super()._on_leave(event)
        self._draw()


class SoftScrollableFrame(ctk.CTkScrollableFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        old = self._scrollbar
        vertical = self._orientation == "vertical"
        self._scrollbar = SoftScrollbar(
            self._parent_frame, orientation=self._orientation,
            command=self._parent_canvas.yview if vertical else self._parent_canvas.xview,
            width=26 if vertical else 200, height=200 if vertical else 26,
            minimum_pixel_length=44, border_spacing=6, fg_color=SURFACE,
        )
        self._parent_canvas.configure(**{
            "yscrollcommand" if vertical else "xscrollcommand": self._scrollbar.set,
        })
        old.destroy()
        self._create_grid()


class SoftButton(_SoftEdges, ctk.CTkButton):
    _sunken = False
    _selected = False

    def _surface_color(self):
        if getattr(self, "_mouse_inside", False) and self._hover and self._state == "normal":
            return self._hover_color or self._fg_color
        return self._fg_color

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        face = self._surface_color()
        if face == "transparent":
            face = self._bg_color
        for label in (getattr(self, "_text_label", None), getattr(self, "_image_label", None)):
            if label is not None:
                label.configure(bg=self._apply_appearance_mode(face))

    def _on_enter(self, event=None):
        super()._on_enter(event)
        self._draw()

    def _on_leave(self, event=None):
        super()._on_leave(event)
        self._draw()

    def __init__(self, master, **kwargs):
        kwargs["corner_radius"] = 14
        kwargs["height"] = max(44, kwargs.get("height", 44))
        super().__init__(master, **kwargs)
        self._canvas.configure(takefocus=1)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Leave>", self._release)
        self.bind("<KeyPress-Return>", self._press)
        self.bind("<KeyPress-space>", self._press)
        self.bind("<KeyRelease-Return>", self._keyboard_release)
        self.bind("<KeyRelease-space>", self._keyboard_release)
        self.bind("<FocusOut>", self._release)
        apply_focus_style(self)

    def _keyboard_release(self, _event=None):
        engaged = self._sunken
        self._release()
        if engaged:
            self.invoke()
        return "break"

    def _press(self, _event=None):
        if self.cget("state") != "disabled":
            self._sunken = True
            self._draw()

    def _release(self, _event=None):
        self._sunken = self._selected
        self._draw()

    def set_selected(self, selected):
        self._selected = bool(selected)
        self._release()


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
        text = self.text() if callable(self.text) else self.text
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty() - 26}")
        label = ctk.CTkLabel(
            tip,
            text=text,
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
    if getattr(button, "_focus_style_installed", False):
        return
    button._focus_style_installed = True
    if isinstance(button, SoftButton):
        def set_focus(focused):
            button._soft_focused = focused
            button._draw()
        button.bind("<FocusIn>", lambda event: set_focus(True))
        button.bind("<FocusOut>", lambda event: set_focus(False))
        return
    try:
        default_width = int(button.cget("border_width"))
    except Exception:
        default_width = 0
    default_color = button.cget("border_color")
    button.configure(border_width=default_width)
    button.bind(
        "<FocusIn>",
        lambda _event: button.configure(border_width=border_width, border_color=FOCUS),
    )
    button.bind(
        "<FocusOut>",
        lambda _event: button.configure(border_width=default_width, border_color=default_color),
    )


def secondary_button(parent, text, command, width=88, height=40):
    button = SoftButton(
        parent,
        text=text,
        command=command,
        width=width,
        height=height,
        corner_radius=14,
        fg_color=SECONDARY_BG,
        hover_color=SECONDARY_HOVER,
        text_color=SECONDARY_TEXT,
        font=ctk.CTkFont(family=APP_FONT, size=13, weight="bold"),
    )
    apply_focus_style(button)
    return button


def remove_button(parent, command, tooltip: str = "移除", width: int = 44, height: int = 44):
    button = SoftButton(
        parent,
        text="×",
        command=command,
        width=width,
        height=height,
        corner_radius=14,
        fg_color="transparent",
        hover_color=DANGER_BG,
        text_color=MUTED,
        font=ctk.CTkFont(family=APP_FONT, size=17),
    )
    ToolTip(button, tooltip)
    apply_focus_style(button)
    return button
