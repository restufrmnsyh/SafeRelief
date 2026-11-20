"""Kamera uji mengirim penanda pose lewat jalur preview Qt tanpa data biometrik."""

from time import monotonic

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage


def observe_pose(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Terjemahkan penanda frame menjadi titik wajah YuNet dan embedding uji."""
    offset = int(frame[0, 0, 0]) - 128
    points = np.array(
        [(30, 30), (70, 30), (50 + offset, 50), (35, 70), (65, 70)],
        dtype=np.float32,
    )
    return np.ones(128, dtype=np.float32), points


def stream_poses(page, status, response: str = "correct") -> QTimer:
    """Gerakkan kamera uji sesuai instruksi yang benar-benar ditampilkan."""
    def send() -> None:
        prompt = status.text()
        offset = 0
        if "sisi kiri" in prompt:
            offset = -16
        elif "sisi kanan" in prompt:
            offset = 16
        if response == "static":
            offset = 0
        elif response == "wrong_direction":
            offset = -offset
        elif response == "never_return" and "Kembali" in prompt:
            offset = 16
        image = QImage(100, 80, QImage.Format.Format_RGB888)
        shade = 128 + offset
        image.fill(0xff000000 | (shade * 0x010101))
        page._display_frame(image, 0.0 if response == "stale" else monotonic())

    timer = QTimer()
    timer.timeout.connect(send)
    timer.start(10)
    return timer
