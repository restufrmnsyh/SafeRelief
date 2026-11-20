"""Kamera uji mengirim penanda pose lewat jalur preview Qt tanpa data biometrik."""

from time import monotonic

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from auth import hand_challenge


def observe_pose(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Kotak wajah dan embedding menggantikan dua keluaran YuNet dan SFace."""
    return np.ones(128, dtype=np.float32), np.array([15, 10, 50, 55])


def mock_hand_camera(monkeypatch) -> None:
    def fingers(frame: np.ndarray, on_left: bool) -> int | None:
        return {128: None, 160: 3, 192: 2, 193: 4, 194: 0, 195: -1, 200: 3}[int(frame[0, 0, 0])]

    monkeypatch.setattr(hand_challenge, "visible_fingers", fingers)
    monkeypatch.setattr(hand_challenge, "face_is_live", lambda frame, _box: int(frame[0, 0, 0]) != 200)


def stream_poses(page, status, response: str = "correct") -> QTimer:
    """Gerakkan kamera uji sesuai instruksi yang benar-benar ditampilkan."""
    def send() -> None:
        prompt = status.text()
        shade = 160 if prompt.startswith("Angkat") else 128
        if response == "static":
            shade = 128
        elif response == "static_three":
            shade = 160
        elif response == "never_return" and prompt.startswith("Turunkan"):
            shade = 160
        elif shade == 160:
            shade = {"two": 192, "four": 193, "fist": 194, "unclear": 195, "photo_face": 200}.get(response, 160)
        image = QImage(100, 80, QImage.Format.Format_RGB888)
        image.fill(0xff000000 | (shade * 0x010101))
        page._display_frame(image, 0.0 if response == "stale" else monotonic())

    timer = QTimer()
    timer.timeout.connect(send)
    timer.start(10)
    return timer
