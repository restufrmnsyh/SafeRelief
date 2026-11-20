"""Pemeriksaan wajah hidup dan jumlah jari dengan model ONNX lokal."""

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

import config


@lru_cache(maxsize=2)
def _net(path: Path) -> cv2.dnn.Net:
    if not path.is_file():
        raise FileNotFoundError(f"Model {path.name} belum tersedia. Jalankan python download_models.py.")
    return cv2.dnn.readNetFromONNX(str(path))


def face_is_live(frame: np.ndarray, box: np.ndarray) -> bool:
    """Nilai area wajah yang embedding-nya sedang dicocokkan oleh SFace."""
    height, width = frame.shape[:2]
    x, y, w, h = box
    x1, x2 = np.clip([int(x), int(x + w)], 0, width)
    y1, y2 = np.clip([int(y), int(y + h)], 0, height)
    if min(x2 - x1, y2 - y1) < 48:
        return False
    # Demo anti-spoof-mn3 memberi sedikit ruang di sekeliling deteksi wajah.
    x1, x2 = np.clip([int(x - 0.05 * w), int(x + 1.05 * w)], 0, width)
    y1, y2 = np.clip([int(y - 0.025 * h), int(y + 1.025 * h)], 0, height)
    crop = cv2.resize(frame[y1:y2, x1:x2], (128, 128), interpolation=cv2.INTER_CUBIC)
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32)
    # Normalisasi dan urutan kelas mengikuti spesifikasi ONNX asli anti-spoof-mn3.
    rgb -= (151.2405, 119.5950, 107.8395)
    rgb /= (63.0105, 56.4570, 55.0035)
    model = _net(config.FACE_ANTISPOOF_MODEL)
    model.setInput(cv2.dnn.blobFromImage(rgb))
    probabilities = model.forward().ravel()
    if probabilities.size != 2 or not np.all((probabilities >= 0) & (probabilities <= 1)):
        raise ValueError("Hasil model wajah tidak valid. Ulangi pemeriksaan.")
    if not np.isclose(probabilities.sum(), 1.0, atol=1e-4):
        raise ValueError("Hasil model wajah tidak valid. Ulangi pemeriksaan.")
    # Demo penerbit memakai batas 0,40 untuk kelas spoof. Worker juga memerlukan
    # persetujuan beberapa frame dari wajah yang sama di setiap tahap.
    return bool(probabilities[1] <= 0.40)


def hand_box(width: int, height: int, on_left: bool) -> tuple[int, int, int]:
    """Kotak persegi yang sama dipakai untuk panduan dan masukan model tangan."""
    side = max(1, int(min(width * 0.44, height * 0.66)))
    margin = int(min(width, height) * 0.03)
    x = margin if on_left else width - margin - side
    return x, (height - side) // 2, side


def count_fingers(points: np.ndarray) -> int:
    """Hitung jari terbuka dari 21 titik 3D. Nilai -1 berarti pose belum jelas."""
    if points.shape != (21, 3) or not np.isfinite(points).all():
        return -1
    palm_axis = points[5] - points[17]  # pangkal kelingking ke pangkal telunjuk
    palm_width = np.linalg.norm(palm_axis)
    if palm_width < 1e-6:
        return -1
    count = 0
    for base, joint, tip in ((2, 3, 4), (5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)):
        first, last = points[joint] - points[base], points[tip] - points[joint]
        lengths = np.linalg.norm(first) * np.linalg.norm(last)
        if lengths < 1e-9:
            return -1
        alignment = (first @ last) / lengths
        if tip == 4:
            # Ibu jari membuka ke samping telapak, termasuk pada tangan kiri.
            reach = (points[tip] - points[5]) @ palm_axis / palm_width ** 2
        else:
            reach = (np.linalg.norm(points[tip] - points[0]) -
                     np.linalg.norm(points[joint] - points[0])) / palm_width
        if alignment > 0.68 and reach > 0.20:
            count += 1
        elif alignment > 0.45 and reach > 0.10:
            return -1
    return count


def visible_fingers(frame: np.ndarray, on_left: bool) -> int | None:
    """None berarti kotak kosong. Tangan terpotong atau ambigu tidak dianggap kosong."""
    height, width = frame.shape[:2]
    x, y, side = hand_box(width, height, on_left)
    crop = cv2.resize(frame[y:y + side, x:x + side], (224, 224))
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    model = _net(config.HAND_MODEL)
    model.setInput(rgb[None])
    screen, presence, _, world = model.forward(["Identity", "Identity_1", "Identity_2", "Identity_3"])
    confidence = float(presence.item())
    if confidence < 0.25:
        return None
    pixels = screen.reshape(21, 3)[:, :2]
    if not np.isfinite(confidence) or confidence < 0.80 or not np.all((pixels > 1) & (pixels < 223)):
        return -1
    return count_fingers(world.reshape(21, 3))
