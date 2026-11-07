"""Manajemen sesi autentikasi SafeRelief."""

import os
from datetime import datetime

import config
from crypto import keys


class Session:
    """Menyimpan identitas user dan master key selama sesi aktif."""

    def __init__(self) -> None:
        self.user: dict[str, object] | None = None
        self._master_key: bytearray | None = None
        self.login_time: datetime | None = None

    @property
    def master_key(self) -> bytes | None:
        """Kembalikan salinan bytes; kunci sesi tetap disimpan mutable untuk dibersihkan."""
        if self._master_key is None:
            return None
        return bytes(self._master_key)

    def login(self, user: dict[str, object], master_key: bytes) -> None:
        """Mulai sesi dengan salinan data user dan master key."""
        if len(master_key) != config.MASTER_KEY_LENGTH:
            raise ValueError(
                f"Master key harus {config.MASTER_KEY_LENGTH} bytes"
            )

        # Bersihkan sesi sebelumnya sebelum mengganti key di memori.
        self.logout()
        self.user = dict(user)
        self._master_key = bytearray(master_key)
        self.login_time = datetime.now()

    def get_derived_key(self, label: bytes) -> bytes:
        """Turunkan kunci sesi untuk label tertentu; gagal jika belum login."""
        if not self.is_logged_in():
            raise RuntimeError("Tidak ada sesi login aktif.")
        return keys.derive_key(bytes(self._master_key), label)

    def get_vigenere_key(self) -> str:
        """Turunkan kunci Vigenere otomatis dari master key sesi."""
        if not self.is_logged_in():
            raise RuntimeError("Tidak ada sesi login aktif.")
        return keys.derive_vigenere_key(bytes(self._master_key))

    def logout(self) -> None:
        """Acak buffer master key sebelum melepaskannya dan hapus identitas sesi."""
        if self._master_key is not None:
            self._master_key[:] = os.urandom(len(self._master_key))
            self._master_key = None
        if self.user is not None:
            self.user.clear()
            self.user = None
        self.login_time = None

    def is_logged_in(self) -> bool:
        """Tentukan apakah user dan master key tersedia bersama."""
        return self.user is not None and self._master_key is not None


_active_session = Session()


def login(user: dict[str, object], master_key: bytes) -> None:
    """Mulai sesi aktif aplikasi."""
    _active_session.login(user, master_key)


def get_derived_key(label: bytes) -> bytes:
    """Turunkan kunci dari master key sesi aktif."""
    return _active_session.get_derived_key(label)


def get_vigenere_key() -> str:
    """Ambil kunci Vigenere turunan untuk sesi aktif."""
    return _active_session.get_vigenere_key()


def logout() -> None:
    """Akhiri sesi aktif dan bersihkan data sensitif dari state sesi."""
    _active_session.logout()


def is_logged_in() -> bool:
    """Periksa apakah aplikasi memiliki sesi aktif."""
    return _active_session.is_logged_in()


def get_current_user() -> dict[str, object]:
    """Kembalikan identitas sesi aktif tanpa mengekspos objek state internal."""
    if _active_session.user is None:
        raise RuntimeError("Tidak ada sesi login aktif.")
    return dict(_active_session.user)


def get_master_key() -> bytes:
    """Kembalikan salinan master key hanya untuk operasi kriptografi sesi."""
    master_key = _active_session.master_key
    if master_key is None:
        raise RuntimeError("Tidak ada sesi login aktif.")
    return master_key
