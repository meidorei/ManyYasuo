"""Run with uv run python tests/ui_accessibility_smoke.py on Windows."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import customtkinter as ctk
from PIL import ImageTk
from ui_theme import (
    BG, CONTROL_BORDER, FOCUS, MUTED, PRIMARY, SURFACE_3, TEXT,
    SoftButton, SoftEntry, SoftProgressBar, SoftScrollableFrame,
)


def contrast(a, b):
    def luminance(color):
        rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
    low, high = sorted((luminance(a), luminance(b)))
    return (high + .05) / (low + .05)


def main():
    for surface in (BG, SURFACE_3):
        for text in (TEXT, MUTED, PRIMARY):
            assert contrast(text, surface) >= 4.5, (text, surface)
        for outline in (CONTROL_BORDER, FOCUS):
            assert contrast(outline, surface) >= 3, (outline, surface)
    assert contrast("#FFFFFF", PRIMARY) >= 4.5

    ctk.set_appearance_mode("light")
    root = ctk.CTk(fg_color=BG)
    root.title("控件无障碍验证")
    calls = []
    button = SoftButton(root, text="验证操作", command=lambda: calls.append(True), fg_color=BG)
    button.pack()
    entry = SoftEntry(root)
    entry.pack()
    progress = SoftProgressBar(root, height=26, fg_color=BG, progress_color=PRIMARY)
    progress.pack()
    scrolling = SoftScrollableFrame(root, width=240, height=120, fg_color=BG)
    scrolling.pack()
    for index in range(40):
        ctk.CTkLabel(scrolling, text=f"滚动项目 {index}").pack()
    root.update()
    try:
        scrollbar = scrolling._scrollbar
        scrolling._parent_canvas.yview_moveto(0)
        root.update()
        assert scrollbar._canvas.find_withtag("soft_thumb")
        scrollbar._canvas.event_generate("<Button-1>", x=13, y=22)
        scrollbar._canvas.event_generate("<B1-Motion>", x=13, y=80)
        scrollbar._canvas.event_generate("<ButtonRelease-1>", x=13, y=80)
        root.update()
        assert scrolling._parent_canvas.yview()[0] > 0, "thumb drag must scroll content"
        scrolling._parent_canvas.yview_moveto(1)
        root.update()
        assert scrolling._parent_canvas.yview()[1] == 1
        # Compare the visible raster to the real Tk label, including redraws
        # while hovered (the original text-background rectangle regression).
        button.configure(hover_color="#E4DFD5")
        for event in ("<Enter>", "<Leave>", "<Enter>"):
            button._canvas.event_generate(event)
            root.update()
            button.configure(text="验证操作")
            raster = ImageTk.getimage(button._soft_photo)
            pixel = raster.getpixel((raster.width // 2, raster.height // 2))[:3]
            label_rgb = tuple(v // 257 for v in button.winfo_rgb(button._text_label.cget("bg")))
            assert pixel == label_rgb, (event, pixel, label_rgb)
        button._on_leave()
        button._press()
        assert button._sunken
        button._keyboard_release()
        assert len(calls) == 1 and not button._sunken
        button.set_selected(True)
        button._release()
        assert button._sunken
        button.set_selected(False)
        button.configure(state="disabled")
        button._press()
        button._keyboard_release()
        assert len(calls) == 1 and not button._sunken
        button.configure(state="normal")
        button._canvas.event_generate("<FocusIn>")
        assert button._soft_focused
        button._canvas.event_generate("<FocusOut>")
        assert not button._soft_focused
        entry.insert(0, "可复制的只读内容")
        entry.configure(state="readonly")
        entry._set_focus(True)
        assert entry.get() == "可复制的只读内容" and entry._soft_focused
        entry_raster = ImageTk.getimage(entry._soft_photo)
        center = entry_raster.getpixel((entry_raster.width // 2, entry_raster.height // 2))[:3]
        assert center == tuple(v // 257 for v in entry.winfo_rgb(entry._entry.cget("bg")))
        fill = tuple(int(PRIMARY[i:i + 2], 16) for i in (1, 3, 5))
        for value in (0, .5, 1, 0):
            progress.set(value)
            pixels = ImageTk.getimage(progress._soft_photo).convert("RGB")
            assert (fill in set(pixels.get_flattened_data())) == (value > 0)
        assert button.cget("height") >= 44
    finally:
        root.destroy()
    print("Contrast, focus, keyboard activation, selection, disabled and readonly: OK")


if __name__ == "__main__":
    main()
