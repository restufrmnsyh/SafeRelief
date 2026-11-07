"""Tes bootstrap admin tanpa USB fisik, webcam, atau file recovery nyata."""

from pathlib import Path

import pytest

import config
from database import db
import setup_admin


@pytest.fixture
def setup_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "setup-test.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    db.init_db(path)
    return path


def test_second_admin_is_rejected_before_prompting(
    setup_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert setup_db.exists()
    monkeypatch.setattr(
        setup_admin.db, "count_admins", lambda *args: len(args)
    )

    def unexpected_input(prompt: str) -> str:
        pytest.fail(f"Input tidak seharusnya diminta: {prompt}")

    def unexpected_password(prompt: str) -> str:
        pytest.fail(f"Password tidak seharusnya diminta: {prompt}")

    monkeypatch.setattr(
        "builtins.input", unexpected_input
    )
    monkeypatch.setattr(setup_admin.getpass, "getpass", unexpected_password)

    assert setup_admin.main() == 1
    assert "admin sudah terdaftar" in capsys.readouterr().out


def test_webcam_failure_rolls_back_inserted_admin(
    setup_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        setup_admin.dongle, "find_removable_drives", lambda: ["D:\\"]
    )
    answers = iter(
        ["1", "Admin Baru", "admin-baru", str(tmp_path / "recovery.key")]
    )

    def answer_input(prompt: str) -> str:
        assert prompt
        return next(answers)

    monkeypatch.setattr("builtins.input", answer_input)
    secrets = iter(
        [
            "admin-pass-123",
            "admin-pass-123",
            "recovery-pass-123",
            "recovery-pass-123",
        ]
    )
    def answer_password(prompt: str) -> str:
        assert prompt
        return next(secrets)

    monkeypatch.setattr(setup_admin.getpass, "getpass", answer_password)
    monkeypatch.setattr(
        setup_admin.face_auth,
        "capture_encodings",
        lambda: (_ for _ in ()).throw(ValueError("webcam gagal")),
    )

    assert setup_admin.main() == 1
    with db.get_connection(setup_db) as conn:
        assert db.count_admins(conn) == 0
        assert db.get_user_by_username(conn, "admin-baru") is None


def test_bootstrap_success_persists_encrypted_face_and_audit_log(
    setup_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np

    monkeypatch.setattr(
        setup_admin.dongle, "find_removable_drives", lambda: ["D:\\"]
    )
    def fake_serial(drive: str) -> str:
        assert drive == "D:\\"
        return "AABB1122"

    def fake_token_path(drive: str) -> Path:
        assert drive == "D:\\"
        return tmp_path / config.DONGLE_KEY_FILE

    monkeypatch.setattr(setup_admin.dongle, "get_volume_serial", fake_serial)
    monkeypatch.setattr(setup_admin.dongle, "_token_path", fake_token_path)
    monkeypatch.setattr(
        setup_admin.face_auth,
        "capture_encodings",
        lambda: np.ones(128, dtype=np.float32),
    )
    def create_recovery(master: bytes, password: str, output: str) -> None:
        assert len(master) == config.MASTER_KEY_LENGTH
        assert password == "recovery-pass-123"
        Path(output).write_bytes(b"recovery")

    monkeypatch.setattr(
        setup_admin.keys, "create_recovery_file", create_recovery
    )
    answers = iter(
        ["1", "Admin Baru", "admin-baru", str(tmp_path / "recovery.key")]
    )

    def answer_input(prompt: str) -> str:
        assert prompt
        return next(answers)

    monkeypatch.setattr("builtins.input", answer_input)
    secrets = iter(
        [
            "admin-pass-123",
            "admin-pass-123",
            "recovery-pass-123",
            "recovery-pass-123",
        ]
    )
    def answer_password(prompt: str) -> str:
        assert prompt
        return next(secrets)

    monkeypatch.setattr(setup_admin.getpass, "getpass", answer_password)

    assert setup_admin.main() == 0
    with db.get_connection(setup_db) as conn:
        admin = db.get_user_by_username(conn, "admin-baru")
        assert admin is not None
        assert admin["role"] == "admin"
        assert admin["face_encoding_enc"] is not None
        assert admin["wrapped_master_key"] is not None
        assert admin["kdf_salt"] is not None
        events = db.list_activity_log(conn)
        assert any(event["aksi"] == "ADMIN_BOOTSTRAP" for event in events)
