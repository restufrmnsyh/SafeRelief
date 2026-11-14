"""
SafeRelief - Tes Autentikasi (4a Login + 4b Dongle)

Strategi mocking:
- psutil.disk_partitions dan get_volume_serial di-mock karena:
  (1) tes tidak boleh bergantung pada USB fisik yang tercolok,
  (2) Windows API (GetVolumeInformationW) tidak tersedia di semua mesin.
- Mocking dilakukan dengan pytest.monkeypatch pada level modul
  auth.dongle sehingga kode lain tidak terpengaruh.
- File .saferelief_key ditulis ke tmp_path (bukan ke drive nyata).
"""

import hashlib
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config
from auth import login as auth_login
from auth import dongle as auth_dongle
from crypto.hashing import hash_password
from database import db


# ─────────────────────────────────────────────────────────────────────
# Fixtures DB
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    path = tmp_path / "test.db"
    db.init_db(path)
    return path


@pytest.fixture()
def conn(tmp_db):
    with db.get_connection(tmp_db) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────

def _make_user(conn, username="user1", password="pass_aman_123",
               role="relawan", is_active=1):
    """Buat user dengan password yang di-hash."""
    return db.insert_user(conn, {
        "nama_lengkap": f"User {username}",
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "is_active": is_active,
    })


# ═════════════════════════════════════════════════════════════════════
# Tes Login (4a)
# ═════════════════════════════════════════════════════════════════════

class TestLogin:

    def test_login_success(self, conn):
        """Login dengan kredensial benar mengembalikan dict user."""
        _make_user(conn, username="alice", password="correct_pass")
        result = auth_login.authenticate(conn, "alice", "correct_pass")
        assert result["username"] == "alice"

    def test_login_wrong_password(self, conn):
        """Password salah raise ValueError dengan pesan generik."""
        _make_user(conn, username="bob", password="right_pass")
        with pytest.raises(ValueError, match="Username atau password salah"):
            auth_login.authenticate(conn, "bob", "wrong_pass")

    def test_login_user_not_found(self, conn):
        """User tidak ada memberi pesan SAMA dengan password salah."""
        with pytest.raises(ValueError) as exc_info:
            auth_login.authenticate(conn, "ghost_user", "anypass")
        # Pesan harus sama persis — tidak boleh ada "tidak ditemukan" dll.
        assert str(exc_info.value) == "Username atau password salah"

    def test_login_inactive_account_same_message(self, conn):
        """Akun nonaktif memberi pesan SAMA dengan password salah."""
        _make_user(conn, username="inactive", password="pass123",
                   is_active=0)
        with pytest.raises(ValueError) as exc_info:
            auth_login.authenticate(conn, "inactive", "pass123")
        assert str(exc_info.value) == "Username atau password salah"

    def test_three_failures_lock_account(self, conn):
        """3x gagal berturut-turut mengunci akun."""
        _make_user(conn, username="carol", password="real_pass")
        for _ in range(config.MAX_LOGIN_ATTEMPTS):
            with pytest.raises(ValueError):
                auth_login.authenticate(conn, "carol", "bad_pass")

        row = db.get_user_by_username(conn, "carol")
        assert row["failed_attempts"] >= config.MAX_LOGIN_ATTEMPTS
        assert row["locked_until"] is not None

    def test_locked_account_rejects_correct_password(self, conn):
        """Saat terkunci, password yang BENAR pun ditolak."""
        _make_user(conn, username="dave", password="correct")
        # Kunci manual
        lock_until = (datetime.now() + timedelta(seconds=300)).isoformat()
        uid = db.get_user_by_username(conn, "dave")["id"]
        db.update_user_login_attempt(conn, uid, 3, lock_until)

        with pytest.raises(ValueError, match="terkunci"):
            auth_login.authenticate(conn, "dave", "correct")

    def test_lockout_message_contains_time(self, conn):
        """Pesan lockout menyebut sisa waktu."""
        _make_user(conn, username="eve", password="pass")
        lock_until = (datetime.now() + timedelta(minutes=3, seconds=45)).isoformat()
        uid = db.get_user_by_username(conn, "eve")["id"]
        db.update_user_login_attempt(conn, uid, 3, lock_until)

        with pytest.raises(ValueError) as exc_info:
            auth_login.authenticate(conn, "eve", "pass")
        msg = str(exc_info.value)
        assert "menit" in msg
        assert "detik" in msg

    def test_lockout_expires_allows_login(self, conn):
        """Setelah locked_until lewat, login bisa dilakukan lagi."""
        _make_user(conn, username="frank", password="mypass")
        # Set lock di masa lalu (sudah lewat)
        past_lock = (datetime.now() - timedelta(seconds=1)).isoformat()
        uid = db.get_user_by_username(conn, "frank")["id"]
        db.update_user_login_attempt(conn, uid, 3, past_lock)

        # Harus bisa login karena lockout sudah kedaluwarsa
        result = auth_login.authenticate(conn, "frank", "mypass")
        assert result["username"] == "frank"

    def test_expired_lockout_starts_a_new_three_attempt_window(self, conn):
        """Salah pertama setelah lima menit tidak memakai hitungan sebelum lockout."""
        uid = _make_user(conn, username="retry", password="correct-password")
        past = (datetime.now() - timedelta(seconds=1)).isoformat()
        db.update_user_login_attempt(conn, uid, config.MAX_LOGIN_ATTEMPTS, past)

        for attempt in range(1, config.MAX_LOGIN_ATTEMPTS + 1):
            with pytest.raises(ValueError, match="Username atau password salah"):
                auth_login.authenticate(conn, "retry", "wrong-password")
            row = db.get_user_by_id(conn, uid)
            assert row["failed_attempts"] == attempt
            assert bool(row["locked_until"]) == (attempt == config.MAX_LOGIN_ATTEMPTS)

        with pytest.raises(ValueError, match="terkunci"):
            auth_login.authenticate(conn, "retry", "correct-password")

    def test_success_resets_failed_attempts(self, conn):
        """Login sukses mereset failed_attempts ke 0."""
        _make_user(conn, username="grace", password="pass_g")
        uid = db.get_user_by_username(conn, "grace")["id"]
        # Set 2 percobaan gagal
        db.update_user_login_attempt(conn, uid, 2, None)

        auth_login.authenticate(conn, "grace", "pass_g")

        row = db.get_user_by_username(conn, "grace")
        assert row["failed_attempts"] == 0
        assert row["locked_until"] is None

    def test_password_verified_is_not_a_complete_login(self, conn):
        """Password benar belum membuktikan dongle dan wajah."""
        _make_user(conn, username="harry", password="h_pass")
        auth_login.authenticate(conn, "harry", "h_pass")

        logs = db.list_activity_log(conn)
        aksi_list = [r["aksi"] for r in logs]
        assert "PASSWORD_VERIFIED" in aksi_list
        assert "LOGIN_SUCCESS" not in aksi_list

    def test_login_logs_failure(self, conn):
        """Login gagal dicatat di activity_log."""
        _make_user(conn, username="ivan", password="i_pass")
        with pytest.raises(ValueError):
            auth_login.authenticate(conn, "ivan", "wrong")

        logs = db.list_activity_log(conn)
        aksi_list = [r["aksi"] for r in logs]
        assert "LOGIN_FAILED" in aksi_list

    def test_logout_logs_event(self, conn):
        """logout() mencatat LOGOUT ke activity_log."""
        uid = _make_user(conn, username="judy", password="j_pass")
        auth_login.logout(conn, uid)

        logs = db.list_activity_log(conn)
        aksi_list = [r["aksi"] for r in logs]
        assert "LOGOUT" in aksi_list


# ═════════════════════════════════════════════════════════════════════
# Tes Dongle (4b)
#
# Mock strategy:
# - auth_dongle.find_removable_drives → kembalikan ['D:\\'] (simulasi USB)
# - auth_dongle.get_volume_serial     → kembalikan serial tetap 'AABB1122'
# - File token ditulis ke tmp_path, bukan ke drive nyata
# ═════════════════════════════════════════════════════════════════════

FAKE_DRIVE  = "D:\\"
FAKE_SERIAL = "AABB1122"


class TestDongle:

    # ── helpers internal ───────────────────────────────────────────────

    def _patch_drive(self, monkeypatch, drive=FAKE_DRIVE, serial=FAKE_SERIAL):
        """
        Mock find_removable_drives dan get_volume_serial.
        Mengembalikan list drive yang berisi 1 USB dengan serial tetap.
        """
        monkeypatch.setattr(
            auth_dongle, "find_removable_drives", lambda: [drive]
        )
        monkeypatch.setattr(
            auth_dongle, "get_volume_serial", lambda d: serial
        )

    def _write_token_file(self, drive_dir: Path, token: bytes) -> None:
        """Tulis file token ke direktori yang mewakili drive."""
        (drive_dir / config.DONGLE_KEY_FILE).write_text(
            token.hex(), encoding="ascii"
        )

    def _provision(self, conn, tmp_path, monkeypatch, user_id,
                   drive=FAKE_DRIVE, serial=FAKE_SERIAL):
        """
        Jalankan provision_dongle dengan drive yang di-mock ke tmp_path.
        Mengembalikan token yang dihasilkan.
        """
        self._patch_drive(monkeypatch, drive, serial)

        # provision_dongle akan menulis ke Path(drive) / DONGLE_KEY_FILE
        # Kita mock _token_path agar menulis ke tmp_path
        monkeypatch.setattr(
            auth_dongle, "_token_path",
            lambda d: tmp_path / config.DONGLE_KEY_FILE
        )
        token = auth_dongle.provision_dongle(conn, drive, user_id)
        return token

    # ── tes ───────────────────────────────────────────────────────────

    def test_provision_then_verify_success(self, conn, tmp_path, monkeypatch):
        """Provision lalu verify dengan drive yang sama → sukses."""
        uid = db.insert_user(conn, {
            "nama_lengkap": "Relawan A",
            "username": "rel_a",
            "password_hash": "h",
            "role": "relawan",
        })

        token = self._provision(conn, tmp_path, monkeypatch, uid)

        # Patch read_token agar membaca dari tmp_path
        monkeypatch.setattr(
            auth_dongle, "read_token",
            lambda d: token   # kembalikan token yang sama
        )
        self._patch_drive(monkeypatch)

        user_row = db.get_user_by_id(conn, uid)
        result = auth_dongle.verify_dongle(user_row)
        assert result == token

    def test_verify_wrong_serial_fails(self, conn, tmp_path, monkeypatch):
        """Drive dengan serial berbeda → verify gagal."""
        uid = db.insert_user(conn, {
            "nama_lengkap": "Relawan B",
            "username": "rel_b",
            "password_hash": "h",
            "role": "relawan",
        })
        self._provision(conn, tmp_path, monkeypatch, uid)

        # Sekarang tancap USB dengan serial berbeda
        monkeypatch.setattr(
            auth_dongle, "find_removable_drives", lambda: [FAKE_DRIVE]
        )
        monkeypatch.setattr(
            auth_dongle, "get_volume_serial", lambda d: "FFFFFFFF"  # salah
        )

        user_row = db.get_user_by_id(conn, uid)
        with pytest.raises(ValueError, match="tidak ditemukan"):
            auth_dongle.verify_dongle(user_row)

    def test_verify_tampered_token_fails(self, conn, tmp_path, monkeypatch):
        """Token diubah → hash tidak cocok → verify gagal."""
        uid = db.insert_user(conn, {
            "nama_lengkap": "Relawan C",
            "username": "rel_c",
            "password_hash": "h",
            "role": "relawan",
        })
        self._provision(conn, tmp_path, monkeypatch, uid)
        self._patch_drive(monkeypatch)

        # Ubah token yang dibaca (simulasi file dimodifikasi)
        tampered_token = os.urandom(32)
        monkeypatch.setattr(
            auth_dongle, "read_token",
            lambda d: tampered_token
        )

        user_row = db.get_user_by_id(conn, uid)
        with pytest.raises(ValueError, match="tidak valid"):
            auth_dongle.verify_dongle(user_row)

    def test_provision_duplicate_serial_rejected(self, conn, tmp_path, monkeypatch):
        """Serial yang sama tidak boleh dipakai dua user berbeda."""
        uid1 = db.insert_user(conn, {
            "nama_lengkap": "User 1", "username": "u1",
            "password_hash": "h", "role": "relawan",
        })
        uid2 = db.insert_user(conn, {
            "nama_lengkap": "User 2", "username": "u2",
            "password_hash": "h", "role": "relawan",
        })

        # Provision user 1 dengan FAKE_SERIAL
        self._provision(conn, tmp_path, monkeypatch, uid1)

        # Coba provision user 2 dengan serial YANG SAMA
        self._patch_drive(monkeypatch)
        monkeypatch.setattr(
            auth_dongle, "_token_path",
            lambda d: tmp_path / config.DONGLE_KEY_FILE
        )
        with pytest.raises(ValueError, match="sudah dipakai"):
            auth_dongle.provision_dongle(conn, FAKE_DRIVE, uid2)

    def test_provision_same_user_same_serial_allowed(self, conn, tmp_path, monkeypatch):
        """Re-provision dongle untuk user yang SAMA boleh (ganti token)."""
        uid = db.insert_user(conn, {
            "nama_lengkap": "User X", "username": "ux",
            "password_hash": "h", "role": "relawan",
        })
        # Provision pertama
        self._provision(conn, tmp_path, monkeypatch, uid)
        # Provision ulang (serial sama, user sama) — tidak boleh error
        self._provision(conn, tmp_path, monkeypatch, uid)

    def test_verify_no_dongle_registered_fails(self, conn, monkeypatch):
        """User tanpa dongle_serial → verify langsung gagal."""
        uid = db.insert_user(conn, {
            "nama_lengkap": "No Dongle", "username": "nd",
            "password_hash": "h", "role": "relawan",
        })
        user_row = db.get_user_by_id(conn, uid)
        with pytest.raises(ValueError, match="belum memiliki dongle"):
            auth_dongle.verify_dongle(user_row)

    def test_verify_file_missing_fails(self, conn, tmp_path, monkeypatch):
        """File .saferelief_key hilang dari drive → verify gagal."""
        uid = db.insert_user(conn, {
            "nama_lengkap": "Rel D", "username": "rd",
            "password_hash": "h", "role": "relawan",
        })
        self._provision(conn, tmp_path, monkeypatch, uid)
        self._patch_drive(monkeypatch)

        # File dihapus setelah provision
        (tmp_path / config.DONGLE_KEY_FILE).unlink()
        monkeypatch.setattr(
            auth_dongle, "read_token",
            lambda d: (_ for _ in ()).throw(FileNotFoundError("hilang"))
        )

        user_row = db.get_user_by_id(conn, uid)
        with pytest.raises(ValueError):
            auth_dongle.verify_dongle(user_row)

    def test_is_any_valid_dongle_present_true(self, conn, tmp_path, monkeypatch):
        """is_any_valid_dongle_present True jika ada dongle valid."""
        uid = db.insert_user(conn, {
            "nama_lengkap": "Rel E", "username": "re",
            "password_hash": "h", "role": "relawan",
        })
        token = self._provision(conn, tmp_path, monkeypatch, uid)
        self._patch_drive(monkeypatch)
        monkeypatch.setattr(auth_dongle, "read_token", lambda d: token)

        assert auth_dongle.is_any_valid_dongle_present(conn) is True

    def test_is_any_valid_dongle_present_false_no_drive(self, conn, monkeypatch):
        """is_any_valid_dongle_present False jika tidak ada USB tercolok."""
        monkeypatch.setattr(auth_dongle, "find_removable_drives", lambda: [])
        assert auth_dongle.is_any_valid_dongle_present(conn) is False

    def test_read_token_invalid_hex(self, tmp_path):
        """File token berisi bukan hex → ValueError."""
        token_file = tmp_path / config.DONGLE_KEY_FILE
        token_file.write_text("BUKAN_HEX_SAMA_SEKALI!!!", encoding="ascii")

        # Patch _token_path agar menunjuk ke tmp_path
        with patch.object(auth_dongle, "_token_path", return_value=token_file):
            with pytest.raises(ValueError, match="hex"):
                auth_dongle.read_token("D:\\")

    def test_read_token_wrong_length(self, tmp_path):
        """File token hex valid tapi panjang bukan 32 byte → ValueError."""
        token_file = tmp_path / config.DONGLE_KEY_FILE
        # 16 byte (32 hex chars) → terlalu pendek
        token_file.write_text(os.urandom(16).hex(), encoding="ascii")

        with patch.object(auth_dongle, "_token_path", return_value=token_file):
            with pytest.raises(ValueError, match="Panjang token"):
                auth_dongle.read_token("D:\\")
