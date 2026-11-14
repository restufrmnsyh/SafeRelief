"""Tema dashboard dibatasi selector agar halaman autentikasi tidak berubah."""

DASHBOARD_STYLE = """
QWidget#dashboardPage { background: #F6F5FC; color: #20243C; }
QWidget#dashboardPage QWidget {
    background: transparent; color: #20243C; font-family: "Segoe UI"; font-size: 13px;
}
QWidget#dashboardPage QFrame, QWidget#dashboardPage QLabel {
    border: none; border-radius: 0px; padding: 0px;
}
QWidget#dashboardPage QFrame#sidebar, QWidget#dashboardPage QFrame#contextPanel {
    background: #FFFFFF; border-radius: 0px;
}
QWidget#dashboardPage QLabel#brand { font-size: 22px; font-weight: 700; }
QWidget#dashboardPage QLabel#muted {
    color: #62677F; font-size: 12px;
}
QWidget#dashboardPage QPushButton, QWidget#dashboardPage QToolButton {
    background: #FFFFFF; border: 1px solid #747A92; border-radius: 8px;
    color: #393E58; padding: 8px 14px; min-height: 26px;
    font-size: 13px; font-weight: 600;
}
QWidget#dashboardPage QPushButton:hover, QWidget#dashboardPage QToolButton:hover {
    background: #EEEDFC; border-color: #4F50D9;
}
QWidget#dashboardPage QPushButton:pressed, QWidget#dashboardPage QToolButton:pressed {
    background: #DEDCF7; border-color: #3334A8;
}
QWidget#dashboardPage QPushButton:focus, QWidget#dashboardPage QToolButton:focus {
    border: 2px solid #3334A8; padding: 7px 13px;
}
QWidget#dashboardPage QPushButton:disabled {
    background: #ECECF2; color: #62677F; border-color: #747A92;
}
QWidget#dashboardPage QPushButton[nav="true"] {
    text-align: left; background: transparent; border: 2px solid transparent;
    color: #393E58; font-weight: 400; padding: 8px 12px;
}
QWidget#dashboardPage QPushButton[nav="true"]:hover { background: #F6F5FC; color: #3334A8; }
QWidget#dashboardPage QPushButton[nav="true"]:checked {
    background: #EEEDFC; color: #3334A8; font-weight: 700;
}
QWidget#dashboardPage QPushButton[nav="true"]:pressed { background: #DEDCF7; }
QWidget#dashboardPage QPushButton[nav="true"]:focus { border-color: #3334A8; }
QWidget#dashboardPage QToolButton[groupToggle="true"] {
    background: transparent; border: 2px solid transparent;
    color: #393E58; font-size: 12px; font-weight: 700;
    padding: 8px 10px; text-align: left;
}
QWidget#dashboardPage QToolButton[groupToggle="true"]:hover { background: #F6F5FC; }
QWidget#dashboardPage QToolButton[groupToggle="true"]:pressed { background: #DEDCF7; }
QWidget#dashboardPage QToolButton[groupToggle="true"]:focus { border-color: #3334A8; }
QWidget#dashboardPage QLabel#pageTitle { font-size: 22px; font-weight: 700; }
QWidget#dashboardPage QLabel#sectionTitle { font-size: 15px; font-weight: 700; }
QWidget#dashboardPage QFrame#welcomePanel { background: #4F50D9; border-radius: 16px; }
QWidget#dashboardPage QFrame#welcomePanel QLabel { color: #FFFFFF; }
QWidget#dashboardPage QLabel#welcomeTitle { font-size: 25px; font-weight: 700; }
QWidget#dashboardPage QLabel#heroTotal { font-size: 44px; font-weight: 700; }
QWidget#dashboardPage QFrame#welcomePanel QPushButton {
    background: #FFFFFF; color: #3334A8; border: 2px solid #FFFFFF;
}
QWidget#dashboardPage QFrame#welcomePanel QPushButton:hover { background: #EEEDFC; }
QWidget#dashboardPage QFrame#welcomePanel QPushButton:pressed { background: #DEDCF7; }
QWidget#dashboardPage QFrame#welcomePanel QPushButton:focus { border-color: #20243C; }
QWidget#dashboardPage QFrame#metricCard { background: #FFFFFF; border-radius: 12px; }
QWidget#dashboardPage QLabel#metricValue { font-size: 27px; font-weight: 700; }
QWidget#dashboardPage QLabel#metricLabel { font-size: 12px; color: #62677F; }
QWidget#dashboardPage QFrame#tablePanel { background: #FFFFFF; border-radius: 16px; }
QWidget#dashboardPage QTableWidget {
    background: #FFFFFF; alternate-background-color: #F9F9FD; border: none;
    gridline-color: #EEEDF5; selection-background-color: #EEEDFC; selection-color: #3334A8;
}
QWidget#dashboardPage QTableWidget::item { padding: 10px 14px; border: none; }
QWidget#dashboardPage QTableWidget::item:selected { background: #EEEDFC; color: #3334A8; }
QWidget#dashboardPage QTableWidget:focus { border: 2px solid #3334A8; }
QWidget#dashboardPage QHeaderView::section {
    background: #F6F5FC; color: #62677F; border: none;
    padding: 12px 14px; font-size: 12px; font-weight: 600;
}
QWidget#dashboardPage QLabel#initials {
    background: #EEEDFC; color: #3334A8; font-size: 20px;
    font-weight: 700; border-radius: 24px;
}
QWidget#dashboardPage QLabel#identityName { font-size: 16px; font-weight: 700; }
QWidget#dashboardPage QFrame#contextStats { background: #F6F5FC; border-radius: 12px; }
QWidget#dashboardPage QLabel#contextValue { font-size: 22px; font-weight: 700; }
QWidget#dashboardPage QFrame#noticePanel { background: #EEEDFC; border-radius: 12px; }
QWidget#dashboardPage QScrollArea { border: none; background: transparent; }
QWidget#dashboardPage QScrollBar:vertical { background: #F6F5FC; width: 10px; }
QWidget#dashboardPage QScrollBar::handle:vertical {
    background: #747A92; min-height: 28px; border-radius: 5px;
}
QWidget#dashboardPage QScrollBar::add-line:vertical,
QWidget#dashboardPage QScrollBar::sub-line:vertical { height: 0px; }
"""

MENU_STYLE = """
QMenu { background: #FFFFFF; color: #20243C; border: 1px solid #747A92;
    padding: 6px; font-family: "Segoe UI"; font-size: 13px; }
QMenu::item { padding: 13px 18px; min-height: 20px; }
QMenu::item:selected { background: #EEEDFC; color: #3334A8; }
QMenu::separator { height: 1px; background: #DADBE6; margin: 4px; }
"""
