"""Optional 100-row / 20,000-file responsiveness smoke test."""

import tempfile
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
from core import create_tag_marker, detect_compression_tag


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        folders = []
        for index in range(100):
            folder = root / f"source-{index:03d}"
            folder.mkdir()
            folders.append(str(folder))
        for index in range(20_000):
            (Path(folders[index % 100]) / f"item-{index:05d}.bin").write_bytes(b"x")

        window = app.UnifiedWindow()
        window.withdraw()
        workstation = app.WorkstationApp(window)
        workstation.show_page("preprocessing")
        page = workstation.pages["preprocessing"]
        window.update()

        added_at = time.perf_counter()
        page.add_paths(folders)
        workstation.show_page("compression")
        workstation.show_page("preprocessing")

        deadline = time.monotonic() + 60
        max_update = 0.0
        while len(page.rows) < 100 or any(row["size_text"] == "计算中…" for row in page.rows):
            started = time.perf_counter()
            window.update()
            max_update = max(max_update, time.perf_counter() - started)
            if time.monotonic() >= deadline:
                raise AssertionError("folder size scan timed out")
            time.sleep(0.01)

        add_seconds = time.perf_counter() - added_at
        assert len(page.rows) == 100
        assert max_update < 0.5, f"Tk update stalled for {max_update:.3f}s"

        for index, folder in enumerate(folders):
            create_tag_marker(folder, "AAA_", f"标签{index}")
        detected_at = time.perf_counter()
        with ThreadPoolExecutor(max_workers=2) as executor:
            detections = list(executor.map(lambda path: detect_compression_tag(path, "AAA_"), folders))
        detection_seconds = time.perf_counter() - detected_at
        assert all(item.found and item.origin == "marker" for item in detections)
        assert detection_seconds < 10, f"tag detection took {detection_seconds:.2f}s"
        page.shutdown()
        window.destroy()
        print(
            f"100 rows / 20,000 files: OK "
            f"(add {add_seconds:.2f}s, max UI tick {max_update:.3f}s, tag scan {detection_seconds:.2f}s)"
        )


if __name__ == "__main__":
    main()
