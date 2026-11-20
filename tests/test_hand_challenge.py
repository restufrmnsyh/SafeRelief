"""Regresi inferensi tangan dan pemeriksaan wajah tanpa webcam atau data pengguna."""

from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from auth import hand_challenge
from download_models import download_model


def hand_points(raised: set[int]) -> np.ndarray:
    """Susun sendi buatan dengan ujung jari mengarah keluar atau terlipat ke telapak."""
    points = np.zeros((21, 3), dtype=np.float32)
    for finger, x in enumerate((3, 1, -1, -3), start=1):
        base = 1 + 4 * finger
        points[base:base + 4, 0] = x
        points[base:base + 4, 1] = (4, 6, 7, 8) if finger in raised else (4, 6, 5, 4.5)
    points[2:5, 0] = (3, 4, 5.5) if 0 in raised else (3, 4, 2)
    points[2:5, 1] = 2.5
    return points


@pytest.mark.parametrize("raised", [set(), {2}, {1, 2}, {1, 2, 3}, {0, 1, 2}, {1, 2, 3, 4}, set(range(5))])
def test_counts_upturned_fingers_on_either_hand(raised: set[int]) -> None:
    points = hand_points(raised)
    assert hand_challenge.count_fingers(points) == len(raised)
    points[:, 0] *= -1
    assert hand_challenge.count_fingers(points) == len(raised)


def test_real_networks_on_empty_camera_image() -> None:
    frame = np.full((240, 320, 3), 128, dtype=np.uint8)
    assert hand_challenge.visible_fingers(frame, on_left=True) is None
    assert not hand_challenge.face_is_live(frame, np.array([20, 20, 80, 80]))


def test_antispoof_uses_padded_face_crop_and_rgb_normalization(monkeypatch) -> None:
    frame = np.zeros((160, 160, 3), np.uint8)
    # Kotak deteksi 64 x 64 diperluas seperti di demo model, termasuk tepi berwarna.
    frame[22:89, 26:97] = (10, 80, 140)
    frame[24:88, 30:94] = (40, 80, 140)
    net = Mock()
    monkeypatch.setattr(hand_challenge, "_net", lambda _: net)
    net.forward.return_value = np.array([[0.98, 0.02]], dtype=np.float32)
    box = np.array([30, 24, 64, 64])
    assert hand_challenge.face_is_live(frame, box)
    blob = net.setInput.call_args.args[0]
    for pixel, blue in [((0, 0), 10), ((64, 64), 40)]:
        expected = (np.array([140, 80, blue]) - [151.2405, 119.595, 107.8395]) / [63.0105, 56.457, 55.0035]
        np.testing.assert_allclose(blob[0, :, pixel[0], pixel[1]], expected, atol=1e-5)
    net.forward.return_value = np.array([[0.02, 0.98]], dtype=np.float32)
    assert not hand_challenge.face_is_live(frame, box)


@pytest.mark.parametrize("probabilities, live", [([0.65, 0.35], True), ([0.59, 0.41], False)])
def test_reference_classifier_decision(monkeypatch, probabilities, live: bool) -> None:
    net = Mock()
    net.forward.return_value = np.array([probabilities], dtype=np.float32)
    monkeypatch.setattr(hand_challenge, "_net", lambda _: net)
    frame = np.zeros((96, 96, 3), dtype=np.uint8)
    assert hand_challenge.face_is_live(frame, np.array([0, 0, 96, 96])) is live


@pytest.mark.parametrize("values", [[np.nan, 0], [0, 0], [0.99], [1.01, -0.01]])
def test_invalid_classifier_output_cannot_give_a_live_vote(monkeypatch, values) -> None:
    net = Mock()
    net.forward.return_value = np.array([values], dtype=np.float32)
    monkeypatch.setattr(hand_challenge, "_net", lambda _: net)
    with pytest.raises(ValueError, match="model wajah tidak valid"):
        hand_challenge.face_is_live(np.zeros((96, 96, 3), np.uint8), np.array([0, 0, 96, 96]))


def test_failed_download_preserves_existing_model(tmp_path: Path) -> None:
    existing = tmp_path / "model.onnx"
    existing.write_bytes(b"existing")
    source = tmp_path / "incomplete"
    source.write_bytes(b"incomplete")
    assert not download_model(existing.name, source.as_uri(), tmp_path, "sha256:" + "0" * 64)
    assert existing.read_bytes() == b"existing"
    assert set(tmp_path.iterdir()) == {source, existing}
