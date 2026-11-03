from __future__ import annotations

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QLabel, QComboBox, QPushButton, QVBoxLayout, QWidget, QScrollArea

from app.hardware.backend import detect_hardware
from app.tts.benchmark import benchmark_provider
from app.tts.providers.piper import PiperProvider


class _BenchmarkThread(QThread):
    finished_result = Signal(str)

    def __init__(self, backend: str, voice: str):
        super().__init__()
        self.backend = backend
        self.voice = voice

    def run(self):
        result = benchmark_provider(
            PiperProvider(backend=self.backend),
            voice=self.voice,
            backend=self.backend,
        )
        if result.success:
            verdict = "faster than realtime" if result.realtime_factor < 1.0 else "slower than realtime"
            self.finished_result.emit(
                f"{result.backend}: {result.seconds:.2f}s for {result.audio_seconds:.2f}s audio • "
                f"RTF {result.realtime_factor:.2f} • {verdict}"
            )
        else:
            self.finished_result.emit(f"{result.backend}: verifier failed • {result.error}")




class HardwarePage(QWidget):
    def __init__(self):
        super().__init__()
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 6, 4, 12)
        layout.setSpacing(14)
        self.profile = None

        layout.addWidget(QLabel("<h2>Hardware & TTS Performance</h2>"))
        self.info = QLabel()
        layout.addWidget(self.info)

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Automatic", "automatic")
        layout.addWidget(self.backend_combo)

        self.benchmark_button = QPushButton("Verify Local Backend (background)")
        self.benchmark_button.clicked.connect(self.run_benchmark)
        self.benchmark_thread = None
        layout.addWidget(self.benchmark_button)

        self.result = QLabel("No benchmark run yet.")
        layout.addWidget(self.result)
        self.info.setText("Hardware details are detected when this screen opens.")

        scroll = QScrollArea(self)
        scroll.setObjectName("hardwareScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def refresh(self):
        # Hardware probing may invoke external tools. Do it only after the user
        # opens this screen and the native shell has had a chance to paint.
        if self.profile is None:
            selected_backend = self.backend_combo.currentData() or "automatic"
            try:
                profile = detect_hardware()
            except Exception as exc:
                self.info.setText(
                    "Hardware detection is unavailable right now. "
                    "Check Logs/application.log for details."
                )
                self.result.setText(f"Hardware detection failed: {type(exc).__name__}: {exc}")
                return

            self.profile = profile
            blocked = self.backend_combo.blockSignals(True)
            try:
                self.backend_combo.clear()
                self.backend_combo.addItem("Automatic", "automatic")
                for backend in profile.backends:
                    if backend.available:
                        self.backend_combo.addItem(backend.name, backend.name)
                restore_index = self.backend_combo.findData(selected_backend)
                if restore_index >= 0:
                    self.backend_combo.setCurrentIndex(restore_index)
            finally:
                self.backend_combo.blockSignals(blocked)

        profile = self.profile
        if profile is None:
            return
        lines = [
            f"CPU: {profile.cpu}",
            f"Architecture: {profile.architecture}",
            f"Recommended backend: {profile.recommended}",
            "",
        ]
        for backend in profile.backends:
            state = "Available" if backend.available else "Unavailable"
            lines.append(
                f"{backend.name}: {state}" + (f" — {backend.device}" if backend.device else "")
            )
        recommendations = ["Provider recommendations from detected hardware:"]
        recommendations.extend(
            f"{name}: {backend}"
            for name, backend in profile.provider_recommendations.items()
        )
        self.info.setText("\n".join(lines + [""] + recommendations))

    def run_benchmark(self):
        voices = PiperProvider.model_paths()
        if not voices:
            self.result.setText("Install a Piper voice first from the Models page.")
            return
        backend = self.backend_combo.currentData() or "automatic"
        provider_backend = (
            "cuda" if backend == "NVIDIA CUDA"
            else "automatic" if backend == "automatic"
            else "cpu"
        )
        self.benchmark_button.setEnabled(False)
        self.result.setText("Verifying selected backend in the background…")
        self.benchmark_thread = _BenchmarkThread(provider_backend, voices[0].stem)
        self.benchmark_thread.finished_result.connect(self._benchmark_finished)
        self.benchmark_thread.finished.connect(lambda: self.benchmark_button.setEnabled(True))
        self.benchmark_thread.start()

    def _benchmark_finished(self, message: str):
        self.result.setText(message)
