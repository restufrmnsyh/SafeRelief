"""Tes penyimpanan dan pembersihan data sesi autentikasi."""

import os

import pytest

from auth import session as auth_session
from crypto import keys


@pytest.fixture(autouse=True)
def clear_session():
    """Pastikan state global tiap tes dimulai dan berakhir dalam keadaan bersih."""
    auth_session.logout()
    yield
    auth_session.logout()


def test_login_stores_user_master_key_and_time() -> None:
    user = {"id": 7, "username": "relawan"}
    master_key = os.urandom(32)

    auth_session.login(user, master_key)

    assert auth_session.is_logged_in()
    assert auth_session._active_session.user == user
    assert auth_session._active_session.master_key == master_key
    assert auth_session._active_session.login_time is not None


def test_get_derived_key_matches_crypto_keys() -> None:
    master_key = os.urandom(32)
    auth_session.login({"id": 1}, master_key)

    assert auth_session.get_derived_key(b"db") == keys.derive_key(master_key, b"db")
    assert auth_session.get_derived_key(b"db") == auth_session.get_derived_key(b"db")


def test_get_vigenere_key_matches_crypto_keys() -> None:
    master_key = os.urandom(32)
    auth_session.login({"id": 1}, master_key)

    assert auth_session.get_vigenere_key() == keys.derive_vigenere_key(master_key)


def test_logout_clears_state_and_overwrites_key(monkeypatch) -> None:
    master_key = os.urandom(32)
    auth_session.login({"id": 1, "username": "relawan"}, master_key)
    key_buffer = auth_session._active_session._master_key
    user_state = auth_session._active_session.user
    monkeypatch.setattr(auth_session.os, "urandom", lambda size: b"\xa5" * size)

    auth_session.logout()

    assert key_buffer == b"\xa5" * len(master_key)
    assert user_state == {}
    assert auth_session._active_session.master_key is None
    assert auth_session._active_session.user is None
    assert auth_session._active_session.login_time is None
    assert not auth_session.is_logged_in()


def test_get_derived_key_after_logout_raises() -> None:
    auth_session.login({"id": 1}, os.urandom(32))
    auth_session.logout()

    with pytest.raises(RuntimeError, match="Tidak ada sesi"):
        auth_session.get_derived_key(b"db")


def test_get_vigenere_key_after_logout_raises() -> None:
    auth_session.login({"id": 1}, os.urandom(32))
    auth_session.logout()

    with pytest.raises(RuntimeError, match="Tidak ada sesi"):
        auth_session.get_vigenere_key()
