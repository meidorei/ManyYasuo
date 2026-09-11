"""Optional GUI smoke test; run with the project dependencies installed."""

import tempfile
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
from core import READY, create_tag_marker


def wait_for(window, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        window.update()
        time.sleep(0.02)
    return predicate()


def main():
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary) / "HGLIST-0001"
        folder.mkdir()
        create_tag_marker(folder, "AAA_", "联动")

        window = app.UnifiedWindow()
        window.withdraw()
        workstation = app.WorkstationApp(window)
        assert window.title() == "批量压缩 · 文件工作台"
        assert set(workstation.pages) == {"compression", "preprocessing", "extraction", "renaming"}
        assert workstation.nav_buttons["preprocessing"].cget("text") == "加入标签"
        assert workstation.nav_buttons["renaming"].cget("text") == "提取标签"
        preprocess = workstation.pages["preprocessing"]
        preprocess_source = Path(temporary) / "wrapper-source"
        nested = preprocess_source / "nested"
        nested.mkdir(parents=True)
        (nested / "payload.bin").write_bytes(b"1234")
        preprocess.counter_var.set("0010")
        preprocess.add_paths([str(preprocess_source)])
        deadline = time.monotonic() + 5
        while not preprocess.rows and time.monotonic() < deadline:
            window.update()
            time.sleep(0.02)
        while preprocess.rows[0]["size_label"].cget("text") == "计算中…" and time.monotonic() < deadline:
            window.update()
            time.sleep(0.02)
        while preprocess.tag_scan_tokens and time.monotonic() < deadline:
            window.update()
            time.sleep(0.02)
        assert not preprocess.tag_scan_tokens, "preprocessing tag detection timed out"
        assert preprocess.rows[0]["target_label"].cget("text") == preprocess_source.name
        assert preprocess.rows[0]["size_label"].cget("text") != "计算中…"
        displayed_size = preprocess.rows[0]["size_label"].cget("text")
        preprocess.rows[0]["size_label"].invoke()
        window.update()
        assert window.clipboard_get() == displayed_size
        preprocess.rows[0]["tag_entry"].insert(0, "预处理联动")
        preprocess.start()
        deadline = time.monotonic() + 5
        while preprocess.is_running and time.monotonic() < deadline:
            window.update()
            time.sleep(0.02)
        assert not preprocess.is_running, "preprocessing timed out"
        assert preprocess_source.exists(), "preprocessing must preserve names by default"
        assert (preprocess_source / "payload.bin").exists()
        assert (preprocess_source / "AAA_预处理联动").is_dir()

        preprocess.rows[0]["number_button"].invoke()
        window.update()
        processed = Path(temporary) / "HGLIST-0010"
        assert processed.exists(), "per-row number rename failed"
        assert preprocess.rows[0]["original_name"] == "HGLIST-0010"
        assert (processed / "payload.bin").exists()
        assert (processed / "AAA_预处理联动").is_dir()

        renamed = Path(temporary) / "HGLIST-0042 图片 (2)"
        renamed.mkdir()
        manual = Path(temporary) / "HGLIST-0043 自动标签"
        manual.mkdir()
        conflict_source = Path(temporary) / "HGLIST-0044 冲突名称"
        conflict_source.mkdir()
        create_tag_marker(conflict_source, "AAA_", "目录冲突")
        compression_wrapper = Path(temporary) / "wrapper-9000"
        wrapped_payload = compression_wrapper / "one" / "two"
        wrapped_payload.mkdir(parents=True)
        (wrapped_payload / "payload.bin").write_bytes(b"wrapped")
        workstation.show_page("compression")
        compression = workstation.pages["compression"]
        compression.add_paths([
            str(processed),
            str(renamed),
            str(manual),
            str(conflict_source),
            str(compression_wrapper),
        ])
        assert wrapped_payload.is_dir(), "adding a folder must not unwrap it before enqueue"
        assert not (compression_wrapper / "payload.bin").exists()
        manual_row = next(row for row in compression.left_rows if row["original_name"] == manual.name)
        manual_row["entry"].delete(0, "end")
        manual_row["entry"].insert(0, "手动标签")
        compression.mark_tag_edited(manual_row)
        deadline = time.monotonic() + 5
        while compression.tag_scan_tokens and time.monotonic() < deadline:
            window.update()
            time.sleep(0.02)
        assert not compression.tag_scan_tokens, "compression tag detection timed out"
        rows = {row["original_name"]: row for row in compression.left_rows}
        assert rows[processed.name]["entry"].get() == "预处理联动"
        assert rows[processed.name]["expected_target_name"] == "HGLIST-0010"
        assert rows[renamed.name]["entry"].get() == "图片"
        assert rows[renamed.name]["expected_target_name"] == "HGLIST-0042"
        assert manual_row["entry"].get() == "手动标签"
        assert manual_row["expected_target_name"] == "HGLIST-0043"
        conflict_row = next(row for row in compression.left_rows if row["original_name"] == conflict_source.name)
        assert conflict_row["conflict"] is True
        assert conflict_row["entry"].get() == ""
        compression.resolve_tag_conflict(conflict_row, "name")
        assert conflict_row["conflict"] is False
        assert conflict_row["entry"].get() == "冲突名称"
        assert conflict_row["expected_target_name"] == "HGLIST-0044"
        compression.do_restructure()
        deadline = time.monotonic() + 5
        while compression.preparing_queue and time.monotonic() < deadline:
            window.update()
            time.sleep(0.02)
        assert not compression.preparing_queue, "compression queue preparation timed out"
        assert not compression.left_rows
        assert len(compression.right_rows) == 5
        assert (Path(temporary) / "HGLIST-0042" / "AAA_图片").is_dir()
        assert (Path(temporary) / "HGLIST-0043" / "AAA_手动标签").is_dir()
        assert (Path(temporary) / "HGLIST-0044" / "AAA_冲突名称").is_dir()
        assert not (Path(temporary) / "HGLIST-0044" / "AAA_目录冲突").exists()
        assert (compression_wrapper / "payload.bin").read_bytes() == b"wrapped"
        assert not (compression_wrapper / "one").exists()
        workstation.show_page("renaming")

        page = workstation.pages["renaming"]
        page.add_folders([str(processed), str(folder)])
        deadline = time.monotonic() + 5
        while page.preview_running and time.monotonic() < deadline:
            window.update()
            time.sleep(0.02)

        assert not page.preview_running, "background preview timed out"
        assert all(row["preview"].status == READY for row in page.rows)
        targets = {row["preview"].target.name for row in page.rows}
        assert "HGLIST-0001 联动" in targets
        assert "HGLIST-0010 预处理联动" in targets

        # Verify all four modules use the same natural ascending order.
        preprocess.clear_rows()
        compression.clear_left_list()
        workstation.show_page("extraction")
        extraction = workstation.pages["extraction"]
        extraction.clear_queue()
        workstation.show_page("renaming")
        page.clear_queue()

        sort_folders = []
        for name in ("sort-10", "sort-2", "sort-1", "sort-3"):
            path = Path(temporary) / name
            path.mkdir()
            sort_folders.append(path)
        sort_folders = sort_folders[:3]

        preprocess.add_paths([str(path) for path in sort_folders])
        assert wait_for(window, lambda: not preprocess.adding_paths)
        assert not hasattr(preprocess, "previous_page_button")
        assert not hasattr(preprocess, "next_page_button")
        assert not hasattr(preprocess, "page_label")
        assert [Path(row["path"]).name for row in preprocess.rows] == ["sort-1", "sort-2", "sort-10"]
        assert all("frame" in row and row["frame"].winfo_exists() for row in preprocess.rows)
        preprocess.add_paths([str(Path(temporary) / "sort-3")])
        assert wait_for(window, lambda: not preprocess.adding_paths)
        assert [Path(row["path"]).name for row in preprocess.rows] == ["sort-1", "sort-2", "sort-3", "sort-10"]
        preprocess.clear_rows()

        compression.add_paths([str(path) for path in reversed(sort_folders)])
        window.update()
        assert [row["original_name"] for row in compression.left_rows] == ["sort-1", "sort-2", "sort-10"]
        button_x_positions = {row["btn_fix"].winfo_rootx() for row in compression.left_rows}
        assert len(button_x_positions) == 1, f"compression buttons misaligned: {button_x_positions}"
        compression.add_paths([str(Path(temporary) / "sort-3")])
        assert [row["original_name"] for row in compression.left_rows] == ["sort-1", "sort-2", "sort-3", "sort-10"]
        compression.clear_left_list()

        alignment_paths = []
        for name in ("短名", "HGLIST-402-被侵犯的公主", "HGLIST-123456789-" + "很长的文件夹名称" * 8):
            path = Path(temporary) / name
            path.mkdir()
            alignment_paths.append(str(path))
        workstation.show_page("compression")
        compression.add_paths(alignment_paths)
        assert wait_for(window, lambda: not compression.tag_scan_tokens)
        compression.revalidate_left_list()
        for row in compression.left_rows:
            if row["original_name"] != row["expected_target_name"]:
                assert row["btn_fix"].cget("text") == f"改为 {row['expected_target_name']}"
        window.deiconify()
        for size in ("1080x680", "1360x820"):
            window.geometry(size)
            window.update()
            for key in ("lbl_name", "entry", "btn_fix", "btn_remove"):
                bounds = {(row[key].winfo_rootx(), row[key].winfo_width()) for row in compression.left_rows}
                assert len(bounds) == 1, (size, key, bounds)
        compression.clear_left_list()
        window.withdraw()

        archive_names = ("archive-10.7z", "archive-2.7z", "archive-1.7z")
        for name in archive_names + ("archive-3.7z",):
            (Path(temporary) / name).write_bytes(b"x")
        extraction.add_archives([str(Path(temporary) / name) for name in archive_names])
        assert [Path(row["path"]).name for row in extraction.rows] == ["archive-1.7z", "archive-2.7z", "archive-10.7z"]
        extraction.add_archives([str(Path(temporary) / "archive-3.7z")])
        assert [Path(row["path"]).name for row in extraction.rows] == ["archive-1.7z", "archive-2.7z", "archive-3.7z", "archive-10.7z"]
        extraction.clear_queue()

        page.add_folders([str(path) for path in reversed(sort_folders)])
        assert [Path(row["source"]).name for row in page.rows] == ["sort-1", "sort-2", "sort-10"]
        page.add_folders([str(Path(temporary) / "sort-3")])
        assert [Path(row["source"]).name for row in page.rows] == ["sort-1", "sort-2", "sort-3", "sort-10"]

        assert workstation.coordinator.try_acquire("compression")
        assert not workstation.coordinator.try_acquire("extraction")
        assert workstation.coordinator.release("compression")
        preprocess.shutdown()
        compression.shutdown()
        window.destroy()

    print("unified UI and background preview: OK")


if __name__ == "__main__":
    main()
