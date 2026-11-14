"""Halaman admin untuk membuat dan mengelola akun relawan."""

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from auth import dongle, session, volunteers
from database import db
from ui.face_enrollment_dialog import FaceEnrollmentDialog
from ui.workspace import style_dialog


class VolunteerFormDialog(QDialog):
    """Dialog profil relawan; password reset opsional ketika mengedit."""

    def __init__(
        self,
        poskoes: list[dict],
        drives: list[str] | None = None,
        volunteer: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._is_new = volunteer is None
        self.setWindowTitle(
            "Tambah Relawan" if self._is_new else "Edit Relawan"
        )
        self.name_input = QLineEdit()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.posko_input = QComboBox()
        self.posko_input.addItem("Tidak ditentukan", None)
        for post in poskoes:
            self.posko_input.addItem(post["nama"], post["id"])
        self.drive_input: QComboBox | None = None

        form = QFormLayout(self)
        form.addRow("Nama lengkap", self.name_input)
        form.addRow("Username", self.username_input)
        if self._is_new:
            self.drive_input = QComboBox()
            for drive in drives or []:
                self.drive_input.addItem(drive, drive)
            form.addRow("Dongle USB", self.drive_input)
            form.addRow("Password awal", self.password_input)
            form.addRow("Konfirmasi password", self.confirm_password_input)
        else:
            form.addRow("Password baru (opsional)", self.password_input)
            form.addRow("Konfirmasi password baru", self.confirm_password_input)
        form.addRow("Posko", self.posko_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if volunteer:
            self.name_input.setText(str(volunteer.get("nama_lengkap") or ""))
            self.username_input.setText(str(volunteer.get("username") or ""))
            self.posko_input.setCurrentIndex(
                max(0, self.posko_input.findData(volunteer.get("posko_id")))
            )
        style_dialog(self)

    def values(self) -> dict[str, object]:
        name = self.name_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirmation = self.confirm_password_input.text()
        if not name or not username:
            raise ValueError("Nama lengkap dan username wajib diisi.")
        if self._is_new and not password:
            raise ValueError("Password awal wajib diisi.")
        if password and password != confirmation:
            raise ValueError("Konfirmasi password tidak cocok.")
        if password and len(password) < 8:
            raise ValueError("Password minimal 8 karakter.")
        return {
            "nama_lengkap": name,
            "username": username,
            "password": password or None,
            "posko_id": self.posko_input.currentData(),
            "drive": self.drive_input.currentData() if self.drive_input else None,
        }


class DongleChangeDialog(QDialog):
    """Dialog pilihan drive baru dan password baru untuk KEK relawan."""

    def __init__(self, drives: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ganti Dongle Relawan")
        self.drive_input = QComboBox()
        self.drive_input.addItems(drives)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        form = QFormLayout(self)
        form.addRow("Dongle USB baru", self.drive_input)
        form.addRow("Password relawan baru", self.password_input)
        form.addRow("Konfirmasi password", self.confirm_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        style_dialog(self)

    def values(self) -> tuple[str, str]:
        password = self.password_input.text()
        if len(password) < 8:
            raise ValueError("Password baru minimal 8 karakter.")
        if password != self.confirm_input.text():
            raise ValueError("Konfirmasi password tidak cocok.")
        return self.drive_input.currentText(), password


class VolunteerManagementPage(QWidget):
    """Daftar relawan dan aksi admin; akses juga dijaga pada lapisan auth."""

    dashboard_requested = Signal()

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        if session.get_current_user().get("role") != "admin":
            raise PermissionError("Halaman ini hanya untuk admin.")
        self._conn = conn
        self._pending_volunteer: dict[str, object] | None = None

        self.setStyleSheet(
            "QWidget { background: #edf5fb; color: #1E2A39; }"
            "QLabel { color: #1E2A39; }"
            "QTableWidget, QLineEdit, QComboBox, QSpinBox { background: #f9fcff; border: 1px solid #dfeaf5; border-radius: 10px; }"
            "QPushButton { background-color: #ffffff; color: #1E2A39; border: 1px solid #dfeaf5; border-radius: 12px; padding: 8px 12px; font-weight: 700; }"
            "QPushButton:hover { background-color: #eef7ff; border-color: #bfdcf0; }"
        )

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ("Nama", "Username", "Posko", "Status", "ID")
        )
        self.table.setColumnHidden(4, True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.add_button = QPushButton("Tambah Relawan")
        self.add_button.clicked.connect(self.add_volunteer)
        self.edit_button = QPushButton("Edit / Reset Password")
        self.edit_button.clicked.connect(self.edit_volunteer)
        self.active_button = QPushButton("Aktifkan / Blokir")
        self.active_button.clicked.connect(self.toggle_active)
        self.dongle_button = QPushButton("Ganti Dongle")
        self.dongle_button.clicked.connect(self.replace_dongle)
        self.delete_button = QPushButton("Hapus")
        self.delete_button.clicked.connect(self.delete_volunteer)
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)
        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(self._confirm_logout)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        actions = QHBoxLayout()
        for button in (
            self.add_button,
            self.edit_button,
            self.active_button,
            self.dongle_button,
            self.delete_button,
        ):
            actions.addWidget(button)
        footer = QHBoxLayout()
        footer.addWidget(self.status_label, stretch=1)
        footer.addWidget(self.back_button)
        footer.addWidget(self.logout_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Manajemen Relawan"))
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(actions)
        layout.addLayout(footer)
        self.refresh()

    def _confirm_logout(self) -> None:
        """Minta konfirmasi sebelum logout dari halaman relawan."""
        window = self.window()
        if window is None or not hasattr(window, "_end_session"):
            return
        reply = QMessageBox.question(
            self,
            "Logout",
            "Yakin ingin logout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            window._end_session("Logout manual dari halaman relawan.")

    def refresh(self) -> None:
        """Tampilkan profil relawan tanpa mengekspos kredensial atau key."""
        try:
            posts = {
                int(post["id"]): str(post["nama"])
                for post in volunteers.list_posko(self._conn)
            }
            rows = volunteers.list_volunteers(self._conn)
        except (PermissionError, sqlite3.Error) as exc:
            self.status_label.setText(str(exc))
            return

        self.table.setRowCount(0)
        for user in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                user.get("nama_lengkap"),
                user.get("username"),
                posts.get(user.get("posko_id"), "-"),
                "Aktif" if user.get("is_active") else "Diblokir",
                user.get("id"),
            )
            for column, value in enumerate(values):
                self.table.setItem(
                    row, column, QTableWidgetItem("" if value is None else str(value))
                )
        self.table.resizeColumnsToContents()

    def _selected_volunteer(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Manajemen Relawan", "Pilih relawan terlebih dahulu."
            )
            return None
        user_id = int(self.table.item(row, 4).text())
        return next(
            (
                user
                for user in volunteers.list_volunteers(self._conn)
                if user["id"] == user_id
            ),
            None,
        )

    def add_volunteer(self) -> None:
        try:
            drives = dongle.find_removable_drives()
            if not drives:
                raise ValueError("Tidak ada removable USB yang terdeteksi.")
            form = VolunteerFormDialog(
                volunteers.list_posko(self._conn), drives=drives, parent=self
            )
            if form.exec() != QDialog.DialogCode.Accepted:
                return
            data = form.values()
            self._pending_volunteer = data
            self.add_button.setEnabled(False)
            self.status_label.setText(
                "Pendaftaran wajah: posisikan relawan di depan kamera..."
            )
            enrollment = FaceEnrollmentDialog(
                str(data["nama_lengkap"]), parent=self
            )
            if enrollment.exec() != QDialog.DialogCode.Accepted:
                self._pending_volunteer = None
                self.add_button.setEnabled(True)
                self.status_label.setText("Pendaftaran relawan dibatalkan.")
                return
            encoding = enrollment.capture_result
            self._pending_volunteer = None
            self.add_button.setEnabled(True)
            if encoding is None:
                self.status_label.setText("")
                QMessageBox.critical(
                    self, "Pendaftaran gagal", "Wajah belum direkam."
                )
                return

            volunteers.create_volunteer(
                self._conn,
                nama_lengkap=str(data["nama_lengkap"]),
                username=str(data["username"]),
                password=str(data["password"]),
                posko_id=data["posko_id"],
                drive=str(data["drive"]),
                encoding=encoding,
            )
            self.status_label.setText("Relawan berhasil didaftarkan.")
            self.refresh()
        except (PermissionError, ValueError, OSError, sqlite3.Error) as exc:
            self._pending_volunteer = None
            self.add_button.setEnabled(True)
            self.status_label.setText("")
            QMessageBox.critical(self, "Gagal membuat relawan", str(exc))

    def edit_volunteer(self) -> None:
        user = self._selected_volunteer()
        if user is None:
            return
        try:
            dialog = VolunteerFormDialog(
                volunteers.list_posko(self._conn), volunteer=user, parent=self
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()
            volunteers.update_volunteer(
                self._conn,
                int(user["id"]),
                nama_lengkap=str(values["nama_lengkap"]),
                username=str(values["username"]),
                posko_id=values["posko_id"],
                new_password=values["password"],
            )
            self.status_label.setText("Data relawan berhasil diperbarui.")
            self.refresh()
        except (PermissionError, ValueError, OSError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Gagal mengedit relawan", str(exc))

    def toggle_active(self) -> None:
        user = self._selected_volunteer()
        if user is None:
            return
        activating = not bool(user["is_active"])
        action = "mengaktifkan" if activating else "memblokir"
        answer = QMessageBox.question(
            self,
            "Konfirmasi",
            f"Yakin ingin {action} relawan {user['username']}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            volunteers.set_volunteer_active(
                self._conn, int(user["id"]), activating
            )
            self.refresh()
        except (PermissionError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Gagal mengubah status", str(exc))

    def replace_dongle(self) -> None:
        user = self._selected_volunteer()
        if user is None:
            return
        try:
            drives = dongle.find_removable_drives()
            if not drives:
                raise ValueError("Tidak ada removable USB yang terdeteksi.")
            dialog = DongleChangeDialog(drives, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            drive, new_password = dialog.values()
            volunteers.replace_volunteer_dongle(
                self._conn, int(user["id"]), drive, new_password
            )
            self.status_label.setText(
                "Dongle diganti dan password relawan diperbarui."
            )
            self.refresh()
        except (PermissionError, ValueError, OSError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Gagal mengganti dongle", str(exc))

    def delete_volunteer(self) -> None:
        """Hapus akun relawan permanen dengan peringatan dampak schema."""
        user = self._selected_volunteer()
        if user is None:
            return
        username = str(user.get("username") or "-")
        answer = QMessageBox.question(
            self,
            "Konfirmasi hapus relawan",
            "Yakin ingin menghapus akun relawan "
            f"{username}? Tindakan ini permanen. "
            "Pesan yang terkait dengan relawan ini akan ikut terhapus, "
            "dan referensi foto/dokumen yang terkait dapat terpengaruh sesuai aturan database.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            db.delete_user(self._conn, int(user["id"]))
            db.log_activity(
                self._conn,
                "DELETE_USER",
                user_id=int(session.get_current_user()["id"]),
                detail=f"volunteer_id={user['id']}; username={username}",
            )
            self.status_label.setText(f"Relawan '{username}' berhasil dihapus.")
            self.refresh()
        except (PermissionError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Gagal menghapus relawan", str(exc))

    def stop_face_capture(self) -> None:
        """Batalkan pendaftaran yang terbuka sebelum halaman sesi dibuang."""
        for dialog in self.findChildren(FaceEnrollmentDialog):
            dialog.reject()
        self._pending_volunteer = None

    def clear_sensitive_state(self) -> None:
        """Lepaskan data formulir dan profil setelah sesi berakhir."""
        self.stop_face_capture()
        self.table.setRowCount(0)

    def closeEvent(self, event) -> None:
        self.stop_face_capture()
        super().closeEvent(event)
