from __future__ import annotations

import math

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QWidget


class FrostedLoadingOverlay(QWidget):
    """Cached blurred-frosted overlay for short, real background tasks.

    A single low-resolution snapshot is captured when shown and reused. The
    blur is created by shrinking then smoothly enlarging the snapshot, so no
    live blur effect or per-frame screenshot is computed while the worker runs.
    The parent remains responsive because expensive work belongs on a worker.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._host = parent
        self._blurred = QPixmap()
        self._title = "Preparing your audiobook"
        self._detail = "Please wait while the local studio prepares the next step…"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.setInterval(55)  # ~18 FPS for the small spinner only.
        self._timer.timeout.connect(self._advance)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

    @property
    def animation_timer_active(self) -> bool:
        return self._timer.isActive()

    def show_loading(self, title: str, detail: str) -> None:
        self._title = str(title or "Preparing your audiobook")
        self._detail = str(detail or "Please wait…")
        self.setGeometry(self._host.rect())
        self._capture_frosted_snapshot()
        self.raise_()
        self.show()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def set_detail(self, detail: str) -> None:
        self._detail = str(detail or "Please wait…")
        if self.isVisible():
            self.update()

    def dismiss(self) -> None:
        self._timer.stop()
        self.hide()
        self._blurred = QPixmap()

    def _capture_frosted_snapshot(self) -> None:
        size = self._host.size()
        if size.width() <= 0 or size.height() <= 0:
            self._blurred = QPixmap()
            return
        try:
            snapshot = self._host.grab()
            # Downscale strongly, then smooth-scale back. This is a cached
            # frosted-glass approximation and keeps the cost to show-time only.
            low_size = size / 14
            low = snapshot.scaled(
                max(1, int(low_size.width())),
                max(1, int(low_size.height())),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._blurred = low.scaled(
                size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception:
            self._blurred = QPixmap()

    def _advance(self) -> None:
        if not self.isVisible():
            self._timer.stop()
            return
        self._phase = (self._phase + 0.24) % (2.0 * math.pi)
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt event name
        super().resizeEvent(event)
        if self.isVisible():
            self.setGeometry(self._host.rect())
            self._capture_frosted_snapshot()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt event name
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt event name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bounds = self.rect()

        if not self._blurred.isNull():
            painter.drawPixmap(bounds, self._blurred)
        else:
            painter.fillRect(bounds, QColor("#08090d"))

        # Obsidian tint and a restrained ember/arcane-violet edge treatment.
        painter.fillRect(bounds, QColor(6, 7, 12, 176))
        wash = QLinearGradient(0, 0, bounds.width(), bounds.height())
        wash.setColorAt(0.0, QColor(130, 19, 45, 28))
        wash.setColorAt(0.52, QColor(16, 13, 25, 20))
        wash.setColorAt(1.0, QColor(90, 43, 132, 30))
        painter.fillRect(bounds, wash)

        card_width = min(520, max(300, bounds.width() - 40))
        card_height = 208
        card = QPainterPath()
        card_rect = Qt.QRectF(
            (bounds.width() - card_width) / 2,
            (bounds.height() - card_height) / 2,
            card_width,
            card_height,
        )
        card.addRoundedRect(card_rect, 18.0, 18.0)
        card_fill = QLinearGradient(card_rect.topLeft(), card_rect.bottomRight())
        card_fill.setColorAt(0.0, QColor("#17151d"))
        card_fill.setColorAt(1.0, QColor("#0d1017"))
        painter.fillPath(card, card_fill)
        painter.setPen(QPen(QColor(204, 43, 77, 180), 1.15))
        painter.drawPath(card)

        # A subtle angular "wing/scale" emblem—geometric, not character art.
        cx = bounds.width() / 2
        cy = card_rect.top() + 34
        emblem = QPainterPath()
        emblem.moveTo(cx - 36, cy - 1)
        emblem.lineTo(cx - 10, cy - 12)
        emblem.lineTo(cx - 16, cy + 3)
        emblem.lineTo(cx - 2, cy + 12)
        emblem.lineTo(cx, cy - 7)
        emblem.lineTo(cx + 2, cy + 12)
        emblem.lineTo(cx + 16, cy + 3)
        emblem.lineTo(cx + 10, cy - 12)
        emblem.lineTo(cx + 36, cy - 1)
        painter.setPen(QPen(QColor("#e54b66"), 1.35))
        painter.drawPath(emblem)

        # 12 small marks orbit the centre point; the timer only changes angle.
        painter.save()
        painter.translate(cx, cy + 4)
        painter.rotate(math.degrees(self._phase))
        painter.setPen(QPen(QColor(255, 114, 83, 190), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for index in range(12):
            painter.rotate(30)
            painter.drawLine(0, -31, 0, -36 if index % 3 == 0 else -34)
        painter.restore()

        font = QFont(self.font())
        font.setPointSize(11)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.Absolute, 1.0)
        painter.setFont(font)
        painter.setPen(QColor("#f5edf3"))
        painter.drawText(
            card_rect.adjusted(18, 81, -18, -74),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            self._title.upper(),
        )

        detail_font = QFont(self.font())
        detail_font.setPointSize(9)
        painter.setFont(detail_font)
        painter.setPen(QColor("#aaa3b1"))
        painter.drawText(
            card_rect.adjusted(25, 117, -25, -43),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap),
            self._detail,
        )

        # A tiny three-stage line animates at the bottom; no progress % is
        # invented for steps whose completion is not actually measurable.
        line_width = min(card_width - 82, 260)
        left = (bounds.width() - line_width) / 2
        top = card_rect.bottom() - 27
        painter.setPen(QPen(QColor("#302a37"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(int(left), int(top), int(left + line_width), int(top))
        glow_start = left + ((self._phase / (2.0 * math.pi)) * (line_width + 48)) - 48
        glow = QLinearGradient(glow_start, 0, glow_start + 48, 0)
        glow.setColorAt(0.0, QColor(230, 65, 96, 0))
        glow.setColorAt(0.5, QColor("#e64160"))
        glow.setColorAt(1.0, QColor(230, 65, 96, 0))
        painter.setPen(QPen(glow, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(int(left), int(top), int(left + line_width), int(top))
        painter.end()
