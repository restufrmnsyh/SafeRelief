"""
SafeRelief - Tes Blockchain

Kriteria lulus Tahap 2 (blockchain):
- Genesis block dibuat otomatis, PoW terpenuhi
- add_block menambah block dengan prev_hash benar
- is_valid() mengembalikan (True, None) untuk chain bersih
- Ubah data block → (False, index_block_rusak)
- Ubah prev_hash block → (False, index_block_rusak)
- Ubah hash block langsung → (False, index_block_rusak)
- to_list / load_from_list round-trip identik
"""

import pytest
import copy

from crypto.blockchain import Block, Blockchain
import config


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def _build_chain(n_extra: int = 3, difficulty: int = 2) -> Blockchain:
    """Buat Blockchain dengan genesis + n_extra block data."""
    bc = Blockchain(difficulty=difficulty)
    for i in range(n_extra):
        bc.add_block({
            "jenis": "beras",
            "jumlah": (i + 1) * 10,
            "dari": "Posko A",
            "ke": f"Posko {i + 1}",
            "petugas": f"relawan_{i}",
        })
    return bc


# ─────────────────────────────────────────────
# Block unit
# ─────────────────────────────────────────────

class TestBlock:

    def test_hash_is_deterministic(self):
        """Hash blok sama jika semua field sama."""
        # timestamp int milidetik
        b1 = Block(0, 1_000_000_000, {"msg": "test"}, "0" * 64, nonce=5)
        b2 = Block(0, 1_000_000_000, {"msg": "test"}, "0" * 64, nonce=5)
        assert b1.hash == b2.hash

    def test_hash_changes_with_data(self):
        """Mengubah data mengubah hash."""
        b1 = Block(1, 1_000_000_000, {"jumlah": 10}, "abc", nonce=0)
        b2 = Block(1, 1_000_000_000, {"jumlah": 99}, "abc", nonce=0)
        assert b1.hash != b2.hash

    def test_pow_prefix(self):
        """Setelah mine(), hash diawali `difficulty` nol."""
        difficulty = 2
        b = Block(1, 1_000_000_000, {"x": 1}, "0" * 64)
        b.mine(difficulty)
        assert b.hash.startswith("0" * difficulty)

    def test_from_dict_restores_hash(self):
        """from_dict() memulihkan hash tersimpan, bukan menghitung ulang."""
        b = Block(1, 1_000_000_000, {"k": "v"}, "0" * 64, nonce=7)
        b.hash = "deadbeef" * 8          # hash palsu (64 char hex)
        d = b.to_dict()
        restored = Block.from_dict(d)
        assert restored.hash == "deadbeef" * 8   # hash palsu tetap ada

    def test_timestamp_is_int(self):
        """Timestamp yang disimpan harus int (milidetik), bukan float."""
        bc = Blockchain(difficulty=2)
        assert isinstance(bc.chain[0].timestamp, int)
        b = bc.add_block({"k": "v"})
        assert isinstance(b.timestamp, int)


# ─────────────────────────────────────────────
# Blockchain
# ─────────────────────────────────────────────

class TestBlockchain:

    def test_genesis_exists(self):
        """Chain baru selalu punya genesis block di index 0."""
        bc = Blockchain(difficulty=2)
        assert len(bc.chain) == 1
        assert bc.chain[0].index == 0

    def test_genesis_pow(self):
        """Genesis block memenuhi PoW."""
        bc = Blockchain(difficulty=2)
        assert bc.chain[0].hash.startswith("00")

    def test_add_block_links_prev_hash(self):
        """Block baru menyimpan hash block sebelumnya sebagai prev_hash."""
        bc = Blockchain(difficulty=2)
        b1 = bc.add_block({"jumlah": 5})
        b2 = bc.add_block({"jumlah": 10})
        assert b1.prev_hash == bc.chain[0].hash
        assert b2.prev_hash == b1.hash

    def test_add_block_pow(self):
        """Block yang ditambahkan memenuhi PoW."""
        bc = Blockchain(difficulty=2)
        b = bc.add_block({"x": 1})
        assert b.hash.startswith("00")

    def test_valid_chain(self):
        """Chain yang bersih adalah valid."""
        bc = _build_chain(3, difficulty=2)
        valid, broken_idx = bc.is_valid()
        assert valid is True
        assert broken_idx is None

    # ------------------------------------------------------------------
    # Deteksi tamper
    # ------------------------------------------------------------------

    def test_tamper_data_detected(self):
        """
        Mengubah data di block tengah terdeteksi;
        is_valid() mengembalikan False dan index block yang rusak.
        """
        bc = _build_chain(3, difficulty=2)
        target_idx = 2                          # block ke-2 (bukan genesis)

        # Ubah jumlah — hash lama tidak lagi cocok
        bc.chain[target_idx].data["jumlah"] = 9999

        valid, broken_idx = bc.is_valid()
        assert valid is False
        assert broken_idx == target_idx

    def test_tamper_prev_hash_detected(self):
        """
        Mengubah prev_hash sebuah block terdeteksi;
        is_valid() menunjuk block yang prev_hash-nya palsu.
        """
        bc = _build_chain(3, difficulty=2)
        target_idx = 2

        # Ubah prev_hash → cek 2 (tautan) gagal
        bc.chain[target_idx].prev_hash = "0" * 64

        valid, broken_idx = bc.is_valid()
        assert valid is False
        assert broken_idx == target_idx

    def test_tamper_hash_directly_detected(self):
        """
        Mengubah field hash langsung (tanpa mengubah data) terdeteksi;
        hash tersimpan tidak lagi sama dengan hash yang dihitung ulang.
        """
        bc = _build_chain(3, difficulty=2)
        target_idx = 1

        # Ganti hash dengan string acak sepanjang 64 hex
        bc.chain[target_idx].hash = "a" * 64

        valid, broken_idx = bc.is_valid()
        assert valid is False
        assert broken_idx == target_idx

    def test_tamper_genesis_detected(self):
        """Mengubah genesis block juga terdeteksi."""
        bc = _build_chain(2, difficulty=2)
        bc.chain[0].data["message"] = "TAMPERED"

        valid, broken_idx = bc.is_valid()
        assert valid is False
        assert broken_idx == 0

    def test_tamper_middle_cascades_correctly(self):
        """
        Jika block 2 diubah, is_valid() menunjuk block 2 (bukan 3),
        karena pemeriksaan berhenti di block rusak pertama.
        """
        bc = _build_chain(4, difficulty=2)
        bc.chain[2].data["jumlah"] = 1

        valid, broken_idx = bc.is_valid()
        assert valid is False
        assert broken_idx == 2     # pertama yang rusak, bukan 3 atau 4

    # ------------------------------------------------------------------
    # Serialisasi
    # ------------------------------------------------------------------

    def test_to_list_length(self):
        """to_list() menghasilkan list sepanjang chain."""
        bc = _build_chain(3, difficulty=2)
        lst = bc.to_list()
        assert len(lst) == 4        # genesis + 3

    def test_to_list_contains_all_fields(self):
        """Setiap dict di to_list() punya semua field yang diperlukan."""
        bc = Blockchain(difficulty=2)
        lst = bc.to_list()
        required = {"index", "timestamp", "data", "prev_hash", "nonce", "hash"}
        for item in lst:
            assert required.issubset(item.keys())

    def test_load_from_list_roundtrip(self):
        """load_from_list(to_list()) → chain identik dan masih valid."""
        bc_orig = _build_chain(3, difficulty=2)
        lst = bc_orig.to_list()

        bc_loaded = Blockchain.load_from_list(lst, difficulty=2)

        # Panjang sama
        assert len(bc_loaded.chain) == len(bc_orig.chain)

        # Setiap block identik
        for orig, loaded in zip(bc_orig.chain, bc_loaded.chain):
            assert orig.hash == loaded.hash
            assert orig.data == loaded.data
            assert orig.prev_hash == loaded.prev_hash

        # Masih valid setelah load
        valid, _ = bc_loaded.is_valid()
        assert valid is True

    def test_load_from_list_empty_raises(self):
        """load_from_list([]) harus raise ValueError."""
        with pytest.raises(ValueError):
            Blockchain.load_from_list([])

    def test_load_then_tamper_detected(self):
        """
        Chain yang di-load dari list, lalu di-tamper,
        tetap terdeteksi oleh is_valid().
        """
        bc = _build_chain(2, difficulty=2)
        lst = bc.to_list()

        # Tamper di list (sebelum load)
        lst[1]["data"]["jumlah"] = 9999

        bc_loaded = Blockchain.load_from_list(lst, difficulty=2)
        valid, broken_idx = bc_loaded.is_valid()
        assert valid is False
        assert broken_idx == 1

    # ------------------------------------------------------------------
    # Properti head dan height
    # ------------------------------------------------------------------

    def test_head_is_last_block(self):
        """head mengembalikan block terakhir."""
        bc = _build_chain(3, difficulty=2)
        assert bc.head is bc.chain[-1]
        assert bc.head.index == 3

    def test_height_equals_chain_length(self):
        """height mengembalikan panjang chain termasuk genesis."""
        bc = Blockchain(difficulty=2)
        assert bc.height == 1
        bc.add_block({"k": "v"})
        assert bc.height == 2

    # ------------------------------------------------------------------
    # Tes tambahan (poin 6 dari permintaan perbaikan)
    # ------------------------------------------------------------------

    def test_tamper_index_detected(self):
        """
        Mengubah block.index agar tidak sesuai posisi di list terdeteksi.
        is_valid() mengembalikan False dan index yang tidak konsisten.
        """
        bc = _build_chain(3, difficulty=2)
        # Ubah index block ke-2 menjadi 99 (tidak sesuai posisi 2)
        bc.chain[2].index = 99

        valid, broken_idx = bc.is_valid()
        assert valid is False
        assert broken_idx == 99       # nilai yang tersimpan di block.index

    def test_tamper_genesis_prev_hash_detected(self):
        """
        Mengubah prev_hash genesis (yang seharusnya '0'*64) terdeteksi.
        """
        bc = _build_chain(2, difficulty=2)
        bc.chain[0].prev_hash = "a" * 64   # bukan "0"*64

        valid, broken_idx = bc.is_valid()
        assert valid is False
        assert broken_idx == 0

    def test_add_block_rejects_int_key(self):
        """Data dengan key int (bukan str) harus ditolak dengan ValueError."""
        bc = Blockchain(difficulty=2)

        with pytest.raises(ValueError, match="str"):
            bc.add_block({1: "value"})     # key int → tidak valid

    def test_add_block_rejects_nested_int_key(self):
        """Key int di nested dict juga harus ditolak."""
        bc = Blockchain(difficulty=2)

        with pytest.raises(ValueError, match="str"):
            bc.add_block({"outer": {99: "inner"}})

    def test_add_block_deepcopy_isolates_data(self):
        """
        Mengubah dict asli setelah add_block TIDAK mengubah isi chain.
        deepcopy memastikan chain menyimpan snapshot saat penambahan.
        """
        bc = Blockchain(difficulty=2)
        data = {"jumlah": 50, "jenis": "beras"}
        block = bc.add_block(data)

        # Mutasi dict asli setelah block ditambahkan
        data["jumlah"] = 9999
        data["jenis"] = "diubah"

        # Chain tidak terpengaruh
        assert block.data["jumlah"] == 50
        assert block.data["jenis"] == "beras"

    def test_truncated_chain_is_valid(self):
        """
        DOKUMENTASI KETERBATASAN:
        Chain yang dipotong (block terakhir dihapus) tetap dianggap valid
        oleh is_valid() karena pemeriksaan hanya melihat konsistensi
        internal chain yang ada.

        Tanpa jangkar eksternal (misal: hash head yang disimpan terpisah),
        penghapusan block terakhir tidak bisa dideteksi.
        Ini keterbatasan yang disengaja dan dicatat di laporan.
        """
        bc = _build_chain(3, difficulty=2)   # genesis + 3 block

        # Hapus block terakhir
        bc.chain.pop()
        assert bc.height == 3               # sekarang genesis + 2 block

        # is_valid() tetap mengembalikan True — ini EXPECTED (keterbatasan)
        valid, broken_idx = bc.is_valid()
        assert valid is True, (
            "Penghapusan block terakhir tidak terdeteksi tanpa jangkar eksternal"
        )
