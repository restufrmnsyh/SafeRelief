"""Tema popup terpusat agar permukaan dialog tidak mewarisi transparansi halaman."""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox, QPushButton


MESSAGE_STYLE = """
QMessageBox, QMessageBox QWidget {
    background-color: #FFFFFF; color: #20243C;
    font-family: "Segoe UI"; font-size: 14px;
}
QMessageBox { border: none; }
QMessageBox QLabel {
    background-color: #FFFFFF; color: #20243C;
    border: none; border-radius: 0px; padding: 0px;
}
QMessageBox QPushButton {
    background-color: #FFFFFF; color: #393E58;
    border: 1px solid #747A92; border-radius: 8px;
    padding: 8px 18px; min-width: 72px; min-height: 26px;
    font-size: 13px; font-weight: 600;
}
QMessageBox QPushButton:hover { background-color: #EEEDFC; border-color: #4F50D9; }
QMessageBox QPushButton:pressed { background-color: #DEDCF7; border-color: #3334A8; }
QMessageBox QPushButton:default { background-color: #4F50D9; color: #FFFFFF; border-color: #4F50D9; }
QMessageBox QPushButton:default:hover { background-color: #4142BE; }
QMessageBox QPushButton:default:pressed { background-color: #3334A8; }
QMessageBox QPushButton:focus { border: 2px solid #20243C; padding: 7px 17px; }
QMessageBox QPushButton:disabled { background-color: #ECECF2; color: #62677F; }
QMessageBox QTextEdit {
    background-color: #F6F5FC; color: #20243C; border: 1px solid #747A92;
    selection-background-color: #4F50D9; selection-color: #FFFFFF;
}
"""

COMBO_POPUP_STYLE = """
QAbstractItemView, QAbstractItemView QWidget {
    background-color: #FFFFFF; color: #20243C;
    font-family: "Segoe UI"; font-size: 13px;
}
QAbstractItemView {
    border: 1px solid #747A92; padding: 4px;
    selection-background-color: #EEEDFC; selection-color: #3334A8;
}
QAbstractItemView::item { min-height: 32px; padding: 6px 12px; }
QAbstractItemView::item:selected { background-color: #EEEDFC; color: #3334A8; }
QAbstractItemView::item:disabled { color: #62677F; }
"""


class PopupTheme(QObject):
    """Pasang gaya lokal sebelum popup tampil, termasuk dari pemanggilan static QMessageBox."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() not in (QEvent.Type.Polish, QEvent.Type.Show):
            return super().eventFilter(watched, event)
        if isinstance(watched, QMessageBox) and watched.styleSheet() != MESSAGE_STYLE:
            # Stylesheet lokal mengalahkan selector halaman dengan background transparan.
            watched.setStyleSheet(MESSAGE_STYLE)
            watched.setMinimumWidth(320)
            palette = watched.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor("#FFFFFF"))
            palette.setColor(QPalette.ColorRole.WindowText, QColor("#20243C"))
            watched.setPalette(palette)
            if watched.layout() is not None:
                watched.layout().setContentsMargins(24, 24, 24, 20)
                watched.layout().setSpacing(16)
            for button in watched.findChildren(QPushButton):
                button.setMinimumHeight(44)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
        elif isinstance(watched, QComboBox):
            view = watched.view()
            if view.styleSheet() != COMBO_POPUP_STYLE:
                view.setStyleSheet(COMBO_POPUP_STYLE)
        return super().eventFilter(watched, event)


def install_popup_theme(app: QApplication) -> None:
    """Satu filter milik aplikasi menangani semua pesan tanpa mengganti isi atau hasilnya."""
    if not hasattr(app, "_saferelief_popup_theme"):
        theme = PopupTheme(app)
        app.installEventFilter(theme)
        app._saferelief_popup_theme = theme
