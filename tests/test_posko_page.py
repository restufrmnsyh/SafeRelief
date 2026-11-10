"""Tes halaman manajemen posko untuk admin dan akses relawan."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import config
from auth import session
from database import db
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
