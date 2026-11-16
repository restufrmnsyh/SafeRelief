"""Rincian metadata foto yang dibedakan antara belum dibuka dan terverifikasi."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QLayout, QPlainTextEdit, QSizePolicy, QVBoxLayout

from ui.workspace_style import PHOTO_METADATA_STYLE


class PhotoMetadataPanel(QFrame):
    """Tampilkan hasil ekstraksi sebagai rincian, tanpa mengekspos JSON ke pengguna."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("photoMetadataPanel")
        self.setStyleSheet(PHOTO_METADATA_STYLE)
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.state_label = self._label("", "photoMetadataState")
        self.description = self._label("", "photoMetadataDescription")
        layout.addWidget(self.state_label)
        layout.addWidget(self.description)
        self.details = QFrame()
        form = QVBoxLayout(self.details)
        form.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        form.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.values: dict[str, QLabel] = {}
        for key, caption in (
            ("victim_id", "Korban"), ("posko_id", "Posko"),
            ("timestamp", "Waktu dokumentasi"), ("officer_id", "Petugas"),
            ("keterangan", "Keterangan"),
        ):
            value = self._label("", "photoMetadataValue")
            value.setAccessibleName(caption)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            self.values[key] = value
            caption_label = self._label(caption, "photoMetadataCaption")
            caption_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            row = QVBoxLayout()
            row.setAlignment(Qt.AlignmentFlag.AlignTop)
            row.setSpacing(4)
            row.addWidget(caption_label)
            row.addWidget(value)
            form.addLayout(row)
        hash_caption = self._label("SHA-256 foto asli", "photoMetadataCaption")
        hash_caption.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.hash_view = QPlainTextEdit()
        self.hash_view.setObjectName("photoMetadataHash")
        self.hash_view.setAccessibleName("SHA-256 foto asli")
        self.hash_view.setReadOnly(True)
        self.hash_view.setMinimumWidth(0)
        self.hash_view.setFixedHeight(88)
        hash_row = QVBoxLayout()
        hash_row.setAlignment(Qt.AlignmentFlag.AlignTop)
        hash_row.setSpacing(4)
        hash_row.addWidget(hash_caption)
        hash_row.addWidget(self.hash_view)
        form.addLayout(hash_row)
        layout.addWidget(self.details)
        self.payload_view = QPlainTextEdit()
        self.payload_view.setAccessibleName("Payload metadata terenkripsi dalam hex")
        self.payload_view.setObjectName("photoMetadataCiphertext")
        self.payload_view.setReadOnly(True)
        self.payload_view.setMaximumHeight(100)
        self.payload_view.setMinimumWidth(0)
        layout.addWidget(self.payload_view)
        self.show_empty()

    @staticmethod
    def _label(text: str, name: str) -> QLabel:
        """Metadata adalah teks biasa; tag HTML dari keterangan tidak ditafsirkan."""
        label = QLabel(text)
        label.setObjectName(name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        return label

    def clear(self) -> None:
        """Lepaskan rincian dan ciphertext ketika sesi atau pilihan foto berubah."""
        for value in self.values.values():
            value.clear()
        self.payload_view.clear()
        self.hash_view.clear()
        self.details.hide()
        self.payload_view.hide()
        self.state_label.clear()
        self.description.clear()

    def _state(self, text: str, description: str, tone: str) -> None:
        self.clear()
        self.state_label.setText(text)
        self.description.setText(description)
        self.state_label.setProperty("tone", tone)
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)

    def show_empty(self) -> None:
        """Jangan tampilkan metadata sebelum foto dipilih dan didekripsi."""
        self._state("Metadata belum dibuka", "Pilih foto, lalu klik Decrypt untuk melihat rinciannya.", "neutral")

    def show_encrypted(self, payload: bytes) -> None:
        """Ciphertext tetap bisa diperiksa untuk demonstrasi steganografi."""
        self._state("Metadata terenkripsi", "Payload berhasil diekstrak. Klik Decrypt untuk membuka metadata.", "neutral")
        self.payload_view.setPlainText(payload.hex())
        self.payload_view.show()

    def show_error(self, message: str) -> None:
        """Kegagalan verifikasi tidak boleh menyisakan rincian foto sebelumnya."""
        self._state("Metadata tidak dapat dibuka", message, "error")

    def show_verified(self, metadata: dict, references: dict[str, str]) -> None:
        """Tampilkan nilai payload, dibantu nama referensi yang masih tersedia."""
        self._state("Metadata terverifikasi", "Hash foto asli cocok dengan catatan penyimpanan.", "success")
        for key, value in self.values.items():
            raw = metadata.get(key)
            if key in references:
                text = references[key]
            elif raw is None or raw == "":
                text = "Tidak dicantumkan"
            elif key == "timestamp":
                text = self._format_timestamp(str(raw))
            else:
                text = str(raw)
            value.setText(text)
        self.hash_view.setPlainText(str(metadata.get("original_sha256") or "Tidak dicantumkan"))
        self.details.show()

    @staticmethod
    def _format_timestamp(raw: str) -> str:
        """Pertahankan zona waktu payload, bukan zona komputer yang membacanya."""
        try:
            stamp = datetime.fromisoformat(raw)
        except ValueError:
            return raw
        months = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
        text = f"{stamp.day} {months[stamp.month - 1]} {stamp.year}, {stamp:%H:%M:%S}"
        offset = stamp.strftime("%z")
        if offset:
            text += f" UTC{offset[:3]}:{offset[3:]}"
        return text
