"""Entry point SafeRelief untuk aplikasi desktop PySide6."""

import sys

from PySide6.QtWidgets import QApplication

from database import db
from ui.main_window import MainWindow


def main() -> int:
    """Inisialisasi database dan jalankan event loop aplikasi."""
    app = QApplication(sys.argv)
    app.setApplicationName("SafeRelief")
    db.init_db()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
