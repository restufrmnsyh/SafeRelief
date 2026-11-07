"""Tes operasi admin untuk manajemen relawan dan pengelolaan kunci."""

import os
from pathlib import Path

import numpy as np
import pytest

import config
from auth import dongle, session, volunteers
from crypto import keys
from database import db, secure_store


@pytest.fixture
def admin_context(tmp_path: Path):
    database_path = tmp_path / "volunteers.db"
    db.init_db(database_path)
    conn = db.get_connection(database_path)
    admin_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Admin",
            "username": "admin",
            "password_hash": "admin-hash",
            "role": "admin",
        },
    )
    master_key = os.urandom(config.MASTER_KEY_LENGTH)
    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        master_key,
    )
    yield conn, master_key
    session.logout()
    conn.close()


def test_admin_can_create_update_and_replace_volunteer_dongle(
    admin_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn, master_key = admin_context
    first_usb = tmp_path / "usb-one"
    second_usb = tmp_path / "usb-two"
    first_usb.mkdir()
    second_usb.mkdir()
    serials = {str(first_usb): "SERIAL-ONE", str(second_usb): "SERIAL-TWO"}
    monkeypatch.setattr(
        dongle, "get_volume_serial", lambda drive: serials[str(drive)]
    )
    monkeypatch.setattr(
        dongle,
        "_token_path",
        lambda drive: Path(drive) / config.DONGLE_KEY_FILE,
    )

    user_id = volunteers.create_volunteer(
        conn,
        nama_lengkap="Relawan Satu",
        username="relawan1",
        password="password-awal",
        posko_id=None,
        drive=str(first_usb),
        encoding=np.ones(128, dtype=np.float32),
    )
    user = db.get_user_by_id(conn, user_id)
    assert user is not None
    assert user["role"] == "relawan"
    assert user["dongle_serial"] == "SERIAL-ONE"
    assert secure_store.load_face_encoding(
        conn,
        keys.derive_key(master_key, config.HKDF_LABEL_DB),
        user_id,
    ) is not None

    first_token = dongle.read_token(str(first_usb))
    def verify_first_user(user) -> bytes:
        assert user["id"] == user_id
        return first_token

    monkeypatch.setattr(dongle, "verify_dongle", verify_first_user)
    volunteers.update_volunteer(
        conn,
        user_id,
        nama_lengkap="Relawan Diperbarui",
        username="relawan1",
        posko_id=None,
        new_password="password-baru",
    )
    user = db.get_user_by_id(conn, user_id)
    assert user is not None
    assert user["nama_lengkap"] == "Relawan Diperbarui"
    assert keys.unwrap_master_key(
        bytes(user["wrapped_master_key"]),
        "password-baru",
        first_token,
        bytes(user["kdf_salt"]),
    ) == master_key

    volunteers.set_volunteer_active(conn, user_id, False)
    assert db.get_user_by_id(conn, user_id)["is_active"] == 0
    volunteers.set_volunteer_active(conn, user_id, True)

    volunteers.replace_volunteer_dongle(
        conn, user_id, str(second_usb), "password-dongle-baru"
    )
    user = db.get_user_by_id(conn, user_id)
    assert user is not None
    assert user["dongle_serial"] == "SERIAL-TWO"
    second_token = dongle.read_token(str(second_usb))
    assert keys.unwrap_master_key(
        bytes(user["wrapped_master_key"]),
        "password-dongle-baru",
        second_token,
        bytes(user["kdf_salt"]),
    ) == master_key


def test_volunteer_management_requires_admin(admin_context) -> None:
    conn, master_key = admin_context
    assert len(master_key) == config.MASTER_KEY_LENGTH
    session.login(
        {"id": 99, "username": "relawan", "role": "relawan"},
        os.urandom(config.MASTER_KEY_LENGTH),
    )

    with pytest.raises(PermissionError, match="Hanya admin"):
        volunteers.list_volunteers(conn)


def test_failed_dongle_provision_rolls_back_volunteer(
    admin_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn, master_key = admin_context
    assert len(master_key) == config.MASTER_KEY_LENGTH
    usb = tmp_path / "failed-usb"
    usb.mkdir()

    def token_path(drive: str) -> Path:
        assert drive == str(usb)
        return Path(drive) / config.DONGLE_KEY_FILE

    def fail_serial(drive: str) -> str:
        assert drive == str(usb)
        raise OSError("serial tidak tersedia")

    monkeypatch.setattr(dongle, "_token_path", token_path)
    monkeypatch.setattr(dongle, "get_volume_serial", fail_serial)

    with pytest.raises(OSError, match="serial tidak tersedia"):
        volunteers.create_volunteer(
            conn,
            nama_lengkap="Relawan Gagal",
            username="gagal",
            password="password-awal",
            posko_id=None,
            drive=str(usb),
            encoding=np.ones(128, dtype=np.float32),
        )

    assert db.get_user_by_username(conn, "gagal") is None
    assert not (usb / config.DONGLE_KEY_FILE).exists()
