"""Regresi tata letak login dan kontrol native tanpa perangkat fisik."""

import os
from pathlib import Path
from time import monotonic, sleep

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit

from auth import dongle, face_auth, session
from crypto import hashing, keys
from database import db, secure_store
from tests.test_workspace import workspace_app
from tests.face_camera import mock_hand_camera, observe_pose, stream_poses
from ui.login_page import LoginPage


@pytest.fixture
def login_screen(tmp_path: Path, workspace_app, monkeypatch: pytest.MonkeyPatch):
    """Pakai pembungkus kunci asli; hanya kamera dan perangkat dongle diganti."""
    path = tmp_path / "login-ui.db"
    db.init_db(path)
    conn = db.get_connection(path)
    password = "Password-Uji-Login"
    master, token, salt = os.urandom(32), os.urandom(32), os.urandom(16)
    uid = db.insert_user(conn, {
        "nama_lengkap": "Admin Uji", "username": "admin-ui", "role": "admin",
        "password_hash": hashing.hash_password(password),
        "wrapped_master_key": keys.wrap_master_key(master, password, token, salt),
        "kdf_salt": salt,
    })
    monkeypatch.setattr(dongle, "verify_dongle", lambda _user: token)
    started: list[bool] = []
    monkeypatch.setattr(LoginPage, "_start_camera", lambda _self: started.append(True))
    page = LoginPage(conn)
    page.set_gate_status("Dongle valid terdeteksi")
    page.resize(980, 700)
    page.show()
    workspace_app.processEvents()
    yield page, conn, uid, password, master, started
    page.close()
    session.logout()
    page.deleteLater()
    workspace_app.processEvents()
    conn.close()


@pytest.mark.parametrize("width,height", [(360, 640), (480, 700), (720, 700), (980, 700), (1440, 900)])
def test_login_reflows_and_all_controls_remain_reachable(
    login_screen, workspace_app, width: int, height: int,
) -> None:
    """Form dan pesan panjang tidak keluar viewport, termasuk setelah preview masuk."""
    page, *_ = login_screen
    page.resize(width, height)
    page._set_message("Kamera tidak tersedia. Periksa izin kamera lalu periksa kembali akun Anda.")
    for _ in range(5):
        workspace_app.processEvents()
    assert page.scroll.horizontalScrollBar().maximum() == 0
    for widget in (page.username_input, page.password_input, page.submit_button, page.verify_face_button):
        page.scroll.ensureWidgetVisible(widget)
        workspace_app.processEvents()
        top = widget.mapTo(page.scroll.viewport(), QPoint(0, 0))
        assert top.x() >= 0
        assert top.x() + widget.width() <= page.scroll.viewport().width()
        assert top.y() >= 0
        assert top.y() + widget.height() <= page.scroll.viewport().height()
        assert widget.height() >= 44
    image = QImage(1920, 1080, QImage.Format.Format_RGB888)
    image.fill(Qt.GlobalColor.gray)
    page._display_frame(image, monotonic())
    workspace_app.processEvents()
    assert page.scroll.horizontalScrollBar().maximum() == 0
    assert page.password_input.echoMode() == QLineEdit.EchoMode.Password
    assert page.card_frame.grab().toImage().pixelColor(20, 20).name() == "#ffffff"
    page.resize(980, 700)
    workspace_app.processEvents()
    assert page.account_panel.isVisible()
    assert page.face_panel.isVisible()


def test_login_keyboard_empty_form_and_camera_failure(login_screen, workspace_app) -> None:
    """Tab dan Enter mengaktifkan kontrol asli, pesan tetap terbaca setelah error."""
    page, *_ = login_screen
    page.username_input.setFocus()
    QTest.keyClick(page.username_input, Qt.Key.Key_Tab)
    assert workspace_app.focusWidget() is page.password_input
    QTest.keyClick(page.password_input, Qt.Key.Key_Tab)
    assert workspace_app.focusWidget() is page.submit_button
    QTest.keyClick(page.submit_button, Qt.Key.Key_Return)
    assert page.message_label.text() == "Username dan password wajib diisi."
    assert not page.verify_face_button.isEnabled()
    page._camera_failed("Webcam tidak dapat dibuka.")
    workspace_app.processEvents()
    assert page.camera_label.text() == "Webcam tidak dapat dibuka."
    assert page.message_label.palette().color(QPalette.ColorRole.WindowText).name() == "#983a32"


@pytest.mark.parametrize("outcome", ["first_login", "existing_face", "wrong_password", "wrong_dongle"])
def test_account_action_preserves_authentication_order(
    login_screen, workspace_app, monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    """Tombol baru tetap memakai Argon2 dan KEK, lalu menunggu faktor wajah."""
    page, conn, uid, password, master, started = login_screen
    if outcome == "existing_face":
        secure_store.save_face_encoding(
            conn, keys.derive_key(master, b"db"), uid,
            face_auth.encoding_to_bytes(np.ones(128, dtype=np.float32)),
        )
    if outcome == "wrong_dongle":
        def reject(_user: dict) -> bytes:
            raise ValueError("Dongle tidak cocok dengan akun.")
        monkeypatch.setattr(dongle, "verify_dongle", reject)
    page.username_input.setText("admin-ui")
    page.password_input.setText("salah" if outcome == "wrong_password" else password)
    QTest.mouseClick(page.submit_button, Qt.MouseButton.LeftButton)
    workspace_app.processEvents()
    accepted = outcome in {"first_login", "existing_face"}
    assert bool(started) == accepted
    assert page.verify_face_button.isEnabled() == accepted
    assert not session.is_logged_in()
    assert page.password_input.text() == ""
    assert page.submit_button.isEnabled()
    assert not any(row["aksi"] == "LOGIN_SUCCESS" for row in db.list_activity_log(conn))
    if accepted:
        assert page._registration_mode == (outcome == "first_login")
        assert page.verify_face_button.text() == (
            "Daftarkan Wajah" if outcome == "first_login" else "Verifikasi Wajah"
        )
        if outcome == "existing_face":
            # Tombol harus menjalankan worker, bukan sekadar mengubah tampilannya.
            monkeypatch.setattr(face_auth, "observe_face", observe_pose)
            mock_hand_camera(monkeypatch)
            page._stored_encoding = -page._stored_encoding
            page._last_frame = np.zeros((32, 32, 3), dtype=np.uint8)
            page.verify_face_button.setFocus()
            QTest.keyClick(page.verify_face_button, Qt.Key.Key_Return)
            assert page._capture_worker is not None
            timer = stream_poses(page, page.message_label)
            deadline = monotonic() + 5
            while page._capture_worker is not None and monotonic() < deadline:
                workspace_app.processEvents()
                sleep(0.005)
            timer.stop()
            assert "Wajah tidak cocok" in page.message_label.text()
            assert page.verify_face_button.isEnabled()
        pending_key = page._transient_master_key
        page.set_gate_status("Mencari dongle...")
        assert pending_key == bytes(32)
        assert page._preauth_user is None
        assert not page.verify_face_button.isEnabled()
        assert "Kamera belum aktif" in page.camera_label.text()
    else:
        assert page.message_label.text()
        assert page._transient_master_key is None
