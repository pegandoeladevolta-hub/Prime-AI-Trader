from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prime_ai_trader.config.settings import app_data_dir
from prime_ai_trader.database.repository import Repository
from prime_ai_trader import __version__


class WindowsReliabilityTests(unittest.TestCase):
    def test_explicit_data_directory_is_respected_on_all_platforms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"PRIME_AI_TRADER_DATA_HOME": temporary},
        ):
            self.assertEqual(app_data_dir(), Path(temporary) / "PrimeAITrader")

    def test_xdg_test_override_remains_isolated_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"XDG_DATA_HOME": temporary},
        ):
            self.assertEqual(app_data_dir(), Path(temporary) / "PrimeAITrader")

    def test_database_connection_is_closed_after_each_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Repository(Path(temporary) / "closed.db")
            with repository.connect() as connection:
                connection.execute("SELECT 1")
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_database_file_is_released_for_windows_cache_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "released.db"
            repository = Repository(path)
            repository.recent(1)
            path.unlink()
            self.assertFalse(path.exists())

    def test_windows_build_rejects_failed_test_suite(self) -> None:
        script = (Path(__file__).parents[1] / "build_windows.ps1").read_text(encoding="utf-8")
        marker = "-m unittest discover -s tests -v"
        self.assertIn(marker, script)
        after_tests = script.split(marker, 1)[1].split('Write-Host "[4/6]', 1)[0]
        self.assertIn('Assert-NativeSuccess "Suíte completa de testes"', after_tests)

    def test_icon_generation_dependency_is_installed_for_windows_build(self) -> None:
        requirements = (Path(__file__).parents[1] / "requirements-build.txt").read_text(encoding="utf-8")
        self.assertIn("pillow", requirements.lower())

    def test_windows_build_validates_full_tkinter_before_packaging(self) -> None:
        root = Path(__file__).parents[1]
        script = (root / "build_windows.ps1").read_text(encoding="utf-8")
        spec = (root / "PrimeAITrader.spec").read_text(encoding="utf-8")
        self.assertIn("from tkinter import filedialog, messagebox, ttk", script)
        self.assertIn('"tkinter.filedialog"', spec)
        self.assertNotIn("setup_entry.py", (root / "installer" / "PrimeAITrader.iss").read_text(encoding="utf-8"))

    def test_product_version_is_consistent_across_windows_artifacts(self) -> None:
        root = Path(__file__).parents[1]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        installer = (root / "installer" / "PrimeAITrader.iss").read_text(encoding="utf-8")
        version_info = (root / "version_info.txt").read_text(encoding="utf-8")
        self.assertIn(f'version = "{__version__}"', pyproject)
        self.assertIn(f'#define MyAppVersion "{__version__}"', installer)
        self.assertIn(f"StringStruct('FileVersion', '{__version__}')", version_info)
        self.assertIn(f"StringStruct('ProductVersion', '{__version__}')", version_info)


if __name__ == "__main__":
    unittest.main()
