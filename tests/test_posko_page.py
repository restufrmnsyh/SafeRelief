"""Tes halaman manajemen posko untuk admin dan akses relawan."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import config
from auth import session
from database import db, secure_store
from ui.posko_management_page import PoskoFormDialog, PoskoManagementPage


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def posko_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp):
    database_path = tmp_path / "posko-page.db"
    monkeypatch.setattr(config, "DB_PATH", database_path)
    db.init_db(database_path)
    conn = db.get_connection(database_path)
    admin_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Admin Posko",
            "username": "admin_posko",
            "password_hash": "hash",
            "role": "admin",
        },
    )
    volunteer_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Relawan Posko",
            "username": "relawan_posko",
            "password_hash": "hash",
            "role": "relawan",
        },
    )
    posko_id = db.insert_posko(
        conn,
        {"nama": "Posko A", "lokasi": "Lokasi A", "kapasitas": 50},
    )
    db.insert_user(
        conn,
        {
            "nama_lengkap": "Relawan Tertaut",
            "username": "relawan_terikat",
            "password_hash": "hash",
            "role": "relawan",
            "posko_id": posko_id,
        },
    )
    db.insert_victim(
        conn,
        {
            "kode_korban": "K-1001",
            "nama_panggilan": "Mawar",
            "status": "selamat",
            "posko_id": posko_id,
            "created_by": volunteer_id,
        },
    )
    session.login({"id": admin_id, "username": "admin_posko", "role": "admin"}, os.urandom(config.MASTER_KEY_LENGTH))
    yield conn, admin_id, volunteer_id, posko_id
    session.logout()
    conn.close()


def test_posko_admin_can_add_edit_and_delete_records(
    posko_context,
    monkeypatch: pytest.MonkeyPatch,
    qapp,
):
    conn, _admin_id, _volunteer_id, existing_posko_id = posko_context

    page = PoskoManagementPage(conn)
    assert page.table.rowCount() >= 1
    assert any(str(row[0]) == "Posko A" for row in [
        (
            page.table.item(r, 0).text(),
            page.table.item(r, 1).text(),
            page.table.item(r, 2).text(),
        )
        for r in range(page.table.rowCount())
    ])

    monkeypatch.setattr(PoskoFormDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        PoskoFormDialog,
        "values",
        lambda self: {"nama": "Posko Baru", "lokasi": "Lokasi Baru", "kapasitas": 20},
    )
    page.add_posko()
    assert db.list_posko(conn)[-1]["nama"] == "Posko Baru"

    page.table.selectRow(0)
    monkeypatch.setattr(
        PoskoFormDialog,
        "values",
        lambda self: {"nama": "Posko A Diedit", "lokasi": "Lokasi A Update", "kapasitas": 77},
    )
    page.edit_posko()
    assert db.get_posko_by_id(conn, existing_posko_id)["nama"] == "Posko A Diedit"

    page.table.selectRow(page.table.rowCount() - 1)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    page.delete_posko()
    assert db.get_posko_by_id(conn, page._last_deleted_id) is None

    page.deleteLater()
    qapp.processEvents()


def test_posko_page_rejects_relawan_access(posko_context, qapp):
    conn, _admin_id, volunteer_id, _posko_id = posko_context
    session.login(
        {"id": volunteer_id, "username": "relawan_posko", "role": "relawan"},
        os.urandom(config.MASTER_KEY_LENGTH),
    )
    with pytest.raises(PermissionError, match="admin"):
        PoskoManagementPage(conn)
    session.logout()
    qapp.processEvents()


@pytest.mark.parametrize("operation", ["add_posko", "edit_posko", "delete_posko"])
@pytest.mark.parametrize("state", ["blocked", "logged_out", "relawan"])
def test_open_posko_page_rejects_lost_admin_access(
    posko_context, monkeypatch: pytest.MonkeyPatch, qapp,
    operation: str, state: str,
) -> None:
    """Izin halaman yang sudah terbuka harus mengikuti status sesi terkini."""
    conn, admin_id, volunteer_id, _posko_id = posko_context
    page = PoskoManagementPage(conn)
    page.table.selectRow(0)
    before = [dict(row) for row in db.list_posko(conn)]
    if state == "blocked":
        db.update_user_active(conn, admin_id, 0)
    elif state == "logged_out":
        session.logout()
    else:
        session.login(dict(db.get_user_by_id(conn, volunteer_id)), os.urandom(32))

    errors: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _p, _t, text: errors.append(text))
    getattr(page, operation)()
    assert errors
    assert [dict(row) for row in db.list_posko(conn)] == before
    page.refresh()
    assert page.table.rowCount() == 0
    page.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize("operation", ["add_posko", "edit_posko", "delete_posko"])
def test_posko_rechecks_admin_after_dialog(
    posko_context, monkeypatch: pytest.MonkeyPatch, qapp, operation: str,
) -> None:
    """Timer dapat berjalan ketika dialog modal terbuka; izin diperiksa lagi saat simpan."""
    conn, admin_id, _volunteer_id, _posko_id = posko_context
    page = PoskoManagementPage(conn)
    page.table.selectRow(0)
    before = [dict(row) for row in db.list_posko(conn)]

    def accept_after_blocking(*_args, **_kwargs):
        db.update_user_active(conn, admin_id, 0)
        return (QMessageBox.StandardButton.Yes if operation == "delete_posko"
                else QDialog.DialogCode.Accepted)

    monkeypatch.setattr(PoskoFormDialog, "exec", accept_after_blocking)
    monkeypatch.setattr(QMessageBox, "question", accept_after_blocking)
    monkeypatch.setattr(PoskoFormDialog, "values", lambda _self: {
        "nama": "Changed", "lokasi": "Changed", "kapasitas": 10,
    })
    errors: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda _p, _t, text: errors.append(text))
    getattr(page, operation)()
    assert errors
    assert [dict(row) for row in db.list_posko(conn)] == before
    page.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize("state", ["blocked", "relawan"])
def test_posko_logic_rejects_unauthorized_writes(posko_context, state: str) -> None:
    """Memanggil lapisan penyimpanan langsung tetap memerlukan admin aktif."""
    conn, admin_id, volunteer_id, posko_id = posko_context
    user_id = volunteer_id
    if state == "blocked":
        db.update_user_active(conn, admin_id, 0)
        user_id = admin_id
    data = {"nama": "Changed", "lokasi": "Changed", "kapasitas": 10}
    before = [dict(row) for row in db.list_posko(conn)]
    with pytest.raises(PermissionError):
        secure_store.add_posko(conn, user_id, data)
    with pytest.raises(PermissionError):
        secure_store.update_posko(conn, user_id, posko_id, data)
    with pytest.raises(PermissionError):
        secure_store.delete_posko(conn, user_id, posko_id)
    with pytest.raises(PermissionError):
        secure_store.list_admin_posko(conn, user_id)
    assert [dict(row) for row in db.list_posko(conn)] == before


def test_posko_counts_and_delete_confirmation_preserve_relations(
    posko_context, monkeypatch: pytest.MonkeyPatch, qapp,
) -> None:
    """Pembatalan hapus menjaga korban/relawan; konfirmasi hanya melepas poskonya."""
    conn, _admin_id, _volunteer_id, posko_id = posko_context
    page = PoskoManagementPage(conn)
    assert page.table.item(0, 3).text() == "1"
    assert page.table.item(0, 4).text() == "1"
    page.table.selectRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)
    page.delete_posko()
    assert db.get_posko_by_id(conn, posko_id) is not None
    assert db.get_victim_by_kode(conn, "K-1001")["posko_id"] == posko_id
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    page.delete_posko()
    assert db.get_posko_by_id(conn, posko_id) is None
    assert db.get_victim_by_kode(conn, "K-1001")["posko_id"] is None
    assert db.get_user_by_username(conn, "relawan_terikat")["posko_id"] is None
    page.deleteLater()
    qapp.processEvents()
