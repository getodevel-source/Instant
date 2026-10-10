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

    def test_numeric_types_and_sound_variants_parsed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"threads": "invalid", "max_seg": "bad", "sound": False}, handle)
            with patch("instant_app.config.config_path", return_value=path), \
                    patch.dict(os.environ, {"DICTADO_SOUND": "si"}, clear=True):
                cfg = config.load()
            self.assertEqual(cfg["threads"], config.DEFAULTS["threads"])
            self.assertEqual(cfg["max_seg"], config.DEFAULTS["max_seg"])
            self.assertTrue(cfg["sound"])

    def test_llm_token_and_update_mode_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({}, handle)
            with patch("instant_app.config.config_path", return_value=path), \
                    patch.dict(os.environ, {"DICTADO_LLM_TOKEN": "tok-env",
                                            "DICTADO_UPDATE": "auto"}, clear=True):
                cfg = config.load()
            self.assertEqual(cfg["llm_token"], "tok-env")
            self.assertEqual(cfg["update_mode"], "auto")
            with patch("instant_app.config.config_path", return_value=path), \
                    patch.dict(os.environ, {"DICTADO_UPDATE": "xxx"}, clear=True):
                cfg = config.load()
            self.assertEqual(cfg["update_mode"], "notify")

    def test_llm_token_persists_and_stays_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with patch("instant_app.config.config_path", return_value=path):
                saved = config.save({**config.DEFAULTS, "llm_token": "tok-1"})
            disk = json.load(open(saved, encoding="utf-8"))
            self.assertEqual(disk["llm_token"], "tok-1")
            with patch("instant_app.config.config_path", return_value=path):
                cfg = config.load()
            self.assertEqual(cfg["llm_token"], "tok-1")

if __name__ == "__main__":
    unittest.main()
