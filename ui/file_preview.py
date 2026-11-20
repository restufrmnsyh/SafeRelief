"""Pratinjau berkas terautentikasi di memori sesi admin."""

from PySide6.QtCore import QBuffer, QIODevice, Qt, QUrl
from PySide6.QtGui import QImage, QPainter, QPixmap, QResizeEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QDialog, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from ui.office_preview import office_text


def prepare_preview(data: bytes) -> QImage | str | bytes:
    """Kenali isi setelah dekripsi, sebab nama unduhan .enc bisa diganti."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        image = QImage.fromData(data, "PNG")
        if image.isNull():
            raise ValueError("Foto PNG tidak dapat dibaca.")
        return image
    if data.startswith(b"PK\x03\x04"):
        return office_text(data)
    if (data.startswith((b"%PDF-", b"\x1a\x45\xdf\xa3"))
            or data[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free")
            or (data.startswith(b"RIFF") and data[8:12] == b"AVI ")):
        return data
    raise ValueError("Format isi berkas tidak dikenali untuk pratinjau.")


class PhotoView(QGraphicsView):
    """Sesuaikan foto dengan ruang yang tersedia sambil menjaga proporsinya."""

    def __init__(self, image: QImage) -> None:
        super().__init__()
        scene = QGraphicsScene(self)
        scene.addPixmap(QPixmap.fromImage(image))
        self.setScene(scene)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class FilePreviewDialog(QDialog):
    """Qt membaca PDF dan video melalui QBuffer selama dialog terbuka."""

    def __init__(self, name: str, content: QImage | str | bytes, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Pratinjau · {name}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(800, 560)
        self.player: QMediaPlayer | None = None
        self.document: QPdfDocument | None = None
        self.buffer = QBuffer(self)
        layout = QVBoxLayout(self)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.hide()
        if isinstance(content, QImage):
            layout.addWidget(PhotoView(content), 1)
        elif isinstance(content, str):
            layout.addWidget(QLabel("Pratinjau teks dokumen"))
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.setPlainText(content)
            layout.addWidget(view, 1)
        else:
            self.buffer.setData(content)
            self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            if content.startswith(b"%PDF-"):
                self._show_pdf(layout)
            else:
                self._show_video(layout)
        layout.addWidget(self.message)
        close = QPushButton("Tutup")
        close.clicked.connect(self.reject)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

    def _show_error(self, message: str) -> None:
        self.message.setText(message)
        self.message.show()

    def _show_pdf(self, layout: QVBoxLayout) -> None:
        document = QPdfDocument(self)
        self.document = document
        view = QPdfView()
        view.setDocument(document)
        view.setPageMode(QPdfView.PageMode.MultiPage)
        view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        layout.addWidget(view, 1)
        document.statusChanged.connect(
            lambda status: self._show_error("PDF tidak dapat ditampilkan.")
            if status == QPdfDocument.Status.Error else None
        )
        document.passwordRequired.connect(lambda: self._show_error("PDF ini dilindungi kata sandi."))
        document.load(self.buffer)

    def _show_video(self, layout: QVBoxLayout) -> None:
        player = QMediaPlayer(self)
        self.player = player
        audio = QAudioOutput(self)
        player.setAudioOutput(audio)
        video = QVideoWidget()
        layout.addWidget(video, 1)
        player.setVideoOutput(video)
        play = QPushButton("Putar")
        seek = QSlider(Qt.Orientation.Horizontal)
        seek.setAccessibleName("Posisi video")
        seek.setRange(0, 0)
        controls = QHBoxLayout()
        controls.addWidget(play)
        controls.addWidget(seek, 1)
        layout.addLayout(controls)
        playing = QMediaPlayer.PlaybackState.PlayingState
        play.clicked.connect(lambda: player.pause() if player.playbackState() == playing else player.play())
        player.playbackStateChanged.connect(lambda state: play.setText("Jeda" if state == playing else "Putar"))
        player.durationChanged.connect(seek.setMaximum)
        player.positionChanged.connect(seek.setValue)
        seek.sliderMoved.connect(player.setPosition)
        player.errorOccurred.connect(lambda *_: self._show_error("Video tidak dapat diputar. Periksa format atau codec video."))
        player.setSourceDevice(self.buffer)

    def done(self, result: int) -> None:
        if self.player is not None:
            self.player.stop()
            self.player.setSource(QUrl())
        if self.document is not None:
            self.document.close()
        super().done(result)
