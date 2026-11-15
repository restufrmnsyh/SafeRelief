"""Tes pemulihan admin dengan kriptografi asli, database sementara, dan USB simulasi."""

import os
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

import config
import reset_admin
from auth import dongle, login, masked_input
from crypto import hashing, keys
from database import db, secure_store


@pytest.fixture
def recovery_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Ganti lokasi penyimpanan dan deteksi USB, bukan implementasi enkripsinya."""
    database_path = tmp_path / "recovery-test.db"
    monkeypatch.setattr(config, "DB_PATH", database_path)
    db.init_db()
    conn = db.get_connection()
    old_drive, new_drive = tmp_path / "old-usb", tmp_path / "new-usb"
    old_drive.mkdir()
    new_drive.mkdir()
    serials = {str(old_drive): "OLD-SERIAL", str(new_drive): "NEW-SERIAL"}
    monkeypatch.setattr(dongle, "get_volume_serial", lambda drive: serials[drive])
    monkeypatch.setattr(dongle, "find_removable_drives", lambda: [str(new_drive)])
    master, old_token, salt = os.urandom(32), os.urandom(32), os.urandom(16)
    old_password = "Password-Lama-Uji"
    recovery_password = "Password-Pemulihan-Uji"
    uid = db.insert_user(conn, {
        "nama_lengkap": "Admin Uji", "username": "admin-uji", "role": "admin",
        "password_hash": hashing.hash_password(old_password),
        "dongle_serial": "OLD-SERIAL", "dongle_token_hash": dongle._hash_token(old_token),
        "wrapped_master_key": keys.wrap_master_key(master, old_password, old_token, salt),
        "kdf_salt": salt,
    })
    volunteer_id = db.insert_user(conn, {
        "nama_lengkap": "Relawan Uji", "username": "relawan-uji", "role": "relawan",
        "password_hash": "hash-tidak-dipakai", "dongle_serial": "VOLUNTEER-SERIAL",
    })
    db.update_user_login_attempt(conn, uid, 3, "2099-01-01T00:00:00")
    db_key = keys.derive_key(master, b"db")
    secure_store.save_face_encoding(conn, db_key, uid, b"encoding-wajah-uji")
    dongle._token_path(str(old_drive)).write_text(old_token.hex(), encoding="ascii")
    recovery_path = tmp_path / "recovery.key"
    keys.create_recovery_file(master, recovery_password, str(recovery_path))
    yield {
        "conn": conn, "uid": uid, "volunteer_id": volunteer_id, "master": master,
        "old_drive": old_drive, "drive": str(new_drive), "old_token": old_token,
        "old_password": old_password, "recovery_password": recovery_password,
        "recovery_path": recovery_path, "password": "Password-Baru-Uji",
    }
    conn.close()


def snapshot(conn: sqlite3.Connection) -> tuple:
    """Bandingkan semua kolom user dan log, termasuk BLOB serta lockout."""
    users = [dict(db.get_user_by_id(conn, row["id"])) for row in db.list_users(conn)]
    logs = [dict(row) for row in db.list_activity_log(conn)]
    return users, logs


def cli_inputs(context: dict, monkeypatch: pytest.MonkeyPatch, secrets: list[str]) -> Mock:
    """Password harus melewati pembaca masked, input biasa hanya untuk path/drive."""
    answers = iter([str(context["recovery_path"]), "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    reader = Mock(side_effect=secrets)
    monkeypatch.setattr(masked_input, "read_masked_password", reader)
    return reader


@pytest.mark.parametrize("failure", ["wrong_password", "corrupt", "missing"])
def test_invalid_recovery_does_not_touch_database_or_dongle(
    recovery_context: dict, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], failure: str,
) -> None:
    c = recovery_context
    if failure == "corrupt":
        c["recovery_path"].write_bytes(b"rusak")
    elif failure == "missing":
        c["recovery_path"].unlink()
    before = snapshot(c["conn"])
    database_before = Path(config.DB_PATH).read_bytes()
    reader = cli_inputs(c, monkeypatch, ["salah" if failure == "wrong_password" else c["recovery_password"]])
    open_db = Mock(side_effect=AssertionError("Tidak boleh membuka DB"))
    drives = Mock(side_effect=AssertionError("Tidak boleh mencari dongle"))
    monkeypatch.setattr(db, "get_connection", open_db)
    monkeypatch.setattr(dongle, "find_removable_drives", drives)
    assert reset_admin.main() == 1
    assert "Pemulihan gagal:" in capsys.readouterr().out
    assert snapshot(c["conn"]) == before
    assert Path(config.DB_PATH).read_bytes() == database_before
    assert not dongle._token_path(c["drive"]).exists()
    reader.assert_called_once()
    open_db.assert_not_called()
    drives.assert_not_called()


def test_success_replaces_existing_admin_credentials_and_preserves_data(
    recovery_context: dict, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    c = recovery_context
    before = dict(db.get_user_by_id(c["conn"], c["uid"]))
    volunteer_before = dict(db.get_user_by_id(c["conn"], c["volunteer_id"]))
    recovery_before = c["recovery_path"].read_bytes()
    reader = cli_inputs(c, monkeypatch, [c["recovery_password"], c["password"], c["password"]])
    assert reset_admin.main() == 0
    output = capsys.readouterr().out
    assert "berhasil diganti" in output and "recovery.key baru secara manual" in output
    for secret in (c["password"], c["recovery_password"], c["master"].hex()):
        assert secret not in output
    assert reader.call_count == 3
    after = dict(db.get_user_by_id(c["conn"], c["uid"]))
    assert db.count_admins(c["conn"]) == 1
    assert dict(db.get_user_by_id(c["conn"], c["volunteer_id"])) == volunteer_before
    changed = {name for name in before if before[name] != after[name]}
    assert changed == {
        "password_hash", "wrapped_master_key", "kdf_salt", "dongle_serial",
        "dongle_token_hash", "failed_attempts", "locked_until",
    }
    assert after["dongle_serial"] == "NEW-SERIAL"
    assert hashing.verify_password(c["password"], after["password_hash"])
    assert not hashing.verify_password(c["old_password"], after["password_hash"])
    new_token = dongle.verify_dongle(after)
    assert keys.unwrap_master_key(after["wrapped_master_key"], c["password"], new_token, after["kdf_salt"]) == c["master"]
    for password, token in ((c["old_password"], new_token), (c["password"], c["old_token"])):
        with pytest.raises(ValueError, match="Gagal membuka master key"):
            keys.unwrap_master_key(after["wrapped_master_key"], password, token, after["kdf_salt"])
    assert secure_store.load_face_encoding(c["conn"], keys.derive_key(c["master"], b"db"), c["uid"]) == b"encoding-wajah-uji"
    assert c["recovery_path"].read_bytes() == recovery_before
    assert dongle.read_token(str(c["old_drive"])) == c["old_token"]
    logs = db.list_activity_log(c["conn"])
    assert len(logs) == 1 and logs[0]["aksi"] == "RESET_ADMIN_DONGLE"
    assert logs[0]["user_id"] == c["uid"] and logs[0]["detail"] is None
    assert login.authenticate(c["conn"], "admin-uji", c["password"])["id"] == c["uid"]


@pytest.mark.parametrize("existing_token", [False, True])
@pytest.mark.parametrize("failure", ["write", "wrap", "credentials", "log", "cancel", "commit"])
def test_failure_restores_all_admin_fields_and_physical_token(
    recovery_context: dict, monkeypatch: pytest.MonkeyPatch, existing_token: bool, failure: str,
) -> None:
    c = recovery_context
    token_path = dongle._token_path(c["drive"])
    original = b"token-lama-di-drive-pengganti\r\n"
    if existing_token:
        token_path.write_bytes(original)
    before = snapshot(c["conn"])
    recovery_before = c["recovery_path"].read_bytes()

    def fail(*_args, **_kwargs) -> None:
        raise OSError("kegagalan simulasi")

    if failure == "write":
        original_write = Path.write_text

        def partial_write(path: Path, *args, **kwargs) -> int:
            if path == token_path:
                path.write_bytes(b"token-parsial")
                raise OSError("tulis dongle gagal")
            return original_write(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", partial_write)
    elif failure == "wrap":
        monkeypatch.setattr(keys, "wrap_master_key", fail)
    elif failure == "credentials":
        update = db.update_admin_recovery_credentials

        def update_then_fail(*args, **kwargs) -> None:
            update(*args, **kwargs)
            fail()

        monkeypatch.setattr(db, "update_admin_recovery_credentials", update_then_fail)
    elif failure in {"log", "cancel"}:
        log = db.log_activity

        def log_then_fail(*args, **kwargs) -> None:
            log(*args, **kwargs)
            if failure == "cancel":
                raise KeyboardInterrupt()
            fail()

        monkeypatch.setattr(db, "log_activity", log_then_fail)

    class FailedCommitConnection(sqlite3.Connection):
        """Biarkan SQLite benar-benar mengubah transaksi sebelum commit gagal."""

        def commit(self) -> None:
            raise sqlite3.OperationalError("commit gagal")

    conn = c["conn"]
    if failure == "commit":
        conn = sqlite3.connect(config.DB_PATH, factory=FailedCommitConnection)
        conn.row_factory = sqlite3.Row
    try:
        error = KeyboardInterrupt if failure == "cancel" else (OSError, sqlite3.Error)
        with pytest.raises(error):
            reset_admin._reset_admin(conn, master_key=c["master"], drive=c["drive"], new_password=c["password"])
        assert not conn.in_transaction
        assert snapshot(conn) == before
        assert snapshot(c["conn"]) == before
    finally:
        if conn is not c["conn"]:
            conn.close()
    if existing_token:
        assert token_path.read_bytes() == original
    else:
        assert not token_path.exists()
    assert c["recovery_path"].read_bytes() == recovery_before
    assert dongle.read_token(str(c["old_drive"])) == c["old_token"]


@pytest.mark.parametrize("case", ["same_recovery_password", "mismatch", "short", "same_drive", "other_owner", "removed_drive"])
def test_rejected_reset_leaves_existing_data_intact(
    recovery_context: dict, monkeypatch: pytest.MonkeyPatch, case: str,
) -> None:
    c = recovery_context
    password, confirmation = c["password"], c["password"]
    if case == "same_recovery_password":
        password = confirmation = c["recovery_password"]
    elif case == "mismatch":
        confirmation = "berbeda"
    elif case == "short":
        password = confirmation = "pendek"
    elif case == "same_drive":
        monkeypatch.setattr(dongle, "get_volume_serial", lambda _drive: "OLD-SERIAL")
    elif case == "other_owner":
        monkeypatch.setattr(dongle, "get_volume_serial", lambda _drive: "VOLUNTEER-SERIAL")
    elif case == "removed_drive":
        monkeypatch.setattr(dongle, "find_removable_drives", Mock(side_effect=[[c["drive"]], []]))
    before = snapshot(c["conn"])
    cli_inputs(c, monkeypatch, [c["recovery_password"], password, confirmation])
    assert reset_admin.main() == 1
    assert snapshot(c["conn"]) == before
    assert not dongle._token_path(c["drive"]).exists()


def test_admin_helper_rejects_volunteer_without_changes(recovery_context: dict) -> None:
    c = recovery_context
    before = snapshot(c["conn"])
    with pytest.raises(ValueError, match="Admin"):
        db.update_admin_recovery_credentials(c["conn"], c["volunteer_id"], "hash", b"wrapped", b"salt", commit=False)
    c["conn"].rollback()
    assert snapshot(c["conn"]) == before


@pytest.mark.parametrize("database_exists", [False, True])
def test_missing_database_or_admin_is_not_bootstrapped(
    recovery_context: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, database_exists: bool,
) -> None:
    c = recovery_context
    path = tmp_path / "empty.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    if database_exists:
        db.init_db()
    before = path.read_bytes() if database_exists else None
    cli_inputs(c, monkeypatch, [c["recovery_password"]])
    assert reset_admin.main() == 1
    assert (path.read_bytes() if path.exists() else None) == before
    assert not dongle._token_path(c["drive"]).exists()


def test_cli_cancellation_rolls_back_and_wipes_master_key(
    recovery_context: dict, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    c = recovery_context
    before = snapshot(c["conn"])
    retained: list[bytearray] = []
    reset = reset_admin._reset_admin

    def retain_key(conn: sqlite3.Connection, **kwargs) -> None:
        retained.append(kwargs["master_key"])
        reset(conn, **kwargs)

    def cancel(*_args, **_kwargs) -> None:
        raise KeyboardInterrupt()

    cli_inputs(c, monkeypatch, [c["recovery_password"], c["password"], c["password"]])
    monkeypatch.setattr(reset_admin, "_reset_admin", retain_key)
    monkeypatch.setattr(db, "log_activity", cancel)
    assert reset_admin.main() == 130
    assert "dibatalkan" in capsys.readouterr().out
    assert retained == [bytearray(32)]
    assert snapshot(c["conn"]) == before
    assert not dongle._token_path(c["drive"]).exists()
