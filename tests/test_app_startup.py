"""Tes persiapan direktori saat startup tanpa membuat QApplication nyata."""

from pathlib import Path
from unittest.mock import Mock, call

import pytest

import app
import config


def test_main_ensures_directories_on_every_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direktori harus siap sebelum DB dan jendela mengakses penyimpanan."""
    startup = Mock()
    qt_app = Mock()
    qt_app.exec.return_value = 0
    monkeypatch.setattr(app, "QApplication", Mock(return_value=qt_app))
    monkeypatch.setattr(app, "_apply_light_theme", Mock())
    monkeypatch.setattr(config, "ensure_directories", startup.ensure_directories)
    monkeypatch.setattr(app.db, "init_db", startup.init_db)
    monkeypatch.setattr(app, "MainWindow", startup.MainWindow)

    for _ in range(2):
        startup.reset_mock()
        assert app.main() == 0
        assert startup.mock_calls == [
            call.ensure_directories(), call.init_db(),
            call.MainWindow(), call.MainWindow().show(),
        ]


def test_ensure_directories_creates_missing_parents_and_preserves_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Path bertingkat yang belum ada dapat dibuat dan dipakai kembali saat restart."""
    paths = []
    for setting in ("DATA_DIR", "STORAGE_DIR", "MODELS_DIR"):
        path = tmp_path / setting.lower() / "nested" / "target"
        monkeypatch.setattr(config, setting, path)
        paths.append(path)

    config.ensure_directories()
    for path in paths:
        assert path.is_dir()
        (path / "existing.txt").write_text("tetap ada", encoding="utf-8")

    config.ensure_directories()
    for path in paths:
        assert (path / "existing.txt").read_text(encoding="utf-8") == "tetap ada"
