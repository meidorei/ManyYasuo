"""Exercise tkdnd's Windows enter/drop dispatch on actual list canvases."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def main():
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory) / "拖放 文件夹 {测试}"
        folder.mkdir()
        window = app.UnifiedWindow()
        workstation = app.WorkstationApp(window)
        try:
            window.update()
            for name, attribute in (("compression", "frame_left"), ("preprocessing", "list_frame"),
                                    ("extraction", "queue_frame"), ("renaming", "queue_frame")):
                workstation.show_page(name)
                window.update()
                page = workstation.pages[name]
                received = []
                original = page.handle_drop
                page.handle_drop = lambda event: received.extend(window.tk.splitlist(event.data))
                area = getattr(page, attribute)
                try:
                    for target in (area._parent_canvas, area):
                        x, y = target.winfo_rootx() + 12, target.winfo_rooty() + 12
                        action = window.tk.call("tkdnd::olednd::HandleDragEnter", str(target),
                                                ("CF_HDROP",), ("copy",), (), x, y, ("CF_HDROP",))
                        assert action == "copy", (name, action)
                        action = window.tk.call("tkdnd::olednd::HandleDrop", str(target), (),
                                                x, y, "CF_HDROP", (str(folder),))
                        assert action == "copy" and received[-1] == str(folder), (name, action, received)
                        window.tk.call("tkdnd::olednd::HandleDragLeave", str(target))
                finally:
                    page.handle_drop = original
            window.withdraw()
            window.update()
            window.deiconify()
            window.update()
            workstation.show_page("compression")
            class Drop:
                data = window.tk.call("list", str(folder))
            assert workstation.handle_drop(Drop()) == "copy"
            assert workstation.pages["compression"].left_rows[0]["path"] == str(folder)
        finally:
            workstation.on_close()
    print("Windows tkdnd dispatch: four pages, nested canvases, Unicode/spaces/braces, remapping: OK")


if __name__ == "__main__":
    main()
