"""Entry point SafeRelief untuk aplikasi desktop PySide6."""

import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from database import db
from ui.main_window import MainWindow


def _apply_light_theme(app: QApplication) -> None:
    """Tetapkan skema visual modern pastel sesuai referensi desain tanpa mengubah logika aplikasi."""
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#EAF3F7"))
    palette.setColor(QPalette.WindowText, QColor("#1E2A39"))
    palette.setColor(QPalette.Base, QColor("#F9FCFF"))
    palette.setColor(QPalette.AlternateBase, QColor("#EEF8FF"))
    palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipText, QColor("#1E2A39"))
    palette.setColor(QPalette.Text, QColor("#1E2A39"))
    palette.setColor(QPalette.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ButtonText, QColor("#1E2A39"))
    palette.setColor(QPalette.Light, QColor("#F1F9FF"))
    palette.setColor(QPalette.Midlight, QColor("#DDECF8"))
    palette.setColor(QPalette.Dark, QColor("#93AFC5"))
    palette.setColor(QPalette.Mid, QColor("#C8D9E8"))
    palette.setColor(QPalette.Shadow, QColor("#30506A"))
    palette.setColor(QPalette.Highlight, QColor("#7FB8D6"))
    palette.setColor(QPalette.HighlightedText, QColor("#102033"))
    palette.setColor(QPalette.Link, QColor("#3A6C8E"))
    palette.setColor(QPalette.LinkVisited, QColor("#3A6C8E"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#6E879C"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#6E879C"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#6E879C"))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QWidget {
            background-color: #EAF3F7;
            color: #1E2A39;
            font-family: "Segoe UI", sans-serif;
        }
        QMainWindow, QStackedWidget {
            background: #EAF3F7;
        }
        QLabel {
            color: #1E2A39;
        }
        QLabel[objectName="dongleStatus"] {
            font-size: 15px;
            font-weight: 700;
            color: #1E2A39;
            letter-spacing: 0.2px;
        }
        QFrame {
            background-color: #F7FBFF;
            border: 1px solid #CFE2EC;
            border-radius: 18px;
        }
        QPushButton {
            background-color: #FFFFFF;
            color: #1E2A39;
            border: 1px solid #D7E6F2;
            border-radius: 12px;
            padding: 10px 14px;
            font-weight: 700;
            min-height: 32px;
        }
        QPushButton:hover {
            background-color: #EEF7FF;
            border-color: #BCD8EB;
        }
        QPushButton:pressed {
            background-color: #DDECF8;
        }
        QPushButton:default {
            background-color: #87BDD9;
            color: #102033;
            border: 1px solid #75AFCB;
        }
        QLineEdit,
        QTextEdit,
        QPlainTextEdit,
        QComboBox,
        QSpinBox,
        QDoubleSpinBox,
        QDateEdit,
        QTimeEdit,
        QDateTimeEdit {
            background-color: #F9FCFF;
            color: #1E2A39;
            border: 1px solid #D4E5F1;
            border-radius: 10px;
            padding: 9px 12px;
            selection-background-color: #89BBD8;
            selection-color: #102033;
        }
        QComboBox::drop-down {
            border: none;
            background: transparent;
        }
        QComboBox {
            padding-right: 26px;
        }
        QTableWidget {
            background-color: #F9FCFF;
            alternate-background-color: #F2F9FF;
            color: #1E2A39;
            border: 1px solid #D4E5F1;
            border-radius: 14px;
            gridline-color: #DDECF8;
        }
        QTableWidget::item {
            padding: 10px 12px;
            border: none;
            color: #1E2A39;
        }
        QTableWidget::item:selected {
            background-color: #DDECF8;
            color: #102033;
        }
        QHeaderView::section {
            background-color: #EDF6FC;
            color: #1E2A39;
            padding: 10px 8px;
            font-weight: 700;
            border: 1px solid #D4E5F1;
        }
        QHeaderView {
            border: 0px;
        }
        QScrollBar:vertical,
        QScrollBar:horizontal {
            background: #EAF3F7;
            border: none;
        }
        QScrollBar::handle {
            background: #B8D6E7;
            border-radius: 7px;
        }
        QMessageBox {
            background-color: #F7FBFF;
        }
        QMessageBox QLabel {
            color: #1E2A39;
        }
        QMessageBox QPushButton {
            min-width: 90px;
        }
        """
    )


def main() -> int:
    """Inisialisasi database dan jalankan event loop aplikasi."""
    app = QApplication(sys.argv)
    _apply_light_theme(app)
    app.setApplicationName("SafeRelief")
    db.init_db()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
