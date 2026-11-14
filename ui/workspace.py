"""Bingkai visual halaman fitur; widget dan koneksi logika tetap milik halaman asal."""

import sqlite3

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QResizeEvent
from PySide6.QtWidgets import (
    QBoxLayout, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit, QMenu, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QTableWidget, QToolButton, QVBoxLayout, QWidget,
)

from auth import session
from database import secure_store
from ui.dashboard_page import NAVIGATION
from ui.dashboard_style import DASHBOARD_STYLE, MENU_STYLE
from ui.workspace_style import FORM_DIALOG_STYLE, WORKSPACE_STYLE


PAGE_INFO = {
    "victims": ("Data Korban", "Cari korban, lihat kondisi, dan kelola pendataan.", "Belum ada korban atau tidak ada hasil yang cocok dengan pencarian.", 1),
    "volunteers": ("Manajemen Relawan", "Kelola akun, status akses, wajah, dan dongle relawan.", "Belum ada relawan. Gunakan Tambah Relawan untuk mendaftarkan akun.", 0),
    "posko": ("Manajemen Posko", "Kelola lokasi posko dan lihat jumlah korban serta relawan terkait.", "Belum ada posko. Gunakan Tambah Posko untuk mulai mendata.", 0),
    "chat": ("Chat Koordinasi", "Pilih percakapan dan buka pesan melalui tombol Decrypt.", "", 0),
    "photos": ("Dokumentasi Foto", "Kelola dokumentasi lapangan dan metadata foto.", "Belum ada foto. Dokumentasi yang diunggah relawan akan tampil di sini.", 3),
    "files": ("Berkas Laporan", "Kelola dokumen laporan yang dikirim dari lapangan.", "Belum ada laporan. Berkas yang diunggah relawan akan tampil di sini.", 1),
    "aid": ("Distribusi Bantuan", "Tinjau riwayat bantuan dan hasil validasi chain.", "Belum ada riwayat distribusi bantuan.", 2),
    "activity": ("Log Aktivitas", "Telusuri aktivitas berdasarkan pengguna dan jenis tindakan.", "Belum ada aktivitas atau tidak ada hasil yang cocok dengan filter.", 3),
    "demo": ("Panel Demo", "Bandingkan ciphertext tersimpan dan hasil dekripsinya.", "", 0),
}


def label(text: str, name: str = "") -> QLabel:
    """Judul dan identitas akun tidak ditafsirkan sebagai markup."""
    result = QLabel(text)
    result.setObjectName(name)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    result.setMinimumWidth(0)
    result.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return result


def _remove_widget(layout: QLayout, widget: QWidget) -> None:
    """Pindahkan kontrol tanpa memutus koneksi sinyal yang sudah terpasang."""
    layout.removeWidget(widget)
    for index in range(layout.count()):
        child = layout.itemAt(index).layout()
        if child is not None:
            _remove_widget(child, widget)


def _layouts(layout: QLayout) -> list[QLayout]:
    """Ambil layout isi halaman untuk penyesuaian ukuran, bukan layout shell."""
    result = [layout]
    for index in range(layout.count()):
        child = layout.itemAt(index).layout()
        if child is not None:
            result.extend(_layouts(child))
        widget = layout.itemAt(index).widget()
        if widget is not None and widget.layout() is not None:
            result.extend(_layouts(widget.layout()))
    return result


def _label_field(page: QWidget, attribute: str, caption: str) -> None:
    """Tambahkan label tetap pada kontrol yang sebelumnya hanya punya placeholder."""
    control = getattr(page, attribute, None)
    if control is None:
        return
    wrapper = QWidget()
    old_item = page.layout().replaceWidget(control, wrapper)
    if old_item is None:
        wrapper.deleteLater()
        return
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    caption_label = label(caption, "fieldCaption")
    caption_label.setBuddy(control)
    control.setAccessibleName(caption)
    layout.addWidget(caption_label)
    layout.addWidget(control)


def _readable_placeholders(owner: QWidget) -> None:
    """Placeholder tetap terbaca di permukaan terang tanpa mengubah isinya."""
    for control in [*owner.findChildren(QLineEdit), *owner.findChildren(QPlainTextEdit)]:
        palette = control.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#62677F"))
        control.setPalette(palette)


def _arrange_sections(owner: QWidget, current: str, layout: QVBoxLayout) -> None:
    """Pisahkan daftar dan area kerja ketika isi halaman membutuhkan dua kolom."""
    if current == "chat":
        for view in (owner.ciphertext_view, owner.plaintext_view):
            view.setMinimumHeight(100)
            view.setMaximumHeight(130)
        return
    if current != "photos" and not (current == "aid" and owner._role == "admin"):
        return
    items = [layout.takeAt(0) for _ in range(layout.count())]
    actions = next(item.layout() for item in items if isinstance(item.layout(), QHBoxLayout))
    actions.setParent(None)
    if current == "aid":
        columns = QHBoxLayout()
        form = QVBoxLayout()
        form.addWidget(label("Catat distribusi", "sectionTitle"))
        form.addWidget(owner.form)
        form.addStretch()
        history = QVBoxLayout()
        history.addWidget(label("Riwayat distribusi", "sectionTitle"))
        history.addWidget(owner.table)
        columns.addLayout(form, 1)
        columns.addLayout(history, 3)
        layout.addLayout(columns, 1)
        layout.addLayout(actions)
        layout.addWidget(owner.status_label)
        return
    for item in items:
        if isinstance(item.layout(), QFormLayout):
            item.layout().setParent(None)
            layout.addLayout(item.layout())
        elif isinstance(item.widget(), QLabel) and item.widget() not in (
            owner.image_view, owner.metadata_view, owner.status_label,
        ):
            item.widget().hide()
    columns = QHBoxLayout()
    gallery = QVBoxLayout()
    gallery.addWidget(label("Daftar dokumentasi", "sectionTitle"))
    gallery.addWidget(owner.table, 1)
    gallery.addLayout(actions)
    gallery.addWidget(owner.status_label)
    preview = QVBoxLayout()
    preview.addWidget(label("Preview foto", "sectionTitle"))
    owner.image_view.setMinimumWidth(0)
    owner.image_view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
    preview.addWidget(owner.image_view, 1)
    preview.addWidget(label("Metadata terverifikasi", "sectionTitle"))
    preview.addWidget(owner.metadata_view)
    columns.addLayout(gallery, 2)
    columns.addLayout(preview, 1)
    layout.addLayout(columns, 1)


class WorkspaceNavigation(QFrame):
    """Sidebar dropdown yang membawa pengguna ke rute aplikasi yang sudah ada."""

    requested = Signal(str)

    def __init__(self, owner: QWidget, current: str, role: str) -> None:
        super().__init__()
        self.setObjectName("workspaceSidebar")
        self.buttons: dict[str, QPushButton] = {}
        self.groups: dict[str, QToolButton] = {}
        self.menu = QMenu(self)
        self.menu.setStyleSheet(MENU_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 28, 16, 20)
        layout.setSpacing(5)
        layout.addWidget(label("SafeRelief", "brand"))
        layout.addWidget(label("Koordinasi tanggap bencana", "muted"))
        layout.addSpacing(24)
        owner.back_button.setText("Dashboard")
        owner.back_button.setProperty("nav", True)
        layout.addWidget(owner.back_button)
        self.menu.addAction("Dashboard", owner.dashboard_requested.emit)
        for group, items in NAVIGATION:
            if role != "admin" and group == "Administrasi":
                continue
            heading = QToolButton()
            heading.setText(group)
            heading.setProperty("groupToggle", True)
            heading.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            heading.setCheckable(True)
            heading.setMinimumHeight(44)
            heading.setCursor(Qt.CursorShape.PointingHandCursor)
            heading.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            heading.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            panel = QWidget()
            children = QVBoxLayout(panel)
            children.setContentsMargins(14, 0, 0, 6)
            children.setSpacing(4)
            submenu = self.menu.addMenu(group)
            for target, title in items:
                button = QPushButton(title)
                button.setMinimumHeight(44)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setProperty("nav", True)
                button.setCheckable(True)
                button.setChecked(target == current)
                button.clicked.connect(lambda _checked=False, route=target: self.requested.emit(route))
                children.addWidget(button)
                self.buttons[target] = button
                action = submenu.addAction(title, lambda route=target: self.requested.emit(route))
                action.setCheckable(True)
                action.setChecked(target == current)
            self.groups[group] = heading
            heading.toggled.connect(lambda opened, h=heading, p=panel: self._toggle(h, p, opened))
            layout.addSpacing(8)
            layout.addWidget(heading)
            layout.addWidget(panel)
            heading.setChecked(any(target == current for target, _title in items))
            self._toggle(heading, panel, heading.isChecked())
        layout.addStretch()
        owner.logout_button.setProperty("nav", True)
        layout.addWidget(owner.logout_button)
        self.menu.addSeparator()
        self.menu.addAction("Logout", owner._confirm_logout)

    @staticmethod
    def _toggle(heading: QToolButton, panel: QWidget, opened: bool) -> None:
        """Status native tombol dan panah mencerminkan isi yang terlihat."""
        heading.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)
        heading.setAccessibleDescription("Kelompok terbuka" if opened else "Kelompok tertutup")
        panel.setVisible(opened)


class FeatureWorkspace(QWidget):
    """Susun sidebar dan konten tanpa mengganti objek halaman pada QStackedWidget."""

    page_requested = Signal(str)

    def __init__(self, owner: QWidget, current: str) -> None:
        super().__init__(owner)
        self.owner = owner
        self.current = current
        self._column_fit_pending = False
        self.user = session.get_current_user()
        self.title, subtitle, empty_text, stretch_column = PAGE_INFO[current]
        old_layout = owner.layout()
        first = old_layout.itemAt(0)
        if first is not None and isinstance(first.widget(), QLabel):
            old_title = first.widget()
            old_layout.removeWidget(old_title)
            old_title.hide()
        for button in (owner.back_button, owner.logout_button):
            _remove_widget(old_layout, button)
        owner.setObjectName("dashboardPage")
        owner.setStyleSheet(DASHBOARD_STYLE + WORKSPACE_STYLE)
        for child in owner.findChildren(QWidget):
            child.setStyleSheet("")
        for button in owner.findChildren(QPushButton):
            button.setMinimumHeight(44)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        for plain in owner.findChildren(QPlainTextEdit):
            plain.setMinimumHeight(min(130, plain.maximumHeight()))
        for name in ("raw_view", "ciphertext_view"):
            if hasattr(owner, name):
                getattr(owner, name).setProperty("encrypted", True)
        if hasattr(owner, "image_view"):
            owner.image_view.setObjectName("photoPreview")
        for attribute, caption in {
            "search_input": "Cari korban", "status_filter": "Status korban",
            "manual_key_input": "Kunci Vigenère manual (opsional)",
            "message_input": "Pesan koordinasi", "record_type": "Jenis data",
            "record_input": "Catatan yang dibandingkan",
        }.items():
            _label_field(owner, attribute, caption)
        _arrange_sections(owner, current, old_layout)
        self.rows = [row for row in _layouts(old_layout) if isinstance(row, QHBoxLayout)]
        self.forms = [row for row in _layouts(old_layout) if isinstance(row, QFormLayout)]
        self.card = QFrame()
        self.card.setObjectName("workspaceCard")
        self.card.setLayout(old_layout)
        old_layout.setContentsMargins(24, 24, 24, 24)
        old_layout.setSpacing(16)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.navigation = WorkspaceNavigation(owner, current, str(self.user["role"]))
        self.navigation.requested.connect(self._navigate)
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFixedWidth(218)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setWidget(self.navigation)
        outer.addWidget(self.sidebar_scroll)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll, 1)
        self.work = QWidget()
        self.work_layout = QVBoxLayout(self.work)
        self.work_layout.setContentsMargins(28, 26, 28, 26)
        self.work_layout.setSpacing(24)
        self.scroll.setWidget(self.work)
        self.menu_button = QToolButton()
        self.menu_button.setText("Menu")
        self.menu_button.setMinimumSize(70, 44)
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.setMenu(self.navigation.menu)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.navigation.menu.aboutToHide.connect(self._restore_focus)
        header = QHBoxLayout()
        header.addWidget(self.menu_button)
        titles = QVBoxLayout()
        titles.addWidget(label("Ruang koordinasi", "muted"))
        titles.addWidget(label(self.title, "workspaceTitle"))
        titles.addWidget(label(subtitle, "workspaceSubtitle"))
        header.addLayout(titles, 1)
        self.identity = label(str(self.user.get("nama_lengkap") or self.user["username"]), "muted")
        self.identity.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.identity.setFixedWidth(180)
        self.identity.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        header.addWidget(self.identity)
        self.work_layout.addLayout(header)
        self.work_layout.addWidget(self.card, 1)
        self.count_label = label("", "muted")
        self.empty_label = label(empty_text, "emptyMessage")
        self.table = getattr(owner, "table", None)
        if self.table is not None:
            self.table.setMinimumHeight(260)
            self.table.setAlternatingRowColors(True)
            self.table.setShowGrid(False)
            self.table.verticalHeader().hide()
            self.table.verticalHeader().setDefaultSectionSize(52)
            self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setMinimumSectionSize(84)
            self.table.horizontalHeader().setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)
            old_layout.insertWidget(0, self.count_label)
            old_layout.insertWidget(1, self.empty_label)
            self.table.model().rowsInserted.connect(self._update_count)
            self.table.model().rowsRemoved.connect(self._update_count)
            self.table.model().modelReset.connect(self._update_count)
            self._update_count()
            # Ukuran tombol per baris dihitung ulang setelah stylesheet terpasang.
            self.table.resizeColumnsToContents()
            self.table.model().rowsInserted.connect(self._schedule_column_fit)
            self._schedule_column_fit()
        primary = getattr(owner, "add_button", None)
        if primary is not None:
            if current == "victims":
                primary.setText("Tambah Korban")
            primary.setProperty("primary", True)
            _remove_widget(old_layout, primary)
            header.addWidget(primary)
        for attribute in ("send_button", "record_button", "upload_button", "decrypt_button"):
            button = getattr(owner, attribute, None)
            if button is not None:
                button.setProperty("primary", True)
        owner.setStyleSheet(DASHBOARD_STYLE + WORKSPACE_STYLE)
        _readable_placeholders(owner)
        self._adapt()

    def clear_sensitive_state(self) -> None:
        """Kosongkan identitas bingkai ketika halaman sesi dibuang."""
        self.navigation.menu.close()
        self.identity.clear()
        self.user.clear()

    def _update_count(self, *_args: object) -> None:
        """Hitungan mengikuti model tabel, termasuk setelah pencarian atau filter."""
        count = self.table.rowCount()
        self.count_label.setText(f"{count} catatan ditampilkan")
        self.empty_label.setVisible(count == 0)

    def _schedule_column_fit(self, *_args: object) -> None:
        """Gabungkan banyak penambahan baris menjadi satu perhitungan ukuran."""
        if not self._column_fit_pending:
            self._column_fit_pending = True
            QTimer.singleShot(0, self._fit_action_columns)

    def _fit_action_columns(self) -> None:
        """Padding sel tidak boleh memotong tombol Decrypt atau Unduh."""
        self._column_fit_pending = False
        for column in range(self.table.columnCount()):
            controls = [self.table.cellWidget(row, column) for row in range(self.table.rowCount())]
            controls = [control for control in controls if control is not None]
            if controls:
                width = max(max(control.minimumWidth(), control.sizeHint().width()) for control in controls) + 28
                self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(column, width)

    def _navigate(self, target: str) -> None:
        """Periksa izin sesi sebelum meminta navigasi ke halaman lain."""
        try:
            user = session.get_current_user()
            if user["id"] != self.user["id"]:
                raise PermissionError("Sesi pengguna telah berubah.")
            secure_store.require_active_user(self.owner._conn, int(user["id"]), str(user["role"]))
        except (PermissionError, RuntimeError, sqlite3.Error) as exc:
            QMessageBox.warning(self.owner, "Akses ditolak", str(exc))
            return
        for name, button in self.navigation.buttons.items():
            button.setChecked(name == self.current)
        self.page_requested.emit(target)

    def _restore_focus(self) -> None:
        if self.menu_button.isVisible():
            self.menu_button.setFocus()

    def _adapt(self) -> None:
        narrow = self.width() < 720
        self.sidebar_scroll.setVisible(not narrow)
        self.menu_button.setVisible(narrow)
        self.identity.setVisible(not narrow)
        margin = 16 if narrow else 28
        self.work_layout.setContentsMargins(margin, 24, margin, 24)
        stacked = self.width() < 900
        for row in self.rows:
            row.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
        for form in self.forms:
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows if stacked else QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._adapt()


def install_workspace(page: QWidget, current: str) -> FeatureWorkspace:
    """Pasang sekali agar refresh tidak membuat ulang widget atau koneksi sinyal."""
    existing = getattr(page, "workspace", None)
    if existing is not None:
        return existing
    workspace = FeatureWorkspace(page, current)
    page.setMinimumSize(0, 0)
    root = QVBoxLayout(page)
    root.setContentsMargins(0, 0, 0, 0)
    root.addWidget(workspace)
    page.workspace = workspace
    return workspace


def style_dialog(dialog: QDialog) -> None:
    """Selaraskan tampilan field tanpa mengubah nilai atau validasinya."""
    # Nama berbeda mencegah dialog cocok dengan selector transparan milik dashboard.
    dialog.setObjectName("formDialog")
    dialog.setStyleSheet(FORM_DIALOG_STYLE)
    palette = dialog.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#20243C"))
    dialog.setPalette(palette)
    dialog.setAutoFillBackground(True)
    dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    _readable_placeholders(dialog)
    for button in dialog.findChildren(QPushButton):
        button.setMinimumHeight(44)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
    for buttons in dialog.findChildren(QDialogButtonBox):
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save is not None:
            save.setText("Simpan")
            save.setProperty("primary", True)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel is not None:
            cancel.setText("Batal")
    layout = dialog.layout()
    field_count = 0
    if layout is not None:
        button_boxes = dialog.findChildren(QDialogButtonBox)
        for buttons in button_boxes:
            _remove_widget(layout, buttons)
        for form in _layouts(layout):
            if isinstance(form, QFormLayout):
                field_count += form.rowCount()
                form.setSpacing(12)
                form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        body = QWidget()
        body.setLayout(layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        root = QVBoxLayout(dialog)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        heading = QVBoxLayout()
        heading.setSpacing(6)
        heading.addWidget(label(dialog.windowTitle(), "workspaceTitle"))
        description = {
            "Tambah Korban": "Isi data korban dan pilih posko penempatan.",
            "Edit Data Korban": "Perbarui data korban yang dipilih.",
            "Tambah Posko": "Tentukan nama, lokasi, dan kapasitas posko.",
            "Edit Posko": "Perbarui informasi posko yang dipilih.",
            "Tambah Relawan": "Isi profil dan kredensial awal sebelum pendaftaran wajah.",
            "Edit Relawan": "Perbarui profil atau reset password relawan.",
            "Ganti Dongle Relawan": "Pilih dongle baru dan konfirmasikan password relawan.",
        }.get(dialog.windowTitle())
        if description:
            heading.addWidget(label(description, "dialogSubtitle"))
        root.addLayout(heading)
        root.addWidget(scroll, 1)
        for buttons in button_boxes:
            root.addWidget(buttons)
    screen = dialog.screen()
    available_height = min(760, screen.availableGeometry().height() - 80) if screen else 680
    desired_height = max(360, 180 + field_count * 56) if field_count else 640
    height = min(available_height, desired_height)
    dialog.resize(960 if dialog.findChildren(QTableWidget) else 640, height)
    dialog.setStyleSheet(FORM_DIALOG_STYLE)
    _readable_placeholders(dialog)
