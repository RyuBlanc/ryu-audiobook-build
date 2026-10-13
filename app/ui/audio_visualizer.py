from __future__ import annotations

import math

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class AudioVisualizer(QWidget):
    """Low-cost crimson waveform animation for audiobook playback.

    The 2D painter uses no images, shaders, OpenGL, audio capture, or background
    thread. Its timer only runs while playback is active, the widget is visible,
    and reduced-motion mode is off. It is a visual companion, not an FFT meter.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._playing = False
        self._reduced_motion = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._timer.setInterval(40)  # 25 fps is smooth without a continuous 60 fps repaint.
        self._timer.timeout.connect(self._advance)
        self.setMinimumHeight(70)
        self.setMaximumHeight(92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Audiobook playback visualizer")
        self.setAccessibleDescription(
            "A lightweight animated visual companion. Animation runs only during playback."
        )

    @property
    def animation_timer_active(self) -> bool:
        """Expose timer state for lightweight regression tests."""
        return self._timer.isActive()

    def set_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        self._sync_timer()
        self.update()

    def set_reduced_motion(self, reduced: bool) -> None:
        self._reduced_motion = bool(reduced)
        self._sync_timer()
        self.update()

    def _sync_timer(self) -> None:
        should_animate = self._playing and not self._reduced_motion and self.isVisible()
        if should_animate:
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()

    def _advance(self) -> None:
        # Advance by a fixed phase per frame. No audio is decoded or analyzed here.
        self._phase = (self._phase + 0.17) % (2.0 * math.pi)
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt event name
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt event name
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt event name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bounds = self.rect().adjusted(1, 1, -1, -1)
        if bounds.width() < 4 or bounds.height() < 4:
            return

        panel = QPainterPath()
        panel.addRoundedRect(bounds, 10.0, 10.0)
        painter.fillPath(panel, QColor("#101014"))
        painter.setPen(QPen(QColor("#29232d"), 1.0))
        painter.drawPath(panel)

        # Small editorial label plus a state dot, matching the studio's dark,
        # velvet-crimson visual language.
        painter.setPen(QColor("#a5a0ad"))
        font = painter.font()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            bounds.adjusted(12, 5, -12, -5),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            "AUDIO VISUALIZER  •  LOW-POWER MOTION",
        )

        dot = QColor("#e64970" if self._playing else "#5e5661")
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(dot)
        painter.drawEllipse(bounds.right() - 17, bounds.top() + 10, 5, 5)

        available_width = max(1, bounds.width() - 26)
        count = max(18, min(42, available_width // 13))
        gap = 4.0 if available_width / count > 8.0 else 2.0
        bar_width = max(2.0, (available_width - gap * (count - 1)) / count)
        total_width = count * bar_width + (count - 1) * gap
        start_x = bounds.left() + (bounds.width() - total_width) / 2.0
        baseline = bounds.bottom() - 9
        max_height = max(12.0, bounds.height() * 0.49)

        gradient = QLinearGradient(start_x, 0, start_x + total_width, 0)
        gradient.setColorAt(0.0, QColor("#7e1731"))
        gradient.setColorAt(0.48, QColor("#d52b55"))
        gradient.setColorAt(0.78, QColor("#a72a67"))
        gradient.setColorAt(1.0, QColor("#6b285d"))
        bar_brush = QBrush(gradient)

        for index in range(count):
            position = index / max(1, count - 1)
            # A low, symmetric resting shape when idle/reduced; a gently
            # travelling envelope during playback. The fixed math is cheap.
            shape = 0.18 + 0.82 * abs(math.sin(position * math.pi))
            if self._playing and not self._reduced_motion:
                wave_a = (math.sin(index * 0.53 + self._phase) + 1.0) * 0.5
                wave_b = (math.sin(index * 0.21 - self._phase * 0.63) + 1.0) * 0.5
                motion = 0.25 + 0.75 * (0.68 * wave_a + 0.32 * wave_b)
                level = shape * motion
            elif self._playing:
                level = shape * 0.50
            else:
                level = shape * 0.34

            height = max(3.0, max_height * level)
            x = start_x + index * (bar_width + gap)
            bar = QPainterPath()
            bar.addRoundedRect(
                x,
                baseline - height,
                bar_width,
                height,
                min(2.5, bar_width / 2),
                min(2.5, bar_width / 2),
            )
            painter.fillPath(bar, bar_brush)

        painter.end()
