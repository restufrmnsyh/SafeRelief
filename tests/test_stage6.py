"""Integration tests for runtime logout, authorization, and demo seeding."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

import config
from auth import dongle, session, volunteers
from database import db, secure_store
from seed_demo import seed_demo_data
from ui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Create one offscreen Qt application for these integration tests."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def admin_context(tmp_path: Path):
    database_path = tmp_path / "stage6.db"
    db.init_db(database_path)
    conn = db.get_connection(database_path)
    admin_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Admin",
            "username": "admin",
            "password_hash": "test-hash",
            "role": "admin",
        },
    )
    volunteer_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Relawan",
            "username": "relawan",
            "password_hash": "test-hash",
            "role": "relawan",
        },
    )
    yield conn, admin_id, volunteer_id
    session.logout()
    conn.close()


@pytest.fixture
def single_admin_context(tmp_path: Path):
    database_path = tmp_path / "single-admin.db"
    db.init_db(database_path)
    conn = db.get_connection(database_path)
    admin_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Admin",
            "username": "admin",
            "password_hash": "test-hash",
            "role": "admin",
        },
    )
    yield conn, admin_id
    conn.close()


def test_dongle_timer_logs_out_and_removes_protected_pages(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp, tmp_path: Path
) -> None:
    conn, admin_id, _volunteer_id = admin_context
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "stage6.db")
    get_connection = db.get_connection
    monkeypatch.setattr(
        db, "get_connection", lambda: get_connection(config.DB_PATH)
    )
    dongle_present = {"value": False}
    monkeypatch.setattr(
        dongle,
        "is_any_valid_dongle_present",
        lambda _conn: dongle_present["value"],
    )

    def missing_dongle(_user) -> bytes:
        raise ValueError("dongle dicabut")

    monkeypatch.setattr(dongle, "verify_dongle", missing_dongle)
    window = MainWindow()
    assert window.pages.currentWidget() is window.gate_page
    assert window.gate_status.text() == "Mencari dongle..."
    dongle_present["value"] = True
    window._check_dongle()
    assert window.pages.currentWidget() is window.login_page
    assert window.login_page.gate_label.text() == "✔ Dongle Valid Terdeteksi"

    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        os.urandom(config.MASTER_KEY_LENGTH),
    )
    window._show_dashboard(session.get_current_user())
    assert window.dashboard_page is not None
    window._open_page("victims")
    assert window.victims_page is not None
    assert window.pages.currentWidget() is window.victims_page
    window._open_page("aid")
    assert window.aid_page is not None
    assert window.pages.currentWidget() is window.aid_page
    dongle_present["value"] = False
    window._check_dongle()

    assert not session.is_logged_in()
    assert window.dashboard_page is None
    assert window.pages.currentWidget() is window.gate_page
    assert window.gate_status.text() == "Dongle dicabut, sesi diakhiri"
    window.close()
    qapp.processEvents()


def test_dashboard_exposes_role_based_navigation_buttons(
    admin_context, qapp
) -> None:
    conn, admin_id, _volunteer_id = admin_context
    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        os.urandom(config.MASTER_KEY_LENGTH),
    )
    window = MainWindow()
    window._show_dashboard(session.get_current_user())

    assert window.dashboard_page is not None
    button_texts = {
        button.text()
        for button in window.dashboard_page.findChildren(QPushButton)
        if isinstance(button, QPushButton)
    }
    assert "Data Korban" in button_texts
    assert "Manajemen Relawan" in button_texts
    assert "Chat Koordinasi" in button_texts
    assert "Dokumentasi Foto" in button_texts
    assert "Berkas Laporan" in button_texts
    assert "Distribusi Bantuan" in button_texts
    assert "Log Aktivitas" in button_texts
    assert "Panel Demo" in button_texts

    triggered: list[str] = []
    window.dashboard_page.page_requested.connect(triggered.append)
    for button in window.dashboard_page.findChildren(QPushButton):
        if button.text() == "Data Korban":
            button.click()
            break
    assert triggered == ["victims"]
    window.close()
    qapp.processEvents()


def test_disabled_admin_cannot_continue_admin_operations(admin_context) -> None:
    conn, admin_id, _volunteer_id = admin_context
    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        os.urandom(config.MASTER_KEY_LENGTH),
    )
    db.update_user_active(conn, admin_id, 0)

    with pytest.raises(PermissionError, match="sudah diblokir"):
        volunteers.list_volunteers(conn)
    with pytest.raises(PermissionError, match="sudah diblokir"):
        secure_store.append_aid_block(
            conn,
            admin_id,
            {
                "jenis": "beras",
                "jumlah": 1,
                "dari": "gudang",
                "ke": "posko",
                "petugas": "admin",
            },
        )


def test_dongle_timer_ends_session_when_account_is_blocked(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp, tmp_path: Path
) -> None:
    conn, admin_id, _volunteer_id = admin_context
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "stage6.db")
    get_connection = db.get_connection
    monkeypatch.setattr(
        db, "get_connection", lambda: get_connection(config.DB_PATH)
    )
    monkeypatch.setattr(dongle, "is_any_valid_dongle_present", lambda _conn: True)
    window = MainWindow()
    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        os.urandom(config.MASTER_KEY_LENGTH),
    )
    window._show_dashboard(session.get_current_user())
    db.update_user_active(conn, admin_id, 0)

    window._check_dongle()

    assert not session.is_logged_in()
    assert window.pages.currentWidget() is window.login_page
    assert window.login_page.message_label.text() == (
        "Akun dinonaktifkan, sesi diakhiri"
    )
    window.close()
    qapp.processEvents()


def test_disabled_chat_participant_rejects_next_message(admin_context) -> None:
    conn, admin_id, volunteer_id = admin_context
    db.update_user_active(conn, volunteer_id, 0)
    with pytest.raises(PermissionError, match="sudah diblokir"):
        secure_store.save_message(conn, admin_id, volunteer_id, b"ciphertext")
    assert db.get_messages_between(conn, admin_id, volunteer_id) == []


def test_seed_demo_is_atomic_and_creates_requested_fictional_records(
    single_admin_context, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn, admin_id = single_admin_context
    # Avoid expensive password hashing for throwaway inactive demo accounts.
    monkeypatch.setattr(
        "seed_demo.hashing.hash_password", lambda _password: "demo-hash"
    )
    seed_demo_data(
        conn,
        {"id": admin_id, "role": "admin"},
        os.urandom(config.MASTER_KEY_LENGTH),
    )

    assert conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = ? AND is_active = 0",
        ("relawan",),
    ).fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM victims").fetchone()[0] == 10
    assert db.count_blocks(conn) == 6  # Genesis plus five aid distributions.
    assert secure_store.load_blockchain(conn).is_valid() == (True, None)


def test_seed_demo_refuses_populated_database_without_partial_records(
    single_admin_context, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn, admin_id = single_admin_context
    db.insert_posko(conn, {"nama": "Existing", "lokasi": "Existing"})
    monkeypatch.setattr(
        "seed_demo.hashing.hash_password", lambda _password: "demo-hash"
    )

    with pytest.raises(ValueError, match="seed dibatalkan"):
        seed_demo_data(
            conn,
            {"id": admin_id, "role": "admin"},
            os.urandom(config.MASTER_KEY_LENGTH),
        )
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM victims").fetchone()[0] == 0
    assert db.count_blocks(conn) == 0
