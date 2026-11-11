"""Entry point SafeRelief untuk aplikasi desktop PySide6."""

import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from database import db
from ui.main_window import MainWindow


def _apply_light_theme(app: QApplication) -> None:
    """Tetapkan skema terang yang konsisten ke seluruh widget aplikasi."""
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#F8FAFC"))
    palette.setColor(QPalette.WindowText, QColor("#0F172A"))
    palette.setColor(QPalette.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.AlternateBase, QColor("#F8FAFC"))
    palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipText, QColor("#0F172A"))
    palette.setColor(QPalette.Text, QColor("#0F172A"))
    palette.setColor(QPalette.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ButtonText, QColor("#0F172A"))
    palette.setColor(QPalette.Light, QColor("#E2E8F0"))
    palette.setColor(QPalette.Midlight, QColor("#F1F5F9"))
    palette.setColor(QPalette.Dark, QColor("#94A3B8"))
    palette.setColor(QPalette.Mid, QColor("#CBD5E1"))
    palette.setColor(QPalette.Shadow, QColor("#0F172A"))
    palette.setColor(QPalette.Highlight, QColor("#0F172A"))
    palette.setColor(QPalette.HighlightedText, QColor("#F8FAFC"))
    palette.setColor(QPalette.Link, QColor("#0F172A"))
    palette.setColor(QPalette.LinkVisited, QColor("#0F172A"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#64748B"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#64748B"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#64748B"))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QWidget {
            background-color: #F8FAFC;
            color: #0F172A;
            font-family: "Segoe UI", sans-serif;
        }
        QLabel {
            color: #0F172A;
        }
        QLabel[objectName="dongleStatus"] {
            font-size: 14px;
            color: #0F172A;
        }
        QFrame {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
        }
        QPushButton {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            padding: 8px 12px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #F8FAFC;
            border-color: #CBD5E1;
        }
        QPushButton:pressed {
            background-color: #E2E8F0;
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
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 8px 10px;
            selection-background-color: #0F172A;
            selection-color: #F8FAFC;
        }
        QTableWidget {
            background-color: #FFFFFF;
            alternate-background-color: #F8FAFC;
            color: #0F172A;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            gridline-color: #E2E8F0;
        }
        QTableWidget::item {
            padding: 8px 10px;
            border: none;
            color: #0F172A;
        }
        QTableWidget::item:selected {
            background-color: #E2E8F0;
            color: #0F172A;
        }
        QHeaderView::section {
            background-color: #F8FAFC;
            color: #0F172A;
            padding: 10px 8px;
            font-weight: 700;
            border: 1px solid #E2E8F0;
        }
        QHeaderView {
            border: 0px;
        }
        QScrollBar:vertical,
        QScrollBar:horizontal {
            background: #F8FAFC;
            border: none;
        }
        QScrollBar::handle {
            background: #CBD5E1;
            border-radius: 6px;
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
