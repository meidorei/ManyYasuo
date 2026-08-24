import json
import tempfile
import unittest
from pathlib import Path

from config_store import ConfigStore, DEFAULT_CONFIG
from job_coordinator import JobCoordinator


class ConfigStoreTests(unittest.TestCase):
    def test_sections_are_independent_and_persist(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            store = ConfigStore(path)
            store.update_section("compression", {"tag_prefix": "ZIP_", "pwd": "one"})
            store.update_section("preprocessing", {"prefix": "PRE-", "tag_prefix": "PRE_TAG_"})
            store.update_section("extraction", {"tag_prefix": "OPEN_", "password": "two"})
            loaded = ConfigStore(path)
            self.assertEqual(loaded.section("compression")["tag_prefix"], "ZIP_")
            self.assertEqual(loaded.section("preprocessing")["prefix"], "PRE-")
            self.assertEqual(loaded.section("preprocessing")["tag_prefix"], "PRE_TAG_")
            self.assertEqual(loaded.section("extraction")["tag_prefix"], "OPEN_")
            self.assertEqual(loaded.section("renaming")["tag_prefix"], "AAA_")

    def test_missing_invalid_and_partial_files_use_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            self.assertEqual(ConfigStore(path).section("renaming"), DEFAULT_CONFIG["renaming"])
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(ConfigStore(path).section("extraction")["output_dir"], "")
            path.write_text(json.dumps({"compression": {"extension": ".x"}}), encoding="utf-8")
            loaded = ConfigStore(path)
            self.assertEqual(loaded.section("compression")["extension"], ".x")
            self.assertEqual(loaded.section("compression")["tag_prefix"], "AAA_")


class JobCoordinatorTests(unittest.TestCase):
    def test_only_one_owner_and_release_is_owner_checked(self):
        coordinator = JobCoordinator()
        changes = []
        coordinator.subscribe(changes.append)
        self.assertTrue(coordinator.try_acquire("compression"))
        self.assertFalse(coordinator.try_acquire("extraction"))
        self.assertFalse(coordinator.release("extraction"))
        self.assertEqual(coordinator.owner, "compression")
        self.assertTrue(coordinator.release("compression"))
        self.assertIsNone(coordinator.owner)
        self.assertEqual(changes, ["compression", None])


if __name__ == "__main__":
    unittest.main()
