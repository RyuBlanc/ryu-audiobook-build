"""Headless Windows Qt acceptance for the native Stage 3 Character Studio.

This boots the real QWidget panel, analyzes source dialogue in its QThread,
uses the actual assignment dialog flow, saves/reopens a real Project, and
runs the panel's real VoicePreviewWorker against a downloaded Piper model.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import wave
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from app.chapters.detector import Chapter
from app.core.project import Project
from app.ui.native_character_studio import (
    NativeCharacterAssignmentDialog,
    NativeCharacterDialoguePanel,
)
from app.tts.voice_profile import VoiceProfile


SERIES = "Stage 3 Native Character UI Acceptance"


class FakeVoiceCastPage(QWidget):
    def __init__(self, project: Project, profile: VoiceProfile, root: Path):
        super().__init__()
        self.project = project
        self.cast_path = root / "voice-cast.json"
        if self.cast_path.is_file():
            try:
                self.rows = json.loads(self.cast_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                self.rows = []
        else:
            self.rows = [{
                "name": "Mira",
                "role": "Lead",
                "series": SERIES,
                "aliases": ["Mira Vale"],
                "voice": profile.name,
                "dialogue_count": 1,
                "examples": ["Stay close."],
                "confidence": 1.0,
            }]
        self.summary = QLabel("")
        self.profile = profile
        self.saved_cast_writes = 0
        self.last_voice_update = False

    def _series_name(self) -> str:
        return SERIES

    def get_chapters(self):
        return list(self.project.chapters)

    def find_character(self, name: str, series: str):
        return next(
            (
                row for row in self.rows
                if str(row.get("name") or "").casefold() == str(name).casefold()
                and str(row.get("series") or "").casefold() == str(series).casefold()
            ),
            None,
        )

    def _refresh_character_counts(self):
        return None

    def _save_cast(self, update_voice: bool = False):
        self.cast_path.write_text(
            json.dumps(self.rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.saved_cast_writes += 1
        self.last_voice_update = bool(update_voice)

    def _refresh_labels(self):
        return None


def _wait_for(app: QApplication, predicate, timeout_seconds: float, failure: str):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()
            return
        time.sleep(0.025)
    app.processEvents()
    if not predicate():
        raise RuntimeError(failure)


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        if audio.getnframes() <= 0 or audio.getframerate() <= 0:
            raise RuntimeError(f"Character preview WAV is empty or invalid: {path}")
        return audio.getnframes() / float(audio.getframerate())


def main() -> None:
    app = QApplication.instance() or QApplication([])
    output_root = Path(os.environ.get("RYU_STAGE3_ACCEPTANCE_OUTPUT", "stage3-real-provider-artifacts"))
    output_root.mkdir(parents=True, exist_ok=True)

    profile = VoiceProfile(
        name="CI Piper Mira",
        provider="piper",
        voice_id="en_US-amy-medium",
        model_id="piper",
        backend="cpu",
        language="en-US",
        authorized=True,
    )

    chapter_one = Chapter(
        1,
        "The Tunnel",
        "The lantern flickered. Mira said, “Stay close.” The tunnel narrowed.",
        review_status="ready",
    )
    chapter_two = Chapter(
        2,
        "The Road",
        "Ren answered, “I can guide us.” Rain covered the road.",
        review_status="ready",
    )

    with tempfile.TemporaryDirectory(prefix="ryu-stage3-native-character-ui-") as temp:
        root = Path(temp)
        project_folder = root / "Library" / "Native Character UI"
        project = Project("Native Character UI", project_folder, None, [chapter_one, chapter_two])
        project.save()

        cast_page = FakeVoiceCastPage(project, profile, root)
        panel = NativeCharacterDialoguePanel(cast_page)
        panel.show()
        panel.refresh_project_data()

        if panel.manual_chapters.count() != 2 or panel.ai_chapters.count() != 2:
            raise RuntimeError("Native Character Studio did not render both saved project chapters.")
        if "Stay close." not in panel.manual_story.toPlainText():
            raise RuntimeError("Manual Character Studio view did not render the first chapter's live source text.")

        # Exercise the real asynchronous dialogue analysis worker and wait for
        # its queued UI completion callback; suggestions are not auto-assigned.
        with (
            patch("app.ui.native_character_studio.load_state", return_value={}),
            patch("app.ui.native_character_studio.list_characters", return_value=[]),
            patch("app.ui.native_character_studio.load_learning_examples", return_value=[]),
            patch("app.ui.native_character_studio.load_profiles", return_value=[profile]),
        ):
            panel.ai_analyze_button.click()
            _wait_for(
                app,
                lambda: panel._analysis_worker is None,
                60.0,
                "Native Character Studio dialogue analysis worker did not finish.",
            )
            if len(panel._review_rows) < 2:
                raise RuntimeError(
                    f"Native Character Studio analysis did not expose both chapters: {panel._review_rows!r}"
                )
            if "I can guide us." not in panel.ai_story.toPlainText():
                raise RuntimeError("AI review view did not render the second chapter's live source dialogue.")

            # Open the real source-backed assignment dialog from its dialogue://
            # link, choose Mira and her saved Audio Profile, then click Assign.
            source = str(project.chapters[0].text)
            dialogue = "Stay close."
            start = source.index(dialogue)
            end = start + len(dialogue)
            dialog_outcome = {}

            def accept_real_assignment_dialog():
                try:
                    dialog = QApplication.activeModalWidget()
                    if not isinstance(dialog, NativeCharacterAssignmentDialog):
                        raise RuntimeError("The real Character Assignment dialog did not open.")
                    mira_row = next(
                        (
                            index for index in range(dialog.saved_characters.count())
                            if str(dialog.saved_characters.item(index).data(256).get("name") or "") == "Mira"
                        ),
                        -1,
                    )
                    if mira_row < 0:
                        raise RuntimeError("Saved Mira character was absent from the assignment selector.")
                    dialog.saved_characters.setCurrentRow(mira_row)
                    profile_index = dialog.profile.findData(profile.name)
                    if profile_index < 0:
                        raise RuntimeError("Saved Piper Audio Profile was absent from the assignment selector.")
                    dialog.profile.setCurrentIndex(profile_index)
                    dialog.assign_button.click()
                    dialog_outcome["accepted"] = True
                except Exception as exc:
                    dialog_outcome["error"] = str(exc)
                    dialog = QApplication.activeModalWidget()
                    if dialog is not None:
                        dialog.reject()

            QTimer.singleShot(0, accept_real_assignment_dialog)
            panel._manual_link_clicked(QUrl(f"dialog://1/{start}/{end}"))
            if dialog_outcome.get("error"):
                raise RuntimeError(dialog_outcome["error"])
            if not dialog_outcome.get("accepted"):
                raise RuntimeError("The real Character Assignment dialog did not complete its Save/Assign action.")

            saved = Project.load(project_folder)
            assignment = next(
                (
                    row for row in saved.chapters[0].dialogue_assignments
                    if row.get("start") == start and row.get("end") == end
                ),
                None,
            )
            if not assignment:
                raise RuntimeError("The native assignment dialog did not persist the selected passage.")
            if assignment.get("speaker") != "Mira" or assignment.get("source") != "manual":
                raise RuntimeError(f"Saved assignment identity/provenance was incorrect: {assignment!r}")
            if assignment.get("series") != SERIES:
                raise RuntimeError(f"Saved assignment lost its series identity: {assignment!r}")
            if not cast_page.last_voice_update or cast_page.rows[0].get("voice") != profile.name:
                raise RuntimeError("The selected saved Audio Profile was not persisted on the cast record.")

            panel.refresh_project_data()
            if "Assigned: Mira" not in panel.manual_story.toHtml():
                raise RuntimeError("Manual Character Studio did not render the saved assignment highlight.")
            if "Assigned: Mira" not in panel.ai_story.toHtml():
                raise RuntimeError("AI review view did not reflect the saved manual assignment distinctly.")

            # Reopen the project and the widget to verify assignment + profile
            # identity survive the same save/reload boundary the user uses.
            reopened = Project.load(project_folder)
            reopened_page = FakeVoiceCastPage(reopened, profile, root)
            reopened_panel = NativeCharacterDialoguePanel(reopened_page)
            reopened_panel.refresh_project_data()
            if "Assigned: Mira" not in reopened_panel.manual_story.toHtml():
                raise RuntimeError("Saved manual speaker assignment did not survive native UI project reopen.")
            if reopened_page.rows[0].get("voice") != profile.name:
                raise RuntimeError("Saved character Audio Profile did not survive native UI reopen.")

            # Run the actual UI preview handler and its QThread worker. It uses
            # provider_from_profile -> PiperProvider and then hands the output
            # to the panel's QMediaPlayer, not a fake preview result.
            status = QLabel("")
            exact_sample = "Stay close."
            reopened_panel.test_voice_profile(profile.name, exact_sample, status)
            worker = reopened_panel._preview_worker
            if worker is None:
                raise RuntimeError(f"Character Studio did not start its real preview worker: {status.text()}")
            _wait_for(
                app,
                lambda: not worker.isRunning(),
                120.0,
                "Native Character Studio selected-profile preview exceeded the 120-second smoke limit.",
            )
            _wait_for(
                app,
                lambda: reopened_panel._preview_worker is None,
                8.0,
                "Native Character Studio did not deliver the preview worker's completion back to the UI thread.",
            )
            preview_path = reopened_panel._preview_dir / "preview.wav"
            if not preview_path.is_file() or preview_path.stat().st_size < 1024:
                raise RuntimeError(f"Selected-profile UI preview did not create a valid WAV: {status.text()}")
            preview_seconds = _wav_duration(preview_path)
            if reopened_panel._player.source().toLocalFile() != str(preview_path):
                raise RuntimeError("Native Character Studio player was not handed the real selected-profile preview file.")
            if cast_page.saved_cast_writes < 1:
                raise RuntimeError("The native UI did not persist its saved cast update.")

            saved_audio = output_root / "native-character-studio-selected-dialogue.wav"
            saved_audio.write_bytes(preview_path.read_bytes())

            print(
                "NATIVE_CHARACTER_STUDIO_UI=PASS "
                f"chapters=2 ai_review_rows={len(panel._review_rows)} "
                f"saved_assignment={assignment['speaker']} "
                f"profile={profile.name} reopened=true"
            )
            print(
                "NATIVE_CHARACTER_STUDIO_SELECTED_VOICE_PREVIEW=PASS "
                f"provider=piper voice={profile.voice_id} "
                f"actual_audio={preview_seconds:.3f}s player_handoff=true "
                f"bytes={saved_audio.stat().st_size}"
            )

            reopened_panel.close()
            panel.close()
            cast_page.close()
            reopened_page.close()

    print("STAGE_3_NATIVE_CHARACTER_UI_ACCEPTANCE=PASS")


if __name__ == "__main__":
    main()
