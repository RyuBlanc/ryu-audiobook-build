from __future__ import annotations

from PySide6.QtWidgets import QLabel, QComboBox, QPushButton, QVBoxLayout, QWidget

from app.hardware.backend import detect_hardware
from app.tts.benchmark import benchmark_provider
from app.tts.providers.piper import PiperProvider


class HardwarePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.profile = detect_hardware()

        layout.addWidget(QLabel("<h2>Hardware & TTS Performance</h2>"))
        self.info = QLabel()
        layout.addWidget(self.info)

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Automatic", "automatic")
        for backend in self.profile.backends:
            if backend.available:
                self.backend_combo.addItem(backend.name, backend.name)
        layout.addWidget(self.backend_combo)

        self.benchmark_button = QPushButton("Benchmark Installed Piper Voice")
        self.benchmark_button.clicked.connect(self.run_benchmark)
        layout.addWidget(self.benchmark_button)

        self.result = QLabel("No benchmark run yet.")
        layout.addWidget(self.result)

        self.refresh()

    def refresh(self):
        lines = [
            f"CPU: {self.profile.cpu}",
            f"Architecture: {self.profile.architecture}",
            f"Recommended backend: {self.profile.recommended}",
            "",
        ]
        for b in self.profile.backends:
            state = "Available" if b.available else "Unavailable"
            lines.append(f"{b.name}: {state}" + (f" — {b.device}" if b.device else ""))
        self.info.setText("\n".join(lines))

    def run_benchmark(self):
        voices = PiperProvider.model_paths()
        if not voices:
            self.result.setText("Install a Piper voice first from the Models page.")
            return
        backend = self.backend_combo.currentData() or "automatic"
        provider_backend = "cuda" if backend == "NVIDIA CUDA" else "cpu"
        result = benchmark_provider(
            PiperProvider(voices[0], backend=provider_backend),
            backend=provider_backend,
        )
        if result.success:
            self.result.setText(
                f"Benchmark: {result.seconds:.2f}s for {result.audio_seconds:.2f}s audio "
                f"(RTF {result.realtime_factor:.2f}). Lower RTF is faster."
            )
        else:
            self.result.setText(f"Benchmark failed: {result.error}")
