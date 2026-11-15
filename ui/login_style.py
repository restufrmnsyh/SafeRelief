"""Tema login lokal agar warna kontrol tidak mengikuti tema global Windows."""

LOGIN_STYLE = """
QWidget#loginPage, QScrollArea#loginScroll, QWidget#loginCanvas {
    background: #F6F5FC; color: #20243C; border: none;
    font-family: "Segoe UI"; font-size: 14px;
}
QFrame#mainLoginCard { background: #FFFFFF; border: none; border-radius: 16px; }
QFrame#loginAccount, QFrame#loginFace {
    background: #FFFFFF; border: none;
}
QLabel { background: transparent; color: #20243C; border: none; }
QLabel#loginTitle { font-size: 26px; font-weight: 700; }
QLabel#loginDescription, QLabel#loginCameraHint { color: #62677F; }
QLabel#loginSectionTitle { font-size: 16px; font-weight: 600; }
QLabel#loginFieldLabel { font-size: 13px; font-weight: 600; }
QLabel#loginGateStatus {
    color: #216345; background: #EDF7F1; border-radius: 8px; padding: 10px 12px;
    font-size: 13px; font-weight: 600;
}
QLabel#loginGateStatus[valid="false"] { color: #983A32; background: #FFF1EF; }
QWidget#loginPage QLineEdit {
    background: #FFFFFF; color: #20243C; border: 1px solid #747A92;
    border-radius: 8px; padding: 0 12px; min-height: 44px; font-size: 14px;
    placeholder-text-color: #62677F;
    selection-background-color: #4F50D9; selection-color: #FFFFFF;
}
QWidget#loginPage QLineEdit:focus { border: 2px solid #4F50D9; padding: 0 11px; }
QWidget#loginPage QPushButton {
    background: #4F50D9; color: #FFFFFF; border: 2px solid #4F50D9;
    border-radius: 8px; padding: 0 12px; min-height: 44px;
    font-size: 14px; font-weight: 600;
}
QWidget#loginPage QPushButton:hover { background: #4142BC; border-color: #4142BC; }
QWidget#loginPage QPushButton:pressed { background: #34359D; border-color: #34359D; }
QWidget#loginPage QPushButton:focus { border: 2px solid #20243C; }
QWidget#loginPage QPushButton:disabled {
    background: #ECECF5; color: #62677F; border: 1px solid #D9DCE9;
}
QLabel#loginCamera {
    background: #F6F5FC; color: #62677F; border: 1px solid #D9DCE9;
    border-radius: 12px; padding: 12px; font-size: 13px;
}
QLabel#loginMessage {
    background: transparent; color: #983A32; font-size: 13px;
}
QWidget#loginPage QScrollBar:vertical { background: #F6F5FC; width: 10px; }
QWidget#loginPage QScrollBar::handle:vertical {
    background: #747A92; border-radius: 4px; min-height: 28px;
}
QWidget#loginPage QScrollBar::add-line:vertical,
QWidget#loginPage QScrollBar::sub-line:vertical { height: 0; }
"""
