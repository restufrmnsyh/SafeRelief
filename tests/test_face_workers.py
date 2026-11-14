"""Tes worker wajah tanpa webcam, termasuk respons UI dan hasil setelah batal."""

import os
from pathlib import Path
from threading import Event, get_ident
from time import monotonic, sleep
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from auth import dongle, face_auth, session
from crypto import keys
from database import db
from ui.face_enrollment_dialog import FaceEnrollmentDialog
from ui.login_page import LoginPage


@pytest.fixture
def face_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Siapkan login pertama dan dialog relawan tanpa perangkat fisik."""
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "faces.db"
    db.init_db(path)
    conn = db.get_connection(path)
    uid = db.insert_user(conn, {
        "nama_lengkap": "Admin", "username": "admin", "role": "admin",
        "password_hash": "test-hash",
    })
    monkeypatch.setattr(FaceEnrollmentDialog, "_start_camera", lambda _self: None)
    monkeypatch.setattr(dongle, "verify_dongle", lambda _user: bytes(32))
    yield app, conn, uid
    session.logout()
    conn.close()


def process_until(app: QApplication, condition) -> None:
    """Beri Qt kesempatan mengirim queued signal dengan batas waktu tes."""
    deadline = monotonic() + 5
    while not condition() and monotonic() < deadline:
        app.processEvents()
        sleep(0.005)
    assert condition()


@pytest.mark.parametrize("outcome", ["success", "mismatch", "error", "dongle_missing", "blocked", "log_failure"])
def test_existing_face_logs_success_only_after_all_factors(
    face_context, monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    """Verifikasi gagal atau log gagal tidak boleh menghasilkan sesi sukses."""
    import sqlite3

    app, conn, uid = face_context
    page = LoginPage(conn)
    page._gate_open = True
    page._preauth_user = dict(db.get_user_by_id(conn, uid))
    page._transient_master_key = bytearray(os.urandom(32))
    emitted: list[dict] = []
    page.authenticated.connect(emitted.append)
    if outcome == "blocked":
        db.update_user_active(conn, uid, 0)
    if outcome == "dongle_missing":
        def missing(_user) -> bytes:
            raise ValueError("Dongle tidak tersedia")
        monkeypatch.setattr(dongle, "verify_dongle", missing)
    if outcome == "log_failure":
        def fail_log(*_args, **_kwargs) -> None:
            raise sqlite3.OperationalError("log unavailable")
        monkeypatch.setattr(db, "log_activity", fail_log)
    try:
        page._face_verification_finished(
            outcome != "mismatch", 0.9, "camera error" if outcome == "error" else "",
        )
        assert session.is_logged_in() == (outcome == "success")
        assert bool(emitted) == (outcome == "success")
        logs = [row for row in db.list_activity_log(conn) if row["aksi"] == "LOGIN_SUCCESS"]
        assert len(logs) == int(outcome == "success")
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("screen", ["login", "volunteer"])
@pytest.mark.parametrize("outcome", ["success", "error", "no_face", "cancel", "blocked"])
def test_face_capture_runs_off_ui_thread_and_ignores_cancelled_results(
    face_context, monkeypatch: pytest.MonkeyPatch, screen: str, outcome: str,
) -> None:
    """Inferensi tertahan tidak menghentikan timer UI atau menyimpan hasil sesi batal."""
    app, conn, uid = face_context
    entered, release = Event(), Event()
    threads: list[int] = []
    main_thread = get_ident()

    def detect(_frame: np.ndarray):
        threads.append(get_ident())
        entered.set()
        assert release.wait(5)
        if outcome == "error":
            raise cv2.error("simulated OpenCV failure")
        if outcome == "no_face":
            return None
        return np.ones(128, dtype=np.float32)

    monkeypatch.setattr(face_auth, "_detect_and_embed", detect)
    if screen == "login":
        page = LoginPage(conn)
        page._gate_open = True
        page._registration_mode = True
        page._preauth_user = dict(db.get_user_by_id(conn, uid))
        master = os.urandom(32)
        page._transient_master_key = bytearray(master)
        page._preauth_db_key = keys.derive_key(master, b"db")
    else:
        page = FaceEnrollmentDialog("Relawan")
        page._camera_worker = SimpleNamespace(
            isRunning=lambda: True, requestInterruption=lambda: None,
            wait=lambda _timeout: True,
        )
    page._last_frame = np.zeros((32, 32, 3), dtype=np.uint8)
    tick: list[bool] = []
    try:
        if screen == "login":
            page.register_current_face()
        else:
            page.capture_face()
        worker = page._capture_worker
        assert worker is not None
        process_until(app, entered.is_set)
        QTimer.singleShot(0, lambda: tick.append(True))
        process_until(app, lambda: bool(tick))
        assert all(thread != main_thread for thread in threads)
        if outcome == "cancel":
            if screen == "login":
                page._clear_pre_auth()
            else:
                page.reject()
        if outcome == "blocked" and screen == "login":
            db.update_user_active(conn, uid, 0)
        release.set()
        worker.wait(5000)
        process_until(app, lambda: page._capture_worker is None)
        app.processEvents()
        if screen == "login":
            stored = db.get_user_by_id(conn, uid)["face_encoding_enc"]
            assert (stored is not None) == (outcome == "success")
            assert session.is_logged_in() == (outcome == "success")
            success_logs = [r for r in db.list_activity_log(conn) if r["aksi"] == "LOGIN_SUCCESS"]
            assert len(success_logs) == int(outcome == "success")
            message = page.message_label.text()
        else:
            assert (page.capture_result is not None) == (outcome in {"success", "blocked"})
            message = page.status_label.text()
        if outcome == "error":
            assert "OpenCV failure" in message
        if outcome == "no_face":
            assert "tidak terdeteksi" in message
    finally:
        release.set()
        if page._capture_worker is not None:
            page._capture_worker.wait(5000)
        page.close()
        page.deleteLater()
        app.processEvents()
