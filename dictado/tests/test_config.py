"""Atomic user-config persistence without touching real user data."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import config


class ConfigPersistenceTests(unittest.TestCase):
    def test_save_replaces_config_and_keeps_previous_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"key": "old"}')

            with patch("instant_app.config.config_path", return_value=path):
                config.save({**config.DEFAULTS, "key": "f10"})

            with open(path, encoding="utf-8") as handle:
                current = json.load(handle)
            with open(path + ".bak", encoding="utf-8") as handle:
                backup = json.load(handle)
            self.assertEqual(current["key"], "f10")
            self.assertEqual(backup, {"key": "old"})
            self.assertCountEqual(os.listdir(directory),
                                  ["config.json", "config.json.bak"])

    def test_failed_serialization_preserves_config_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            previous = '{"key": "old"}'
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(previous)

            with patch("instant_app.config.config_path", return_value=path), \
                    patch("instant_app.config.json.dump",
                          side_effect=TypeError("cannot serialize")):
                with self.assertRaisesRegex(TypeError, "cannot serialize"):
                    config.save({**config.DEFAULTS, "key": "f10"})

            with open(path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), previous)
            self.assertEqual(os.listdir(directory), ["config.json"])

    def test_corrupt_config_recovers_from_previous_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{ truncated")
            with open(path + ".bak", "w", encoding="utf-8") as handle:
                json.dump({**config.DEFAULTS, "key": "f10"}, handle)

            with patch("instant_app.config.config_path", return_value=path), \
                    patch.dict(os.environ, {}, clear=True), \
                    self.assertLogs("instant", level="ERROR") as logs:
                restored = config.load()

            self.assertIn("config corrupta", logs.output[0])
            self.assertEqual(restored["key"], "f10")
            with open(path, encoding="utf-8") as handle:
                repaired = json.load(handle)
            self.assertEqual(repaired["key"], "f10")


if __name__ == "__main__":
    unittest.main()
