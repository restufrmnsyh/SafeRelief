"""
SafeRelief - Steganografi LSB (Least Significant Bit)

Menyembunyikan data di LSB kanal RGB setiap piksel gambar PNG.
Modul ini HANYA urusan embed/extract bit — enkripsi payload dilakukan
oleh pemanggil (AES-GCM dengan kunci b"stego").

Kenapa LSB:
- Perubahan piksel maksimal ±1 per kanal, tidak terlihat mata
- Implementasi bisa ditulis sendiri (requirement tugas)
- PNG lossless → bit yang disisipkan tidak rusak saat save

Format data tersembunyi di gambar:
  [ panjang payload (4 byte, big-endian) | payload bytes ]
Tiap byte payload membutuhkan 8 bit; bit-bit itu ditulis berurutan ke
kanal R, G, B piksel demi piksel. 1 byte = ~2,67 piksel (3 bit per
piksel, masing-masing 1 dari kanal R, G, B).

Catatan channel alpha: gambar RGBA/P/lainnya dikonversi ke RGB saat
dibuka — kanal alpha DIBUANG dan tidak disimpan ke output.

Keterbatasan:
- Rapuh terhadap konversi format (JPG, WebP lossy) → piksel berubah
- Tidak ada error correction
- Mudah dideteksi dengan steganalysis (chi-square attack, dll.)
"""

import warnings
import numpy as np
from PIL import Image
from pathlib import Path


# ===== helper tingkat bit =====

def _bytes_to_bits(data: bytes) -> list[int]:
    """Ubah bytes ke list bit [0/1], MSB first per byte."""
    bits = []
    for byte in data:
        for i in range(7, -1, -1):          # bit 7 → bit 0
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    """Ubah list bit kembali ke bytes. Panjang bits harus kelipatan 8."""
    result = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        result.append(byte)
    return bytes(result)


# ===== API publik =====

def capacity(image_path: str) -> int:
    """
    Hitung kapasitas maksimum payload (byte) yang bisa disisipkan.

    Kapasitas = (jumlah piksel × 3 kanal) // 8  minus 4 byte header.
    Tiga kanal RGB masing-masing menyimpan 1 bit → 3 bit per piksel.

    Args:
        image_path: Path ke file gambar (PNG, JPG, atau format lain
                    yang didukung Pillow).

    Returns:
        Kapasitas dalam byte (tidak termasuk 4 byte header).
    """
    with Image.open(image_path) as img:
        w, h = img.size
    total_bits = w * h * 3          # 3 kanal × 1 bit per kanal
    total_bytes = total_bits // 8
    return total_bytes - 4          # kurangi 4 byte untuk header panjang


def embed(cover_path: str, payload: bytes, out_path: str) -> Path:
    """
    Sisipkan payload ke gambar cover menggunakan LSB.

    Proses:
    1. Buka gambar, konversi ke RGB (alpha DIBUANG jika ada)
    2. Tolak payload kosong
    3. Cek kapasitas; tolak jika payload terlalu besar
    4. Susun bit_stream = bits(header 4 byte) + bits(payload)
    5. Tulis tiap bit ke LSB kanal R, G, B secara berurutan
    6. Simpan sebagai PNG (lossless wajib)

    Args:
        cover_path: Path gambar asli. JPG/PNG/RGBA diterima;
                    JPG memunculkan UserWarning; alpha dibuang.
        payload   : Bytes yang akan disisipkan (sudah dienkripsi AES-GCM).
                    Tidak boleh kosong.
        out_path  : Path output yang diinginkan. Ekstensi dipaksa .png.

    Returns:
        Path output yang sebenarnya digunakan (ekstensi sudah .png).

    Raises:
        ValueError: Payload kosong, atau kapasitas gambar tidak cukup.
    """
    src = Path(cover_path)
    if src.suffix.lower() in (".jpg", ".jpeg"):
        warnings.warn(
            f"Input {src.name} adalah JPG (lossy). "
            "Dikonversi ke RGB; kualitas asli tidak dipertahankan.",
            UserWarning,
            stacklevel=2,
        )

    # --- validasi payload ---
    if len(payload) == 0:
        raise ValueError("Payload tidak boleh kosong.")

    try:
        with Image.open(cover_path) as img:
            img_rgb = img.convert("RGB")   # alpha DIBUANG di sini
    except (OSError, ValueError) as exc:
        message = str(exc).lower()
        if src.suffix.lower() == ".webp" or "webp" in message:
            raise ValueError(
                "Format WEBP ini tidak dapat diproses, coba format lain"
            ) from exc
        raise
    w, h = img_rgb.size

    # --- validasi kapasitas ---
    max_payload = capacity(cover_path)
    if len(payload) > max_payload:
        raise ValueError(
            f"Payload ({len(payload)} byte) melebihi kapasitas gambar "
            f"({max_payload} byte untuk {w}×{h} piksel)."
        )

    # --- susun bit stream: header(4B big-endian) + payload ---
    header = len(payload).to_bytes(4, "big")
    bit_stream = _bytes_to_bits(header + payload)

    # --- embed ke array numpy ---
    arr = np.array(img_rgb, dtype=np.uint8)    # shape (h, w, 3)
    flat = arr.flatten()                        # urutan R,G,B,R,G,B,...

    for idx, bit in enumerate(bit_stream):
        # Hapus LSB lalu set dengan bit baru
        flat[idx] = (flat[idx] & 0xFE) | bit

    arr_out = flat.reshape(arr.shape)

    # --- tentukan path output (paksa .png) ---
    out = Path(out_path)
    if out.suffix.lower() != ".png":
        out = out.with_suffix(".png")

    # Image.fromarray tanpa mode — numpy uint8 (H,W,3) otomatis "RGB"
    Image.fromarray(arr_out).save(str(out), format="PNG")

    return out


def extract(stego_path: str) -> bytes:
    """
    Ekstrak payload dari gambar stego.

    Proses:
    1. Buka gambar, konversi ke RGB
    2. Baca LSB tiap kanal (R,G,B) dalam urutan raster
    3. Kumpulkan 32 bit pertama → header → panjang payload
    4. Validasi panjang (> 0 dan ≤ kapasitas gambar)
    5. Kumpulkan bit sesuai panjang, konversi ke bytes

    Args:
        stego_path: Path gambar PNG stego.

    Returns:
        Payload bytes (terserah pemanggil untuk dekripsi AES-GCM).

    Raises:
        ValueError: Gambar tidak mengandung payload valid (panjang header
                    tidak masuk akal) — tidak crash atau mengembalikan
                    data acak tanpa peringatan.
    """
    with Image.open(stego_path) as img:
        img_rgb = img.convert("RGB")
        w, h = img_rgb.size
        arr = np.array(img_rgb, dtype=np.uint8)

    flat = arr.flatten()                        # urutan R,G,B,...

    # --- baca 32 bit header ---
    if len(flat) < 32:
        raise ValueError("Gambar terlalu kecil untuk mengandung header stego.")

    header_bits = [int(flat[i] & 1) for i in range(32)]
    payload_len = int.from_bytes(_bits_to_bytes(header_bits), "big")

    # --- validasi panjang ---
    max_payload = (len(flat) // 8) - 4
    if payload_len <= 0 or payload_len > max_payload:
        raise ValueError(
            f"Panjang payload dalam header ({payload_len}) tidak valid. "
            "Gambar mungkin tidak mengandung data stego atau telah diubah."
        )

    # --- baca payload bits ---
    total_bits_needed = 32 + payload_len * 8
    if total_bits_needed > len(flat):
        raise ValueError(
            "Data stego di header melebihi ukuran gambar; gambar mungkin rusak."
        )

    payload_bits = [int(flat[i] & 1) for i in range(32, total_bits_needed)]
    return _bits_to_bytes(payload_bits)
