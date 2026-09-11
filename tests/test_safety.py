import os
import queue
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import (FAILED, INVALID, RenameOptions, analyze_folder,
                  execute_explicit_preprocess_batch, find_tag_marker,
                  unwrap_single_child_chain)
from app import CoordinatedCompression
from main import PipelineApp
from job_coordinator import JobCoordinator


class RollbackTests(unittest.TestCase):
    def test_failure_at_every_rename_restores_contents(self):
        for names, targets in [(('A', 'B'), ('B', 'A')),
                               (('A', 'B', 'C'), ('B', 'C', 'A')),
                               (('A', 'B'), ('X', 'Y'))]:
            for fail_at in range(1, 2 * len(names) + 1):
                with self.subTest(names=names, fail_at=fail_at), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    sources = [root / name for name in names]
                    for source in sources:
                        source.mkdir()
                        (source / 'identity').write_text(source.name)
                    rename = os.rename
                    calls = 0

                    def failing(source, target):
                        nonlocal calls
                        calls += 1
                        if calls == fail_at:
                            raise OSError('injected failure')
                        return rename(source, target)

                    with patch('core.os.rename', side_effect=failing):
                        results = execute_explicit_preprocess_batch(
                            sources, [root / name for name in targets], [], 'AAA_')
                    self.assertTrue(all(result.status == FAILED for result in results))
                    self.assertEqual(set(p.name for p in root.iterdir()), set(names))
                    for source in sources:
                        self.assertEqual((source / 'identity').read_text(), source.name)

    def test_failed_recovery_reports_actual_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = [root / name for name in ('A', 'B', 'C')]
            for source in sources:
                source.mkdir()
                (source / 'identity').write_text(source.name)
            rename = os.rename
            calls = 0

            def failing(source, target):
                nonlocal calls
                calls += 1
                if calls in (6, 7):
                    raise OSError('injected recovery failure')
                return rename(source, target)

            with patch('core.os.rename', side_effect=failing):
                results = execute_explicit_preprocess_batch(
                    sources, sources[1:] + sources[:1], [], 'AAA_')
            self.assertEqual(sorted((p / 'identity').read_text() for p in root.iterdir()), ['A', 'B', 'C'])
            for result in results:
                self.assertEqual((result.target / 'identity').read_text(), result.source.name)
                self.assertIn('实际保留位置', result.message)
                self.assertIn('injected recovery failure', result.message)


@unittest.skipUnless(os.name == 'nt', 'Windows junction test')
class JunctionTests(unittest.TestCase):
    def test_junctions_are_not_traversed_or_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected, outside = root / 'selected', root / 'outside'
            selected.mkdir()
            outside.mkdir()
            (outside / 'identity').write_text('keep')
            (outside / 'AAA_tag').mkdir()
            junction = selected / 'wrapper'
            # mklink creates a junction without symlink privileges; all paths
            # are generated within this test's temporary directory.
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(outside)],
                           check=True, capture_output=True)
            try:
                self.assertTrue(junction.is_junction())
                self.assertIsNone(find_tag_marker(selected, 'AAA_'))
                self.assertEqual(unwrap_single_child_chain(selected), 0)
                self.assertEqual((outside / 'identity').read_text(), 'keep')
                self.assertEqual(analyze_folder(junction, RenameOptions()).status, INVALID)
                result = execute_explicit_preprocess_batch([junction], [junction], ['new'], 'AAA_')[0]
                self.assertEqual(result.status, INVALID)
                with self.assertRaises(OSError):
                    unwrap_single_child_chain(junction)
                self.assertTrue((outside / 'AAA_tag').exists())
                self.assertFalse((outside / 'AAA_new').exists())
            finally:
                junction.rmdir()
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), str(selected)],
                           check=True, capture_output=True)
            try:
                self.assertIsNone(find_tag_marker(selected, 'AAA_'))
                self.assertEqual(unwrap_single_child_chain(selected), 0)
            finally:
                junction.rmdir()


class EnqueueLockTests(unittest.TestCase):
    def setUp(self):
        self.page = CoordinatedCompression.__new__(CoordinatedCompression)
        self.page.coordinator = JobCoordinator()
        self.page.preparing_queue = False
        self.page.left_rows = []
        self.page.refresh_enqueue_state = Mock()

    def test_busy_owner_blocks_entry(self):
        self.page.coordinator.try_acquire('extraction')
        with patch.object(PipelineApp, 'do_restructure') as start, patch('app.messagebox.showinfo'):
            self.page.do_restructure()
        start.assert_not_called()
        self.assertEqual(self.page.coordinator.owner, 'extraction')

    def test_success_holds_lock_until_completion(self):
        def start():
            self.page.preparing_queue = True
        with patch.object(PipelineApp, 'do_restructure', side_effect=start):
            self.page.do_restructure()
        self.assertFalse(self.page.coordinator.try_acquire('renaming'))
        with patch.object(PipelineApp, 'finish_enqueue'):
            self.page.finish_enqueue([], [], [])
        self.assertTrue(self.page.coordinator.try_acquire('renaming'))

    def test_start_and_callback_failures_release_lock(self):
        def start():
            self.page.preparing_queue = True
            raise RuntimeError('thread failed')
        with patch.object(PipelineApp, 'do_restructure', side_effect=start), patch('app.messagebox.showerror'):
            self.page.do_restructure()
        self.assertIsNone(self.page.coordinator.owner)
        self.page.coordinator.try_acquire('compression')
        self.page.preparing_queue = True
        with patch.object(PipelineApp, 'finish_enqueue', side_effect=RuntimeError('callback failed')):
            with self.assertRaises(RuntimeError):
                self.page.finish_enqueue([], [], [])
        self.assertFalse(self.page.preparing_queue)
        self.assertIsNone(self.page.coordinator.owner)

    def test_validation_return_releases_lock(self):
        with patch.object(PipelineApp, 'do_restructure'):
            self.page.do_restructure()
        self.assertIsNone(self.page.coordinator.owner)

    def test_worker_exception_posts_completion(self):
        self.page.ui_events = queue.Queue()
        self.page.coordinator.try_acquire('compression')
        with patch('main.execute_explicit_preprocess_batch', side_effect=RuntimeError('worker failed')):
            self.page.enqueue_worker([], ['source'], ['target'], ['tag'], 'AAA_', [])
        event = self.page.ui_events.get_nowait()
        self.assertEqual(event[0], 'enqueue_finished')
        self.assertEqual(event[2][0].status, FAILED)
        self.assertEqual(self.page.coordinator.owner, 'compression')
        with patch.object(PipelineApp, 'finish_enqueue'):
            self.page.finish_enqueue(*event[1:])
        self.assertIsNone(self.page.coordinator.owner)
