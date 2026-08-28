from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prime_ai_trader.app.clean_start import (
    CLEAN_START_EPOCH,
    CLEAN_START_MARKER,
    initialize_clean_mt5_start,
)


class CleanMT5StartTests(unittest.TestCase):
    def test_first_start_removes_all_legacy_local_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "PrimeAITrader"
            root.mkdir()
            (root / "settings.json").write_text('{"platform_name":"VEX"}', encoding="utf-8")
            (root / "secrets.dat").write_bytes(b"legacy")
            (root / "prime_ai_trader.db").write_bytes(b"legacy-db")
            (root / "logs").mkdir()
            (root / "logs" / "app.log").write_text("old log", encoding="utf-8")
            (root / "models" / "contexts").mkdir(parents=True)
            (root / "models" / "active_model.joblib").write_bytes(b"old-model")
            (root / "models" / "contexts" / "old.joblib").write_bytes(b"old-context")
            (root / ".old_epoch").write_text("legacy", encoding="utf-8")

            result = initialize_clean_mt5_start(root)

            self.assertTrue(result.reset)
            self.assertGreaterEqual(result.removed_entries, 6)
            self.assertEqual(
                (root / CLEAN_START_MARKER).read_text(encoding="utf-8"),
                CLEAN_START_EPOCH,
            )
            self.assertFalse((root / "settings.json").exists())
            self.assertFalse((root / "secrets.dat").exists())
            self.assertFalse((root / "prime_ai_trader.db").exists())
            self.assertFalse((root / "logs").exists())
            self.assertFalse((root / "models").exists())
            self.assertFalse((root / ".old_epoch").exists())

    def test_clean_start_runs_only_once_and_preserves_new_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "PrimeAITrader"
            root.mkdir()
            (root / "settings.json").write_text("old", encoding="utf-8")

            first = initialize_clean_mt5_start(root)
            self.assertTrue(first.reset)

            new_settings = root / "settings.json"
            new_database = root / "prime_ai_trader.db"
            new_settings.write_text("new-settings", encoding="utf-8")
            new_database.write_bytes(b"new-db")

            second = initialize_clean_mt5_start(root)

            self.assertFalse(second.reset)
            self.assertEqual(new_settings.read_text(encoding="utf-8"), "new-settings")
            self.assertEqual(new_database.read_bytes(), b"new-db")


if __name__ == "__main__":
    unittest.main()
