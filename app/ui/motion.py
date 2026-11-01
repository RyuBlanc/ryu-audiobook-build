from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, QSettings, QTimer, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QProgressBar, QWidget


def reduced_motion_enabled() -> bool:
    return bool(QSettings("RyuBlanc", "Ryu's Audiobook").value("ui/reduce_motion", False, type=bool))


class SmoothProgressBar(QProgressBar):
    """A progress bar that eases between true progress updates without faking ETA.

    Determinate progress uses a short value animation. Indeterminate bars get a
    low-frame-rate moving highlight. Timers stop whenever a bar is hidden or
    reduced-motion mode is enabled.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._reduce_motion = reduced_motion_enabled()
        self._busy = False
        self._phase = 0
        self._value_animation: QPropertyAnimation | None = None
        self._busy_timer = QTimer(self)
        self._busy_timer.setTimerType(Qt.TimerType.CoarseTimer)
        self._busy_timer.setInterval(65)  # ~15 FPS; intentionally lower-cost than 60 FPS.
        self._busy_timer.timeout.connect(self._advance_phase)

    def _get_animated_value(self) -> int:
        return QProgressBar.value(self)

    def _set_animated_value(self, value: int) -> None:
        QProgressBar.setValue(self, int(value))

    animatedValue = Property(int, _get_animated_value, _set_animated_value)

    def setValue(self, value: int) -> None:  # noqa: N802 - Qt API
        target = int(value)
        if self._reduce_motion or not self.isVisible() or self._busy:
            if self._value_animation and self._value_animation.state() == QPropertyAnimation.State.Running:
                self._value_animation.stop()
            QProgressBar.setValue(self, target)
            return
        current = QProgressBar.value(self)
        if current == target:
            return
        if self._value_animation and self._value_animation.state() == QPropertyAnimation.State.Running:
            current = self._get_animated_value()
            self._value_animation.stop()
        animation = QPropertyAnimation(self, b"animatedValue", self)
        animation.setDuration(180)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(current)
        animation.setEndValue(target)
        self._value_animation = animation
        animation.start()

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802 - Qt API
        QProgressBar.setRange(self, minimum, maximum)
        self._busy = int(minimum) == 0 and int(maximum) == 0
        self._sync_busy_timer()

    def setMinimum(self, minimum: int) -> None:  # noqa: N802 - Qt API
        QProgressBar.setMinimum(self, minimum)
        self._busy = self.minimum() == 0 and self.maximum() == 0
        self._sync_busy_timer()

    def setMaximum(self, maximum: int) -> None:  # noqa: N802 - Qt API
        QProgressBar.setMaximum(self, maximum)
        self._busy = self.minimum() == 0 and self.maximum() == 0
        self._sync_busy_timer()

    def _advance_phase(self) -> None:
        self._phase = (self._phase + 7) % max(1, self.width() + 70)
        self.update()

    def _sync_busy_timer(self) -> None:
        if self._busy and not self._reduce_motion and self.isVisible():
            if not self._busy_timer.isActive():
                self._busy_timer.start()
        elif self._busy_timer.isActive():
            self._busy_timer.stop()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt event name
        super().showEvent(event)
        self._sync_busy_timer()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt event name
        self._busy_timer.stop()
        super().hideEvent(event)

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduce_motion = bool(enabled)
        self._sync_busy_timer()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt event name
        super().paintEvent(event)
        if not self._busy or self._reduce_motion:
            return
        painter = QPainter(self)
        painter.setClipRect(self.rect())
        width = max(36, self.width() // 11)
        x = self._phase - width
        gradient = QLinearGradient(x, 0, x + width, 0)
        gradient.setColorAt(0.0, QColor(255, 93, 76, 0))
        gradient.setColorAt(0.5, QColor(255, 117, 79, 80))
        gradient.setColorAt(1.0, QColor(255, 93, 76, 0))
        painter.fillRect(self.rect().adjusted(1, 1, -1, -1), gradient)
        painter.end()
