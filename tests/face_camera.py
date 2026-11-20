"""Frame sintetis untuk menguji pratinjau Qt tanpa membuka webcam."""

from time import monotonic

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage


def single_face(_frame: np.ndarray) -> np.ndarray:
    """Embedding tetap mewakili satu orang yang menatap kamera."""
    return np.ones(128, dtype=np.float32)


def stream_frames(page, *, timestamp: float | None = None) -> QTimer:
    """Kirim frame identik melalui kamera uji dengan waktu pengambilan per frame."""
    image = QImage(100, 80, QImage.Format.Format_RGB888)
    image.fill(0xff808080)

    def send() -> None:
        page._display_frame(image, monotonic() if timestamp is None else timestamp)

    timer = QTimer()
    timer.timeout.connect(send)
    timer.start(10)
    return timer
