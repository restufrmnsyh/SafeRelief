"""Tes operasi admin untuk manajemen relawan dan pengelolaan kunci."""

import os
from pathlib import Path
from time import monotonic, sleep
from unittest.mock import Mock

import numpy as np
import pytest
from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from tests.face_camera import single_face, stream_frames


class FakeCameraWorker(QObject):
    """Worker kamera palsu untuk tes UI tanpa membuka perangkat keras."""

    frame_ready = Signal(QImage, float)
    camera_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def start(self) -> None:
        self._running = True
        image = QImage(
            np.zeros((80, 100, 3), dtype=np.uint8).tobytes(),
            100,
            80,
            100 * 3,
            QImage.Format.Format_RGB888,
        )
        self.frame_ready.emit(image, monotonic())

    def isRunning(self) -> bool:
        return self._running

    def requestInterruption(self) -> None:
        self._running = False

    def wait(self, timeout: int = 0) -> bool:
        return True

import config
from auth import dongle, face_auth, session, volunteers
from crypto import keys
from database import db, secure_store
from ui.face_enrollment_dialog import FaceEnrollmentDialog
from ui.volunteer_management_page import VolunteerFormDialog, VolunteerManagementPage


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Gunakan satu QApplication untuk tes widget."""
    return QApplication.instance() or QApplication([])


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


@pytest.mark.parametrize("is_active,username", [(1, "relawan1"), (0, "relawan1"), (1, "admin")])
def test_duplicate_username_is_reported_before_face_enrollment(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp: QApplication,
    is_active: int, username: str,
) -> None:
    """Username terpakai ditolak sebelum kamera dan penulisan dongle dimulai."""
    conn, _ = admin_context
    if username != "admin":
        db.insert_user(conn, {
            "nama_lengkap": "Relawan Satu", "username": username,
            "password_hash": "hash-uji", "role": "relawan", "is_active": is_active,
        })
    before = [dict(row) for row in db.list_users(conn)]
    monkeypatch.setattr(dongle, "find_removable_drives", lambda: ["Z:\\"])
    camera = Mock(side_effect=AssertionError("Kamera tidak boleh dibuka untuk username duplikat."))
    provision = Mock()
    monkeypatch.setattr(FaceEnrollmentDialog, "__init__", camera)
    monkeypatch.setattr(dongle, "provision_dongle", provision)

    def submit_form(form: VolunteerFormDialog) -> QDialog.DialogCode:
        form.name_input.setText("Relawan Baru")
        form.username_input.setText(f"  {username}  ")
        form.password_input.setText("password-awal")
        form.confirm_password_input.setText("password-awal")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(VolunteerFormDialog, "exec", submit_form)
    errors: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _p, _t, text: errors.append(text))
    page = VolunteerManagementPage(conn)
    try:
        page.add_button.click()
        assert errors == ["Username tersebut sudah digunakan."]
        camera.assert_not_called()
        provision.assert_not_called()
        assert [dict(row) for row in db.list_users(conn)] == before
        assert db.list_activity_log(conn) == []
        assert page._pending_volunteer is None
        assert page.add_button.isEnabled()
        assert page.status_label.text() == ""
    finally:
        page.close()
        page.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("late_duplicate", [False, True])
def test_multiple_volunteers_have_unique_usernames(
    admin_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    late_duplicate: bool,
) -> None:
    """Pendaftaran ganda ditolak, termasuk ketika username baru dipakai saat transaksi."""
    conn, _ = admin_context
    monkeypatch.setattr(dongle, "_token_path", lambda drive: Path(drive) / config.DONGLE_KEY_FILE)
    monkeypatch.setattr(dongle, "get_volume_serial", lambda drive: Path(drive).name)
    for username in ("relawan1", "relawan2"):
        drive = tmp_path / username
        drive.mkdir()
        volunteers.create_volunteer(
            conn, nama_lengkap=username, username=username, password="password-awal",
            posko_id=None, drive=str(drive), encoding=np.ones(128, dtype=np.float32),
        )
    assert len(volunteers.list_volunteers(conn)) == 2
    before = [dict(row) for row in db.list_users(conn)]
    logs_before = [dict(row) for row in db.list_activity_log(conn)]
    tokens_before = {path: path.read_bytes() for path in tmp_path.glob("*/.saferelief_key")}
    if late_duplicate:
        existing = db.get_user_by_username(conn, "relawan1")
        monkeypatch.setattr(db, "get_user_by_username", Mock(side_effect=[None, existing]))
    rejected_drive = tmp_path / "rejected-usb"
    rejected_drive.mkdir()
    with pytest.raises(ValueError, match="Username tersebut sudah digunakan"):
        volunteers.create_volunteer(
            conn, nama_lengkap="Relawan Ketiga", username="  relawan1  ",
            password="password-awal", posko_id=None, drive=str(rejected_drive),
            encoding=np.ones(128, dtype=np.float32),
        )
    assert [dict(row) for row in db.list_users(conn)] == before
    assert [dict(row) for row in db.list_activity_log(conn)] == logs_before
    assert all(path.read_bytes() == contents for path, contents in tokens_before.items())
    assert not list(rejected_drive.iterdir())
    assert not conn.in_transaction


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


def test_face_enrollment_preview_keeps_its_size_between_frames(
    monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    monkeypatch.setattr(FaceEnrollmentDialog, "_start_camera", lambda self: None)
    dialog = FaceEnrollmentDialog("Relawan Uji")
    dialog.show()
    try:
        qapp.processEvents()
        label = dialog.camera_label
        geometry = label.geometry()
        assert geometry.size() == QSize(320, 240)
        for width, height in [(640, 480), (480, 640), (1280, 720)]:
            image = QImage(width, height, QImage.Format.Format_RGB888)
            image.fill(0)
            dialog._display_frame(image, monotonic())
            qapp.processEvents()
            assert label.geometry() == geometry
            assert label.pixmap().size() == image.size().scaled(
                label.contentsRect().size(), Qt.AspectRatioMode.KeepAspectRatio
            )
    finally:
        dialog.close()


def test_face_enrollment_dialog_shows_live_feed_and_captures_encoding(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    conn, _ = admin_context

    monkeypatch.setattr(face_auth, "observe_face", single_face)
    monkeypatch.setattr(
        "ui.face_enrollment_dialog.CameraWorker",
        FakeCameraWorker,
    )
    monkeypatch.setattr(dongle, "get_volume_serial", lambda drive: "SERIAL-FAKE")
    monkeypatch.setattr(
        dongle,
        "_token_path",
        lambda drive: Path(drive) / config.DONGLE_KEY_FILE,
    )
    monkeypatch.setattr(
        dongle,
        "provision_dongle",
        lambda conn, drive, user_id, commit=False: b"a" * 32,
    )

    dialog = FaceEnrollmentDialog("Relawan Uji")
    assert dialog.camera_label.pixmap() is not None

    dialog.capture_face()
    timer = stream_frames(dialog)
    deadline = monotonic() + 5
    while dialog._capture_worker is not None and monotonic() < deadline:
        qapp.processEvents()
        sleep(0.005)
    timer.stop()
    assert dialog.capture_result is not None
    assert dialog.capture_result.shape == (128,)
    assert dialog.status_label.text() == "Wajah berhasil direkam!"

    user_id = volunteers.create_volunteer(
        conn,
        nama_lengkap="Relawan Uji",
        username="relawan-uji",
        password="password-awal",
        posko_id=None,
        drive="Z:",
        encoding=dialog.capture_result,
    )
    stored = secure_store.load_face_encoding(
        conn,
        keys.derive_key(session.get_master_key(), config.HKDF_LABEL_DB),
        user_id,
    )
    assert stored is not None
    dialog.stop_camera()


def test_face_enrollment_dialog_cancel_keeps_database_empty(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    conn, _ = admin_context
    monkeypatch.setattr(
        "ui.face_enrollment_dialog.CameraWorker",
        FakeCameraWorker,
    )
    dialog = FaceEnrollmentDialog("Relawan Batal")
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert db.get_user_by_username(conn, "relawan-batal") is None
    dialog.stop_camera()
