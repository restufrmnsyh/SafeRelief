"""
SafeRelief - Blockchain Sederhana untuk Distribusi Bantuan

Implementasi blockchain lokal dengan SHA-256 + Proof-of-Work.
Digunakan untuk audit trail distribusi bantuan yang tidak bisa diubah diam-diam.

Kenapa blockchain (meski lokal):
- Setiap block menyimpan hash block sebelumnya → rantai sebab-akibat
- Ubah satu block → hash berubah → semua block sesudahnya invalid
- PoW: menambah block butuh kerja komputasi, tidak bisa di-spam
- Cocok untuk demonstrasi konsep immutability (requirement tugas)

Keterbatasan yang diakui (penting untuk laporan):
- Tidak terdistribusi → satu titik kegagalan; pemegang file DB bisa
  membangun ulang chain dari awal dengan data palsu beserta PoW baru.
- Penghapusan block TERAKHIR tidak terdeteksi tanpa jangkar eksternal
  (misal: hash head chain yang disimpan di tempat lain). is_valid()
  hanya memeriksa konsistensi internal chain yang ada.
- PoW ringan (difficulty 3) → bukan keamanan produksi.
- BLOCKCHAIN_DIFFICULTY tidak boleh diubah setelah ada data: block lama
  akan gagal validasi PoW dengan difficulty baru.

Format JSON hash:
  json.dumps(block_dict, sort_keys=True, separators=(",", ":"))
  sort_keys agar urutan key dict tidak mempengaruhi hash.
  separators tanpa spasi agar konsisten lintas platform.

Timestamp:
  Integer milidetik: int(time.time() * 1000)
  Integer lebih mudah di-serialize/compare lintas bahasa.
"""

import copy
import hashlib
import json
import time
from typing import Optional
import config


# ──────────────────────────────────────────────────────────────────────
# Validasi data block
# ──────────────────────────────────────────────────────────────────────

def _validate_data(data: object, path: str = "data") -> None:
    """
    Pastikan `data` adalah dict yang bisa di-json.dumps dan semua key
    (termasuk nested) bertipe str.

    Rekursif untuk menangani dict bersarang.

    Args:
        data: Objek yang divalidasi.
        path: Jalur field untuk pesan error yang informatif.

    Raises:
        ValueError: Jika data bukan dict, key bukan str, atau tidak
                    bisa di-serialisasi ke JSON.
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"'{path}' harus berupa dict, bukan {type(data).__name__}."
        )
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValueError(
                f"Semua key dict harus bertipe str. "
                f"Key {key!r} di '{path}' bertipe {type(key).__name__}."
            )
        # Validasi rekursif untuk nested dict
        if isinstance(value, dict):
            _validate_data(value, path=f"{path}.{key}")

    # Tes akhir: pastikan seluruh dict bisa di-json.dumps
    try:
        json.dumps(data)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Data di '{path}' tidak dapat di-serialisasi ke JSON: {exc}"
        ) from exc


# ──────────────────────────────────────────────────────────────────────
# Block
# ──────────────────────────────────────────────────────────────────────

class Block:
    """
    Satu block dalam blockchain.

    Atribut:
        index      : Nomor urut (0 = genesis)
        timestamp  : Waktu pembuatan block dalam milidetik (int),
                     dihitung sebagai int(time.time() * 1000)
        data       : Dict payload (jenis, jumlah, dari, ke, petugas).
                     Semua key harus str.
        prev_hash  : Hash hex block sebelumnya ("0"*64 untuk genesis)
        nonce      : Bilangan yang di-increment saat PoW
        hash       : Hash SHA-256 hex dari semua field di atas
    """

    def __init__(
        self,
        index: int,
        timestamp: int,
        data: dict,
        prev_hash: str,
        nonce: int = 0,
    ) -> None:
        self.index = index
        self.timestamp = timestamp       # int milidetik
        self.data = data
        self.prev_hash = prev_hash
        self.nonce = nonce
        # Hash dihitung saat __init__; di-update oleh mine()
        self.hash = self._compute_hash()

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    def _compute_hash(self) -> str:
        """
        Hitung SHA-256 dari representasi JSON block ini.

        sort_keys=True       : urutan key dict tidak mempengaruhi hasil
        separators=(",",":")  : tanpa spasi → output konsisten lintas platform
        """
        block_dict = {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "prev_hash": self.prev_hash,
            "nonce": self.nonce,
        }
        block_str = json.dumps(block_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(block_str.encode("utf-8")).hexdigest()

    def recompute_hash(self) -> str:
        """Hitung ulang hash dari state block saat ini (tanpa side-effect)."""
        return self._compute_hash()

    # ------------------------------------------------------------------
    # Proof-of-Work
    # ------------------------------------------------------------------

    def mine(self, difficulty: int) -> None:
        """
        Lakukan PoW: increment nonce sampai hash diawali `difficulty` nol.

        Args:
            difficulty: Jumlah karakter '0' di awal hash yang diperlukan.
        """
        prefix = "0" * difficulty
        self.nonce = 0
        self.hash = self._compute_hash()
        while not self.hash.startswith(prefix):
            self.nonce += 1
            self.hash = self._compute_hash()

    # ------------------------------------------------------------------
    # Serialisasi
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Ubah block ke dict (untuk simpan ke DB atau JSON)."""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "prev_hash": self.prev_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        """
        Buat Block dari dict (hasil to_dict atau baris dari DB).

        Hash TIDAK dihitung ulang otomatis — hash dipulihkan dari dict.
        Ini penting agar is_valid() bisa mendeteksi jika hash diubah.
        """
        block = cls(
            index=d["index"],
            timestamp=d["timestamp"],
            data=d["data"],
            prev_hash=d["prev_hash"],
            nonce=d["nonce"],
        )
        # Override hash yang baru saja dihitung dengan yang tersimpan
        block.hash = d["hash"]
        return block

    def __repr__(self) -> str:
        return f"Block(index={self.index}, hash={self.hash[:10]}...)"


# ──────────────────────────────────────────────────────────────────────
# Blockchain
# ──────────────────────────────────────────────────────────────────────

class Blockchain:
    """
    Rantai block untuk mencatat distribusi bantuan.

    Saat diinisialisasi (tanpa data awal), genesis block dibuat otomatis.
    Untuk memulihkan chain dari DB, gunakan load_from_list().
    """

    def __init__(self, difficulty: Optional[int] = None) -> None:
        """
        Args:
            difficulty: PoW difficulty. Default dari config.BLOCKCHAIN_DIFFICULTY.
        """
        self.difficulty: int = (
            difficulty if difficulty is not None else config.BLOCKCHAIN_DIFFICULTY
        )
        self.chain: list[Block] = []
        self._create_genesis()

    # ------------------------------------------------------------------
    # Genesis
    # ------------------------------------------------------------------

    def _create_genesis(self) -> None:
        """
        Buat genesis block (index 0).

        prev_hash genesis = "0" * 64 (konvensi standar blockchain).
        Genesis block tidak membawa data distribusi — hanya penanda awal.
        """
        genesis = Block(
            index=0,
            timestamp=int(time.time() * 1000),   # int milidetik
            data={"message": "SafeRelief Genesis Block"},
            prev_hash="0" * 64,
        )
        genesis.mine(self.difficulty)
        self.chain.append(genesis)

    # ------------------------------------------------------------------
    # Properti
    # ------------------------------------------------------------------

    @property
    def head(self) -> Block:
        """Block terakhir (paling baru) dalam chain."""
        return self.chain[-1]

    @property
    def height(self) -> int:
        """Jumlah total block dalam chain (termasuk genesis)."""
        return len(self.chain)

    # ------------------------------------------------------------------
    # Menambah block
    # ------------------------------------------------------------------

    def add_block(self, data: dict) -> Block:
        """
        Tambah block baru berisi data distribusi bantuan.

        Proses:
        1. Validasi data: harus dict dengan semua key str, bisa di-JSON
        2. Simpan salinan dalam (deepcopy) agar mutasi dict asli tidak
           mengubah isi chain
        3. Ambil hash block terakhir sebagai prev_hash
        4. Buat Block baru dengan timestamp milidetik sekarang
        5. Lakukan PoW (mine)
        6. Tambahkan ke chain

        Args:
            data: Dict distribusi, contoh:
                  {"jenis": "beras", "jumlah": 50, "dari": "Posko A",
                   "ke": "Posko B", "petugas": "Budi"}
                  Semua key (termasuk nested) harus bertipe str.

        Returns:
            Block baru yang sudah ditambahkan.

        Raises:
            ValueError: data bukan dict, key bukan str, atau tidak
                        bisa di-serialisasi ke JSON.
        """
        # Validasi sebelum menyentuh chain
        _validate_data(data)

        prev_block = self.chain[-1]
        new_block = Block(
            index=len(self.chain),
            timestamp=int(time.time() * 1000),   # int milidetik
            data=copy.deepcopy(data),             # isolasi dari mutasi luar
            prev_hash=prev_block.hash,
        )
        new_block.mine(self.difficulty)
        self.chain.append(new_block)
        return new_block

    # ------------------------------------------------------------------
    # Validasi
    # ------------------------------------------------------------------

    def is_valid(self) -> tuple[bool, Optional[int]]:
        """
        Validasi seluruh chain.

        Lima pemeriksaan per block:
        1. Hash tersimpan == hash yang dihitung ulang dari field block
           → mendeteksi perubahan data/nonce/timestamp
        2. block.index == posisi di list
           → mendeteksi block yang index-nya dimanipulasi
        3. prev_hash block ini == hash block sebelumnya (kecuali genesis)
           → mendeteksi perubahan urutan atau penyisipan block
        4. prev_hash genesis == "0" * 64
           → mendeteksi penggantian genesis dengan block palsu
        5. Hash memenuhi PoW
           → mendeteksi block tanpa kerja PoW

        Returns:
            (True, None)     → chain valid
            (False, index)   → block pada `index` pertama yang rusak
        """
        prefix = "0" * self.difficulty
        genesis_sentinel = "0" * 64

        for i, block in enumerate(self.chain):

            # --- cek 1: hash konsisten dengan isi block ---
            if block.hash != block.recompute_hash():
                return False, block.index

            # --- cek 2: index harus sesuai posisi di list ---
            if block.index != i:
                return False, block.index

            if i == 0:
                # --- cek 4: prev_hash genesis harus "000...0" ---
                if block.prev_hash != genesis_sentinel:
                    return False, block.index
            else:
                # --- cek 3: tautan prev_hash ---
                if block.prev_hash != self.chain[i - 1].hash:
                    return False, block.index

            # --- cek 5: PoW terpenuhi ---
            if not block.hash.startswith(prefix):
                return False, block.index

        return True, None

    # ------------------------------------------------------------------
    # Serialisasi chain
    # ------------------------------------------------------------------

    def to_list(self) -> list[dict]:
        """
        Ubah seluruh chain ke list of dict.

        Dipakai untuk menyimpan ke tabel `blockchain` di SQLite
        (setiap dict menjadi satu baris).
        """
        return [b.to_dict() for b in self.chain]

    @classmethod
    def load_from_list(
        cls, data: list[dict], difficulty: Optional[int] = None
    ) -> "Blockchain":
        """
        Pulihkan chain dari list of dict (dari DB atau file JSON).

        TIDAK memanggil _create_genesis() — chain diisi penuh dari data.
        Hash TIDAK dihitung ulang saat load; panggil is_valid() setelah
        load untuk memastikan chain masih utuh.

        Args:
            data      : Output dari to_list() sebelumnya.
            difficulty: PoW difficulty. Default dari config.

        Returns:
            Blockchain yang dipulihkan.

        Raises:
            ValueError: Jika data kosong.
        """
        if not data:
            raise ValueError("Data chain tidak boleh kosong.")

        bc = cls.__new__(cls)          # bypass __init__ agar genesis tidak dibuat
        bc.difficulty = (
            difficulty if difficulty is not None else config.BLOCKCHAIN_DIFFICULTY
        )
        bc.chain = [Block.from_dict(d) for d in data]
        return bc
