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
from tests.face_camera import mock_hand_camera, observe_pose, stream_poses
from crypto import keys
from database import db
from ui.face_enrollment_dialog import FaceEnrollmentDialog
from ui.face_capture_worker import FaceCaptureWorker
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
    mock_hand_camera(monkeypatch)
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


@pytest.mark.parametrize("role", ["admin", "relawan"])
@pytest.mark.parametrize("outcome", ["success", "mismatch", "error", "dongle_missing", "blocked", "log_failure"])
def test_existing_face_logs_success_only_after_all_factors(
    face_context, monkeypatch: pytest.MonkeyPatch, outcome: str, role: str,
) -> None:
    """Verifikasi gagal atau log gagal tidak boleh menghasilkan sesi sukses."""
    import sqlite3

    app, conn, uid = face_context
    if role == "relawan":
        uid = db.insert_user(conn, {
            "nama_lengkap": "Relawan", "username": "relawan", "role": role,
            "password_hash": "test-hash",
        })
    page = LoginPage(conn)
    page._gate_open = True
    page._preauth_user = dict(db.get_user_by_id(conn, uid))
    page._transient_master_key = bytearray(os.urandom(32))
    page._stored_encoding = np.full(128, -1 if outcome == "mismatch" else 1, dtype=np.float32)
    page._last_frame = np.zeros((32, 32, 3), dtype=np.uint8)

    def observe(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if outcome == "error":
            raise cv2.error("camera error")
        return observe_pose(frame)

    monkeypatch.setattr(face_auth, "observe_face", observe)
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
    timer = stream_poses(page, page.message_label)
    try:
        page.verify_current_face()
        assert page._capture_worker is not None
        process_until(app, lambda: page._capture_worker is None)
        assert session.is_logged_in() == (outcome == "success")
        assert bool(emitted) == (outcome == "success")
        logs = [row for row in db.list_activity_log(conn) if row["aksi"] == "LOGIN_SUCCESS"]
        assert len(logs) == int(outcome == "success")
    finally:
        timer.stop()
        page.close()
        page.deleteLater()
        app.processEvents()


def test_expired_camera_frames_are_ignored_and_user_can_retry(face_context, monkeypatch):
    app, _, _ = face_context
    page = FaceEnrollmentDialog("Relawan")
    page._camera_worker = SimpleNamespace(
        isRunning=lambda: True, requestInterruption=lambda: None, wait=lambda _timeout: True,
    )
    observations = []

    def observe(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        observations.append(True)
        return observe_pose(frame)

    monkeypatch.setattr(face_auth, "observe_face", observe)
    monkeypatch.setattr(FaceCaptureWorker, "TIMEOUT_SECONDS", 0.4)
    timer = stream_poses(page, page.status_label, "stale")
    try:
        page.capture_button.click()
        process_until(app, lambda: page._capture_worker is None)
        assert not observations
        assert page.capture_result is None
        assert "Waktu pemeriksaan habis" in page.status_label.text()
        timer.stop()
        monkeypatch.setattr(FaceCaptureWorker, "TIMEOUT_SECONDS", 5)
        timer = stream_poses(page, page.status_label)
        page.capture_button.click()
        process_until(app, lambda: page._capture_worker is None)
        assert page.capture_result is not None
    finally:
        timer.stop()
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("box_on_left", [True, False])
def test_three_finger_challenge_requires_lowering_hand(face_context, monkeypatch, box_on_left: bool) -> None:
    app, conn, uid = face_context
    monkeypatch.setattr("ui.face_capture_worker.secrets.choice", lambda _: box_on_left)
    monkeypatch.setattr(face_auth, "observe_face", observe_pose)
    page = LoginPage(conn)
    page._gate_open = True
    page._preauth_user = dict(db.get_user_by_id(conn, uid))
    page._transient_master_key = bytearray(os.urandom(32))
    page._stored_encoding = np.ones(128, dtype=np.float32)
    page._last_frame = np.zeros((32, 32, 3), dtype=np.uint8)
    instructions: list[tuple[str, bool]] = []

    def record(message: str) -> None:
        instructions.append((message.split()[0], session.is_logged_in()))

    timer = stream_poses(page, page.message_label)
    try:
        page.verify_current_face()
        assert page._capture_worker.box_on_left is box_on_left
        page._capture_worker.instruction.connect(record)
        process_until(app, lambda: page._capture_worker is None)
        assert session.is_logged_in()
        responses = [step for step in instructions if step[0] != "Tatap"]
        assert responses == [("Angkat", False), ("Turunkan", False)]
    finally:
        timer.stop()
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("screen", ["login", "volunteer", "existing"])
@pytest.mark.parametrize("outcome", [
    "success", "error", "no_face", "cancel", "blocked", "static", "static_three", "two", "four",
    "never_return", "multiple_faces", "identity_changed", "photo_face", "fist", "unclear",
])
def test_face_capture_runs_off_ui_thread_and_ignores_cancelled_results(
    face_context, monkeypatch: pytest.MonkeyPatch, screen: str, outcome: str,
) -> None:
    """Inferensi tertahan tidak menghentikan timer UI atau menyimpan hasil sesi batal."""
    app, conn, uid = face_context
    entered, release = Event(), Event()
    threads: list[int] = []
    main_thread = get_ident()

    def detect(frame: np.ndarray):
        threads.append(get_ident())
        entered.set()
        assert release.wait(5)
        if outcome == "error":
            raise cv2.error("simulated OpenCV failure")
        if outcome == "no_face":
            return None
        encoding, points = observe_pose(frame)
        if int(frame[0, 0, 0]) != 128:
            if outcome == "multiple_faces":
                raise ValueError("Terdeteksi lebih dari satu wajah.")
            if outcome == "identity_changed":
                encoding = -encoding
        return encoding, points

    monkeypatch.setattr(face_auth, "observe_face", detect)
    expect_timeout = outcome in {"static", "static_three", "two", "four", "fist", "unclear", "never_return"}
    if expect_timeout:
        monkeypatch.setattr(FaceCaptureWorker, "TIMEOUT_SECONDS", 0.8)
    if screen != "volunteer":
        page = LoginPage(conn)
        page._gate_open = True
        page._registration_mode = screen == "login"
        if screen == "existing":
            page._stored_encoding = np.ones(128, dtype=np.float32)
        page._preauth_user = dict(db.get_user_by_id(conn, uid))
        master = os.urandom(32)
        page._transient_master_key = bytearray(master)
        page._preauth_db_key = keys.derive_key(master, b"db")
        page._last_frame = np.zeros((32, 32, 3), dtype=np.uint8)
    else:
        page = FaceEnrollmentDialog("Relawan")
        page._camera_worker = SimpleNamespace(
            isRunning=lambda: True, requestInterruption=lambda: None,
            wait=lambda _timeout: True,
        )
    label = page.status_label if screen == "volunteer" else page.message_label
    timer = stream_poses(page, label, outcome)
    tick: list[bool] = []
    try:
        if screen != "volunteer":
            page.verify_current_face()
        else:
            page.capture_face()
        worker = page._capture_worker
        assert worker is not None
        process_until(app, entered.is_set)
        QTimer.singleShot(0, lambda: tick.append(True))
        process_until(app, lambda: bool(tick))
        assert all(thread != main_thread for thread in threads)
        if outcome == "cancel":
            if screen != "volunteer":
                page._clear_pre_auth()
            else:
                page.reject()
        if outcome == "blocked" and screen != "volunteer":
            db.update_user_active(conn, uid, 0)
        release.set()
        process_until(app, lambda: page._capture_worker is None)
        if outcome == "cancel":
            worker.wait(5000)
        if screen != "volunteer":
            stored = db.get_user_by_id(conn, uid)["face_encoding_enc"]
            assert (stored is not None) == (outcome == "success" and screen == "login")
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
        if expect_timeout:
            assert "Waktu pemeriksaan habis" in message
        if outcome == "photo_face":
            assert "Wajah hidup belum terverifikasi" in message
        if outcome == "multiple_faces":
            assert "lebih dari satu wajah" in message
        if outcome == "identity_changed":
            assert "Wajah tidak cocok" in message
    finally:
        timer.stop()
        release.set()
        if page._capture_worker is not None:
            page._capture_worker.requestInterruption()
            page._capture_worker.wait(5000)
        page.close()
        page.deleteLater()
        app.processEvents()
