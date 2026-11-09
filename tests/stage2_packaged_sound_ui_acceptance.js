Warning: truncated output (original token count: 63671)
Total output lines: 3830

(async function () {
  const config = window.__RYU_SOUND_UI_ACCEPTANCE_CONFIG__ || {};
  const checks = {};
  const errors = [];
  const stage8ResponsiveDestinations = [
    "dashboard", "library", "import", "chapters", "voices",
    "characters", "pronunciation", "sound", "generate", "player",
    "history", "models", "performance", "settings", "help"
  ];

  const pauseLabel = "Pause selected track";
  const NativeAudio = window.Audio;
  window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ = [];
  window.Audio = function (src) {
    const audio = new NativeAudio(src);
    window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__.push(audio);
    return audio;
  };
  window.Audio.prototype = NativeAudio.prototype;
  const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));
  function record(name, passed, detail) {
    checks[name] = String(detail || (passed ? "passed" : "failed"));
    if (!passed) errors.push(name + ": " + checks[name]);
  }
  function must(condition, message) {
    if (!condition) throw new Error(message);
  }
  async function waitFor(label, predicate, timeoutMs) {
    const deadline = Date.now() + (timeoutMs || 15000);
    while (Date.now() < deadline) {
      try { if (await predicate()) return true; } catch (_) {}
      await sleep(150);
    }
    throw new Error("Timed out waiting for " + label + ".");
  }
  async function invoke(command, payload) {
    const response = await window.ryuBackend.invoke(command, payload || {});
    if (!response || response.success !== true) {
      throw new Error((response && response.error && response.error.message) || (command + " failed."));
    }
    return response.data;
  }
  function musicButtons() { return Array.from(document.querySelectorAll("#soundTrackGrid [data-select-sound]")); }
  function rowText(button) {
    const row = button && button.closest("article");
    return String(row ? row.textContent : (button && button.parentElement && button.parentElement.parentElement
      ? button.parentElement.parentElement.textContent : ""));
  }
  function findTrackButton(path) {
    return musicButtons().find(button => String(button.dataset.selectSound || "") === String(path || ""));
  }
  function visibleHas(title) { return musicButtons().some(button => rowText(button).includes(title)); }
  function latestAcceptanceAudio() {
    const rows = window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || [];
    return rows.length ? rows[rows.length - 1] : null;
  }
  function audioUsesPath(audio, path) {
    if (!audio || !path) return false;
    const fileName = String(path).replace(/\\/g, "/").split("/").pop().toLowerCase();
    let source = String(audio.currentSrc || audio.src || "").toLowerCase();
    try { source = decodeURIComponent(source); } catch (_) {}
    return Boolean(fileName && source.includes(fileName));
  }
  async function waitForRealPlayback(label, path) {
    let observed = null;
    await waitFor(label, function () {
      observed = latestAcceptanceAudio();
      return Boolean(observed && audioUsesPath(observed, path) &&
        observed.readyState >= 2 && observed.currentTime > 0.05 &&
        !observed.paused && !observed.error);
    }, 12000);
    return observed;
  }
  async function waitForPausedAudio(label, audio) {
    await waitFor(label, function () { return Boolean(audio && audio.paused); }, 5000);
    const pausedAt = Number(audio.currentTime || 0);
    await sleep(300);
    must(audio.paused && Math.abs(Number(audio.currentTime || 0) - pausedAt) <= 0.12,
      label + ": media time continued advancing after Pause.");
    return pausedAt;
  }
  function publish(status) {
    window.__RYU_SOUND_UI_ACCEPTANCE_RESULT__ = {
      status: status, checks: checks, errors: errors, completed_at: new Date().toISOString()
    };
  }

  async function runStage53JobUiAcceptance() {
    const jobId = "stage53-ui-state-job";
    const stage53 = {
      commands: [],
      rows: [{
        job_id: jobId, id: jobId, type: "audiobook-generation",
        title: "Stage 5.3 UI State Acceptance", state: "running",
        progress: 32, stage: "Rendering acceptance chapter",
        project_folder: String(config.project_folder || ""), recoverable: false
      }]
    };
    window.__RYU_STAGE53_JOB_UI_ACCEPTANCE__ = stage53;
    const jobsButton = document.querySelector("#backgroundJobsButton");
    const modal = document.querySelector("#backgroundJobsModal");
    const rowSelector = '[data-backend-job="' + jobId + '"]';
    must(jobsButton && modal, "Background Jobs controls are unavailable in the packaged app.");
    const refreshSyntheticJobs = async state => {
      stage53.rows[0].state = state;
      jobsButton.click();
      await waitFor("Background Jobs " + state + " state", function () {
        const row = document.querySelector(rowSelector);
        const label = row && row.querySelector("[data-job-state]");
        return Boolean(row && label && label.textContent.toLowerCase().startsWith(state));
      }, 12000);
      return document.querySelector(rowSelector);
    };
    const actionNames = row => Array.from(row.querySelectorAll("[data-job-action]"))
      .map(button => String(button.dataset.jobAction || ""));
    let row = await refreshSyntheticJobs("running");
    must(JSON.stringify(actionNames(row)) === JSON.stringify(["pause","cancel"]),
      "Running generation must expose Pause and Cancel only: " + JSON.stringify(actionNames(row)));
    row.querySelector('[data-job-action="pause"]').click();
    await waitFor("Pause request command", () => stage53.commands.some(item => item.command === "job.pause"), 5000);
    row = await refreshSyntheticJobs("pause_requested");
    must(JSON.stringify(actionNames(row)) === JSON.stringify(["cancel"]),
      "A pending pause must not expose a misleading Resume control: " + JSON.stringify(actionNames(row)));
    must(row.textContent.includes("Pausing at the next saved chunk/batch boundary"),
      "Background Jobs must communicate the pending saved chunk/batch pause.");
    row = await refreshSyntheticJobs("paused");
    must(JSON.stringify(actionNames(row)) === JSON.stringify(["resume","cancel"]),
      "Paused generation must expose Resume and Cancel only: " + JSON.stringify(actionNames(row)));
    row.querySelector('[data-job-action="resume"]').click();
    await waitFor("Resume command", () => stage53.commands.some(item => item.command === "job.resume"), 5000);
    row = await refreshSyntheticJobs("running");
    row.querySelector('[data-job-action="cancel"]').click();
    await waitFor("Cancel command", () => stage53.commands.some(item => item.command === "job.cancel"), 5000);
    row = await refreshSyntheticJobs("cancel_requested");
    must(actionNames(row).length === 0 && row.textContent.includes("Cancelling…"),
      "A pending cancellation must show its state and disable further actions.");

    const failedFilter = document.querySelector('[data-job-filter="failed"]');
    must(failedFilter, "Background Jobs failed/cancelled filter is missing.");
    failedFilter.click();
    stage53.rows[0].recoverable = true;
    stage53.rows[0].error = {code:"cancelled"};
    row = await refreshSyntheticJobs("cancelled");
    must(JSON.stringify(actionNames(row)) === JSON.stringify(["retry"]),
      "Cancelled generation must expose Retry only: " + JSON.stringify(actionNames(row)));
    row.querySelector('[data-job-action="retry"]').click();
    await waitFor("Retry command", () => stage53.commands.some(item => item.command === "job.retry"), 5000);

    stage53.rows[0].state = "failed";
    stage53.rows[0].recoverable = true;
    stage53.rows[0].error = {code:"interrupted"};
    row = await refreshSyntheticJobs("failed");
    must(JSON.stringify(actionNames(row)) === JSON.stringify(["recover"]),
      "Interrupted generation must expose Recover only: " + JSON.stringify(actionNames(row)));
    row.querySelector('[data-job-action="recover"]').click();
    await waitFor("Recover command", () => stage53.commands.some(item => item.command === "job.recover"), 5000);
    record("stage54_background_job_retry_recovery_controls", true,
      "Packaged Background Jobs exposes Retry for cancelled generation and Recover for interrupted generation, dispatching job.retry and job.recover.");

    record("stage53_background_job_state_controls", true,
      "Packaged Background Jobs shows mutually exclusive running/pause-pending/paused/cancel-pending controls and dispatches the real bridge command names.");

    const dashboardActiveJobsFilter = modal.querySelector('[data-job-filter="active"]');
    must(dashboardActiveJobsFilter, "Background Jobs Active filter is missing before Dashboard control acceptance.");
    dashboardActiveJobsFilter.click();
    await waitFor("Background Jobs Active filter restored", function () {
      return dashboardActiveJobsFilter.classList.contains("active");
    }, 5000);
    modal.classList.remove("show");
    must(typeof window.go === "function", "Dashboard navigation is unavailable for Stage 5.3 job-state acceptance.");
    window.go("dashboard");
    await waitFor("Dashboard page", function () {
      const page = document.querySelector("#dashboard");
      return Boolean(page && page.classList.contains("active"));
    }, 12000);
    const dashboardControl = () => document.querySelector('#dashboard [data-dashboard-generation-control="1"]');
    const dashboardCases = [
      ["running","Pause",false,"pause"],
      ["pause_requested","Pausing…",true,""],
      ["paused","Resume",false,"resume"],
      ["cancel_requested","Cancelling…",true,""]
    ];
    for (const [state,label,disabled,action] of dashboardCases) {
      await refreshSyntheticJobs(state);
      await waitFor("Dashboard control " + state, function () {
        const control = dashboardControl();
        return Boolean(control && control.textContent.trim() === label);
      }, 12000);
      const control = dashboardControl();
      must(Boolean(control.disabled) === disabled,
        "Dashboard " + state + " control disabled state was incorrect.");
      must(String(control.dataset.dashboardGenerationAction || "") === action,
        "Dashboard " + state + " control advertised an incorrect action.");
    }
    record("stage53_dashboard_job_state_controls", true,
      "Dashboard pause/resume control remains discoverable across polls and accurately shows Pause, Pausing, Resume and Cancelling states.");
    modal.classList.remove("show");
    delete window.__RYU_STAGE53_JOB_UI_ACCEPTANCE__;
    window.go("production");
  }

  try {
    const bridge = window.ryuBackend;
    must(bridge && typeof bridge.invoke === "function", "The native desktop bridge is unavailable.");
    const originalInvoke = bridge.invoke.bind(bridge);
    const originalBootstrap = typeof bridge.bootstrap === "function"
      ? bridge.bootstrap.bind(bridge) : function () { return Promise.resolve({}); };
    const importedMusicCategories = new Set();
    const wrappedBridge = Object.freeze({
      invoke: function (command, payload) {
        const request = Object.assign({}, payload || {});
        if (command === "sound.import" && request.target_kind === "music" &&
            (!Array.isArray(request.paths) || !request.paths.length)) {
          const category = String(request.category || "universal");
          if (category === String(config.expected_category || "fantasy") && !importedMusicCategories.has(category)) {
            request.paths = Array.isArray(config.music_paths) ? config.music_paths.slice() : [];
          } else {
            const fixture = (config.category_imports || []).find(item =>
              String(item.category) === category && !importedMusicCategories.has(category));
            request.paths = fixture && fixture.source_path ? [fixture.source_path] : [];
          }
          if (!request.paths.length) throw new Error("No unused Music Library fixture was configured for category " + category + ".");
          importedMusicCategories.add(category);
        } else if (command === "sound.import" && request.target_kind === "cue" &&
            (!Array.isArray(request.paths) || !request.paths.length)) {
          if (config.reject_long_cue_import === true) {
            config.reject_long_cue_import = false;
            request.paths = [String(config.long_cue_path || "")];
          } else {
            request.paths = Array.isArray(config.cue_import_paths) ? config.cue_import_paths.slice() : [];
          }
          if (!request.paths.length || !request.paths[0]) throw new Error("No generated cue fixture paths were provided.");
        }
        if (command === "sound.cues.save" && config.reject_next_cue_save === true) {
          config.reject_next_cue_save = false;
          return Promise.resolve({success:false,error:{message:"Deterministic packaged-acceptance cue-save failure."}});
        }
        if (command === "sound.save_manifest" && config.fail_next_manifest_save === true) {
          config.fail_next_manifest_save = false;
          return Promise.resolve({success:false,error:{message:"Deterministic packaged-acceptance manifest-save failure."}});
        }
        if (command === "project.metadata.save" && config.fail_next_metadata_save === true) {
          config.fail_next_metadata_save = false;
          return Promise.resolve({success:false,error:{message:"Deterministic packaged-acceptance metadata-save failure."}});
        }
        const stage53Ui = window.__RYU_STAGE53_JOB_UI_ACCEPTANCE__;
        if (stage53Ui && command === "job.list") {
          return Promise.resolve({success:true,data:stage53Ui.rows});
        }
        if (stage53Ui && ["job.pause","job.resume","job.cancel","job.retry","job.recover"].includes(command)) {
          stage53Ui.commands.push({command:command,payload:request});
          const nextState = {
            "job.pause":"pause_requested", "job.resume":"running",
            "job.cancel":"cancel_requested", "job.retry":"running",
            "job.recover":"running"
          }[command];
          const owned = stage53Ui.rows.find(row => String(row.job_id || "") === String(request.job_id || ""));
          if (owned) owned.state = nextState;
          return Promise.resolve({success:true,data:{job_id:request.job_id,state:nextState}});
        }
        const result = originalInvoke(command, request);
        if (command === "sound.preview_book") {
          return Promise.resolve(result).then(response => {
            if (response && response.success === true && response.data && response.data.job_id) {
              window.__RYU_SOUND_UI_ACCEPTANCE_PREVIEW_JOB_ID__ = response.data.job_id;
            }
            return response;
          });
        }
        return result;
      },
      bootstrap: originalBootstrap
    });
    Object.defineProperty(window, "ryuBackend", {
      configurable: true, enumerable: true, writable: true, value: wrappedBridge
    });
    record("native_bridge", true, "Real Qt WebChannel bridge connected; the UI import action delegates to the native backend.");

    if (config.phase === "restart") {
      const persistedProject = await invoke("project.get_active", {});
      const expectedMetadata = config.metadata || {};
      must(persistedProject && String(persistedProject.folder || "") === String(config.project_folder || ""),
        "The active project identity was not restored after application restart.");
      must(String(persistedProject.title || "") === String(expectedMetadata.title || "") &&
        String(persistedProject.author || "") === String(expectedMetadata.author || "") &&
        String(persistedProject.publisher || "") === String(expectedMetadata.publisher || "") &&
        String(persistedProject.series || "") === String(expectedMetadata.series || "") &&
        String(persistedProject.series_volume || "") === String(expectedMetadata.series_volume || "") &&
        String(persistedProject.language || "") === String(expectedMetadata.language || "") &&
        String(persistedProject.year || "") === String(expectedMetadata.year || "") &&
        String(persistedProject.genre || "") === String(expectedMetadata.genre || ""),
        "Production metadata was not restored from the saved project after application restart.");
      const normalizedCoverPath = String(persistedProject.cover_path || "")
        .split(String.fromCharCode(92)).join("/").toLowerCase();
      must(normalizedCoverPath.endsWith("/assets/cover.png"),
        "The project-local PNG cover was not resolved after application restart.");
      must(String(persistedProject.narrator || "") === String(config.narrator_profile_name || ""),
        "The selected Voice Studio narrator profile was not restored after application restart.");
      record("production_metadata_application_restart", true,
        "Book metadata, project-local cover and the selected Voice Studio narrator profile were reloaded by a new frozen-app process.");

      // AB-06: prove the position survives an actual frozen-app process restart.
      const stage6RestartFixture = (config.audiobook_library_fixtures || [])[0];
      must(stage6RestartFixture && stage6RestartFixture.folder,
        "The Stage 6 audiobook fixture is unavailable to the restarted process.");
      const [stage6PersistedPlayer,stage6PersistedSettings] = await Promise.all([
        invoke("player.get_active", {folder:stage6RestartFixture.folder}),
        invoke("settings.get", {})
      ]);
      must(Math.abs(Number(stage6PersistedPlayer.playback_position_seconds) - 1.25) < 0.35,
        "The audiobook playback position was not retained in project state after the app restarted.");
      must(Math.abs(Number(stage6PersistedPlayer.playback_rate) - 1.25) < 0.01 &&
        Math.abs(Number(stage6PersistedPlayer.playback_volume) - 0.42) < 0.01 &&
        Math.abs(Number(stage6PersistedSettings.player_rate) - 1.25) < 0.01 &&
        Math.abs(Number(stage6PersistedSettings.player_volume) - 0.42) < 0.01,
        "Global player settings did not survive restart: " +
          JSON.stringify({player:stage6PersistedPlayer,settings:stage6PersistedSettings}));
      window.go("player");
      await waitFor("Audiobooks page restored in the second process", () =>
        document.querySelector("#player")?.classList.contains("active") === true, 12000);
      const stage6RestartCard = Array.from(document.querySelectorAll("#backendAudiobookLibrary .audiobook-library-card"))
        .find(card => String(card.dataset.projectFolder || "") === String(stage6RestartFixture.folder || ""));
      must(stage6RestartCard, "The previously selected audiobook is missing after process restart.");
      stage6RestartCard.querySelector("[data-open-project-folder]").click();
      await waitFor("actual decoded audio restores the saved position", () => {
        const audio = latestAcceptanceAudio();
        return Boolean(audio && String(audio.dataset.projectFolder || "") === String(stage6RestartFixture.folder || "") &&
          audio.readyState >= 1 && Math.abs(Number(audio.currentTime) - 1.25) < 0.35);
      }, 18000);
      const stage6RestoredAudio = latestAcceptanceAudio();
      const stage6RestoreDiagnostics = {
        expectedVolume:Number(stage6PersistedPlayer.playback_volume),
        actualVolume:Number(stage6RestoredAudio.volume),
        expectedRate:Number(stage6PersistedPlayer.playback_rate),
        actualRate:Number(stage6RestoredAudio.playbackRate)
      };
      must(Math.abs(stage6RestoreDiagnostics.actualVolume-stage6RestoreDiagnostics.expectedVolume) < 0.02 &&
        Math.abs(stage6RestoreDiagnostics.actualRate-stage6RestoreDiagnostics.expectedRate) < 0.02,
        "The restored player did not apply saved volume/rate to real audio: " + JSON.stringify(stage6RestoreDiagnostics));
      record("stage6_playback_position_restored_after_process_restart", true,
        "A second frozen-app process restored the correct audiobook and sought real decoded audio to its saved timestamp.");

      // The mini-player remains the same media session after restart and navigation.
      await stage6RestoredAudio.play();
      window.go("dashboard");
      const stage6RestoredMini = document.querySelector("#miniPlayer");
      await waitFor("restored mini-player is available after navigation", () =>
        Boolean(stage6RestoredMini && !stage6RestoredMini.classList.contains("hidden") &&
          stage6RestoredMini.getClientRects().length), 8000);
      const stage6RestoredMiniPlay = stage6RestoredMini.querySelector("#miniPlay");
      must(stage6RestoredMiniPlay, "The restored mini-player has no Play/Pause control.");
      const stage6RestartAudioCount = (window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || []).length;
      stage6RestoredMiniPlay.click();
      await waitFor("restored mini-player pauses the same audio object", () =>
        stage6RestoredAudio.paused && stage6RestoredMiniPlay.textContent.trim() === "▶", 5000);
      stage6RestoredMiniPlay.click();
      await waitFor("restored mini-player resumes the same audio object", () =>
        !stage6RestoredAudio.paused && stage6RestoredMiniPlay.textContent.trim() !== "▶", 5000);
      must(latestAcceptanceAudio() === stage6RestoredAudio &&
        (window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || []).length === stage6RestartAudioCount,
        "The mini-player created a duplicate playback instance after process restart.");
      document.querySelector("#hideMini")?.click();
      await waitFor("restored mini-player close hides the dock", () =>
        stage6RestoredMini.classList.contains("hidden"), 5000);
      must(!stage6RestoredAudio.paused && latestAcceptanceAudio() === stage6RestoredAudio,
        "Closing the restored mini-player interrupted playback.");
      stage6RestoredAudio.pause();
      record("stage6_mini_player_navigation_and_close_after_restart", true,
        "After restart, mini-player Play/Pause controlled the restored media object and closing its dock did not stop playback.");

      const catalogue = await invoke("sound.catalog", {});
      const saved = await invoke("sound.chapter_bgm.get", {});
      const cues = await invoke("sound.cues.get", {});
      const expectedMusicPaths = (config.track_paths || []).concat((config.category_imports || []).map(item => item.path));
      const missingTracks = expectedMusicPaths.filter(path =>
        !Array.isArray(catalogue) || !catalogue.some(track => String(track.path || "") === String(path) &&
          String(track.role || "").toLowerCase() === "music"));
      must(missingTracks.length === 0, "Imported Music Library files disappeared after app restart: " + missingTracks.join(", "));
      must(saved && saved.strategy === "custom" && Array.isArray(saved.chapters) && saved.chapters.length === 3,
        "Chapter-Based strategy or three chapter records were not restored after restart.");
      must(String(saved.default_path || "") === String(config.track_paths[0]),
        "The saved book-default preference was not retained for switching back to Same BGM.");
      must(saved.bgm_enabled === true &&
        Math.abs(Number(saved.default_volume) - 0.42) < 0.005 &&
        Math.abs(Number(saved.narration_volume) - 0.82) < 0.005 &&
        Math.abs(Number(saved.cue_volume) - 0.30) < 0.005,
        "BGM, narration or cue levels changed across the application restart.");
      const overrides = saved.overrides || {};
      must(overrides["1"] && overrides["1"].rule === "custom" &&
        String(overrides["1"].path || "") === String(config.track_paths[0]) &&
        Math.abs(Number(overrides["1"].volume) - 0.37) < 0.005 &&
        overrides["1"].start_offset === "after_first_paragraph" &&
…51671 tokens truncated…= await invoke("player.get_active", {folder:secondFixture.folder});
    must(firstOpenedAudio.paused &&
      normalizeOutputPath(secondOpenedData.output_path) === normalizeOutputPath(secondFixture.output_path) &&
      String(secondOpenedData.title || "") === secondFixture.title &&
      String(secondOpenedData.author || "") === secondFixture.author &&
      String(secondOpenedData.narrator || "") === secondFixture.narrator,
      "Switching audiobook left stale audio or cross-associated metadata/output.");
    record("stage6_audiobooks_switch_preserves_project_output_identity", true,
      "Switching books paused the previous audio and loaded the second book's own M4B, cover and metadata without leaking the first project's identity.");

    // AB-06: persist a measured position from real decoded audio before process exit.
    const stage6PositionCard = Array.from(document.querySelectorAll("#backendAudiobookLibrary .audiobook-library-card"))
      .find(card => String(card.dataset.projectFolder || "") === String(firstFixture.folder || ""));
    must(stage6PositionCard, "The first audiobook card is unavailable for playback-position acceptance.");
    stage6PositionCard.querySelector("[data-open-project-folder]").click();
    await waitFor("Stage 6 position fixture opens paused", () => {
      const audio = latestAcceptanceAudio();
      return Boolean(audio && String(audio.dataset.projectFolder || "") === String(firstFixture.folder || "") &&
        audio.readyState >= 1 && audio.paused);
    }, 15000);
    const stage6PositionAudio = latestAcceptanceAudio();
    const stage6SpeedButton = Array.from(document.querySelectorAll("#player .player-grid .toolbar .segmented button"))
      .find(button => button.textContent.trim() === "1.25×");
    must(stage6SpeedButton, "The player speed control does not expose 1.25×.");
    stage6SpeedButton.click();
    const stage6VolumeControl = document.querySelector("#player .player-grid .toolbar input.range");
    must(stage6VolumeControl, "The player volume control is unavailable.");
    stage6VolumeControl.value = "42";
    stage6VolumeControl.dispatchEvent(new Event("input",{bubbles:true}));
    stage6VolumeControl.dispatchEvent(new Event("change",{bubbles:true}));
    await waitFor("actual player controls persist 1.25× and 42% preferences", async () => {
      const [settings, player] = await Promise.all([
        invoke("settings.get", {}),
        invoke("player.get_active", {folder:firstFixture.folder})
      ]);
      return Math.abs(Number(settings.player_rate)-1.25) < 0.01 &&
        Math.abs(Number(settings.player_volume)-0.42) < 0.01 &&
        Math.abs(Number(player.playback_rate)-1.25) < 0.01 &&
        Math.abs(Number(player.playback_volume)-0.42) < 0.01 &&
        Math.abs(Number(stage6PositionAudio.playbackRate)-1.25) < 0.01 &&
        Math.abs(Number(stage6PositionAudio.volume)-0.42) < 0.02;
    }, 12000);
    record("stage6_player_volume_rate_persisted_before_restart", true,
      "Real player speed and volume controls saved 1.25× and 42%; native Settings and player read-back acknowledged them.");

    const stage6TargetPosition = 1.25;
    must(Number(stage6PositionAudio.duration) > stage6TargetPosition + 1,
      "The Stage 6 playback-position fixture is too short for a reliable restart assertion.");
    stage6PositionAudio.currentTime = stage6TargetPosition;
    await stage6PositionAudio.play();
    await waitFor("position fixture has actually started", () => !stage6PositionAudio.paused, 5000);
    stage6PositionAudio.pause();
    let stage6SavedPlayer = null;
    await waitFor("pause saves playback position to project state", async () => {
      stage6SavedPlayer = await invoke("player.get_active", {folder:firstFixture.folder});
      return Math.abs(Number(stage6SavedPlayer.playback_position_seconds) - stage6TargetPosition) < 0.35;
    }, 12000);
    record("stage6_playback_position_persisted_before_process_restart", true,
      "Pause on the real decoded audiobook persisted its measured timestamp to the selected audiobook's own project state.");

    // AB-05: the mini-player must operate the same Audio object and close only its dock.
    await stage6PositionAudio.play();
    window.go("dashboard");
    const stage6PositionMini = document.querySelector("#miniPlayer");
    await waitFor("mini-player appears after navigation", () =>
      Boolean(stage6PositionMini && !stage6PositionMini.classList.contains("hidden") &&
        stage6PositionMini.getClientRects().length), 8000);
    const stage6PositionMiniPlay = stage6PositionMini.querySelector("#miniPlay");
    must(stage6PositionMiniPlay, "The persistent mini-player Play/Pause control is missing.");
    const stage6AudioCount = (window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || []).length;
    stage6PositionMiniPlay.click();
    await waitFor("mini-player pauses the same audiobook", () =>
      stage6PositionAudio.paused && stage6PositionMiniPlay.textContent.trim() === "▶", 5000);
    stage6PositionMiniPlay.click();
    await waitFor("mini-player resumes the same audiobook", () =>
      !stage6PositionAudio.paused && stage6PositionMiniPlay.textContent.trim() !== "▶", 5000);
    must(latestAcceptanceAudio() === stage6PositionAudio &&
      (window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || []).length === stage6AudioCount,
      "Mini-player created a duplicate audio session or changed audiobook identity.");
    document.querySelector("#hideMini")?.click();
    await waitFor("manual mini-player close hides only the dock", () =>
      stage6PositionMini.classList.contains("hidden"), 5000);
    must(!stage6PositionAudio.paused && latestAcceptanceAudio() === stage6PositionAudio,
      "Closing the mini-player stopped playback or replaced the active audiobook.");
    record("stage6_mini_player_close_preserves_active_session", true,
      "Closing the mini-player hid the dock but preserved the active audiobook and its media session.");
    stage6PositionAudio.currentTime = stage6TargetPosition;
    stage6PositionAudio.pause();
    await waitFor("position is durably saved before process exit", async () => {
      stage6SavedPlayer = await invoke("player.get_active", {folder:firstFixture.folder});
      return Math.abs(Number(stage6SavedPlayer.playback_position_seconds) - stage6TargetPosition) < 0.35;
    }, 12000);

    window.go("dashboard");
    await waitFor("Dashboard restored after Stage 5.5 Audiobooks acceptance", function () {
      const page = document.querySelector("#dashboard");
      return Boolean(page && page.classList.contains("active"));
    }, 15000);
    await openProjectFromDashboard(config.project_folder, "Primary");
    await waitFor("Primary preview project restored after full-generation acceptance", async function () {
      const active = await invoke("project.get_active", {});
      const soundState = await invoke("sound.chapter_bgm.get", {});
      return String(active.folder || "") === String(config.project_folder || "") &&
        Array.isArray(soundState.chapters) && soundState.chapters.length === 3;
    }, 20000);

    await runStage53JobUiAcceptance();

    // Stage 5.4 installed-app job controls: use a real saved project and the
    // actual Background Jobs buttons. No fake job.list or command interception
    // is enabled in this portion of the acceptance.
    await openProjectFromDashboard(config.control_project_folder, "Stage 5.4 job controls");
    await waitFor("Stage 5.4 job-control project activation", async function () {
      const active = await invoke("project.get_active", {});
      return String(active.folder || "") === String(config.control_project_folder || "");
    }, 20000);
    const selectedControlNarrator = await invoke("voice.select", {
      profile_name:narratorProfileName, backend:"automatic"
    });
    must(selectedControlNarrator && selectedControlNarrator.saved === true &&
      String(selectedControlNarrator.name || "") === narratorProfileName,
      "The Stage 5.4 job-control project could not persist the saved Offline Neural narrator.");
    window.go("generate");
    await waitFor("Stage 5.4 Production job-control page", function () {
      return document.querySelector("#generate")?.classList.contains("active") === true &&
        Boolean(document.querySelector("#startGenerate"));
    }, 20000);
    await waitFor("Stage 5.4 job-control metadata gate", function () {
      const button = document.querySelector("#startGenerate");
      return Boolean(button && !button.disabled);
    }, 20000);

    const jobsBeforeControlGeneration = await invoke("job.list", {include_hidden:true});
    const previousControlIds = new Set((Array.isArray(jobsBeforeControlGeneration) ? jobsBeforeControlGeneration : [])
      .filter(job => job.type === "audiobook-generation" &&
        String(job.project_folder || "") === String(config.control_project_folder || ""))
      .map(job => String(job.job_id || "")));
    const controlGenerateButton = document.querySelector("#startGenerate");
    const controlPreflight = {
      project: await invoke("project.get_active", {}),
      narrator: await invoke("voice.select.get", {}).catch(error => ({error:String(error)})),
      readiness: await invoke("production.readiness", {}).catch(error => ({error:String(error)})),
      button: controlGenerateButton ? {
        disabled: controlGenerateButton.disabled,
        title: controlGenerateButton.title,
        text: controlGenerateButton.textContent.trim(),
        ariaDisabled: controlGenerateButton.getAttribute("aria-disabled")
      } : null
    };
    let controlStartResponse = null;
    if (!controlGenerateButton) throw new Error("Stage 5.4 Start button disappeared before the real generation click.");
    controlGenerateButton.click();
    let controlJobId = "";
    const readJob = async jobId => {
      const rows = await invoke("job.list", {include_hidden:true});
      return Array.isArray(rows) ? rows.find(item => String(item.job_id || "") === String(jobId || "")) : null;
    };
    try {
      await waitFor("real Stage 5.4 control generation start", async function () {
        const rows = await invoke("job.list", {include_hidden:true});
        const job = Array.isArray(rows) ? rows.find(item =>
          item.type === "audiobook-generation" &&
          String(item.project_folder || "") === String(config.control_project_folder || "") &&
          !previousControlIds.has(String(item.job_id || "")) &&
          Boolean(item.job_id)) : null;
        if (!job) return false;
        controlJobId = String(job.job_id);
        return true;
      }, 30000);
    } catch (startError) {
      const activeAfterClick = await invoke("project.get_active", {}).catch(error => ({error:String(error)}));
      const jobsAfterClick = await invoke("job.list", {include_hidden:true}).catch(error => ({error:String(error)}));
      const generateStatus = document.querySelector("#generateStatus");
      const statusText = document.querySelector("#generationStatus");
      const diagnostic = {
        preflight: controlPreflight,
        activeAfterClick,
        startResponse: controlStartResponse,
        generateStatus: generateStatus ? generateStatus.textContent.trim() : null,
        generationStatus: statusText ? statusText.textContent.trim() : null,
        button: controlGenerateButton ? {
          disabled: controlGenerateButton.disabled,
          title: controlGenerateButton.title,
          text: controlGenerateButton.textContent.trim(),
          ariaDisabled: controlGenerateButton.getAttribute("aria-disabled")
        } : null,
        jobsAfterClick
      };
      throw new Error(String(startError?.message || startError) +
        ". Stage 5.4 start diagnostic=" + JSON.stringify(diagnostic));
    }

    const jobsButton = document.querySelector("#backgroundJobsButton");
    const jobsModal = document.querySelector("#backgroundJobsModal");
    must(jobsButton && jobsModal, "Installed Background Jobs controls are unavailable.");
    if (!jobsModal.classList.contains("show")) jobsButton.click();
    const activeJobsFilter = jobsModal.querySelector('[data-job-filter="active"]');
    if (activeJobsFilter) activeJobsFilter.click();
    const controlRowSelector = '[data-backend-job="' + controlJobId + '"]';
    await waitFor("real control job appears in Background Jobs", function () {
      return Boolean(document.querySelector(controlRowSelector));
    }, 15000);
    await waitFor("real control job exposes Pause", async function () {
      const job = await readJob(controlJobId);
      const row = document.querySelector(controlRowSelector);
      return Boolean(job && job.state === "running" && row &&
        row.querySelector('[data-job-action="pause"]'));
    }, 90000);
    document.querySelector(controlRowSelector).querySelector('[data-job-action="pause"]').click();
    await waitFor("native GenerationManager reaches persisted paused state", async function () {
      const job = await readJob(controlJobId);
      return Boolean(job && job.state === "paused");
    }, 120000);
    await waitFor("Background Jobs exposes Resume for the paused native job", function () {
      const row = document.querySelector(controlRowSelector);
      return Boolean(row && row.querySelector('[data-job-action="resume"]'));
    }, 20000);
    document.querySelector(controlRowSelector).querySelector('[data-job-action="resume"]').click();
    await waitFor("native GenerationManager resumes the real job", async function () {
      const job = await readJob(controlJobId);
      return Boolean(job && job.state === "running");
    }, 20000);
    await waitFor("Background Jobs exposes Cancel after Resume", function () {
      const row = document.querySelector(controlRowSelector);
      return Boolean(row && row.querySelector('[data-job-action="cancel"]'));
    }, 15000);
    document.querySelector(controlRowSelector).querySelector('[data-job-action="cancel"]').click();
    await waitFor("native GenerationManager reaches cancelled terminal state", async function () {
      const job = await readJob(controlJobId);
      return Boolean(job && job.state === "cancelled");
    }, 90000);
    const cancelledControlJob = await readJob(controlJobId);
    must(cancelledControlJob && cancelledControlJob.state === "cancelled",
      "The installed Cancel button did not cancel the actual full-generation job.");
    record("stage54_real_generation_pause_resume_cancel", true,
      "The installed Background Jobs Pause, Resume and Cancel buttons controlled a real saved-project GenerationManager job at persisted chunk checkpoints.");

    const failedJobsFilter = jobsModal.querySelector('[data-job-filter="failed"]');
    must(failedJobsFilter, "Background Jobs failed/cancelled filter is missing.");
    failedJobsFilter.click();
    await waitFor("cancelled real generation job exposes Retry", function () {
      const row = document.querySelector(controlRowSelector);
      return Boolean(row && row.querySelector('[data-job-action="retry"]'));
    }, 20000);
    document.querySelector(controlRowSelector).querySelector('[data-job-action="retry"]').click();
    let retriedControlJobId = "";
    await waitFor("native Retry creates a linked generation attempt", async function () {
      const rows = await invoke("job.list", {include_hidden:true});
      const job = Array.isArray(rows) ? rows.find(item =>
        item.type === "audiobook-generation" &&
        String(item.project_folder || "") === String(config.control_project_folder || "") &&
        String(item.retry_of_job_id || "") === controlJobId &&
        Boolean(item.job_id)) : null;
      if (!job) return false;
      retriedControlJobId = String(job.job_id);
      return true;
    }, 30000);
    let retriedControlJob = null;
    await waitFor("real retried generation completes", async function () {
      retriedControlJob = await readJob(retriedControlJobId);
      if (!retriedControlJob) return false;
      const state = String(retriedControlJob.state || "").toLowerCase();
      if (state === "failed" || state === "cancelled") {
        throw new Error("The real generation Retry ended " + state + ": " +
          String(retriedControlJob.error?.message || retriedControlJob.message || ""));
      }
      return state === "completed";
    }, 360000);
    const controlHistory = await invoke("history.list", {});
    const controlHistoryRow = Array.isArray(controlHistory)
      ? controlHistory.find(item => String(item.job_id || "") === retriedControlJobId) : null;
    const controlProjectSummary = await invoke("project.get_active", {});
    const normalizeControlOutput = value => String(value || "").replace(/\\/g, "/").toLowerCase();
    const expectedControlOutput = normalizeControlOutput(config.control_output_path);
    must(retriedControlJob.state === "completed" &&
      String(retriedControlJob.retry_of_job_id || "") === controlJobId &&
      normalizeControlOutput(retriedControlJob.output_path) === expectedControlOutput,
      "The completed retry is not linked to the cancelled source job and expected M4B output.");
    must(controlHistoryRow && controlHistoryRow.state === "completed" &&
      String(controlHistoryRow.project_folder || "") === String(config.control_project_folder || "") &&
      normalizeControlOutput(controlHistoryRow.output_path) === expectedControlOutput,
      "History did not preserve the retried job's original project/output identity.");
    must(String(controlProjectSummary.folder || "") === String(config.control_project_folder || "") &&
      controlProjectSummary.completed === true &&
      normalizeControlOutput(controlProjectSummary.output_path) === expectedControlOutput,
      "The retried output is not attached to the original project summary.");
    record("stage54_real_generation_retry_and_history_ownership", true,
      "The installed Retry action restarted the original project from compatible checkpoints and unified the new job, History and output ownership.");
    jobsModal.classList.remove("show");
    window.go("dashboard");
    await waitFor("Dashboard readiness flow updates for retried project", async function () {
      const active = await invoke("project.get_active", {});
      const stages = Array.from(document.querySelectorAll(".production-flow .flow-stage"));
      const finalStage = stages[stages.length - 1];
      const detail = finalStage?.querySelector(".flow-copy small");
      return String(active.folder || "") === String(config.control_project_folder || "") &&
        active.completed === true &&
        Boolean(finalStage && finalStage.dataset.projectReady === "true" &&
          String(detail?.textContent || "").includes("Audiobook ready"));
    }, 20000);
    const readinessProject = await invoke("project.get_active", {});
    const readinessLabel = document.querySelector(".production-flow .flow-readiness span")?.textContent || "";
    must(readinessProject.completed === true &&
      String(readinessProject.status || "").toLowerCase() === "completed" &&
      String(readinessLabel).includes("stages ready"),
      "Dashboard production readiness did not reflect the completed retried audiobook.");
    record("stage54_real_readiness_and_dashboard_ownership", true,
      "Dashboard's live seven-stage production-readiness flow reported the retried project as Audiobook ready using the same completed project identity.");

    // Now leave a real job paused at a persisted chunk checkpoint. The runner
    // exits this frozen app process immediately after this marker; the next
    // process must classify the durable paused job as interrupted and recover it.
    await openProjectFromDashboard(config.recovery_project_folder, "Stage 5.4 restart recovery");
    await waitFor("Stage 5.4 restart-recovery project activation", async function () {
      const active = await invoke("project.get_active", {});
      return String(active.folder || "") === String(config.recovery_project_folder || "");
    }, 20000);
    const selectedRecoveryNarrator = await invoke("voice.select", {
      profile_name:narratorProfileName, backend:"automatic"
    });
    must(selectedRecoveryNarrator && selectedRecoveryNarrator.saved === true &&
      String(selectedRecoveryNarrator.name || "") === narratorProfileName,
      "The restart-recovery project could not persist the saved Offline Neural narrator.");
    window.go("generate");
    await waitFor("Stage 5.4 restart-recovery Production page", function () {
      return document.querySelector("#generate")?.classList.contains("active") === true &&
        Boolean(document.querySelector("#startGenerate"));
    }, 20000);
    await waitFor("Stage 5.4 restart-recovery metadata gate", function () {
      const button = document.querySelector("#startGenerate");
      return Boolean(button && !button.disabled);
    }, 20000);
    const jobsBeforeRecoveryStage = await invoke("job.list", {include_hidden:true});
    const previousRecoveryIds = new Set((Array.isArray(jobsBeforeRecoveryStage) ? jobsBeforeRecoveryStage : [])
      .filter(job => job.type === "audiobook-generation" &&
        String(job.project_folder || "") === String(config.recovery_project_folder || ""))
      .map(job => String(job.job_id || "")));
    document.querySelector("#startGenerate").click();
    let interruptedSourceJobId = "";
    await waitFor("real restart-recovery generation start", async function () {
      const rows = await invoke("job.list", {include_hidden:true});
      const job = Array.isArray(rows) ? rows.find(item =>
        item.type === "audiobook-generation" &&
        String(item.project_folder || "") === String(config.recovery_project_folder || "") &&
        !previousRecoveryIds.has(String(item.job_id || "")) &&
        Boolean(item.job_id)) : null;
      if (!job) return false;
      interruptedSourceJobId = String(job.job_id);
      return true;
    }, 30000);
    if (!jobsModal.classList.contains("show")) jobsButton.click();
    const activeFilterForRecovery = jobsModal.querySelector('[data-job-filter="active"]');
    if (activeFilterForRecovery) activeFilterForRecovery.click();
    const recoveryRowSelector = '[data-backend-job="' + interruptedSourceJobId + '"]';
    await waitFor("restart-recovery job appears as a real active row", function () {
      return Boolean(document.querySelector(recoveryRowSelector));
    }, 15000);
    await waitFor("restart-recovery job exposes safe Pause", function () {
      const row = document.querySelector(recoveryRowSelector);
      return Boolean(row && row.querySelector('[data-job-action="pause"]'));
    }, 60000);
    document.querySelector(recoveryRowSelector).querySelector('[data-job-action="pause"]').click();
    await waitFor("restart-recovery generation pauses at a saved chunk", async function () {
      const job = await readJob(interruptedSourceJobId);
      return Boolean(job && job.state === "paused");
    }, 120000);
    jobsModal.classList.remove("show");
    await openProjectFromDashboard(config.project_folder, "Primary");
    await waitFor("Primary project restored before forced app restart", async function () {
      const active = await invoke("project.get_active", {});
      return String(active.folder || "") === String(config.project_folder || "");
    }, 20000);
    record("stage54_real_restart_interruption_staged", true,
      "A real saved-project GenerationManager job was paused at a committed chunk checkpoint and left durable for the next frozen-app process to recover.");
    publish("passed");
  } catch (error) {
    errors.push(String(error && error.stack || error));
    publish("failed");
  }
})();

