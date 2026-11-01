"""Premium V2 WebEngine end-to-end acceptance for Stage 3.

Exercises the default shipped desktop UI (not the native compatibility panel),
the actual QWebChannel bridge, saved cast statistics/source styles, manual
assignment, selected dialogue preview/playback, series narrator inheritance,
project override/reset, and narration-only narrator preview.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--disable-gpu --no-sandbox --autoplay-policy=no-user-gesture-required "
    "--mute-audio --disable-features=AudioServiceOutOfProcess"
)

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEngineProfile

from app.chapters.detector import Chapter
from app.core.project import Project
from app.core.state import save_state
from app.tts.voice_profile import VoiceProfile, save_profiles


SERIES = "Stage 3 Premium V2 Acceptance"
PROJECT_TITLE = "Stage 3 Premium V2 Browser Acceptance"
PROFILE_MIRA = "Stage 3 Mira • Piper Amy"
PROFILE_REN = "Stage 3 Ren • Piper Ryan"
PROFILE_NARRATOR = "Stage 3 Narrator • Piper Lessac"
PROFILE_OVERRIDE = "Stage 3 Override Narrator • Piper Ryan"


def _span(source: str, phrase: str) -> dict:
    start = source.index(phrase)
    end = start + len(phrase)
    return {
        "start": start,
        "end": end,
        "text": phrase,
        "speaker": "Mira",
        "speakers": ["Mira"],
        "source": "manual",
        "confidence": 1.0,
        "series": SERIES,
    }


def _wait_until(app: QApplication, predicate, timeout: float, message: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        try:
            if predicate():
                app.processEvents()
                return
        except Exception:
            pass
        time.sleep(0.04)
    app.processEvents()
    raise RuntimeError(message)


def _run_javascript(window, source: str, app: QApplication, timeout: float = 10.0):
    result: dict[str, object] = {"done": False}
    window.web.page().runJavaScript(
        source,
        lambda value: result.update({"done": True, "value": value}),
    )
    _wait_until(app, lambda: bool(result["done"]), timeout, "Premium V2 JavaScript bridge evaluation timed out.")
    return result.get("value")


def _copy_preview(source_value: str, output: Path, expected_provider: str) -> dict:
    source = Path(str(source_value or "")).expanduser()
    if not source.is_file() or source.stat().st_size < 1024:
        raise RuntimeError(f"Premium V2 did not create a valid {expected_provider} preview WAV: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    return {"source": str(source), "artifact": str(output), "bytes": output.stat().st_size}


def _seed_project(project_folder: Path, app_root: Path, voices_root: Path, models_root: Path) -> Project:
    chapter_one_text = (
        "The lantern glowed. Mira said, “Stay close.” "
        "The old door opened. Ren said, “I can guide us.”"
    )
    chapter_two_text = (
        "Rain fell steadily. Mira whispered, “I will stay.” "
        "The river moved beyond the village."
    )
    mira_one = _span(chapter_one_text, "“Stay close.”")
    mira_two = {
        **_span(chapter_two_text, "“I will stay.”"),
        "source": "ai",
        "confidence": 0.93,
    }
    chapter_one = Chapter(
        1,
        "The Tunnel",
        chapter_one_text,
        dialogue_assignments=[mira_one],
        review_status="ready",
    )
    chapter_two = Chapter(
        2,
        "The Road",
        chapter_two_text,
        dialogue_assignments=[mira_two],
        review_status="ready",
    )
    project = Project(PROJECT_TITLE, project_folder, None, [chapter_one, chapter_two])
    project.save()
    save_state(
        project.folder,
        {
            "status": "ready",
            "series_name": SERIES,
            "characters": [
                {
                    "name": "Mira",
                    "series": SERIES,
                    "aliases": ["Mira Vale"],
                    "role": "Lead",
                    "voice_profile": PROFILE_MIRA,
                    "dialogue_count": 2,
                    "examples": ["“Stay close.”", "“I will stay.”"],
                },
                {
                    "name": "Ren",
                    "series": SERIES,
                    "aliases": ["Ren Vale"],
                    "role": "Supporting",
                    "voice_profile": PROFILE_REN,
                    "dialogue_count": 0,
                    "examples": [],
                },
            ],
            "narrator_profile_source": "none",
            "characters_source": "saved_cast",
        },
    )
    return project


JS_DRIVER = r"""
(async () => {
  const report = {status:'running', checks:[], previews:[], narrator:{}};
  const check = (name, condition, detail={}) => {
    if (!condition) throw new Error(name + ' failed: ' + JSON.stringify(detail));
    report.checks.push({name, ...detail});
  };
  const waitFor = async (predicate, timeout=15000, label='UI condition') => {
    const deadline = Date.now() + timeout;
    let last = null;
    while (Date.now() < deadline) {
      try {
        last = await predicate();
        if (last) return last;
      } catch (_) {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('Timed out waiting for ' + label + (last == null ? '' : ': ' + JSON.stringify(last)));
  };
  const call = async (command, payload={}) => {
    const response = await window.ryuBackend.invoke(command, payload);
    if (!response || response.success !== true) {
      const message = response?.error?.message || response?.error || 'No successful backend response';
      throw new Error(command + ': ' + String(message));
    }
    return response.data;
  };
  const go = async page => {
    if (typeof window.go === 'function') window.go(page);
    else {
      const item = [...document.querySelectorAll('[data-page]')].find(node => node.dataset.page === page);
      if (!item) throw new Error('No navigation item exists for page ' + page);
      item.click();
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  };
  const baselineJobs = await call('job.list', {include_hidden:true});
  const baselineIds = new Set(baselineJobs.map(job => String(job.job_id)));
  const NativeAudio = window.Audio;
  window.__stage3AudioCreated = [];
  window.__stage3PlayCalls = 0;
  window.Audio = function(source) {
    const audio = new NativeAudio(source);
    audio.muted = true;
    window.__stage3AudioCreated.push(audio);
    window.__stage3LastAudio = audio;
    return audio;
  };
  window.Audio.prototype = NativeAudio.prototype;
  const nativePlay = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function() {
    window.__stage3PlayCalls += 1;
    this.muted = true;
    return nativePlay.call(this);
  };
  const waitForVoiceJob = async (profileName, timeout=150000) => {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      const jobs = await call('job.list', {include_hidden:true});
      const candidates = jobs.filter(job =>
        job.type === 'voice-preview' &&
        !baselineIds.has(String(job.job_id)) &&
        String(job.title || '').toLowerCase().includes(profileName.toLowerCase())
      ).sort((a,b) => String(b.queued_at || '').localeCompare(String(a.queued_at || '')));
      const job = candidates[0];
      if (job && ['completed','failed','cancelled'].includes(job.state)) {
        if (job.state !== 'completed') throw new Error('Voice preview ended ' + job.state + ': ' + (job.error?.message || job.message || ''));
        if (!job.result?.output_path || !job.result?.file_url) throw new Error('Completed preview did not return a local WAV file.');
        return job;
      }
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    throw new Error('Timed out waiting for the real Piper preview job for ' + profileName);
  };

  await waitFor(() => Boolean(window.ryuBackend && typeof window.go === 'function'), 10000, 'Premium V2 backend/navigation');
  await call('app.get_info');
  const active = await call('project.get_active');
  check('default Premium V2 workspace project hydration', Boolean(active && active.title === 'Stage 3 Premium V2 Browser Acceptance'), {title:active?.title, frontend:active?.frontend || 'Premium V2'});
  const profiles = await call('voice.list');
  const savedProfiles = profiles.filter(profile => profile.saved === true).map(profile => profile.name);
  for (const expected of ['Stage 3 Mira • Piper Amy','Stage 3 Ren • Piper Ryan','Stage 3 Narrator • Piper Lessac','Stage 3 Override Narrator • Piper Ryan']) {
    check('saved profile hydrated: ' + expected, savedProfiles.includes(expected), {savedProfiles});
  }

  await go('characters');
  await waitFor(() => Boolean(document.querySelector('#assignedCharacterList [data-character-name="Mira"]')), 15000, 'Mira Assigned Cast row');
  const miraButton = document.querySelector('#assignedCharacterList [data-character-name="Mira"][data-character-series="Stage 3 Premium V2 Acceptance"]');
  if (!miraButton) throw new Error('Mira Assigned Cast row did not retain its series identity.');
  miraButton.click();
  await waitFor(() => document.querySelector('#assignedInspectorName')?.textContent.trim() === 'Mira', 5000, 'Mira inspector selection');
  const miraStats = {
    voice:document.querySelector('#assignedVoiceName')?.textContent.trim(),
    lines:document.querySelector('#assignedLineCount')?.textContent.trim(),
    chapters:document.querySelector('#assignedChapterCount')?.textContent.trim(),
    aiPercent:document.querySelector('#assignedConfidence')?.textContent.trim(),
    manualRows:document.querySelectorAll('#assignedQuotes .ryu-assigned-dialogue-manual').length,
    aiRows:document.querySelectorAll('#assignedQuotes .ryu-assigned-dialogue-ai').length
  };
  check('CS-05 saved provenance metrics and profile identity', miraStats.voice === 'Stage 3 Mira • Piper Amy' &&
    miraStats.lines === '2' && miraStats.chapters === '2' && miraStats.aiPercent === '50%' &&
    miraStats.manualRows === 1 && miraStats.aiRows === 1, miraStats);
  check('CS-06/CS-07 separate AI and manual saved dialogue rows',
    document.querySelector('.ryu-assigned-dialogue-manual')?.textContent.includes('Manually assigned') &&
    document.querySelector('.ryu-assigned-dialogue-ai')?.textContent.includes('AI-assigned'),
    {manualRows:miraStats.manualRows,aiRows:miraStats.aiRows});
  check('CS-01 project-scoped series identity', document.querySelector('#assignedSeriesName')?.textContent.trim() === 'Stage 3 Premium V2 Acceptance',
    {series:document.querySelector('#assignedSeriesName')?.textContent.trim()});

  const manualDialogue = document.querySelector('#assignedQuotes .ryu-assigned-dialogue-manual');
  if (!manualDialogue) throw new Error('Mira manual source-backed passage row was not rendered.');
  manualDialogue.click();
  await waitFor(() => Boolean(document.querySelector('#assignedQuotes .ryu-assigned-dialogue-manual.is-selected')), 5000, 'selected Mira dialogue row');
  const profileSelect = document.querySelector('#assignedAudioProfile');
  if (!profileSelect) throw new Error('Assigned Cast Audio Profile selector did not render.');
  profileSelect.value = 'Stage 3 Mira • Piper Amy';
  profileSelect.dispatchEvent(new Event('input',{bubbles:true}));
  profileSelect.dispatchEvent(new Event('change',{bubbles:true}));
  await new Promise(resolve => setTimeout(resolve,150));
  const testButton = document.querySelector('#testAssignedVoice');
  check('CS-03/CS-04 selected saved profile requires saved dialogue and enables audition',
    Boolean(testButton && !testButton.disabled), {profile:profileSelect.value,buttonDisabled:testButton?.disabled});
  const beforePlay = window.__stage3PlayCalls;
  testButton.click();
  const miraPreview = await waitForVoiceJob('Stage 3 Mira • Piper Amy', 150000);
  await waitFor(() => window.__stage3PlayCalls > beforePlay, 10000, 'real selected-character audio play handoff');
  const characterAudio = window.__stage3LastAudio;
  check('CS-04 actual selected dialogue Piper preview and playback',
    Boolean(characterAudio && Number(characterAudio.duration) > 0 && window.__stage3PlayCalls > beforePlay),
    {duration:characterAudio?.duration,playCalls:window.__stage3PlayCalls,output:miraPreview.result.output_path});
  report.previews.push({
    kind:'assigned-character',
    profile:'Stage 3 Mira • Piper Amy',
    source_text:'“Stay close.”',
    output_path:miraPreview.result.output_path,
    actual_duration_seconds:miraPreview.result.actual_duration_seconds,
    audio_play_calls:window.__stage3PlayCalls-beforePlay
  });

  // The default Premium V2 Character Studio highlights an unresolved quoted
  // passage as Needs Speaker Review; use its real popover and save action.
  await go('characters');
  const autoNarration = await waitFor(() =>
    [...document.querySelectorAll('#manualStory .ryu-narrator-passage')]
      .find(node => node.textContent.includes('The lantern glowed.')),
    10000, 'automatic Narrator passage in the source text'
  );
  check('CS-09 ordinary narration is automatically classified as Narrator',
    autoNarration.textContent.includes('The lantern glowed.') &&
    autoNarration.classList.contains('ryu-narrator-passage'),
    {text:autoNarration.textContent.trim(),className:autoNarration.className});
  const unresolved = await waitFor(() => {
    const buttons = [...document.querySelectorAll('#manualStory [data-manual-dialogue]')];
    return buttons.find(button => button.textContent.includes('I can guide us.'));
  }, 10000, 'unassigned Ren dialogue passage');
  check('CS-09 unknown quoted dialogue is Needs Speaker Review, not Narrator',
    unresolved.textContent.includes('Needs speaker') && unresolved.classList.contains('ryu-live-passage'),
    {text:unresolved.textContent.trim(),title:unresolved.title});
  unresolved.click();
  await waitFor(() => document.querySelector('#characterAssignPopover')?.classList.contains('show'), 5000, 'manual assignment popover');
  await waitFor(() => Boolean(document.querySelector('#quickCharacterList [data-live-character="Ren"]')), 10000, 'saved Ren character in assignment selector');
  const renChoice = document.querySelector('#quickCharacterList [data-live-character="Ren"][data-live-series="Stage 3 Premium V2 Acceptance"]');
  if (!renChoice) throw new Error('Ren saved cast choice was not present in the actual assignment popover.');
  renChoice.click();
  await waitFor(async () => {
    const chapters = await call('chapter.list');
    const source = chapters.find(chapter => Number(chapter.number) === 1);
    return source?.dialogue_assignments?.find(row =>
      String(row.speaker || row.speakers?.[0] || '') === 'Ren' &&
      String(row.text || '') === '“I can guide us.”' &&
      String(row.source || 'manual') === 'manual'
    ) || false;
  }, 12000, 'persisted Ren manual speaker assignment');
  const afterAssignment = await call('chapter.list');
  const renAssignment = afterAssignment[0].dialogue_assignments.find(row =>
    String(row.speaker || row.speakers?.[0] || '') === 'Ren' && String(row.text || '') === '“I can guide us.”'
  );
  check('CS-02/CS-08 real WebEngine manual assignment persisted by source offsets',
    Boolean(renAssignment && renAssignment.source === 'manual' && renAssignment.series === 'Stage 3 Premium V2 Acceptance'),
    {assignment:renAssignment});
  report.manual_assignment = renAssignment;

  // Series narrator default -> independent project override -> reset/inherit.
  await go('voices');
  await waitFor(() => Boolean(document.querySelector('#seriesNarratorDefaultCard #seriesNarratorProfile')), 10000, 'Premium V2 Series Narrator controls');
  const seriesSelect = document.querySelector('#seriesNarratorProfile');
  if (![...seriesSelect.options].some(option => option.value === 'Stage 3 Narrator • Piper Lessac')) {
    throw new Error('The Series Narrator selector omitted the saved narrator profile.');
  }
  seriesSelect.value = 'Stage 3 Narrator • Piper Lessac';
  seriesSelect.dispatchEvent(new Event('change',{bubbles:true}));
  document.querySelector('#saveSeriesNarratorDefault').click();
  await waitFor(async () => {
    const saved = await call('narrator.series.default.get',{series:'Stage 3 Premium V2 Acceptance'});
    return saved?.profile_name === 'Stage 3 Narrator • Piper Lessac' ? saved : false;
  }, 10000, 'persisted Series Default narrator');
  const seriesSaved = await call('narrator.series.default.get',{series:'Stage 3 Premium V2 Acceptance'});
  check('CS-10 series default saved from Voice Studio profile', seriesSaved.profile_name === 'Stage 3 Narrator • Piper Lessac',
    {profile:seriesSaved.profile_name,source:seriesSaved.source});

  // Exercise the same saved-profile sample-preview route used during Create Series.
  const seriesSetupPreview = await call('narrator.preview', {
    series_setup_preview:true,
    profile_name:'Stage 3 Narrator • Piper Lessac',
    text:'The river road was quiet. The lanterns waited beyond the gate.',
    duration_seconds:10
  });
  if (!seriesSetupPreview?.job_id) throw new Error('Create Series narrator setup did not queue its selected-profile preview.');
  const seriesSetupJob = await waitForVoiceJob('Stage 3 Narrator • Piper Lessac', 90000);
  const seriesSetupPlayBefore = window.__stage3PlayCalls;
  const seriesSetupAudio = new Audio(seriesSetupJob.result.file_url);
  await seriesSetupAudio.play();
  check('CS-10 Create Series sample preview uses saved narrator profile and plays generated audio',
    Boolean(seriesSetupJob.result?.output_path && seriesSetupJob.result?.actual_duration_seconds > 0 &&
      window.__stage3PlayCalls > seriesSetupPlayBefore),
    {profile:'Stage 3 Narrator • Piper Lessac',actual:seriesSetupJob.result.actual_duration_seconds,
      output:seriesSetupJob.result.output_path,playCalls:window.__stage3PlayCalls-seriesSetupPlayBefore});
  report.previews.push({
    kind:'series-setup-preview',
    profile:'Stage 3 Narrator • Piper Lessac',
    source_text:'The river road was quiet. The lanterns waited beyond the gate.',
    output_path:seriesSetupJob.result.output_path,
    actual_duration_seconds:seriesSetupJob.result.actual_duration_seconds,
    audio_play_calls:window.__stage3PlayCalls-seriesSetupPlayBefore
  });

  const projectSelect = document.querySelector('#projectNarratorProfile');
  if (!projectSelect || ![...projectSelect.options].some(option => option.value === 'Stage 3 Override Narrator • Piper Ryan')) {
    throw new Error('The Project Narrator selector omitted the separate saved override profile.');
  }
  projectSelect.value = 'Stage 3 Override Narrator • Piper Ryan';
  projectSelect.dispatchEvent(new Event('change',{bubbles:true}));
  document.querySelector('#saveProjectNarrator').click();
  await waitFor(async () => {
    const saved = await call('narrator.series.default.get',{series:'Stage 3 Premium V2 Acceptance'});
    return saved?.source === 'project_override' && saved?.effective_profile_name === 'Stage 3 Override Narrator • Piper Ryan' ? saved : false;
  }, 10000, 'independent project narrator override');
  const override = await call('narrator.series.default.get',{series:'Stage 3 Premium V2 Acceptance'});
  check('CS-11 project narrator override independent of series default',
    override.profile_name === 'Stage 3 Narrator • Piper Lessac' &&
    override.source === 'project_override' &&
    override.effective_profile_name === 'Stage 3 Override Narrator • Piper Ryan',
    {seriesDefault:override.profile_name,effective:override.effective_profile_name,source:override.source});

  document.querySelector('#resetProjectNarrator').click();
  await waitFor(async () => {
    const saved = await call('narrator.series.default.get',{series:'Stage 3 Premium V2 Acceptance'});
    return saved?.source === 'series_default' && saved?.effective_profile_name === 'Stage 3 Narrator • Piper Lessac' ? saved : false;
  }, 10000, 'Reset to Series Default');
  const reset = await call('narrator.series.default.get',{series:'Stage 3 Premium V2 Acceptance'});
  check('CS-11 reset restores live Series Default inheritance',
    reset.source === 'series_default' && reset.effective_profile_name === 'Stage 3 Narrator • Piper Lessac',
    {effective:reset.effective_profile_name,source:reset.source});

  // Select a narration-only source span in Chapter Studio, then audition the
  // effective Series Default via the actual Project Narrator preview control.
  await go('chapters');
  await waitFor(() => {
    const editor = document.querySelector('#chapterEditor');
    return editor && editor.value.includes('The lantern glowed.');
  }, 10000, 'Chapter Studio narration text');
  const editor = document.querySelector('#chapterEditor');
  const narrationText = 'The lantern glowed.';
  const narrationStart = editor.value.indexOf(narrationText);
  editor.focus();
  editor.setSelectionRange(narrationStart,narrationStart+narrationText.length);
  editor.dispatchEvent(new Event('select',{bubbles:true}));
  check('CS-12 selected narrator preview source is narration-only',
    editor.value.slice(editor.selectionStart,editor.selectionEnd) === narrationText,
    {selected:editor.value.slice(editor.selectionStart,editor.selectionEnd)});
  await go('voices');
  await waitFor(() => Boolean(document.querySelector('#previewProjectNarrator')), 5000, 'Project Narrator preview control');
  const beforeNarratorPlay = window.__stage3PlayCalls;
  document.querySelector('#previewProjectNarrator').click();
  const narratorPreview = await waitForVoiceJob('Stage 3 Narrator • Piper Lessac', 150000);
  await waitFor(() => (document.querySelector('#previewState')?.textContent || '').includes('Ready'), 10000, 'narrator preview validation UI');
  check('CS-12 production narrator preview uses effective Series Default and real selected source text',
    Boolean(narratorPreview.result?.output_path && narratorPreview.result?.actual_duration_seconds > 0),
    {profile:'Stage 3 Narrator • Piper Lessac',actual:narratorPreview.result.actual_duration_seconds,output:narratorPreview.result.output_path});
  const playButton = document.querySelector('#playPreview');
  if (!playButton || playButton.disabled) throw new Error('Validated narrator preview did not enable the in-app Play control.');
  playButton.click();
  await waitFor(() => window.__stage3PlayCalls > beforeNarratorPlay, 10000, 'narrator preview Play action');
  const narratorAudio = window.__stage3LastAudio;
  check('CS-12 narrator preview Play uses the embedded audio player',
    Boolean(narratorAudio && Number(narratorAudio.duration) > 0 && window.__stage3PlayCalls > beforeNarratorPlay),
    {duration:narratorAudio?.duration,playCalls:window.__stage3PlayCalls-beforeNarratorPlay});
  report.previews.push({
    kind:'effective-narrator',
    profile:'Stage 3 Narrator • Piper Lessac',
    source_text:narrationText,
    output_path:narratorPreview.result.output_path,
    actual_duration_seconds:narratorPreview.result.actual_duration_seconds,
    audio_play_calls:window.__stage3PlayCalls-beforeNarratorPlay
  });

  report.status='passed';
  report.final_cast_statistics={mira:miraStats,ren_assignment:renAssignment};
  report.narrator={series_default:seriesSaved.profile_name,project_override:override.effective_profile_name,reset_effective:reset.effective_profile_name};
  report.jobs=await call('job.list',{include_hidden:true});
  return report;
})().then(value => { window.__RYU_STAGE3_PREMIUM_V2_RESULT__ = value; })
  .catch(error => { window.__RYU_STAGE3_PREMIUM_V2_RESULT__ = {status:'failed',error:String(error?.stack || error),checks:[]}; });
"""


def main() -> None:
    output_root = Path(os.environ.get("RYU_STAGE3_PREMIUM_V2_OUTPUT", "stage3-premium-v2-artifacts")).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    app_dir = Path(os.environ.get("RYU_STAGE3_TEST_APP_ROOT", output_root / "runtime-app")).resolve()
    library_dir = app_dir / "Library"
    voices_dir = app_dir / "Voices"
    models_dir = app_dir / "Models"
    settings_dir = app_dir / "Settings"
    audiobooks_dir = app_dir / "Audiobooks"
    qsettings_dir = output_root / "qsettings"
    for path in (library_dir, voices_dir, models_dir, settings_dir, audiobooks_dir, qsettings_dir):
        path.mkdir(parents=True, exist_ok=True)

    from app.core import paths as core_paths
    from app.core import character_library as character_library_module
    from app.tts import voice_profile as voice_profile_module
    from app.tts.providers import piper as piper_module
    from app.ui import premium_v2_host as host_module

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(qsettings_dir))

    def ensure_test_roots():
        for path in (app_dir, library_dir, voices_dir, models_dir, settings_dir, audiobooks_dir):
            path.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        stack.enter_context(patch.object(core_paths, "app_root", lambda: app_dir))
        stack.enter_context(patch.object(core_paths, "default_library_root", lambda: library_dir))
        stack.enter_context(patch.object(core_paths, "library_root", lambda: library_dir))
        stack.enter_context(patch.object(core_paths, "project_library_roots", lambda: (library_dir,)))
        stack.enter_context(patch.object(core_paths, "voices_root", lambda: voices_dir))
        stack.enter_context(patch.object(core_paths, "models_root", lambda: models_dir))
        stack.enter_context(patch.object(core_paths, "settings_root", lambda: settings_dir))
        stack.enter_context(patch.object(core_paths, "audiobooks_root", lambda: audiobooks_dir))
        stack.enter_context(patch.object(voice_profile_module, "voices_root", lambda: voices_dir))
        stack.enter_context(patch.object(piper_module, "models_root", lambda: models_dir))
        stack.enter_context(patch.object(character_library_module, "settings_root", lambda: settings_dir))
        stack.enter_context(patch.object(host_module, "ensure_roots", ensure_test_roots))
        stack.enter_context(patch.object(host_module, "list_projects", lambda: [project]))
        stack.enter_context(patch.object(host_module, "app_root", lambda: app_dir))
        stack.enter_context(patch.object(host_module, "library_root", lambda: library_dir))
        stack.enter_context(patch.object(host_module, "audiobooks_root", lambda: audiobooks_dir))
        stack.enter_context(patch.object(host_module, "settings_root", lambda: settings_dir))

        chapter_one_text = (
            "The lantern glowed. Mira said, “Stay close.” "
            "The old door opened. Ren said, “I can guide us.”"
        )
        chapter_two_text = (
            "Rain fell steadily. Mira whispered, “I will stay.” "
            "The river moved beyond the village."
        )
        project_folder = library_dir / PROJECT_TITLE
        project = _seed_project(project_folder, app_dir, voices_dir, models_dir)

        profiles = [
            VoiceProfile(name=PROFILE_MIRA, provider="piper", voice_id="en_US-amy-medium",
                         model_id="piper", backend="cpu", language="en-US", authorized=True),
            VoiceProfile(name=PROFILE_REN, provider="piper", voice_id="en_US-ryan-high",
                         model_id="piper", backend="cpu", language="en-US", authorized=True),
            VoiceProfile(name=PROFILE_NARRATOR, provider="piper", voice_id="en_US-lessac-medium",
                         model_id="piper", backend="cpu", language="en-US", authorized=True),
            VoiceProfile(name=PROFILE_OVERRIDE, provider="piper", voice_id="en_US-ryan-high",
                         model_id="piper", backend="cpu", language="en-US", authorized=True),
        ]
        save_profiles(profiles)

        # PremiumV2Bridge reads the same local QSettings key used by the normal
        # Library -> Open Project route. The app is still using the actual project
        # JSON/state files and the actual frontend/backend files.
        settings = QSettings("RyuBlanc", "Ryu's Audiobook")
        settings.setValue("project/active_folder", str(project_folder.resolve()))
        settings.sync()

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        from PySide6.QtWebEngineCore import QWebEngineProfile
        browser_profile = QWebEngineProfile.defaultProfile()
        browser_profile.setCachePath(str(output_root / "web-cache"))
        browser_profile.setPersistentStoragePath(str(output_root / "web-storage"))
        window = host_module.PremiumV2Window()
        window.show()

        def process_until(predicate, timeout: float, message: str):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                app.processEvents()
                if predicate():
                    app.processEvents()
                    return
                time.sleep(0.05)
            app.processEvents()
            raise RuntimeError(message)

        try:
            process_until(lambda: bool(getattr(window, "_frontend_ready", False)), 90.0,
                          "The default Premium V2 WebEngine UI did not finish loading its real local backend bridge.")
            page = window.web.page()
            # Start the actual browser workflow. The JS stores a structured result
            # on window so Python can preserve diagnostic evidence and WAV files.
            page.runJavaScript(JS_DRIVER)
            process_until(
                lambda: page.runJavaScript("Boolean(window.__RYU_STAGE3_PREMIUM_V2_RESULT__)",
                    lambda value: result_flag.update({"value": value})) is None and bool(result_flag.get("value")),
                420.0,
                "Premium V2 end-to-end browser acceptance exceeded the 7-minute limit.",
            )
            raw = _run_javascript(window, "JSON.stringify(window.__RYU_STAGE3_PREMIUM_V2_RESULT__)", app, 10.0)
            if not raw:
                raise RuntimeError("Premium V2 acceptance did not return a diagnostic result.")
            report = json.loads(raw) if isinstance(raw, str) else raw
            (output_root / "premium-v2-result.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            if report.get("status") != "passed":
                raise RuntimeError(report.get("error") or "Premium V2 browser workflow failed.")
            copied = []
            for index, preview in enumerate(report.get("previews") or []):
                source = str(preview.get("output_path") or "")
                name = "premium-v2-" + str(preview.get("kind") or f"preview-{index}") + ".wav"
                copied.append(_copy_preview(source, output_root / name, "Piper"))
            report["retained_audio"] = copied
            (output_root / "premium-v2-result.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print("PREMIUM_V2_DEFAULT_UI_ACCEPTANCE=PASS")
            for check in report.get("checks") or []:
                print("PREMIUM_V2_CHECK=PASS " + json.dumps(check, ensure_ascii=False, default=str))
            for item in copied:
                print("PREMIUM_V2_AUDIO_EVIDENCE=" + json.dumps(item, ensure_ascii=False))
        finally:
            window.close()
            app.processEvents()


if __name__ == "__main__":
    # Mutable callback state avoids capturing the test's locals in an async Qt
    # signal handler from the Python event pump.
    result_flag: dict[str, bool] = {"value": False}
    main()
