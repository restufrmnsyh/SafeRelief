"""Integration tests for runtime logout, authorization, and demo seeding."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

import config
from auth import dongle, session, volunteers
from database import db, secure_store
from seed_demo import seed_demo_data
from ui.main_window import MainWindow
from ui.face_enrollment_dialog import FaceEnrollmentDialog
from ui.victims_page import VictimDetailDialog
from ui.volunteer_management_page import DongleChangeDialog, VolunteerFormDialog


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
    assert window.login_page.gate_label.text() == "Dongle valid terdeteksi"

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


@pytest.mark.parametrize("reason", ["manual", "dongle_removed", "blocked", "close"])
def test_end_session_after_opening_volunteers_cancels_enrollment(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp, tmp_path: Path,
    reason: str,
) -> None:
    """Semua jalur keluar tetap membersihkan halaman relawan dan dialog wajah."""
    from types import SimpleNamespace

    conn, admin_id, _volunteer_id = admin_context
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "stage6.db")
    monkeypatch.setattr(dongle, "is_any_valid_dongle_present", lambda _conn: True)
    monkeypatch.setattr(FaceEnrollmentDialog, "_start_camera", lambda _self: None)
    window = MainWindow()
    session.login(dict(db.get_user_by_id(conn, admin_id)), os.urandom(32))
    window._show_dashboard(session.get_current_user())
    window._open_page("volunteers")
    page = window.volunteer_page
    assert page is not None
    page._pending_volunteer = {"password": "transient-test-password"}
    dialog = FaceEnrollmentDialog("Relawan", parent=page)
    calls: list[str] = []
    dialog._camera_worker = SimpleNamespace(
        requestInterruption=lambda: calls.append("interrupt"),
        wait=lambda _timeout: calls.append("wait"),
    )
    dialog.rejected.connect(lambda: calls.append("rejected"))
    dialog.show()
    try:
        if reason == "manual":
            window._end_session("Logout manual")
        elif reason == "close":
            window.close()
        else:
            if reason == "blocked":
                db.update_user_active(conn, admin_id, 0)
            else:
                def missing_dongle(_user) -> bytes:
                    raise ValueError("dongle dicabut")
                monkeypatch.setattr(dongle, "verify_dongle", missing_dongle)
            window._check_dongle()
        assert not session.is_logged_in()
        assert window.volunteer_page is None
        assert window.dashboard_page is None
        assert page._pending_volunteer is None
        assert page.table.rowCount() == 0
        assert dialog._camera_worker is None
        assert calls[:2] == ["interrupt", "wait"]
        assert "rejected" in calls
        assert not dialog.isVisible()
        logout_logs = [row for row in db.list_activity_log(conn) if row["aksi"] == "LOGOUT"]
        assert len(logout_logs) == 1
        assert logout_logs[0]["user_id"] == admin_id
        assert logout_logs[0]["detail"] == {
            "manual": "manual", "close": "window_closed",
            "blocked": "account_inactive", "dongle_removed": "dongle_removed",
        }[reason]
        if reason != "close":
            assert window.pages.currentWidget() in (window.gate_page, window.login_page)
    finally:
        window.close()
        qapp.processEvents()


@pytest.mark.parametrize("reason", ["manual", "dongle_removed", "blocked"])
def test_end_session_rejects_all_visible_dialogs_before_discarding_pages(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp, tmp_path: Path, reason: str,
) -> None:
    """Formulir dan popup mengambang harus batal sebelum induknya dihapus."""
    conn, admin_id, _volunteer_id = admin_context
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "stage6.db")
    monkeypatch.setattr(dongle, "is_any_valid_dongle_present", lambda _conn: True)
    monkeypatch.setattr(dongle, "verify_dongle", lambda _user: bytes(32))
    window = MainWindow()
    session.login(dict(db.get_user_by_id(conn, admin_id)), os.urandom(32))
    window._show_dashboard(session.get_current_user())
    window._open_page("victims")
    page = window.victims_page
    detail = VictimDetailDialog({}, {"nik": b"ciphertext", "kondisi_medis": b"ciphertext"}, page)
    detail.show_plaintext({"nik": "NIK-UJI", "kondisi_medis": "Data medis uji"})
    page._detail_dialog = detail
    detail.finished.connect(page._reset_detail_dialog)
    form = VolunteerFormDialog([], ["Z:\\"], parent=window)
    replacement = DongleChangeDialog(["Z:\\"], parent=form)
    confirmation = QMessageBox(
        QMessageBox.Icon.Question, "Konfirmasi", "Simpan perubahan?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, window,
    )
    confirmation.setDefaultButton(QMessageBox.StandardButton.Yes)
    dialogs = [detail, form, replacement, confirmation]
    hidden = QDialog(window)
    accepted, rejected, hidden_rejected = [], [], []
    hidden.rejected.connect(lambda: hidden_rejected.append(True))
    for dialog in dialogs:
        dialog.accepted.connect(lambda: accepted.append(True))
        dialog.rejected.connect(lambda: rejected.append(True))
        dialog.setModal(True)
        dialog.show()
    discard = window._discard_authenticated_pages

    def discard_after_dialogs_are_rejected() -> None:
        assert all(not dialog.isVisible() for dialog in dialogs)
        assert not session.is_logged_in()
        discard()

    monkeypatch.setattr(window, "_discard_authenticated_pages", discard_after_dialogs_are_rejected)
    try:
        qapp.processEvents()
        assert all(dialog.isVisible() for dialog in dialogs)
        assert detail._table.item(0, 2).text() == "NIK-UJI"
        if reason == "manual":
            window._end_session("Logout manual")
        else:
            if reason == "blocked":
                db.update_user_active(conn, admin_id, 0)
            else:
                monkeypatch.setattr(dongle, "is_any_valid_dongle_present", lambda _conn: False)

                def missing_dongle(_user) -> bytes:
                    raise ValueError("Dongle dicabut")

                monkeypatch.setattr(dongle, "verify_dongle", missing_dongle)
            window._check_dongle()
        assert all(not dialog.isVisible() for dialog in dialogs)
        assert all(dialog.result() == QDialog.DialogCode.Rejected for dialog in dialogs)
        assert accepted == []
        assert len(rejected) == len(dialogs)
        assert hidden_rejected == []
        assert detail._table.item(0, 2).text() == ""
        assert detail._table.isColumnHidden(2)
        assert window.dashboard_page is None
        assert window.victims_page is None
        assert not session.is_logged_in()
        assert window.pages.currentWidget() in (window.gate_page, window.login_page)
    finally:
        for dialog in dialogs:
            dialog.reject()
        hidden.reject()
        window.close()
        qapp.processEvents()


def test_forced_enrollment_rejection_stops_running_camera_before_discard(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp, tmp_path: Path,
) -> None:
    """Reject global harus menjalankan stop kamera meski dialog tidak dimiliki halaman relawan."""
    from PySide6.QtTest import QTest

    class CameraUntilCancelled(QThread):
        """Simulasikan thread kamera aktif tanpa membuka perangkat fisik."""

        def run(self) -> None:
            while not self.isInterruptionRequested():
                self.msleep(5)

    conn, admin_id, _volunteer_id = admin_context
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "stage6.db")
    monkeypatch.setattr(dongle, "is_any_valid_dongle_present", lambda _conn: True)
    monkeypatch.setattr(dongle, "verify_dongle", lambda _user: bytes(32))
    monkeypatch.setattr(FaceEnrollmentDialog, "_start_camera", lambda _self: None)
    window = MainWindow()
    session.login(dict(db.get_user_by_id(conn, admin_id)), os.urandom(32))
    window._show_dashboard(session.get_current_user())
    dialog = FaceEnrollmentDialog("Relawan Uji", parent=window)
    camera = CameraUntilCancelled(dialog)
    dialog._camera_worker = camera
    camera.start()
    dialog.setModal(True)
    dialog.show()
    rejected = []
    dialog.rejected.connect(lambda: rejected.append(camera.isRunning()))
    discard = window._discard_authenticated_pages

    def discard_after_camera_stops() -> None:
        assert not dialog.isVisible()
        assert dialog._camera_worker is None
        assert camera.isFinished()
        discard()

    monkeypatch.setattr(window, "_discard_authenticated_pages", discard_after_camera_stops)
    try:
        QTest.qWait(20)
        assert camera.isRunning()
        assert dialog.isVisible()
        window._end_session("Dongle dicabut, sesi diakhiri", "dongle_removed")
        assert not dialog.isVisible()
        assert dialog.result() == QDialog.DialogCode.Rejected
        assert rejected == [False]
        assert not camera.isRunning()
        assert dialog.capture_result is None
        assert not session.is_logged_in()
    finally:
        camera.requestInterruption()
        camera.wait(2000)
        dialog.reject()
        window.close()
        qapp.processEvents()


def test_logout_clears_session_even_when_activity_log_fails(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp, tmp_path: Path,
) -> None:
    """Gangguan SQLite tidak boleh menghalangi pembersihan sesi dan halaman."""
    import sqlite3
    from auth import login

    conn, admin_id, _volunteer_id = admin_context
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "stage6.db")
    monkeypatch.setattr(dongle, "is_any_valid_dongle_present", lambda _conn: True)
    window = MainWindow()
    session.login(dict(db.get_user_by_id(conn, admin_id)), os.urandom(32))
    window._show_dashboard(session.get_current_user())

    def fail_log(*_args) -> None:
        raise sqlite3.OperationalError("log unavailable")

    monkeypatch.setattr(login, "logout", fail_log)
    try:
        window._end_session("Logout manual")
        assert not session.is_logged_in()
        assert window.dashboard_page is None
        assert window.pages.currentWidget() is window.login_page
        assert "gagal disimpan" in window.statusBar().currentMessage()
    finally:
        window.close()
        qapp.processEvents()


def test_dashboard_exposes_role_based_navigation_buttons(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp, tmp_path: Path
) -> None:
    conn, admin_id, _volunteer_id = admin_context
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "stage6.db")
    get_connection = db.get_connection
    monkeypatch.setattr(
        db, "get_connection", lambda: get_connection(config.DB_PATH)
    )
    window = MainWindow()
    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        os.urandom(config.MASTER_KEY_LENGTH),
    )
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


def test_dashboard_manual_logout_confirms_and_returns_to_gate(
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

    logout_called = {"value": False}
    real_logout = session.logout

    def spy_logout() -> None:
        logout_called["value"] = True
        real_logout()

    monkeypatch.setattr(session, "logout", spy_logout)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    assert window.dashboard_page is not None
    assert window.dashboard_page.logout_button.text() == "Logout"
    window.dashboard_page.logout_button.click()

    assert logout_called["value"] is True
    assert not session.is_logged_in()
    assert window.pages.currentWidget() in (window.gate_page, window.login_page)
    window.close()
    qapp.processEvents()


def test_feature_page_logout_starts_session_end(
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
    window._open_page("victims")

    logout_called = {"value": False}
    real_logout = session.logout

    def spy_logout() -> None:
        logout_called["value"] = True
        real_logout()

    monkeypatch.setattr(session, "logout", spy_logout)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    assert window.victims_page is not None
    assert hasattr(window.victims_page, "logout_button")
    window.victims_page.logout_button.click()

    assert logout_called["value"] is True
    assert not session.is_logged_in()
    assert window.pages.currentWidget() in (window.gate_page, window.login_page)
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
