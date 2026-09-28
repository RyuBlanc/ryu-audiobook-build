from __future__ import annotations

from pathlib import Path
import json
import time
import tempfile

from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QVBoxLayout, QWidget, QComboBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

from app.chapters.detector import Chapter, detect_chapters
from app.chapters.characters import analyze_book
from app.tts.pronunciation_suggester import suggest_pronunciation, COMMON_ENGLISH_WORDS
from app.documents.parser import extract_text
from app.core.state import load_state, save_state
from app.tts.manager import GenerationManager, GenerationSummary
from app.tts.profile_provider import provider_from_profile
from app.tts.voice_profile import load_profiles, VoiceProfile
from app.tts.providers.piper import PiperProvider
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.preview import build_voice_preview


class GenerationSignals(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(object)


class GenerationPage(QWidget):
    def __init__(self, chapters: list[Chapter], audio_root: Path, project_folder: Path | None = None) -> None:
        super().__init__()
        self.chapters = chapters
        self.audio_root = audio_root
        self.project_folder = project_folder
        self.profiles = load_profiles()
        self.signals = GenerationSignals()
        self.manager: GenerationManager | None = None
        self.started_at: float | None = None
        self.last_progress_value = 0

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self._player_position)
        self.player.durationChanged.connect(self._player_duration)

        self.preview_player = QMediaPlayer(self)
        self.preview_audio_output = QAudioOutput(self)
        self.preview_audio_output.setVolume(0.85)
        self.preview_player.setAudioOutput(self.preview_audio_output)
        self.preview_player.positionChanged.connect(self._preview_position)
        self.preview_player.durationChanged.connect(self._preview_duration)
        self.preview_player.playbackStateChanged.connect(self._preview_state_changed)
        self.preview_path: Path | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(6, 4, 6, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(QLabel("<h2>Generate Audiobook</h2>"))
        header.addStretch(1)
        header.addWidget(QLabel("Review → Generate → Listen"))
        root.addLayout(header)

        book_name = self.project_folder.name if self.project_folder else "Audiobook"
        self.title = QLineEdit(book_name)
        self.author = QLineEdit()
        form = QFormLayout()
        form.addRow("Book title", self.title)
        form.addRow("Author / narrator", self.author)
        root.addLayout(form)

        overview = QGroupBox("Audiobook")
        overview_layout = QHBoxLayout(overview)
        self.chapter_count = QLabel()
        self.word_count = QLabel()
        self.duration_estimate = QLabel()
        overview_layout.addWidget(self.chapter_count)
        overview_layout.addWidget(self.word_count)
        overview_layout.addWidget(self.duration_estimate)
        overview_layout.addStretch(1)
        root.addWidget(overview)
        self._update_overview()

        cast_box = QGroupBox("Voice Cast")
        cast_layout = QVBoxLayout(cast_box)
        self.cast_summary = QLabel("No character-specific voice assignments saved. Narrator voice will be used.")
        self.cast_summary.setWordWrap(True)
        cast_layout.addWidget(self.cast_summary)
        root.addWidget(cast_box)

        pronunciation_box = QGroupBox("Pronunciation Dictionary")
        pronunciation_layout = QVBoxLayout(pronunciation_box)
        pronunciation_hint = QLabel(
            "Add words or names the voice should pronounce differently. "
            "This changes only narration text; the original book remains untouched."
        )
        pronunciation_hint.setWordWrap(True)
        pronunciation_layout.addWidget(pronunciation_hint)

        self.pronunciation_table = QTableWidget(0, 3)
        self.pronunciation_table.setHorizontalHeaderLabels(["Written", "Pronounce as", "Enabled"])
        pronunciation_layout.addWidget(self.pronunciation_table)

        pronunciation_actions = QHBoxLayout()
        self.add_pronunciation = QPushButton("+ Add Pronunciation")
        self.add_pronunciation.clicked.connect(self._add_pronunciation_row)
        self.suggest_pronunciation = QPushButton("Suggest Character Pronunciations")
        self.suggest_pronunciation.clicked.connect(self._suggest_pronunciations)
        self.remove_pronunciation = QPushButton("Remove Selected")
        self.remove_pronunciation.clicked.connect(self._remove_pronunciation_row)
        self.clean_english_pronunciations = QPushButton("Clean Obvious English")
        self.clean_english_pronunciations.clicked.connect(self._clean_obvious_english_pronunciations)
        self.save_pronunciation = QPushButton("Save Pronunciations")
        self.save_pronunciation.setObjectName("primary")
        self.save_pronunciation.clicked.connect(self._save_pronunciations)
        pronunciation_actions.addWidget(self.add_pronunciation)
        pronunciation_actions.addWidget(self.suggest_pronunciation)
        pronunciation_actions.addWidget(self.remove_pronunciation)
        pronunciation_actions.addWidget(self.clean_english_pronunciations)
        pronunciation_actions.addStretch(1)
        pronunciation_actions.addWidget(self.save_pronunciation)
        pronunciation_layout.addLayout(pronunciation_actions)

        self.pronunciation_status = QLabel("No pronunciation overrides saved for this book.")
        self.pronunciation_status.setWordWrap(True)
        pronunciation_layout.addWidget(self.pronunciation_status)
        root.addWidget(pronunciation_box)

        settings = QGroupBox("Audio settings")
        settings_form = QFormLayout(settings)

        voice_row = QHBoxLayout()
        self.voice_profile = QComboBox()
        self.refresh_voice_profiles = QPushButton("Refresh")
        self.refresh_voice_profiles.clicked.connect(self._refresh_voice_profiles)
        voice_row.addWidget(self.voice_profile, 1)
        voice_row.addWidget(self.refresh_voice_profiles)
        settings_form.addRow("Voice", voice_row)
        self._load_profiles()

        self.backend = QComboBox()
        self.backend.addItem("Automatic", "automatic")
        self.backend.addItem("CPU Only", "cpu")
        self.backend.addItem("NVIDIA CUDA", "cuda")
        self.backend.addItem("DirectML", "directml")
        settings_form.addRow("Backend", self.backend)
        self.narration_speed = QComboBox()
        self.narration_speed.addItem("0.85×  Very relaxed", 0.85)
        self.narration_speed.addItem("0.90×  Natural story", 0.90)
        self.narration_speed.addItem("0.95×  Slightly slower", 0.95)
        self.narration_speed.addItem("1.00×  Original speed", 1.00)
        self.narration_speed.setCurrentIndex(1)
        settings_form.addRow("Narration speed", self.narration_speed)

        self.pacing_profile = QComboBox()
        self.pacing_profile.addItem("Natural Story • balanced pauses", "natural")
        self.pacing_profile.addItem("Relaxed Story • longer pauses", "relaxed")
        self.pacing_profile.addItem("Minimal Pauses • lighter pacing", "minimal")
        self.pacing_profile.addItem("Off • provider timing only", "off")
        self.pacing_profile.setCurrentIndex(0)
        settings_form.addRow("Story pacing", self.pacing_profile)
        self.pacing_hint = QLabel(
            "Adds small, sentence-aware pauses after generated narration units. "
            "The original wording is not changed."
        )
        self.pacing_hint.setWordWrap(True)
        settings_form.addRow("", self.pacing_hint)
        self.cover: Path | None = None
        cover_row = QHBoxLayout()
        self.cover_label = QLabel("No cover selected")
        self.cover_button = QPushButton("Choose Cover")
        self.cover_button.clicked.connect(self.choose_cover)
        cover_row.addWidget(self.cover_button)
        cover_row.addWidget(self.cover_label, 1)
        settings_form.addRow("Cover", cover_row)
        root.addWidget(settings)

        output_box = QGroupBox("Output")
        output_layout = QVBoxLayout(output_box)
        self.output = QLineEdit()
        self.output.setReadOnly(True)
        output_layout.addWidget(self.output)
        output_actions = QHBoxLayout()
        self.change_output = QPushButton("Change output location…")
        self.change_output.clicked.connect(self.choose_output)
        output_actions.addWidget(self.change_output)
        output_actions.addWidget(QLabel("M4B with embedded chapters"))
        output_actions.addStretch(1)
        output_layout.addLayout(output_actions)
        root.addWidget(output_box)

        preview_box = QGroupBox("Voice Preview")
        preview_layout = QVBoxLayout(preview_box)

        preview_source_row = QHBoxLayout()
        preview_source_row.addWidget(QLabel("Source"))
        self.preview_chapter = QComboBox()
        for chapter in self.chapters:
            self.preview_chapter.addItem(
                f"Chapter {chapter.number}: {chapter.title}",
                chapter.number,
            )
        self.preview_chapter.setEnabled(bool(self.chapters))
        preview_source_row.addWidget(self.preview_chapter, 1)
        preview_layout.addLayout(preview_source_row)

        preview_actions = QHBoxLayout()
        self.preview_button = QPushButton("▶  Generate Voice Preview")
        self.preview_button.clicked.connect(self.preview)
        self.preview_play_button = QPushButton("▶  Play Preview")
        self.preview_play_button.setEnabled(False)
        self.preview_play_button.clicked.connect(self.play_preview)
        self.preview_stop_button = QPushButton("■  Stop")
        self.preview_stop_button.setEnabled(False)
        self.preview_stop_button.clicked.connect(self.stop_preview)
        preview_actions.addWidget(self.preview_button, 1)
        preview_actions.addWidget(self.preview_play_button)
        preview_actions.addWidget(self.preview_stop_button)
        preview_layout.addLayout(preview_actions)

        preview_time_row = QHBoxLayout()
        self.preview_status = QLabel("Generate a preview to listen to the selected voice.")
        self.preview_time = QLabel("0:00 / 0:00")
        preview_time_row.addWidget(self.preview_status, 1)
        preview_time_row.addWidget(self.preview_time)
        preview_layout.addLayout(preview_time_row)
        root.addWidget(preview_box)

        progress_box = QGroupBox("Generation")
        progress_layout = QVBoxLayout(progress_box)
        self.progress = QProgressBar()
        progress_layout.addWidget(self.progress)
        stats = QHBoxLayout()
        self.stage = QLabel("Ready")
        self.elapsed = QLabel("Elapsed: 0:00")
        self.remaining = QLabel("Remaining: —")
        self.speed = QLabel("Speed: —")
        stats.addWidget(self.stage)
        stats.addStretch(1)
        stats.addWidget(self.elapsed)
        stats.addWidget(self.remaining)
        stats.addWidget(self.speed)
        progress_layout.addLayout(stats)
        root.addWidget(progress_box)

        result_box = QGroupBox("Audiobook Ready")
        result_layout = QVBoxLayout(result_box)
        self.result_label = QLabel("Your finished audiobook will appear here after M4B packaging.")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)
        result_actions = QHBoxLayout()
        self.play_button = QPushButton("▶  Play Audiobook")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_result)
        self.stop_button = QPushButton("■  Stop")
        self.stop_button.clicked.connect(self.player.stop)
        self.open_button = QPushButton("Open Folder")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_result_folder)
        result_actions.addWidget(self.play_button)
        result_actions.addWidget(self.stop_button)
        result_actions.addWidget(self.open_button)
        result_layout.addLayout(result_actions)
        self.result_time = QLabel("0:00 / 0:00")
        result_layout.addWidget(self.result_time)
        root.addWidget(result_box)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Generate Audiobook")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.start_button)
        actions.addWidget(self.cancel_button)
        root.addLayout(actions)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self.status = QLabel("Ready")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        self.signals.progress.connect(self.update_progress)
        self.signals.finished.connect(self.finished)
        self.start_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_live_stats)

        self._restore_state()
        self._load_pronunciations()
        self._load_voice_cast_summary()
        self._set_default_output()

    def _add_pronunciation_row(self, written="", spoken="", enabled=True):
        from PySide6.QtCore import Qt
        row = self.pronunciation_table.rowCount()
        self.pronunciation_table.insertRow(row)
        self.pronunciation_table.setItem(row, 0, QTableWidgetItem(written))
        self.pronunciation_table.setItem(row, 1, QTableWidgetItem(spoken))
        item = QTableWidgetItem()
        item.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        self.pronunciation_table.setItem(row, 2, item)

    def _suggest_pronunciations(self):
        existing = {
            str(self.pronunciation_table.item(row, 0).text()).casefold()
            for row in range(self.pronunciation_table.rowCount())
            if self.pronunciation_table.item(row, 0)
        }
        suggestions = []
        try:
            analysis = analyze_book(self.chapters)
            for character in analysis.characters:
                if character.name:
                    suggestions.append(character.name)
                suggestions.extend(character.aliases or [])
        except Exception:
            pass

        # Automatic suggestions come only from detected characters/aliases.
        # Do not scan every capitalized word because ordinary English words
        # such as "But", "She", "Her", and "What" are not names.
        added = 0
        for name in suggestions:
            clean = name.strip()
            key = clean.casefold()
            if (
                not clean
                or key in existing
                or len(clean) < 3
                or key in COMMON_ENGLISH_WORDS
            ):
                continue
            spoken = suggest_pronunciation(clean)
            self._add_pronunciation_row(clean, spoken, True)
            existing.add(key)
            added += 1
            if added >= 40:
                break

        if added:
            self.pronunciation_status.setText(
                f"Added {added} character name{'s' if added != 1 else ''} with draft pronunciation suggestions. "
                "Only detected characters/aliases are suggested automatically; review the spoken form before saving."
            )
        else:
            self.pronunciation_status.setText(
                "No new character names found. Use + Add Pronunciation for custom terms."
            )

    def _clean_obvious_english_pronunciations(self):
        removed = 0
        row = 0
        while row < self.pronunciation_table.rowCount():
            item = self.pronunciation_table.item(row, 0)
            written = item.text().strip().casefold() if item else ""
            if written in COMMON_ENGLISH_WORDS:
                self.pronunciation_table.removeRow(row)
                removed += 1
                continue
            row += 1
        self._save_pronunciations()
        self.pronunciation_status.setText(
            f"Removed {removed} obvious English-word override{'s' if removed != 1 else ''}."
            if removed
            else "No obvious English-word overrides found."
        )

    def _remove_pronunciation_row(self):
        row = self.pronunciation_table.currentRow()
        if row >= 0:
            self.pronunciation_table.removeRow(row)
            self._save_pronunciations()

    def _pronunciation_entries(self):
        from PySide6.QtCore import Qt
        entries = []
        for row in range(self.pronunciation_table.rowCount()):
            a = self.pronunciation_table.item(row, 0)
            b = self.pronunciation_table.item(row, 1)
            c = self.pronunciation_table.item(row, 2)
            written = a.text().strip() if a else ""
            spoken = b.text().strip() if b else ""
            if written and spoken:
                entries.append({"written": written, "spoken": spoken, "enabled": c is not None and c.checkState() == Qt.CheckState.Checked})
        return entries

    def _load_pronunciations(self):
        self.pronunciation_table.setRowCount(0)
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        entries = state.get("pronunciation_dictionary", [])
        cleaned = []
        removed_obvious = 0
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                written = str(item.get("written", "")).strip()
                if written.casefold() in COMMON_ENGLISH_WORDS:
                    removed_obvious += 1
                    continue
                cleaned.append(item)
                self._add_pronunciation_row(
                    written,
                    str(item.get("spoken", "")),
                    item.get("enabled", True) is not False,
                )
        if removed_obvious and cleaned != entries:
            state["pronunciation_dictionary"] = cleaned
            save_state(self.project_folder, state)
        count = len(self._pronunciation_entries())
        self.pronunciation_status.setText(f"{count} pronunciation override{'s' if count != 1 else ''} saved for this book." if count else "No pronunciation overrides saved for this book.")

    def _save_pronunciations(self):
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        entries = self._pronunciation_entries()
        state["pronunciation_dictionary"] = entries
        save_state(self.project_folder, state)
        self.pronunciation_status.setText(f"{len(entries)} pronunciation override{'s' if len(entries) != 1 else ''} saved for this book." if entries else "No pronunciation overrides saved for this book.")
    def _load_voice_cast_summary(self):
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        cast = state.get("voice_cast", {})
        if not cast:
            self.cast_summary.setText("No character-specific voice assignments saved. Narrator voice will be used.")
            return
        lines = [f"{name} → {voice}" for name, voice in cast.items()]
        self.cast_summary.setText(
            "Saved voice cast assignments:\n" + "\n".join(lines) +
            "\n\nThese assignments are stored with this book and are ready for the cast-aware narration engine."
        )

    def _load_profiles(self, keep_name: str | None = None) -> None:
        self.voice_profile.clear()
        for profile in self.profiles:
            self.voice_profile.addItem(profile.name, profile)
        if not self.profiles:
            self.voice_profile.addItem("No saved voice profiles", None)
            return
        if keep_name:
            index = self.voice_profile.findText(keep_name)
            if index >= 0:
                self.voice_profile.setCurrentIndex(index)

    def _refresh_voice_profiles(self) -> None:
        current = self.voice_profile.currentText()
        self.profiles = load_profiles()
        self._load_profiles(current)
        self.status.setText("Voice profiles refreshed.")

    def _update_overview(self) -> None:
        words = sum(len(ch.text.split()) for ch in self.chapters)
        minutes = max(1, round(words / 150))
        self.chapter_count.setText(f"Chapters: {len(self.chapters)}")
        self.word_count.setText(f"Words: {words:,}")
        self.duration_estimate.setText(f"Estimated length: {minutes // 60}h {minutes % 60:02d}m")

    def _default_output(self) -> Path | None:
        if not self.project_folder:
            return None
        folder = self.project_folder / "Audiobook"
        folder.mkdir(parents=True, exist_ok=True)
        title = self.title.text().strip() or self.project_folder.name
        safe = "".join(c if c not in '<>:"/\\|?*' else "_" for c in title).strip() or "Audiobook"
        return folder / f"{safe}.m4b"

    def _set_default_output(self) -> None:
        default = self._default_output()
        state = load_state(self.project_folder) if self.project_folder else {}
        saved = Path(state["output_path"]) if state.get("output_path") else None
        # Old versions used Downloads. New projects always default to the
        # project's Audiobook folder unless the saved path is already there.
        if saved and self.project_folder and saved.parent == self.project_folder / "Audiobook":
            self.output.setText(str(saved))
        elif default:
            self.output.setText(str(default))

    def _restore_state(self) -> None:
        if not self.project_folder:
            return
        state = load_state(self.project_folder)
        profile_name = state.get("voice_profile")
        if profile_name:
            index = self.voice_profile.findText(profile_name)
            if index >= 0:
                self.voice_profile.setCurrentIndex(index)
        speed = state.get("narration_speed")
        if speed is not None:
            index = self.narration_speed.findData(float(speed))
            if index >= 0:
                self.narration_speed.setCurrentIndex(index)
        pacing = state.get("pacing_profile")
        if pacing:
            index = self.pacing_profile.findData(pacing)
            if index >= 0:
                self.pacing_profile.setCurrentIndex(index)

        cover = state.get("cover_path")
        if cover and Path(cover).exists():
            self.cover = Path(cover)
            self.cover_label.setText(self.cover.name)

    def _selected_profile(self) -> VoiceProfile | None:
        value = self.voice_profile.currentData()
        return value if isinstance(value, VoiceProfile) else None

    def choose_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save M4B", str(self._default_output() or ""),
            "M4B Audiobook (*.m4b)",
        )
        if path:
            self.output.setText(str(Path(path).with_suffix(".m4b")))

    def choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Cover", "", "Images (*.jpg *.jpeg *.png)")
        if path:
            self.cover = Path(path)
            self.cover_label.setText(self.cover.name)

    def _cast_provider(self, narrator_provider, narrator_voice):
        if not self.project_folder:
            return narrator_provider, narrator_voice
        state = load_state(self.project_folder)
        assignments = state.get("voice_cast", {})
        if not assignments:
            return narrator_provider, narrator_voice
        from app.tts.cast_provider import CastAwareProvider
        profiles = {profile.name: profile for profile in self.profiles}
        narrating_character = state.get("voice_cast_narrating_character")
        return CastAwareProvider(
            narrator_provider,
            narrator_voice,
            profiles,
            assignments,
            narrating_character=narrating_character,
            backend_override=self.backend.currentData() or "automatic",
        ), narrator_voice

    def _provider(self):
        profile = self._selected_profile()
        if not profile:
            return None, None
        backend = self.backend.currentData() or profile.backend
        if backend == "automatic":
            backend = profile.backend
        if profile.provider == "piper":
            return PiperProvider(backend=backend), profile.voice_id
        if profile.provider == "windows-sapi":
            return SystemSAPIProvider(), profile.voice_id
        provider, voice = provider_from_profile(profile)
        if hasattr(provider, "backend"):
            provider.backend = backend
        return provider, voice

    def preview(self) -> None:
        provider, voice = self._provider()
        if not provider:
            self.status.setText("Create or select a Voice Profile first.")
            return

        index = self.preview_chapter.currentIndex()
        if index < 0 or index >= len(self.chapters):
            self.status.setText("Select a chapter for the preview.")
            return

        chapter = self.chapters[index]
        self._save_pronunciations()
        pronunciation_dictionary = self._pronunciation_entries()
        provider = self._cast_provider(provider, voice)[0]

        text = chapter.text
        output = Path(tempfile.gettempdir()) / "ryu_audiobook_voice_preview.wav"

        try:
            result = build_voice_preview(
                text,
                provider,
                voice,
                output,
                pronunciation_dictionary=pronunciation_dictionary,
                narration_speed=float(self.narration_speed.currentData() or 0.90),
                pacing_profile=self.pacing_profile.currentData() or "natural",
            )
            self.preview_path = result.output_path
            self.preview_player.stop()
            self.preview_player.setSource(QUrl.fromLocalFile(str(result.output_path)))
            self.preview_play_button.setEnabled(True)
            self.preview_stop_button.setEnabled(True)
            self.preview_play_button.setText("▶  Play Preview")

            voice_summary = ", ".join(result.voices_used) if result.voices_used else "Narrator"
            message = (
                f"Preview ready • {result.segments} narration segment(s) • "
                f"Voices: {voice_summary}"
            )
            self.preview_status.setText(message)
            self.status.setText(
                f"Preview generated from Chapter {chapter.number} using the current "
                "pronunciation, voice cast, speed and pacing settings."
            )
        except Exception as exc:
            self.preview_path = None
            self.preview_play_button.setEnabled(False)
            self.preview_stop_button.setEnabled(False)
            self.preview_status.setText("Preview generation failed.")
            self.status.setText(f"Preview failed: {exc}")
        finally:
            close = getattr(provider, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    def play_preview(self) -> None:
        if not self.preview_path or not self.preview_path.exists():
            self.preview_status.setText("Generate a voice preview first.")
            return
        if self.preview_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_player.pause()
        else:
            self.preview_player.play()

    def stop_preview(self) -> None:
        self.preview_player.stop()

    def _preview_state_changed(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.preview_play_button.setText("Ⅱ  Pause Preview")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.preview_play_button.setText("▶  Resume Preview")
        else:
            self.preview_play_button.setText("▶  Play Preview")

    def _preview_position(self, position: int) -> None:
        self.preview_time.setText(
            f"{self._fmt(position)} / {self._fmt(self.preview_player.duration())}"
        )

    def _preview_duration(self, duration: int) -> None:
        self.preview_time.setText(
            f"{self._fmt(self.preview_player.position())} / {self._fmt(duration)}"
        )

    def _set_generation_locked(self, locked: bool) -> None:
        controls = [
            self.title, self.author, self.voice_profile, self.refresh_voice_profiles,
            self.backend, self.cover_button, self.change_output, self.preview_button,
            self.start_button,
        ]
        for control in controls:
            control.setEnabled(not locked)

    def _repair_empty_chapters_from_source(self) -> bool:
        if not self.project_folder:
            return False
        try:
            project_file = self.project_folder / "project.json"
            metadata = json.loads(project_file.read_text(encoding="utf-8"))
            source_name = metadata.get("source_file")
            if not source_name:
                return False
            source = self.project_folder / "source" / source_name
            if not source.exists():
                return False
            detected = detect_chapters(extract_text(source).text)
            if not detected or any(not c.text.strip() for c in detected):
                return False
            chapters_file = self.project_folder / "chapters.json"
            chapters_file.write_text(
                json.dumps(
                    [
                        {"number": c.number, "title": c.title, "text": c.text}
                        for c in detected
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            self.chapters = detected
            self._update_overview()
            self.status.setText("Chapter list was automatically repaired from the original source.")
            return True
        except Exception:
            return False

    def start(self) -> None:
        if not self.chapters:
            self.status.setText("No chapters available.")
            return

        empty = [c for c in self.chapters if not c.text or not c.text.strip()]
        if empty:
            self._repair_empty_chapters_from_source()
            empty = [c for c in self.chapters if not c.text or not c.text.strip()]
        if empty:
            # Empty records are never synthesizable. If the source cannot be
            # re-read, safely remove only the empty records instead of blocking
            # an otherwise valid audiobook because of stale project state.
            self.chapters = [c for c in self.chapters if c.text and c.text.strip()]
            for number, chapter in enumerate(self.chapters, start=1):
                chapter.number = number
            if self.project_folder:
                try:
                    chapters_file = self.project_folder / "chapters.json"
                    chapters_file.write_text(
                        json.dumps(
                            [{"number": c.number, "title": c.title, "text": c.text} for c in self.chapters],
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
            self._update_overview()
            empty = [c for c in self.chapters if not c.text or not c.text.strip()]
        if empty:
            numbers = ", ".join(str(c.number) for c in empty)
            self.status.setText(
                f"Generation stopped: chapter(s) {numbers} contain no body text. "
                "Please review the Chapters page."
            )
            return

        output = Path(self.output.text().strip()) if self.output.text().strip() else self._default_output()
        if not output:
            self.status.setText("Choose an M4B output.")
            return
        self._save_pronunciations()
        profile = self._selected_profile()
        if profile and profile.provider == "chatterbox" and not runtime_ready():
            self.status.setText(
                "Custom voice engine is not installed. Open Models → Install / Repair Custom Voice Engine, "
                "then return to Generate."
            )
            return

        provider, voice = self._provider()
        if not provider:
            self.status.setText("Select a Voice Profile.")
            return
        provider, voice = self._cast_provider(provider, voice)

        output.parent.mkdir(parents=True, exist_ok=True)
        if self.project_folder:
            state = load_state(self.project_folder)
            profile = self._selected_profile()
            state.update({
                "voice_profile": profile.name if profile else None,
                "output_path": str(output),
                "cover_path": str(self.cover) if self.cover else None,
                "narration_speed": float(self.narration_speed.currentData() or 0.90),
                "pacing_profile": self.pacing_profile.currentData() or "natural",
                "status": "generating",
            })
            save_state(self.project_folder, state)

        self.progress.setRange(0, len(self.chapters))
        self.progress.setValue(0)
        self.last_progress_value = 0
        self.started_at = time.monotonic()
        self.timer.start(1000)
        self._set_generation_locked(True)
        self.cancel_button.setEnabled(True)
        self.play_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.result_label.setText("Generating chapters and packaging the final M4B…")
        self.status.setText("Starting generation…")

        self.manager = GenerationManager(
            provider, voice, self.chapters, self.audio_root,
            on_progress=lambda *args: self.signals.progress.emit(*args),
            on_finished=lambda summary: self.signals.finished.emit(summary),
            pronunciation_dictionary=self._pronunciation_entries(),
            narration_speed=float(self.narration_speed.currentData() or 0.90),
            pacing_profile=self.pacing_profile.currentData() or "natural",
        )
        self.manager.start(output, self.title.text().strip(), self.author.text().strip(), self.cover)

    def cancel(self) -> None:
        if self.manager:
            self.manager.cancel()
            self.status.setText("Cancelling after the current chunk…")

    def update_progress(self, chapter: int, total: int, done: int, message: str) -> None:
        if message.startswith("plan:"):
            try:
                planned = max(1, int(message.split(":", 1)[1]))
            except ValueError:
                planned = max(1, total)
            self.progress.setRange(0, planned)
            self.progress.setValue(0)
            self.last_progress_value = 0
            self.stage.setText(f"Preparing {planned:,} audio chunks…")
            return

        if message.startswith("m4b-complete"):
            self.progress.setValue(self.progress.maximum())
            self.stage.setText("M4B packaging complete")
        elif message.startswith("m4b-failed"):
            self.stage.setText("M4B packaging failed")
            self.status.setText(message)
        elif message.startswith("chunk:"):
            try:
                current, planned = message.split(":", 1)[1].split("/", 1)
                current_n, planned_n = int(current), int(planned)
                self.progress.setRange(0, max(1, planned_n))
                self.progress.setValue(current_n)
                self.last_progress_value = current_n
                self.stage.setText(
                    f"Generating audio • chunk {current_n:,}/{planned_n:,} • chapter {chapter}/{total}"
                )
            except (ValueError, IndexError):
                self.stage.setText(f"Chapter {chapter}/{total}")
        else:
            value = chapter if message == "chapter-complete" else max(0, chapter - 1)
            self.progress.setValue(value)
            self.last_progress_value = value
            if message == "chapter-complete":
                self.stage.setText(f"Chapter {chapter}/{total} complete")
            elif message.startswith("chapter-failed"):
                self.stage.setText(f"Chapter {chapter}/{total} failed")
            else:
                self.stage.setText(f"Chapter {chapter}/{total}")

    def _update_live_stats(self) -> None:
        if self.started_at is None:
            return
        elapsed = int(time.monotonic() - self.started_at)
        self.elapsed.setText(f"Elapsed: {elapsed // 60}:{elapsed % 60:02d}")
        current = self.progress.value()
        total = max(1, self.progress.maximum())
        if current > 0 and elapsed > 2:
            estimated_total = elapsed * total / current
            remaining = max(0, int(estimated_total - elapsed))
            self.remaining.setText(f"Remaining: {remaining // 60}:{remaining % 60:02d}")
            speed = current / elapsed * 60
            self.speed.setText(f"Speed: {speed:.2f} chunks/min")
        else:
            self.remaining.setText("Remaining: calculating…")
            self.speed.setText("Speed: calculating…")

    def finished(self, summary: GenerationSummary) -> None:
        self.timer.stop()
        self._set_generation_locked(False)
        self.cancel_button.setEnabled(False)
        if self.project_folder:
            state = load_state(self.project_folder)
            state["status"] = "completed" if summary.output_path else ("failed" if (summary.chapters_failed or summary.packaging_failed) else "cancelled")
            state["completed_chapters"] = [c.number for c in self.chapters[:summary.chapters_completed]]
            state["failed_chapters"] = summary.chapters_failed
            save_state(self.project_folder, state)

        if summary.output_path:
            self.progress.setValue(self.progress.maximum())
            self.stage.setText("Audiobook ready")
            self.result_label.setText(f"✓ Finished M4B\n{summary.output_path}")
            self.play_button.setEnabled(True)
            self.open_button.setEnabled(True)
            self.status.setText("Audiobook created successfully. Intermediate generation audio has been cleaned.")
        elif summary.packaging_failed:
            self.stage.setText("M4B packaging failed")
            error = f"\n\nPackaging error: {summary.packaging_error}" if summary.packaging_error else ""
            self.result_label.setText(
                "The chapters were generated, but the final M4B could not be packaged. "
                "Temporary files were kept so you can retry." + error
            )
            self.status.setText("M4B creation failed. The generated audio has been kept for retry.")
        elif summary.chapters_failed:
            self.stage.setText("Generation failed")
            details = []
            for number in summary.chapters_failed:
                reason = (summary.failure_details or {}).get(number, "Unknown generation error")
                details.append(f"Chapter {number}: {reason}")
            self.result_label.setText(
                "Generation failed. Temporary files were kept so you can retry.\n\n"
                + "\n".join(details)
            )
            self.status.setText("The final M4B was not created. See the chapter-specific errors above.")
        else:
            self.stage.setText("Generation cancelled")
            self.result_label.setText("Generation cancelled. Temporary files were kept for resume.")
            self.status.setText("No final M4B was created.")

    def play_result(self) -> None:
        path = Path(self.output.text().strip())
        if not path.exists():
            self.status.setText("Final M4B was not found.")
            return
        if self.player.source().toLocalFile() != str(path):
            self.player.setSource(QUrl.fromLocalFile(str(path)))
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("▶  Play Audiobook")
        else:
            self.player.play()
            self.play_button.setText("Ⅱ  Pause")

    def open_result_folder(self) -> None:
        path = Path(self.output.text().strip())
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _player_position(self, position: int) -> None:
        self.result_time.setText(f"{self._fmt(position)} / {self._fmt(self.player.duration())}")

    def _player_duration(self, duration: int) -> None:
        self.result_time.setText(f"{self._fmt(self.player.position())} / {self._fmt(duration)}")

    @staticmethod
    def _fmt(ms: int) -> str:
        seconds = max(0, ms // 1000)
        return f"{seconds // 60}:{seconds % 60:02d}"
