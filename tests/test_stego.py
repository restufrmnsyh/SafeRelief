"""
SafeRelief - Tes Steganografi LSB

Kriteria lulus Tahap 2 (stego):
- Round-trip embed → extract menghasilkan payload identik
- Payload terlalu besar ditolak dengan ValueError
- Selisih piksel maksimal 1 per kanal
- Gambar tanpa payload valid ditolak (ValueError, bukan crash / sampah)
"""

import pytest
import os
import numpy as np
from pathlib import Path
from PIL import Image

from crypto import stego_lsb
from crypto import aes_module


# ─────────────────────────────────────────────
# Helper: buat gambar PNG dummy di tmpdir
# ─────────────────────────────────────────────

def _make_png(path: Path, width: int, height: int, seed: int = 42) -> Path:
    """Buat gambar RGB acak dan simpan sebagai PNG."""
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    Image.fromarray(arr, "RGB").save(str(path), format="PNG")
    return path


def _make_jpg(path: Path, width: int, height: int, seed: int = 7) -> Path:
    """Buat gambar RGB acak dan simpan sebagai JPG."""
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    Image.fromarray(arr, "RGB").save(str(path), format="JPEG", quality=95)
    return path


def _make_rgba(path: Path, width: int, height: int, seed: int = 13) -> Path:
    """Buat gambar RGBA acak dan simpan sebagai PNG."""
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (height, width, 4), dtype=np.uint8)
    Image.fromarray(arr, "RGBA").save(str(path), format="PNG")
    return path


# ─────────────────────────────────────────────
# Tes
# ─────────────────────────────────────────────

class TestStego:

    def test_roundtrip(self, tmp_path):
        """Embed lalu extract menghasilkan payload yang identik."""
        cover = _make_png(tmp_path / "cover.png", 100, 100)
        out   = tmp_path / "stego.png"
        payload = b"Payload rahasia untuk SafeRelief!"

        actual_out = stego_lsb.embed(str(cover), payload, str(out))
        recovered  = stego_lsb.extract(str(actual_out))

        assert recovered == payload

    def test_roundtrip_binary_payload(self, tmp_path):
        """Payload bytes acak (simulasi AES-GCM output) juga round-trip."""
        cover = _make_png(tmp_path / "cover.png", 200, 200)
        out   = tmp_path / "stego.png"
        payload = os.urandom(256)

        actual_out = stego_lsb.embed(str(cover), payload, str(out))
        recovered  = stego_lsb.extract(str(actual_out))

        assert recovered == payload

    def test_payload_too_large_raises(self, tmp_path):
        """Payload melebihi kapasitas harus raise ValueError dengan pesan jelas."""
        cover = _make_png(tmp_path / "cover.png", 10, 10)  # kapasitas ~33 byte
        oversized = bytes(100)

        with pytest.raises(ValueError, match="kapasitas"):
            stego_lsb.embed(str(cover), oversized, str(tmp_path / "out.png"))

    def test_payload_empty_raises(self, tmp_path):
        """Payload kosong harus raise ValueError."""
        cover = _make_png(tmp_path / "cover.png", 50, 50)

        with pytest.raises(ValueError, match="kosong"):
            stego_lsb.embed(str(cover), b"", str(tmp_path / "out.png"))

    def test_pixel_diff_max_one(self, tmp_path):
        """Selisih nilai piksel antara cover dan stego maksimal 1 per kanal."""
        cover_path = _make_png(tmp_path / "cover.png", 100, 100)
        out_path   = tmp_path / "stego.png"
        payload    = os.urandom(100)

        actual_out = stego_lsb.embed(str(cover_path), payload, str(out_path))

        arr_cover = np.array(Image.open(str(cover_path)).convert("RGB"), dtype=np.int16)
        arr_stego = np.array(Image.open(str(actual_out)).convert("RGB"),  dtype=np.int16)

        diff = np.abs(arr_cover - arr_stego)
        assert diff.max() <= 1, f"Selisih piksel maksimum {diff.max()} > 1"

    def test_extract_plain_image_raises(self, tmp_path):
        """
        Gambar tanpa payload valid harus raise ValueError.
        Tidak boleh crash dengan exception lain atau mengembalikan sampah diam-diam.
        """
        plain = _make_png(tmp_path / "plain.png", 50, 50, seed=99)

        with pytest.raises(ValueError):
            stego_lsb.extract(str(plain))

    def test_extract_tiny_image_raises(self, tmp_path):
        """Gambar terlalu kecil untuk header 4 byte harus raise ValueError."""
        tiny = tmp_path / "tiny.png"
        # 1×1 piksel → hanya 3 bit, tidak cukup untuk 32-bit header
        Image.fromarray(np.zeros((1, 1, 3), dtype=np.uint8), "RGB").save(str(tiny))

        with pytest.raises(ValueError):
            stego_lsb.extract(str(tiny))

    def test_capacity_formula(self, tmp_path):
        """capacity() mengembalikan nilai sesuai rumus: (w*h*3)//8 - 4."""
        png = _make_png(tmp_path / "img.png", 80, 60)
        expected = (80 * 60 * 3) // 8 - 4
        assert stego_lsb.capacity(str(png)) == expected

    def test_output_is_always_png(self, tmp_path):
        """out_path dengan ekstensi .jpg tetap disimpan sebagai PNG dan return path-nya."""
        cover = _make_png(tmp_path / "cover.png", 100, 100)
        out   = tmp_path / "output.jpg"        # ekstensi salah, tapi OK
        payload = b"test"

        actual_out = stego_lsb.embed(str(cover), payload, str(out))

        # embed() harus mengembalikan path dengan .png
        assert Path(actual_out).suffix == ".png"
        assert Path(actual_out).exists()
        # file .jpg TIDAK dibuat
        assert not out.exists()

    def test_embed_jpg_input_warns(self, tmp_path):
        """Input JPG diterima tetapi memunculkan UserWarning."""
        jpg   = _make_jpg(tmp_path / "cover.jpg", 100, 100)
        out   = tmp_path / "stego.png"
        payload = b"test JPG input"

        with pytest.warns(UserWarning):
            actual_out = stego_lsb.embed(str(jpg), payload, str(out))

        recovered = stego_lsb.extract(str(actual_out))
        assert recovered == payload

    def test_modified_stego_raises(self, tmp_path):
        """
        Gambar stego yang dimodifikasi pada piksel area data harus
        menyebabkan extract menghasilkan data berbeda atau ValueError.

        50 byte payload + 4 byte header = 432 bit → 144 piksel pertama.
        Ubah piksel (0,1) yang pasti dalam area tersebut.
        """
        cover   = _make_png(tmp_path / "cover.png", 100, 100)
        stego   = tmp_path / "stego.png"
        payload = os.urandom(50)

        actual_out = stego_lsb.embed(str(cover), payload, str(stego))

        arr = np.array(Image.open(str(actual_out)).convert("RGB"), dtype=np.uint8)
        arr[0, 1, 0] ^= 0xFF          # flip seluruh byte kanal R, LSB pasti berubah
        Image.fromarray(arr, "RGB").save(str(actual_out), format="PNG")

        try:
            recovered = stego_lsb.extract(str(actual_out))
            assert recovered != payload, "Data yang rusak seharusnya berbeda"
        except ValueError:
            pass    # juga diterima — header menjadi tidak valid

    # ------------------------------------------------------------------
    # Tes baru (poin 5 dari permintaan perbaikan)
    # ------------------------------------------------------------------

    def test_embed_exact_capacity_roundtrip(self, tmp_path):
        """Payload tepat sebesar capacity() harus berhasil dan round-trip."""
        cover = _make_png(tmp_path / "cover.png", 100, 100)
        cap   = stego_lsb.capacity(str(cover))
        payload = os.urandom(cap)           # tepat capacity byte

        actual_out = stego_lsb.embed(str(cover), payload, str(tmp_path / "stego.png"))
        recovered  = stego_lsb.extract(str(actual_out))

        assert recovered == payload

    def test_embed_capacity_plus_one_raises(self, tmp_path):
        """Payload capacity()+1 byte harus ditolak dengan ValueError."""
        cover = _make_png(tmp_path / "cover.png", 100, 100)
        cap   = stego_lsb.capacity(str(cover))
        oversized = os.urandom(cap + 1)

        with pytest.raises(ValueError, match="kapasitas"):
            stego_lsb.embed(str(cover), oversized, str(tmp_path / "out.png"))

    def test_embed_rgba_cover_produces_rgb_png(self, tmp_path):
        """Cover RGBA: alpha dibuang, output adalah PNG RGB yang valid."""
        cover   = _make_rgba(tmp_path / "cover_rgba.png", 100, 100)
        out     = tmp_path / "stego.png"
        payload = b"data dari RGBA cover"

        actual_out = stego_lsb.embed(str(cover), payload, str(out))

        # Verifikasi output adalah PNG RGB (bukan RGBA)
        with Image.open(str(actual_out)) as img_out:
            assert img_out.mode == "RGB"
            assert img_out.format == "PNG" or actual_out.suffix == ".png"

        # Round-trip tetap benar
        recovered = stego_lsb.extract(str(actual_out))
        assert recovered == payload

    def test_stego_aes_gcm_integration(self, tmp_path):
        """
        Tes gabungan stego + AES-GCM:
        embed payload terenkripsi, ubah satu piksel di area payload,
        lalu extract + dekripsi HARUS gagal dengan InvalidTag.
        """
        from cryptography.exceptions import InvalidTag

        cover   = _make_png(tmp_path / "cover.png", 100, 100)
        stego   = tmp_path / "stego.png"
        aes_key = os.urandom(32)

        # Enkripsi plaintext dengan AES-GCM
        plaintext        = b"Data korban sensitif"
        encrypted_payload = aes_module.encrypt(plaintext, aes_key)

        # Embed payload terenkripsi
        actual_out = stego_lsb.embed(str(cover), encrypted_payload, str(stego))

        # Rusak satu piksel dalam area data (header=32 bit, lalu payload)
        # encrypted_payload cukup panjang → piksel (0,1) pasti dalam area
        arr = np.array(Image.open(str(actual_out)).convert("RGB"), dtype=np.uint8)
        arr[0, 1, 0] ^= 0xFF
        Image.fromarray(arr, "RGB").save(str(actual_out), format="PNG")

        # Extract mungkin berhasil tapi menghasilkan ciphertext rusak,
        # atau langsung ValueError karena header rusak
        try:
            extracted = stego_lsb.extract(str(actual_out))
            # Jika extract tidak raise, dekripsi HARUS gagal dengan InvalidTag
            with pytest.raises(InvalidTag):
                aes_module.decrypt(extracted, aes_key)
        except ValueError:
            pass    # header rusak → juga valid

