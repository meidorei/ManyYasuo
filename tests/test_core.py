import tempfile
import unittest
import os
import shutil
from pathlib import Path
from unittest.mock import patch

from core import (
    NO_TAG,
    CANCELLED,
    FAILED,
    INVALID,
    PREPROCESSED,
    READY,
    RENAMED,
    RENAMED_MARKER_KEPT,
    RenameOptions,
    PreprocessOptions,
    analyze_explicit_preprocess_batch,
    analyze_preprocess_batch,
    analyze_folder,
    analyze_folders,
    create_tag_marker,
    remove_empty_tag_marker,
    build_sequence_targets,
    execute_preprocess_batch,
    execute_explicit_preprocess_batch,
    execute_rename,
    finalize_extraction,
    find_blocking_file,
    find_tag_marker,
    detect_compression_tag,
    folder_size,
    format_size,
    natural_name_key,
    path_sort_key,
    parse_block_terms,
    sanitize_name,
    split_numbered_folder_tag,
    unwrap_single_child_chain,
)


class SharedRuleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_compression_marker_is_read_by_renamer(self):
        folder = self.root / "HGLIST-0001"
        folder.mkdir()
        marker = create_tag_marker(folder, "AAA_", "客户:资料")
        self.assertEqual(marker.name, "AAA_客户_资料")
        preview = analyze_folder(folder, RenameOptions(tag_prefix="AAA_"))
        self.assertEqual(preview.status, READY)
        self.assertEqual(preview.target.name, "HGLIST-0001 客户_资料")

    def test_prefixes_are_independent(self):
        folder = self.root / "HGLIST-0001"
        folder.mkdir()
        create_tag_marker(folder, "WRITE_", "客户")
        self.assertEqual(analyze_folder(folder, RenameOptions(tag_prefix="READ_")).status, NO_TAG)

    def test_breadth_first_marker_selection_stops_at_shallowest_level(self):
        folder = self.root / "source"
        (folder / "deep" / "AAA_甲").mkdir(parents=True)
        (folder / "AAA_乙").mkdir()
        self.assertEqual(find_tag_marker(folder, "AAA_").name, "AAA_乙")

    def test_same_level_marker_selection_is_deterministic(self):
        folder = self.root / "source"
        (folder / "B" / "AAA_乙").mkdir(parents=True)
        (folder / "A" / "AAA_甲").mkdir(parents=True)
        self.assertEqual(find_tag_marker(folder, "AAA_").name, "AAA_乙")

    def test_protection_requires_every_term_in_one_direct_file(self):
        folder = self.root / "source"
        folder.mkdir()
        (folder / "路径和中文.txt").write_text("x", encoding="utf-8")
        terms = parse_block_terms("路径, 中文")
        self.assertEqual(find_blocking_file(folder, terms).name, "路径和中文.txt")

    def test_protection_does_not_scan_child_directories(self):
        folder = self.root / "source"
        nested = folder / "one"
        nested.mkdir(parents=True)
        (nested / "路径和中文.txt").write_text("x", encoding="utf-8")
        self.assertIsNone(find_blocking_file(folder, parse_block_terms("路径, 中文")))

    def test_protection_does_not_scan_depth_three(self):
        folder = self.root / "source"
        nested = folder / "one" / "two"
        nested.mkdir(parents=True)
        (nested / "路径和中文.txt").write_text("x", encoding="utf-8")
        self.assertIsNone(find_blocking_file(folder, parse_block_terms("路径, 中文")))

    def test_rename_removes_only_empty_marker(self):
        empty = self.root / "HGLIST-0001"
        empty.mkdir()
        create_tag_marker(empty, "AAA_", "甲")
        result = execute_rename(empty, RenameOptions())
        self.assertEqual(result.status, RENAMED)
        self.assertTrue(result.marker_removed)

        nonempty = self.root / "HGLIST-0002"
        nonempty.mkdir()
        marker = create_tag_marker(nonempty, "AAA_", "乙")
        (marker / "keep.txt").write_text("x", encoding="utf-8")
        result = execute_rename(nonempty, RenameOptions())
        self.assertEqual(result.status, RENAMED_MARKER_KEPT)
        self.assertTrue((result.target / "AAA_乙" / "keep.txt").exists())

    def test_colliding_names_are_reserved_across_queue(self):
        first = self.root / "plain-a"
        second = self.root / "plain-b"
        first.mkdir()
        second.mkdir()
        create_tag_marker(first, "AAA_", "相同")
        create_tag_marker(second, "AAA_", "相同")
        previews = analyze_folders([first, second], RenameOptions())
        self.assertEqual([item.target.name for item in previews], ["相同", "相同 (2)"])

    def test_extractor_uses_the_same_marker_rules(self):
        output = self.root / "output"
        staging = output / ".staging"
        payload = staging / "HGLIST-0008"
        payload.mkdir(parents=True)
        create_tag_marker(payload, "AAA_", "项目")
        destination, message = finalize_extraction(
            staging,
            output,
            self.root / "archive.1",
            {"tag_prefix": "AAA_", "block_terms": "路径, 中文"},
        )
        self.assertEqual(destination.name, "HGLIST-0008 项目")
        self.assertIn("已按标签改名", message)
        self.assertFalse((destination / "AAA_项目").exists())

    def test_renamer_strips_existing_name_tag_before_marker_tag(self):
        folder = self.root / "HGLIST-0042 旧标签"
        folder.mkdir()
        create_tag_marker(folder, "AAA_", "新标签")
        preview = analyze_folder(folder, RenameOptions(tag_prefix="AAA_"))
        self.assertEqual(preview.target.name, "HGLIST-0042 新标签")

    def test_extractor_strips_existing_name_tag_before_marker_tag(self):
        output = self.root / "output"
        staging = output / ".staging"
        payload = staging / "HGLIST-0042 旧标签"
        payload.mkdir(parents=True)
        create_tag_marker(payload, "AAA_", "新标签")
        destination, _ = finalize_extraction(
            staging,
            output,
            self.root / "archive.1",
            {"tag_prefix": "AAA_", "block_terms": "路径, 中文"},
        )
        self.assertEqual(destination.name, "HGLIST-0042 新标签")

    def test_sanitize_windows_names(self):
        self.assertEqual(sanitize_name("CON"), "_CON")
        self.assertEqual(sanitize_name('a:b?c.'), "a_b_c")

    def test_one_hundred_item_queue(self):
        folders = []
        for index in range(100):
            folder = self.root / f"HGLIST-{index:04d}"
            folder.mkdir()
            create_tag_marker(folder, "AAA_", f"标签{index}")
            folders.append(folder)
        previews = analyze_folders(folders, RenameOptions())
        self.assertEqual(len(previews), 100)
        self.assertTrue(all(item.status == READY for item in previews))


class PreprocessCoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def make_folders(self, *names):
        folders = []
        for name in names:
            folder = self.root / name
            folder.mkdir()
            folders.append(folder)
        return folders

    def test_sequence_preserves_input_order_and_padding(self):
        beta, alpha = self.make_folders("beta", "alpha")
        targets = build_sequence_targets([beta, alpha], "HGLIST-", "0098")
        self.assertEqual([item.name for item in targets], ["HGLIST-0098", "HGLIST-0099"])

    def test_numbered_name_tag_parsing_and_collision_suffix(self):
        self.assertEqual(
            split_numbered_folder_tag("HGLIST-0042 图片"),
            ("HGLIST-0042", "图片"),
        )
        self.assertEqual(
            split_numbered_folder_tag("HGLIST-0042 图片 (2)"),
            ("HGLIST-0042", "图片"),
        )
        self.assertEqual(
            split_numbered_folder_tag("HGLIST-345 游戏名2"),
            ("HGLIST-345", "游戏名2"),
        )
        self.assertEqual(split_numbered_folder_tag("HGLIST-0042"), ("HGLIST-0042", ""))
        self.assertEqual(split_numbered_folder_tag("普通文件夹"), ("", ""))

    def test_compression_detection_reads_marker_only(self):
        folder = self.root / "HGLIST-0042"
        folder.mkdir()
        create_tag_marker(folder, "AAA_", "目录标签")
        detected = detect_compression_tag(folder, "AAA_")
        self.assertEqual((detected.tag, detected.origin, detected.preserved_name), ("目录标签", "marker", "HGLIST-0042"))

    def test_compression_detection_reads_name_only(self):
        folder = self.root / "HGLIST-0043 名称标签 (2)"
        folder.mkdir()
        detected = detect_compression_tag(folder, "AAA_")
        self.assertEqual((detected.tag, detected.origin, detected.preserved_name), ("名称标签", "name", "HGLIST-0043"))

    def test_compression_detection_keeps_digits_at_end_of_name_tag(self):
        folder = self.root / "HGLIST-345 游戏名2"
        folder.mkdir()
        detected = detect_compression_tag(folder, "AAA_")
        self.assertEqual(
            (detected.tag, detected.origin, detected.preserved_name),
            ("游戏名2", "name", "HGLIST-345"),
        )

    def test_compression_detection_marks_conflict_when_tags_differ(self):
        folder = self.root / "HGLIST-0044 名称标签"
        folder.mkdir()
        create_tag_marker(folder, "AAA_", "目录标签")
        detected = detect_compression_tag(folder, "AAA_")
        self.assertTrue(detected.conflict)
        self.assertEqual(detected.origin, "conflict")
        self.assertEqual(detected.tag, "")
        self.assertEqual(detected.preserved_name, "HGLIST-0044")
        self.assertEqual((detected.name_tag, detected.marker_tag), ("名称标签", "目录标签"))

    def test_compression_detection_same_tags_are_not_conflict(self):
        folder = self.root / "HGLIST-0045 相同"
        folder.mkdir()
        create_tag_marker(folder, "AAA_", "相同")
        detected = detect_compression_tag(folder, "AAA_")
        self.assertFalse(detected.conflict)
        self.assertEqual(detected.origin, "marker")
        self.assertEqual(detected.tag, "相同")

    def test_compression_detection_ignores_wrong_prefix(self):
        plain = self.root / "普通文件夹"
        plain.mkdir()
        create_tag_marker(plain, "WRITE_", "不可见")
        self.assertFalse(detect_compression_tag(plain, "READ_").found)

    def test_explicit_targets_preserve_detected_number_and_prepare_markers(self):
        recognized, plain = self.make_folders("HGLIST-0042 图片", "plain")
        targets = [self.root / "HGLIST-0042", self.root / "HGLIST-0002"]
        self.assertTrue(analyze_explicit_preprocess_batch([recognized, plain], targets).valid)
        results = execute_explicit_preprocess_batch(
            [recognized, plain], targets, ["图片", "手动"], "AAA_"
        )
        self.assertTrue(all(item.status == PREPROCESSED for item in results))
        self.assertTrue((targets[0] / "AAA_图片").is_dir())
        self.assertTrue((targets[1] / "AAA_手动").is_dir())

    def test_remove_empty_tag_marker_handles_missing_empty_and_nonempty(self):
        folder = self.root / "marker-remove"
        folder.mkdir()
        remove_empty_tag_marker(folder, "AAA_", "缺失")

        empty = create_tag_marker(folder, "AAA_", "空")
        self.assertIsNotNone(empty)
        remove_empty_tag_marker(folder, "AAA_", "空")
        self.assertFalse(empty.exists())

        nonempty = create_tag_marker(folder, "AAA_", "非空")
        self.assertIsNotNone(nonempty)
        (nonempty / "keep.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(OSError):
            remove_empty_tag_marker(folder, "AAA_", "非空")
        self.assertTrue((nonempty / "keep.txt").exists())

    def test_preprocess_auto_strips_filename_tag_when_adding_marker(self):
        source = self.root / "HGLIST-0042 旧标签"
        source.mkdir()
        results = execute_explicit_preprocess_batch(
            [source], [source], ["新标签"], "AAA_", unwrap_nested=False
        )
        self.assertEqual(results[0].status, PREPROCESSED)
        target = results[0].target
        self.assertEqual(target.name, "HGLIST-0042")
        self.assertTrue((target / "AAA_新标签").is_dir())
        self.assertFalse(source.exists())

    def test_preprocess_replaces_empty_marker_without_explicit_removal(self):
        source = self.root / "HGLIST-0043"
        source.mkdir()
        old_marker = create_tag_marker(source, "AAA_", "旧标签")
        self.assertIsNotNone(old_marker)
        results = execute_explicit_preprocess_batch(
            [source], [source], ["新标签"], "AAA_", unwrap_nested=False
        )
        self.assertEqual(results[0].status, PREPROCESSED)
        self.assertFalse(old_marker.exists())
        self.assertTrue((source / "AAA_新标签").is_dir())

    def test_preprocess_rejects_nonempty_old_marker_without_explicit_removal(self):
        source = self.root / "HGLIST-0044"
        source.mkdir()
        old_marker = create_tag_marker(source, "AAA_", "旧标签")
        self.assertIsNotNone(old_marker)
        (old_marker / "keep.txt").write_text("x", encoding="utf-8")
        results = execute_explicit_preprocess_batch(
            [source], [source], ["新标签"], "AAA_", unwrap_nested=False
        )
        self.assertEqual(results[0].status, FAILED)
        self.assertTrue((old_marker / "keep.txt").exists())
        self.assertFalse((source / "AAA_新标签").exists())

    def test_explicit_preprocess_replaces_empty_conflicting_marker(self):
        source = self.root / "HGLIST-0046 名称标签"
        source.mkdir()
        create_tag_marker(source, "AAA_", "目录标签")
        target = self.root / "HGLIST-0046"
        results = execute_explicit_preprocess_batch(
            [source], [target], ["名称标签"], "AAA_", remove_marker_tags=["目录标签"]
        )
        self.assertEqual(results[0].status, PREPROCESSED)
        self.assertTrue((target / "AAA_名称标签").is_dir())
        self.assertFalse((target / "AAA_目录标签").exists())

    def test_explicit_preprocess_rejects_nonempty_conflicting_marker(self):
        source = self.root / "HGLIST-0047 名称标签"
        source.mkdir()
        old_marker = create_tag_marker(source, "AAA_", "目录标签")
        self.assertIsNotNone(old_marker)
        (old_marker / "keep.txt").write_text("x", encoding="utf-8")
        target = self.root / "HGLIST-0047"
        results = execute_explicit_preprocess_batch(
            [source], [target], ["名称标签"], "AAA_", remove_marker_tags=["目录标签"]
        )
        self.assertEqual(results[0].status, FAILED)
        self.assertTrue(target.exists())
        self.assertTrue((target / "AAA_目录标签" / "keep.txt").exists())
        self.assertFalse((target / "AAA_名称标签").exists())

    def test_explicit_target_conflict_blocks_whole_batch(self):
        first, second = self.make_folders("first", "second")
        occupied = self.root / "HGLIST-0042"
        occupied.mkdir()
        results = execute_explicit_preprocess_batch(
            [first, second], [occupied, self.root / "HGLIST-0002"], ["甲", "乙"], "AAA_"
        )
        self.assertTrue(first.exists() and second.exists())
        self.assertTrue(any(item.status == INVALID for item in results))

    def test_empty_prefix_and_invalid_inputs(self):
        (folder,) = self.make_folders("source")
        self.assertEqual(build_sequence_targets([folder], "", "0001")[0].name, "0001")
        for value in ("", "-1", "1.5", "一"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_sequence_targets([folder], "", value)
        with self.assertRaises(ValueError):
            build_sequence_targets([folder], "bad:", "1")

    def test_external_conflict_blocks_entire_batch(self):
        first, second = self.make_folders("first", "second")
        (self.root / "HGLIST-0002").mkdir()
        options = PreprocessOptions(start_number="0001")
        batch = analyze_preprocess_batch([first, second], options)
        self.assertFalse(batch.valid)
        results = execute_preprocess_batch([first, second], ["", ""], options)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertTrue(any(item.status == INVALID for item in results))

    def test_internal_name_cycle_uses_staging(self):
        first, second = self.make_folders("HGLIST-0002", "HGLIST-0001")
        (first / "first.txt").write_text("1", encoding="utf-8")
        (second / "second.txt").write_text("2", encoding="utf-8")
        results = execute_preprocess_batch(
            [first, second], ["甲", "乙"], PreprocessOptions(start_number="0001", unwrap_nested=False)
        )
        self.assertTrue(all(item.status == PREPROCESSED for item in results))
        self.assertTrue((self.root / "HGLIST-0001" / "first.txt").exists())
        self.assertTrue((self.root / "HGLIST-0002" / "second.txt").exists())
        self.assertTrue((self.root / "HGLIST-0001" / "AAA_甲").is_dir())
        self.assertTrue((self.root / "HGLIST-0002" / "AAA_乙").is_dir())

    def test_preprocess_can_keep_original_name_and_only_add_tag(self):
        (source,) = self.make_folders("keep-original-name")
        results = execute_explicit_preprocess_batch(
            [source], [source], ["保留名称"], "AAA_", unwrap_nested=False
        )
        self.assertEqual(results[0].status, PREPROCESSED)
        self.assertEqual(results[0].target, source)
        self.assertTrue(source.is_dir())
        self.assertTrue((source / "AAA_保留名称").is_dir())

    def test_rename_failure_rolls_staged_batch_back(self):
        first, second = self.make_folders("first", "second")
        (first / "first.txt").write_text("1", encoding="utf-8")
        (second / "second.txt").write_text("2", encoding="utf-8")
        real_rename = os.rename
        calls = 0

        def flaky_rename(source, target):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("simulated failure")
            return real_rename(source, target)

        with patch("core.os.rename", side_effect=flaky_rename):
            results = execute_preprocess_batch([first, second], ["", ""], PreprocessOptions())
        self.assertTrue(all(item.status == FAILED for item in results))
        self.assertTrue((first / "first.txt").exists())
        self.assertTrue((second / "second.txt").exists())

    def test_preprocess_tag_is_read_by_rename_and_extraction(self):
        (source,) = self.make_folders("source")
        result = execute_preprocess_batch(
            [source], ["联动"], PreprocessOptions(start_number="0007", unwrap_nested=False)
        )[0]
        self.assertEqual(result.status, PREPROCESSED)
        rename_preview = analyze_folder(result.target, RenameOptions(tag_prefix="AAA_"))
        self.assertEqual(rename_preview.target.name, "HGLIST-0007 联动")

        output = self.root / "output"
        staging = output / ".staging"
        staging.mkdir(parents=True)
        payload = staging / result.target.name
        shutil.move(str(result.target), str(payload))
        destination, _ = finalize_extraction(
            staging,
            output,
            self.root / "archive.1",
            {"tag_prefix": "AAA_", "block_terms": "路径, 中文"},
        )
        self.assertEqual(destination.name, "HGLIST-0007 联动")

    def test_cancel_before_mutation(self):
        (folder,) = self.make_folders("source")
        results = execute_preprocess_batch(
            [folder], [""], PreprocessOptions(), cancelled=lambda: True
        )
        self.assertEqual(results[0].status, CANCELLED)
        self.assertTrue(folder.exists())

    def test_single_child_chain_unwraps_but_multiple_children_do_not(self):
        (single,) = self.make_folders("single")
        payload = single / "one" / "two"
        payload.mkdir(parents=True)
        (payload / "file.bin").write_bytes(b"abc")
        self.assertEqual(unwrap_single_child_chain(single), 2)
        self.assertTrue((single / "file.bin").exists())

        (multiple,) = self.make_folders("multiple")
        (multiple / "a").mkdir()
        (multiple / "b").mkdir()
        self.assertEqual(unwrap_single_child_chain(multiple), 0)

        marker_only = self.root / "marker-only"
        marker_only.mkdir()
        create_tag_marker(marker_only, "AAA_", "保留")
        self.assertEqual(unwrap_single_child_chain(marker_only, "AAA_"), 0)
        self.assertTrue((marker_only / "AAA_保留").exists())

    def test_folder_size_is_recursive_and_format_is_binary(self):
        (folder,) = self.make_folders("source")
        (folder / "a.bin").write_bytes(b"a" * 1024)
        nested = folder / "nested"
        nested.mkdir()
        (nested / "b.bin").write_bytes(b"b" * 512)
        self.assertEqual(folder_size(folder), 1536)
        self.assertEqual(format_size(1536), "1.5 KB")
        self.assertEqual(format_size(8), "8 B")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_folder_size_does_not_follow_directory_symlink(self):
        (folder,) = self.make_folders("source")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "large.bin").write_bytes(b"x" * 4096)
        try:
            os.symlink(outside, folder / "link", target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation not permitted")
        self.assertEqual(folder_size(folder), 0)


class NaturalSortTests(unittest.TestCase):
    def test_numbers_sort_by_numeric_value(self):
        names = ["item-10", "item-2", "item-1"]
        self.assertEqual(sorted(names, key=natural_name_key), ["item-1", "item-2", "item-10"])

    def test_natural_sort_is_case_insensitive(self):
        self.assertEqual(natural_name_key("a2"), natural_name_key("A2"))

    def test_path_sort_key_orders_by_name_then_path(self):
        first = Path("C:/x/item-2")
        second = Path("C:/x/item-10")
        self.assertLess(path_sort_key(first), path_sort_key(second))

    def test_path_sort_key_uses_path_as_tiebreaker(self):
        same_name_a = Path("C:/a/item")
        same_name_b = Path("C:/b/item")
        self.assertLess(path_sort_key(same_name_a), path_sort_key(same_name_b))


if __name__ == "__main__":
    unittest.main()
