"""Tambahan tema bersama untuk tabel, formulir, dan dialog ruang kerja."""

WORKSPACE_STYLE = """
QWidget#dashboardPage QFrame#workspaceCard { background: #FFFFFF; border-radius: 16px; }
QWidget#dashboardPage QFrame#workspaceSidebar { background: #FFFFFF; }
QWidget#dashboardPage QLabel#workspaceTitle { font-size: 26px; font-weight: 700; }
QWidget#dashboardPage QLabel#workspaceSubtitle { color: #62677F; font-size: 13px; }
QWidget#dashboardPage QLabel#fieldCaption { color: #393E58; font-size: 12px; font-weight: 600; }
QWidget#dashboardPage QLabel#emptyMessage {
    color: #62677F; background: #F6F5FC; border-radius: 10px; padding: 16px;
}
QWidget#dashboardPage QPushButton[primary="true"] {
    background: #4F50D9; color: #FFFFFF; border: 2px solid #4F50D9;
}
QWidget#dashboardPage QPushButton[primary="true"]:hover { background: #4142BE; }
QWidget#dashboardPage QPushButton[primary="true"]:pressed { background: #3334A8; }
QWidget#dashboardPage QPushButton[primary="true"]:focus { border-color: #20243C; }
QWidget#dashboardPage QPushButton[primary="true"]:disabled {
    background: #ECECF2; color: #62677F; border-color: #747A92;
}
QWidget#dashboardPage QLineEdit, QWidget#dashboardPage QComboBox,
QWidget#dashboardPage QSpinBox, QWidget#dashboardPage QDoubleSpinBox {
    background: #FFFFFF; border: 1px solid #747A92; border-radius: 8px;
    color: #20243C; padding: 8px 12px; min-height: 26px;
    selection-background-color: #4F50D9; selection-color: #FFFFFF;
}
QWidget#dashboardPage QLineEdit:focus, QWidget#dashboardPage QComboBox:focus,
QWidget#dashboardPage QSpinBox:focus, QWidget#dashboardPage QDoubleSpinBox:focus {
    border: 2px solid #3334A8; padding: 7px 11px;
}
QWidget#dashboardPage QLineEdit:disabled, QWidget#dashboardPage QComboBox:disabled {
    background: #ECECF2; color: #62677F;
}
QWidget#dashboardPage QComboBox::drop-down {
    width: 24px; border: none; background: transparent;
}
QWidget#dashboardPage QPlainTextEdit, QWidget#dashboardPage QTextEdit,
QWidget#dashboardPage QListWidget {
    background: #F9F9FD; color: #20243C; border: 1px solid #747A92;
    border-radius: 10px; padding: 12px;
    selection-background-color: #EEEDFC; selection-color: #3334A8;
}
QWidget#dashboardPage QPlainTextEdit:focus, QWidget#dashboardPage QTextEdit:focus,
QWidget#dashboardPage QListWidget:focus { border: 2px solid #3334A8; padding: 11px; }
QWidget#dashboardPage QListWidget::item { padding: 12px; min-height: 28px; }
QWidget#dashboardPage QListWidget::item:selected { background: #EEEDFC; color: #3334A8; }
QWidget#dashboardPage QPlainTextEdit[encrypted="true"] {
    font-family: "Consolas", "Courier New"; font-size: 12px;
}
QWidget#dashboardPage QLabel#photoPreview {
    background: #F6F5FC; color: #62677F; border: 1px solid #747A92;
    border-radius: 12px; padding: 16px;
}
QWidget#dashboardPage QTableWidget::item { padding: 8px 12px; }
QWidget#dashboardPage QHeaderView::section {
    background: #F6F5FC; border: none; padding: 14px 12px;
}
QWidget#dashboardPage QScrollBar:horizontal { background: #F6F5FC; height: 10px; }
QWidget#dashboardPage QScrollBar::handle:horizontal {
    background: #747A92; min-width: 28px; border-radius: 5px;
}
QWidget#dashboardPage QScrollBar::add-line:horizontal,
QWidget#dashboardPage QScrollBar::sub-line:horizontal { width: 0px; }
QDialog#dashboardPage { background: #FFFFFF; }
"""


FORM_DIALOG_STYLE = """
QDialog#formDialog, QDialog#formDialog QWidget {
    background-color: #FFFFFF; color: #20243C;
    font-family: "Segoe UI"; font-size: 13px;
}
QDialog#formDialog QFrame, QDialog#formDialog QLabel {
    border: none; border-radius: 0px; padding: 0px;
}
QDialog#formDialog QLabel#workspaceTitle { font-size: 22px; font-weight: 700; }
QDialog#formDialog QLabel#dialogSubtitle { color: #62677F; }
QDialog#formDialog QLabel#sectionTitle { font-size: 15px; font-weight: 700; }
QDialog#formDialog QScrollArea { border: none; background-color: #FFFFFF; }
QDialog#formDialog QLineEdit, QDialog#formDialog QComboBox,
QDialog#formDialog QSpinBox, QDialog#formDialog QDoubleSpinBox {
    background-color: #FFFFFF; color: #20243C;
    border: 1px solid #747A92; border-radius: 8px;
    padding: 8px 12px; min-height: 26px;
    selection-background-color: #4F50D9; selection-color: #FFFFFF;
}
QDialog#formDialog QLineEdit:focus, QDialog#formDialog QComboBox:focus,
QDialog#formDialog QSpinBox:focus, QDialog#formDialog QDoubleSpinBox:focus {
    border: 2px solid #3334A8; padding: 7px 11px;
}
QDialog#formDialog QLineEdit:disabled, QDialog#formDialog QComboBox:disabled {
    background-color: #ECECF2; color: #62677F;
}
QDialog#formDialog QComboBox::drop-down { border: none; width: 24px; }
QDialog#formDialog QPushButton {
    background-color: #FFFFFF; color: #393E58;
    border: 1px solid #747A92; border-radius: 8px;
    padding: 8px 18px; min-height: 26px; min-width: 64px; font-weight: 600;
}
QDialog#formDialog QPushButton:hover { background-color: #EEEDFC; border-color: #4F50D9; }
QDialog#formDialog QPushButton:pressed { background-color: #DEDCF7; border-color: #3334A8; }
QDialog#formDialog QPushButton:focus { border: 2px solid #20243C; padding: 7px 17px; }
QDialog#formDialog QPushButton[primary="true"] {
    background-color: #4F50D9; color: #FFFFFF; border-color: #4F50D9;
}
QDialog#formDialog QPushButton[primary="true"]:hover { background-color: #4142BE; }
QDialog#formDialog QPushButton[primary="true"]:pressed { background-color: #3334A8; }
QDialog#formDialog QPushButton[primary="true"]:focus { border-color: #20243C; }
QDialog#formDialog QPushButton:disabled { background-color: #ECECF2; color: #62677F; }
QDialog#formDialog QTableWidget {
    background-color: #FFFFFF; color: #20243C;
    alternate-background-color: #F6F5FC; border: 1px solid #747A92;
    selection-background-color: #EEEDFC; selection-color: #3334A8;
}
QDialog#formDialog QTableWidget::item { padding: 8px 12px; }
QDialog#formDialog QHeaderView::section {
    background-color: #F6F5FC; color: #393E58; border: none; padding: 10px 12px;
}
QDialog#formDialog QScrollBar:vertical { background: #F6F5FC; width: 10px; }
QDialog#formDialog QScrollBar::handle:vertical {
    background: #747A92; min-height: 28px; border-radius: 5px;
}
QDialog#formDialog QScrollBar::add-line:vertical,
QDialog#formDialog QScrollBar::sub-line:vertical { height: 0px; }
"""
