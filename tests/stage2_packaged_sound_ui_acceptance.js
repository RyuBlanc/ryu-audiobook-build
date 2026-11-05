(async function () {
  const config = window.__RYU_SOUND_UI_ACCEPTANCE_CONFIG__ || {};
  const checks = {};
  const errors = [];
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
        overrides["1"].end_behavior === "continue_to_transition",
        "Chapter One's track, volume, paragraph offset or end policy was not restored.");
      must(overrides["2"] && overrides["2"].rule === "custom" &&
        String(overrides["2"].path || "") === String(config.track_paths[1]) &&
        Math.abs(Number(overrides["2"].volume) - 0.29) < 0.005 &&
        overrides["2"].start_offset === "after_10_seconds" &&
        overrides["2"].end_behavior === "stop_immediately",
        "Chapter Two's track, volume, start offset or end policy was not restored.");
      must(overrides["3"] && overrides["3"].rule === "none",
        "Chapter Three's explicit No BGM rule was not restored.");
      const expectedCueSlots = {
        opening: String(config.cue_paths[1]),
        chapter: String(config.cue_paths[1]),
        closing: String(config.cue_paths[0])
      };
      const cueCatalogue = Array.isArray(catalogue)
        ? catalogue.filter(track => String(track.role || "").toLowerCase() === "cue")
        : [];
      const cuesRestored = Object.entries(expectedCueSlots).every(([slot, expectedPath]) =>
        String(cues[slot] && cues[slot].path || "") === expectedPath &&
        cues[slot].available === true && cues[slot].assigned === true && cues[slot].missing === false);
      must(cuesRestored,
        "Opening, Next Chapter or Closing cue assignments/assets were not restored. " +
        JSON.stringify({actual:cues, expected:expectedCueSlots,
          cue_catalogue:cueCatalogue.map(track => ({path:track.path, role:track.role, title:track.title}))}));
      record("application_restart_music_library_persistence", true, "All imported Music Library assets and categories remained available after a new frozen-app process.");
      record("application_restart_chapter_bgm_persistence", true, "Strategy, default preference, assignments, No BGM, offsets, end policies and chapter volume survived restart.");
      record("application_restart_mix_and_cue_persistence", true, "Narration/BGM/cue levels and all three cue slots survived restart.");

      // This process must discover the paused job left by the previous frozen
      // app process. Durable-job startup reconciliation marks it interrupted;
      // Recover must then pass through the actual Background Jobs UI/native bridge.
      const durableJobsAfterRestart = await invoke("job.list", {include_hidden:true});
      const interruptedSourceJob = Array.isArray(durableJobsAfterRestart)
        ? durableJobsAfterRestart.find(item =>
            item.type === "audiobook-generation" &&
            String(item.project_folder || "") === String(config.recovery_project_folder || "") &&
            String(item.state || "").toLowerCase() === "failed" &&
            item.recoverable === true &&
            String(item.error?.code || "").toLowerCase() === "interrupted")
        : null;
      must(interruptedSourceJob && interruptedSourceJob.job_id,
        "The second frozen-app process did not reconcile the saved paused generation as an interrupted recoverable job: " +
          JSON.stringify(interruptedSourceJob || durableJobsAfterRestart));
      const recoverySourceJobId = String(interruptedSourceJob.job_id);
      const jobsButton = document.querySelector("#backgroundJobsButton");
      const jobsModal = document.querySelector("#backgroundJobsModal");
      must(jobsButton && jobsModal, "Background Jobs is unavailable for restart recovery acceptance.");
      if (!jobsModal.classList.contains("show")) jobsButton.click();
      const failedJobsFilter = jobsModal.querySelector('[data-job-filter="failed"]');
      must(failedJobsFilter, "Background Jobs failed/cancelled filter is unavailable after application restart.");
      failedJobsFilter.click();
      const sourceRowSelector = '[data-backend-job="' + recoverySourceJobId + '"]';
      await waitFor("interrupted generation appears in Background Jobs", function () {
        return Boolean(document.querySelector(sourceRowSelector));
      }, 20000);
      await waitFor("interrupted generation exposes Recover", function () {
        const row = document.querySelector(sourceRowSelector);
        return Boolean(row && row.querySelector('[data-job-action="recover"]'));
      }, 20000);
      document.querySelector(sourceRowSelector).querySelector('[data-job-action="recover"]').click();

      let recoveredJobId = "";
      await waitFor("native Recover creates a linked generation job", async function () {
        const jobs = await invoke("job.list", {include_hidden:true});
        const row = Array.isArray(jobs) ? jobs.find(item =>
          item.type === "audiobook-generation" &&
          String(item.project_folder || "") === String(config.recovery_project_folder || "") &&
          String(item.recovery_of_job_id || "") === recoverySourceJobId &&
          Boolean(item.job_id)) : null;
        if (!row) return false;
        recoveredJobId = String(row.job_id);
        return true;
      }, 30000);
      let recoveredJob = null;
      await waitFor("recovered real audiobook generation completes", async function () {
        const jobs = await invoke("job.list", {include_hidden:true});
        recoveredJob = Array.isArray(jobs)
          ? jobs.find(item => String(item.job_id || "") === recoveredJobId) : null;
        if (!recoveredJob) return false;
        const state = String(recoveredJob.state || "").toLowerCase();
        if (state === "failed" || state === "cancelled") {
          throw new Error("Real restart recovery ended " + state + ": " +
            String(recoveredJob.error?.message || recoveredJob.message || ""));
        }
        return state === "completed";
      }, 360000);

      const recoveredHistory = await invoke("history.list", {});
      const recoveredHistoryRow = Array.isArray(recoveredHistory)
        ? recoveredHistory.find(item => String(item.job_id || "") === recoveredJobId) : null;
      await openProjectFromDashboard(config.recovery_project_folder, "Stage 5.4 recovered project");
      const recoveredProject = await invoke("project.get_active", {});
      const normalizedRecoveryOutput = String(config.recovery_output_path || "").replace(/\\/g, "/").toLowerCase();
      must(String(recoveredJob.recovery_of_job_id || "") === recoverySourceJobId &&
        String(recoveredJob.state || "").toLowerCase() === "completed" &&
        String(recoveredJob.output_path || "").replace(/\\/g, "/").toLowerCase() === normalizedRecoveryOutput,
        "The recovered job did not complete with the original interrupted job as its recovery parent.");
      must(recoveredHistoryRow && recoveredHistoryRow.state === "completed" &&
        String(recoveredHistoryRow.project_folder || "") === String(config.recovery_project_folder || "") &&
        String(recoveredHistoryRow.output_path || "").replace(/\\/g, "/").toLowerCase() === normalizedRecoveryOutput,
        "History does not match the recovered generation job's project and output ownership.");
      must(String(recoveredProject.folder || "") === String(config.recovery_project_folder || "") &&
        recoveredProject.completed === true &&
        String(recoveredProject.status || "").toLowerCase() === "completed" &&
        String(recoveredProject.output_path || "").replace(/\\/g, "/").toLowerCase() === normalizedRecoveryOutput,
        "The recovered M4B is not attached to the original recovered project.");
      record("stage54_real_restart_recovery", true,
        "A real paused job survived process termination as interrupted, was recovered through the installed Background Jobs button/native bridge, reused its project checkpoints, and completed with the same project/History/output identity.");

      // Step 7: compare the completed production operation across its owning project,
      // History, Background Jobs, Audiobooks card and actual Full Player media source.
      const stage7Folder = String(config.recovery_project_folder || "");
      const stage7Output = String(config.recovery_output_path || "");
      const stage7Player = await invoke("player.get_active", {folder:stage7Folder});
      const stage7Path = value => String(value || "").replace(/\\/g,"/").toLowerCase();
      must(stage7Folder && stage7Output &&
        stage7Path(stage7Player.output_path) === stage7Path(stage7Output),
        "Audiobooks player lookup returned a different project output from Production.");
      const stage7Jobs = await invoke("job.list", {include_hidden:true});
      const stage7Job = Array.isArray(stage7Jobs)
        ? stage7Jobs.find(row => String(row.job_id || "") === String(recoveredJobId)) : null;
      must(stage7Job && String(stage7Job.state || "").toLowerCase() === "completed" &&
        String(stage7Job.project_folder || "") === stage7Folder &&
        stage7Path(stage7Job.output_path) === stage7Path(stage7Output) &&
        String(recoveredHistoryRow.project_folder || "") === stage7Folder &&
        stage7Path(recoveredHistoryRow.output_path) === stage7Path(stage7Output),
        "Production, Background Jobs and History do not share the recovered project's job/output identity.");
      must(String(stage7Player.title || "") === String(recoveredProject.title || "") &&
        String(stage7Player.narrator || "") === String(recoveredProject.narrator || ""),
        "Audiobooks title or narrator differs from the recovered Production project.");
      window.go("player");
      await waitFor("Audiobooks page opens for recovered project", () =>
        Boolean(document.querySelector("#player")?.classList.contains("active") &&
          document.querySelector("#backendAudiobookLibrary")), 12000);
      let stage7Card = null;
      await waitFor("recovered production output appears in Audiobooks", () => {
        stage7Card = Array.from(document.querySelectorAll("#backendAudiobookLibrary .audiobook-library-card"))
          .find(card => String(card.dataset.projectFolder || "") === stage7Folder) || null;
        return Boolean(stage7Card);
      }, 12000);
      must(stage7Card.querySelector("[data-open-project-folder]") &&
        stage7Card.querySelector("[data-play-project-folder]"),
        "Recovered Audiobooks card is missing Open or Play.");
      stage7Card.querySelector("[data-open-project-folder]").click();
      await waitFor("Full Player opens recovered project without autoplay", () => {
        const audio = latestAcceptanceAudio();
        return Boolean(audio && String(audio.dataset.projectFolder || "") === stage7Folder &&
          audio.readyState >= 1 && audio.paused);
      }, 18000);
      const stage7Audio = latestAcceptanceAudio();
      must(audioUsesPath(stage7Audio, stage7Player.playback_output_path || stage7Player.file_url),
        "Full Player loaded media from a different project/output.");
      // Opening a card re-renders the library because selection identity changes.
      // Never click the detached pre-refresh card: reacquire the live row by project.
      stage7Card = Array.from(document.querySelectorAll("#backendAudiobookLibrary .audiobook-library-card"))
        .find(card => String(card.dataset.projectFolder || "") === stage7Folder) || null;
      must(stage7Card && stage7Card.isConnected,
        "The recovered audiobook card was not present in the live library after Open.");
      const stage7Rows = Array.from(document.querySelectorAll("#player [data-audiobook-chapter-start]"));
      const stage7Chapters = Array.isArray(stage7Player.chapters) ? stage7Player.chapters : [];
      must(stage7Rows.length === stage7Chapters.length && stage7Rows.every((row,index) =>
        Math.abs(Number(row.dataset.audiobookChapterStart)-Number(stage7Chapters[index].start_seconds)) < 0.05 &&
        Math.abs(Number(row.dataset.audiobookChapterEnd)-Number(stage7Chapters[index].end_seconds)) < 0.05),
        "Full Player chapters differ from the recovered M4B embedded chapter intervals.");
      const stage7LivePlay = stage7Card.querySelector("[data-play-project-folder]");
      must(stage7LivePlay && stage7LivePlay.isConnected &&
        String(stage7LivePlay.dataset.playProjectFolder || "") === stage7Folder,
        "The live recovered audiobook Play control is missing or belongs to another project.");
      stage7LivePlay.click();
      await waitFor("Audiobooks Play starts the recovered M4B", () =>
        !stage7Audio.paused && stage7Audio.readyState >= 2 && stage7Audio.currentTime > 0.05, 12000);
      must(latestAcceptanceAudio() === stage7Audio &&
        audioUsesPath(stage7Audio,stage7Player.playback_output_path || stage7Player.file_url),
        "Audiobooks Play switched to stale or different-project audio.");
      window.go("dashboard");
      await waitFor("Mini-Player preserves recovered-project playback across navigation", () => {
        const mini = document.querySelector("#miniPlayer");
        return Boolean(mini && !mini.classList.contains("hidden") && mini.getClientRects().length &&
          latestAcceptanceAudio() === stage7Audio);
      }, 8000);
      stage7Audio.pause();
      record("stage6_cross_module_production_audiobooks_player_job_history_identity", true,
        "Production, Background Jobs, History, Audiobooks, embedded chapters, Full Player and Mini-Player all retained the same recovered project/output identity.");

      // HIS-01 to HIS-03: query real durable History, filter it, and open details.
      must(recoveredHistoryRow && recoveredHistoryRow.completed_at,
        "The recovered History record does not expose its completion timestamp.");
      const stage6HistoryDate = new Date(recoveredHistoryRow.completed_at);
      const stage6HistoryDay = stage6HistoryDate.getFullYear() + "-" +
        String(stage6HistoryDate.getMonth()+1).padStart(2,"0") + "-" +
        String(stage6HistoryDate.getDate()).padStart(2,"0");
      window.go("history");
      await waitFor("History controls mount in the frozen application", () =>
        Boolean(document.querySelector("#historySearchFilter") &&
          document.querySelector("#historyFromDate") && document.querySelector("#historyToDate")), 12000);
      const stage6HistorySearch = document.querySelector("#historySearchFilter");
      const stage6HistoryFrom = document.querySelector("#historyFromDate");
      const stage6HistoryTo = document.querySelector("#historyToDate");
      stage6HistorySearch.value = String(recoveredJobId);
      stage6HistoryFrom.value = stage6HistoryDay;
      stage6HistoryTo.value = stage6HistoryDay;
      const stage6CompletedHistoryFilter = Array.from(document.querySelectorAll("#historyFilters button"))
        .find(button => button.textContent.trim().toLowerCase() === "completed");
      must(stage6CompletedHistoryFilter, "History is missing the Completed status filter.");
      stage6CompletedHistoryFilter.click();
      stage6HistorySearch.dispatchEvent(new Event("input",{bubbles:true}));
      stage6HistoryFrom.dispatchEvent(new Event("change",{bubbles:true}));
      stage6HistoryTo.dispatchEvent(new Event("change",{bubbles:true}));
      await waitFor("History applies exact job search, Completed status and inclusive date range", () => {
        const rows = Array.from(document.querySelectorAll("#history [data-backend-history]"));
        return rows.length === 1 && String(rows[0].dataset.historyJob || "") === String(recoveredJobId);
      }, 12000);
      const stage6HistoryView = document.querySelector('#history [data-history-job="' + String(recoveredJobId) + '"]');
      must(stage6HistoryView, "The filtered History row has no View action.");
      stage6HistoryView.click();
      await waitFor("History View opens actual job details", () =>
        Boolean(document.querySelector("#jobDetailsModal.show [data-job-detail-field='job-id']")), 8000);
      must(document.querySelector("#jobDetailsModal [data-job-detail-field='job-id']").textContent.trim() ===
        String(recoveredJobId), "History View opened a different job's details.");
      document.querySelector("#jobDetailsModal [data-job-detail-close]")?.click();
      record("stage6_history_real_search_date_status_and_details", true,
        "History displayed the recovered generation job, applied exact search/status/date filters, and opened its matching details.");

      // JOB-01 to JOB-05: verify the visible Task Manager against native job.list.
      window.go("dashboard");
      const stage6JobsButton = document.querySelector("#backgroundJobsButton");
      must(stage6JobsButton && jobsModal, "Task Manager is unavailable after History acceptance.");
      if (!jobsModal.classList.contains("show")) stage6JobsButton.click();
      await waitFor("Task Manager modal opens", () => jobsModal.classList.contains("show"), 8000);
      const stage6TaskSource = await invoke("job.list", {include_hidden:false});
      must(Array.isArray(stage6TaskSource) && stage6TaskSource.length > 0,
        "Task Manager acceptance has no real job.list records.");
      const stage6TaskAll = jobsModal.querySelector('[data-job-filter="all"]');
      const stage6TaskActive = jobsModal.querySelector('[data-job-filter="active"]');
      const stage6TaskCompleted = jobsModal.querySelector('[data-job-filter="completed"]');
      must(stage6TaskAll && stage6TaskActive && stage6TaskCompleted,
        "Task Manager is missing All, Active or Completed filters.");
      const stage6TaskRowsMatchNativeJobs = () => {
        const rows = Array.from(document.querySelectorAll("#backgroundJobsList [data-backend-job]"));
        const renderedIds = rows.map(row => String(row.dataset.backendJob || "")).sort();
        const sourceIds = stage6TaskSource.map(row => String(row.job_id || "")).sort();
        return rows.length === stage6TaskSource.length &&
          JSON.stringify(renderedIds) === JSON.stringify(sourceIds) &&
          rows.every(row => row.children.length === 3 &&
            row.children[0].classList.contains("job-type-icon") &&
            row.children[1].classList.contains("job-main") &&
            row.children[2].classList.contains("job-actions") &&
            row.querySelector('[data-job-view]')?.dataset.jobView === row.dataset.backendJob) &&
          !document.querySelector("#backgroundJobsList .job-row:not([data-backend-job])");
      };
      stage6TaskAll.click();
      await waitFor("Task Manager All filter renders every native job with its View action",
        stage6TaskRowsMatchNativeJobs, 12000);
      const stage6AllRows = Array.from(document.querySelectorAll("#backgroundJobsList [data-backend-job]"));
      must(stage6AllRows.length === stage6TaskSource.length,
        "Task Manager All filter does not match native job.list identities.");
      must(stage6AllRows.every(row =>
        row.children.length === 3 &&
        row.children[0].classList.contains("job-type-icon") &&
        row.children[1].classList.contains("job-main") &&
        row.children[2].classList.contains("job-actions") &&
        row.querySelector("[data-job-view]")),
        "Task Manager rows do not use the complete responsive actions layout.");
      const expectedRunningCount = stage6TaskSource.filter(row =>
        ["running","pause_requested","cancel_requested","retrying"].includes(row.state)).length;
      const expectedQueuedCount = stage6TaskSource.filter(row => row.state === "queued").length;
      const expectedCompletedCount = stage6TaskSource.filter(row => row.state === "completed").length;
      must(Number(document.querySelector("#jobsRunningCount").textContent) === expectedRunningCount &&
        Number(document.querySelector("#jobsQueuedCount").textContent) === expectedQueuedCount &&
        Number(document.querySelector("#jobsCompletedCount").textContent) === expectedCompletedCount,
        "Task Manager summary counts do not match native job.list.");
      stage6TaskCompleted.click();
      await waitFor("Task Manager Completed filter", () => {
        const rows = Array.from(document.querySelectorAll("#backgroundJobsList [data-backend-job]"));
        return rows.length === expectedCompletedCount && rows.every(row => {
          const job = stage6TaskSource.find(item => String(item.job_id) === String(row.dataset.backendJob));
          return Boolean(job && job.state === "completed");
        });
      }, 8000);
      stage6TaskActive.click();
      await waitFor("Task Manager Active filter", () => {
        const expected = stage6TaskSource.filter(row => !["completed","failed","cancelled"].includes(row.state));
        const rows = Array.from(document.querySelectorAll("#backgroundJobsList [data-backend-job]"));
        return rows.length === expected.length && rows.every(row => {
          const job = stage6TaskSource.find(item => String(item.job_id) === String(row.dataset.backendJob));
          return Boolean(job && !["completed","failed","cancelled"].includes(job.state));
        });
      }, 8000);
      stage6TaskAll.click();
      let stage6TaskRow = null;
      await waitFor("Task Manager All filter restores current rows and actionable View controls", () => {
        if (!stage6TaskRowsMatchNativeJobs()) return false;
        stage6TaskRow = Array.from(document.querySelectorAll("#backgroundJobsList [data-backend-job]"))
          .find(row => Boolean(row.querySelector("[data-job-view]"))) || null;
        return Boolean(stage6TaskRow);
      }, 12000);
      const stage6TaskJob = stage6TaskSource.find(item =>
        String(item.job_id) === String(stage6TaskRow?.dataset.backendJob));
      must(stage6TaskJob && stage6TaskRow.querySelector("[data-job-view]"),
        "A Task Manager job row is missing its View action after the live All-filter refresh completed.");
      stage6TaskRow.querySelector("[data-job-view]").click();
      await waitFor("Task Manager View opens actual job details", () =>
        Boolean(document.querySelector("#jobDetailsModal.show [data-job-detail-field='job-id']")), 8000);
      must(document.querySelector("#jobDetailsModal [data-job-detail-field='job-id']").textContent.trim() ===
        String(stage6TaskJob.job_id), "Task Manager View opened a different job's details.");
      document.querySelector("#jobDetailsModal [data-job-detail-close]")?.click();
      await sleep(4500);
      await waitFor("Task Manager backend rows remain owned after the former prototype timer window",
        stage6TaskRowsMatchNativeJobs, 12000);
      must(Array.from(document.querySelectorAll("#backgroundJobsList [data-backend-job]")).every(row =>
        Boolean(row.querySelector("[data-job-view]")) &&
        row.querySelector("[data-job-view]").dataset.jobView === row.dataset.backendJob),
        "A delayed refresh replaced a live Task Manager row or removed its actionable View button.");
      record("stage6_task_manager_backend_dom_stays_stable_after_delayed_refresh", true,
        "After more than the former four-second prototype timer interval, backend job identities and actionable View controls remained intact.");
      jobsModal.classList.remove("show");
      record("stage6_task_manager_real_records_filters_details_and_counts", true,
        "Task Manager All/Active/Completed views, row layout, summary counts and operation details matched native jobs.");

      // UI-06 / Step 8: emulate every requested CSS viewport against the actual
      // Premium V2 DOM and stylesheet, including the Audiobooks, History,
      // mini-player, Task Manager and operation-details components.
      const stage6ResponsiveCss = Array.from(document.querySelectorAll("style"))
        .map(style => style.textContent || "").join("\n");
      const stage6ResponsiveApp = document.querySelector("#app")?.outerHTML || "";
      const stage6ResponsiveJobs = jobsModal?.outerHTML || "";
      const stage6ResponsiveDetails = document.querySelector("#jobDetailsModal")?.outerHTML || "";
      must(stage6ResponsiveCss.length > 10000 &&
        stage6ResponsiveApp.includes('id="player"') &&
        stage6ResponsiveApp.includes('id="history"') &&
        stage6ResponsiveApp.includes('id="miniPlayer"') &&
        stage6ResponsiveJobs.includes('id="backgroundJobsList"') &&
        stage6ResponsiveDetails.includes('id="jobDetailsModal"'),
        "The responsive viewport fixture could not clone all required live Premium V2 surfaces.");
      const stage6ResponsiveFrame = document.createElement("iframe");
      stage6ResponsiveFrame.setAttribute("aria-hidden","true");
      stage6ResponsiveFrame.width = 1920;
      stage6ResponsiveFrame.height = 1080;
      stage6ResponsiveFrame.setAttribute("width","1920");
      stage6ResponsiveFrame.setAttribute("height","1080");
      Object.assign(stage6ResponsiveFrame.style,{
        position:"fixed",left:"-20000px",top:"-20000px",
        display:"block",minWidth:"0",minHeight:"0",
        width:"1920px",height:"1080px",border:"0",opacity:"0",
        pointerEvents:"none",zIndex:"-1"
      });
      document.body.appendChild(stage6ResponsiveFrame);
      const stage6ResponsiveTheme = document.documentElement.dataset.theme || "dark";
      const stage6ResponsiveEffects = document.documentElement.dataset.effects || "high";
      const stage6ResponsiveStyle = stage6ResponsiveCss.replace(/<\/style/gi,"<\\/style");
      stage6ResponsiveFrame.srcdoc = '<!doctype html><html data-theme="' + stage6ResponsiveTheme +
        '" data-effects="' + stage6ResponsiveEffects + '"><head><meta charset="utf-8">' +
        '<meta name="viewport" content="width=device-width, initial-scale=1">' +
        '<style>' + stage6ResponsiveStyle + '</style></head><body>' +
        stage6ResponsiveApp + stage6ResponsiveJobs + stage6ResponsiveDetails + '</body></html>';
      await waitFor("responsive CSS fixture loads",() => {
        const frameDoc = stage6ResponsiveFrame.contentDocument;
        return Boolean(frameDoc && frameDoc.readyState === "complete" &&
          frameDoc.querySelector("#player") && frameDoc.querySelector("#history") &&
          frameDoc.querySelector("#miniPlayer") && frameDoc.querySelector("#backgroundJobsList"));
      },15000);
      const stage6ResponsiveDoc = stage6ResponsiveFrame.contentDocument;
      stage6ResponsiveDoc.body.style.margin = "0";
      const stage6ResponsiveAppRoot = stage6ResponsiveDoc.querySelector("#app");
      const stage6ResponsivePlayer = stage6ResponsiveDoc.querySelector("#player");
      const stage6ResponsiveHistory = stage6ResponsiveDoc.querySelector("#history");
      for (const page of stage6ResponsiveDoc.querySelectorAll(".page")) page.classList.remove("active");
      stage6ResponsivePlayer.classList.add("active");
      stage6ResponsiveHistory.classList.add("active");
      stage6ResponsiveDoc.querySelector("#miniPlayer")?.classList.remove("hidden");
      stage6ResponsiveDoc.querySelector("#backgroundJobsModal")?.classList.add("show");
      stage6ResponsiveDoc.querySelector("#jobDetailsModal")?.classList.add("show");
      stage6ResponsiveAppRoot.style.width = "100%";
      const stage6ResponsiveLibrary = stage6ResponsiveDoc.querySelector("#player .audiobook-library-grid") ||
        (() => {
          const shelf = stage6ResponsiveDoc.createElement("div");
          shelf.className = "audiobook-library-grid";
          stage6ResponsivePlayer.insertBefore(shelf,stage6ResponsivePlayer.querySelector(".player-grid"));
          return shelf;
        })();
      if (!stage6ResponsiveLibrary.querySelector(".audiobook-library-card")) {
        stage6ResponsiveLibrary.innerHTML =
          '<article class="audiobook-library-card"><div class="audiobook-card-cover"></div>' +
          '<div class="audiobook-card-content"><h3 class="audiobook-card-title">Responsive audiobook acceptance</h3>' +
          '<div class="audiobook-card-status-row"><span class="badge">Completed M4B</span></div>' +
          '<div class="audiobook-card-actions"><button class="btn small secondary">Open</button>' +
          '<button class="btn small">Play</button></div></div></article>';
      }
      const stage6ResponsiveJobList = stage6ResponsiveDoc.querySelector("#backgroundJobsList");
      stage6ResponsiveJobList.innerHTML =
        '<article class="job-row" data-backend-job="responsive-job">' +
          '<div class="job-type-icon" aria-hidden="true">♪</div>' +
          '<div class="job-main"><h3>Responsive generation job</h3>' +
          '<p>Chapter 3 · Audio rendering</p><div class="job-meta">Test Project · Chapter 3 · 00:32</div>' +
          '<div class="job-progress-line"><div class="progress"><i style="width:72%"></i></div>' +
          '<small class="job-state-running">running · 72%</small></div></div>' +
          '<div class="job-actions"><button class="btn small secondary">View</button>' +
          '<button class="btn small danger">Cancel</button></div></article>';
      const stage6ResponsiveViewports = [
        ["1920x1080",1920,1080],["1366x768",1366,768],["1280x720",1280,720],
        ["800x600",800,600],["1024x768",1024,768],["1280x960",1280,960],
        ["1400x1050",1400,1050],["1600x1200",1600,1200],["2048x1536",2048,1536],
        ["1280x1024",1280,1024],["1600x1280",1600,1280],
        ["1280x800",1280,800],["1440x900",1440,900],["1680x1050",1680,1050],
        ["1920x1200",1920,1200],["2560x1600",2560,1600],["3840x2400",3840,2400],
        ["1024x576",1024,576],["1600x900",1600,900],["2560x1440",2560,1440],
        ["3840x2160",3840,2160],["5120x2880",5120,2880],["7680x4320",7680,4320],
        ["2560x1080",2560,1080],["3440x1440",3440,1440],["3840x1600",3840,1600],
        ["5120x2160",5120,2160],["3840x1080",3840,1080],["5120x1440",5120,1440],
        ["7680x2160",7680,2160],["960x640",960,640],["1440x960",1440,960],
        ["2160x1440",2160,1440],["2880x1920",2880,1920],
        ["600x800",600,800],["768x1024",768,1024],["800x1280",800,1280],
        ["900x1440",900,1440],["1080x1920",1080,1920],["1440x2560",1440,2560],
        ["2160x3840",2160,3840]
      ];
      const stage6CheckResponsiveViewport = async (label,width,height) => {
        // Change both the iframe browsing-context attributes and its CSS size.
        // Wait for the real iframe viewport resize; a synthetic resize event
        // cannot change innerWidth or innerHeight.
        stage6ResponsiveFrame.width = width;
        stage6ResponsiveFrame.height = height;
        stage6ResponsiveFrame.setAttribute("width",String(width));
        stage6ResponsiveFrame.setAttribute("height",String(height));
        stage6ResponsiveFrame.style.width = width + "px";
        stage6ResponsiveFrame.style.height = height + "px";
        stage6ResponsiveAppRoot.style.minHeight = height + "px";
        await waitFor("iframe viewport reaches " + label,() =>
          stage6ResponsiveFrame.contentWindow.innerWidth === width &&
          stage6ResponsiveFrame.contentWindow.innerHeight === height,5000);
        const d = stage6ResponsiveDoc;
        const actualWidth = stage6ResponsiveFrame.contentWindow.innerWidth;
        const actualHeight = stage6ResponsiveFrame.contentWindow.innerHeight;
        must(actualWidth === width && actualHeight === height,
          "Responsive emulation did not reach requested viewport " + label +
            ": got " + actualWidth + "x" + actualHeight);
        const shell = d.querySelector(".app");
        const workspace = d.querySelector(".workspace");
        const topbar = d.querySelector(".topbar");
        const playerPage = d.querySelector("#player.page");
        const playerGrid = d.querySelector("#player .player-grid");
        const historyRow = d.querySelector("#history .history-row");
        const mini = d.querySelector("#miniPlayer");
        const jobsPanel = d.querySelector("#backgroundJobsModal .jobs-modal");
        const jobRow = d.querySelector("#backgroundJobsList .job-row");
        const libraryCard = d.querySelector("#player .audiobook-library-card");
        const detailsPanel = d.querySelector("#jobDetailsModal .modal");
        const rects = [
          ["application-shell",shell],["workspace",workspace],["topbar",topbar],["player-page",playerPage],
          ["player-grid",playerGrid],["history-row",historyRow],["mini-player",mini],
          ["Task Manager",jobsPanel],["job-row",jobRow],["audiobook-card",libraryCard],
          ["job-details",detailsPanel]
        ];
        for (const [name,element] of rects) {
          must(element, "Responsive fixture is missing " + name + " at " + label + ".");
          const r = element.getBoundingClientRect();
          must(r.width <= width + 2 && r.left >= -2 && r.right <= width + 2,
            name + " exceeds the viewport at " + label + ": " +
              JSON.stringify({left:r.left,right:r.right,width:r.width,viewport:width}));
        }
        must(getComputedStyle(workspace).minWidth === "0px",
          "The shared workspace grid item retained its automatic minimum width at " + label + ".");
        const shellStyle = getComputedStyle(shell);
        if (width <= 800) {
          must(shellStyle.display === "block",
            "The mobile application shell did not switch to its single-column layout at " + label + ".");
        } else {
          must(shellStyle.gridTemplateColumns.split(" ").length === 2,
            "The desktop/tablet application shell lost its bounded sidebar/workspace grid at " + label + ".");
        }
        const playerColumns = getComputedStyle(playerGrid).gridTemplateColumns.trim().split(/\s+/).length;
        const historyColumns = getComputedStyle(historyRow).gridTemplateColumns.trim().split(/\s+/).length;
        const jobColumns = getComputedStyle(jobRow).gridTemplateColumns.trim().split(/\s+/).length;
        must(playerColumns === (width <= 1250 ? 1 : 3),
          "Audiobooks player grid breakpoint mismatch at " + label + ": " + playerColumns + " columns.");
        must(historyColumns === (width <= 800 ? 2 : 4),
          "History row breakpoint mismatch at " + label + ": " + historyColumns + " columns.");
        must(jobColumns === (width <= 650 ? 2 : 3),
          "Task Manager row breakpoint mismatch at " + label + ": " + jobColumns + " columns.");
        must(getComputedStyle(mini).position === "fixed",
          "Mini-player stopped using its viewport-pinned layout at " + label + ".");
      };
      for (const viewport of stage6ResponsiveViewports) {
        await stage6CheckResponsiveViewport(viewport[0],viewport[1],viewport[2]);
      }
      record("stage6_responsive_shared_shell_bounds_41_resolutions",true,
        "At all 41 viewports, the two-column application shell, top bar and workspace stayed within the viewport, with min-width:0 applied to the workspace.");
      record("stage6_responsive_viewport_matrix_41_resolutions",true,
        "All 41 requested aspect-ratio resolutions were emulated against the actual Premium V2 stylesheet and player, library, mini-player, History, Task Manager and job-details DOM.");

      // Window-size and effective CSS viewport emulation. These are browser
      // viewport checks, not assertions about physical monitor topology or OS DPI.
      const stage6WindowViewports = [
        ["restored-window",1366,768],["half-screen",960,1080],["quarter-screen",960,540],
        ["ultrawide-window",3440,1440],["maximized-window",1920,1080],["portrait-window",800,1280]
      ];
      for (const viewport of stage6WindowViewports) {
        await stage6CheckResponsiveViewport(viewport[0],viewport[1],viewport[2]);
      }
      const stage6ScaleViewports = [
        ["100%",1920,1080],["125%",1536,864],["150%",1280,720],["200%",960,540]
      ];
      for (const viewport of stage6ScaleViewports) {
        await stage6CheckResponsiveViewport("effective viewport at " + viewport[0],viewport[1],viewport[2]);
      }
      record("stage6_responsive_window_and_scale_emulation",true,
        "Restored, half-screen, quarter-screen, maximized, ultrawide and portrait viewport cases plus effective 100/125/150/200% scale sizes passed CSS emulation. Physical minimized/mixed-monitor/extended-monitor/DPI verification remains a separate OS-level check.");
      stage6ResponsiveFrame.remove();

      publish("passed");
      return;
    }

    const initial = await invoke("sound.chapter_bgm.get", {});
    must(initial && Array.isArray(initial.chapters) && initial.chapters.length === 3,
      "The isolated three-chapter acceptance project did not load.");
    record("active_project", true, "The packaged app loaded a three-chapter project with real saved narration fixtures.");

    must(typeof window.go === "function", "The Premium V2 navigation function is unavailable.");
    window.go('sound');
    await waitFor("Sound Design page", function () {
      const page = document.querySelector("#sound");
      return page && page.classList.contains("active");
    }, 12000);

    const pageHead = document.querySelector("#sound > .page-head");
    must(pageHead && !pageHead.querySelector("#soundPreviewBook") &&
      !pageHead.querySelector("#saveSoundPresetAdvanced"),
      "A removed top-right Sound Design preview or advanced preset action reappeared.");
    record("sd01_removed_top_right_actions", true, "The removed top-right preview and advanced preset actions remain absent in the frozen UI.");

    for (const view of ["music", "chapters", "cues", "mix"]) {
      const tab = document.querySelector('#sound .sound-tabs [data-sound-tab="' + view + '"]');
      must(tab, "Sound Design tab is missing: " + view);
      tab.click();
      await waitFor(view + " view", function () {
        const activeTab = document.querySelector('#sound .sound-tabs [data-sound-tab="' + view + '"]');
        const activeView = document.querySelector('#sound .sound-view[data-sound-view="' + view + '"]');
        return activeTab && activeTab.classList.contains("active") &&
          activeView && activeView.classList.contains("active");
      }, 8000);
    }
    document.querySelector('#sound .sound-tabs [data-sound-tab="music"]').click();
    await waitFor("Music Library view", function () {
      const view = document.querySelector('#sound .sound-view[data-sound-view="music"]');
      return view && view.classList.contains("active");
    }, 8000);
    record("sound_design_navigation", true, "All four Sound Design tabs navigated correctly in the packaged app.");

    const categories = ["all", "fantasy-adventure", "battle-warfare", "mystery", "horror", "romance", "sci-fi", "calm-narration", "others"];
    for (const category of categories) {
      const button = document.querySelector('#sound .sound-categories-list [data-music-category="' + category + '"]');
      must(button, "Music category button is missing: " + category);
      button.click();
      await waitFor("category selection " + category, function () { return button.classList.contains("active"); }, 5000);
    }
    record("all_music_category_filters", true, "All nine Music Library category filters accepted clicks and updated active state.");

    const importCategory = document.querySelector("#musicImportCategory");
    must(importCategory && Array.from(importCategory.options || []).some(option => option.value === config.expected_category),
      "Fantasy is not a valid Music Library import category.");
    importCategory.value = config.expected_category;
    importCategory.dispatchEvent(new Event("change", { bubbles: true }));
    const importButton = document.querySelector("#importMusicTracks");
    must(importButton && !importButton.disabled, "Music Library Import Tracks control is missing or disabled.");
    importButton.click();

    let catalog = [];
    await waitFor("two generated music tracks to import", async function () {
      catalog = await invoke("sound.catalog", {});
      const matches = (config.track_titles || []).map(title => catalog.find(track =>
        track.title === title && String(track.role || "").toLowerCase() === "music"));
      return matches.length === 2 && matches.every(Boolean);
    }, 30000);
    const alpha = catalog.find(track => track.title === config.track_titles[0] && String(track.role || "").toLowerCase() === "music");
    const beta = catalog.find(track => track.title === config.track_titles[1] && String(track.role || "").toLowerCase() === "music");
    must(alpha && beta, "Imported music files were not returned by the native Music Library catalogue.");
    must(alpha.category === config.expected_category && beta.category === config.expected_category,
      "The selected import category was not retained in track metadata.");
    must(String(alpha.source || "").toLowerCase().includes("imported") &&
      String(beta.source || "").toLowerCase().includes("imported"),
      "The Music Library did not classify both imported tracks as Imported locally.");
    record("real_music_import_and_category", true, "The real import control imported both WAV fixtures and the backend retained Music role, Imported source, and Fantasy category.");

    const allCategory = document.querySelector('#sound .sound-categories-list [data-music-category="all"]');
    allCategory.click();
    await waitFor("All Music Library category", function () { return allCategory.classList.contains("active"); }, 5000);
    const allSource = document.querySelector('#soundSourceFilter [data-source="all"]');
    const importedSource = document.querySelector('#soundSourceFilter [data-source="imported"]');
    const builtInSource = document.querySelector('#soundSourceFilter [data-source="built-in"]');
    must(allSource && importedSource && builtInSource, "Music Library source filter buttons are incomplete.");
    builtInSource.click();
    try {
      await waitFor("Built-in filter to render only bundled music", function () {
        const rows = musicButtons();
        return builtInSource.classList.contains("active") &&
          rows.length > 0 &&
          rows.every(button => rowText(button).includes("Bundled with application")) &&
          !visibleHas(config.track_titles[0]) && !visibleHas(config.track_titles[1]);
      }, 12000);
    } catch (filterError) {
      const diagnosticCatalog = await invoke("sound.catalog", {});
      const sourceCounts = {};
      const categoryCounts = {};
      const roleCounts = {};
      for (const track of Array.isArray(diagnosticCatalog) ? diagnosticCatalog : []) {
        const metadata = track && typeof track.metadata === "object" ? track.metadata : {};
        const role = String(track?.role || metadata.role || "music").trim().toLowerCase();
        const source = String(track?.source || "(missing source)");
        const category = String(track?.category || metadata.category || "(missing category)");
        sourceCounts[source] = (sourceCounts[source] || 0) + 1;
        categoryCounts[category] = (categoryCounts[category] || 0) + 1;
        roleCounts[role] = (roleCounts[role] || 0) + 1;
      }
      const renderedRows = musicButtons().map(rowText);
      const diagnosticGrid = document.querySelector("#soundTrackGrid");
      throw new Error("Built-in filter did not settle on bundled music rows. " +
        JSON.stringify({
          cause:String(filterError),
          catalogCount:Array.isArray(diagnosticCatalog) ? diagnosticCatalog.length : -1,
          sourceCounts, categoryCounts, roleCounts,
          activeCategory:document.querySelector('#sound .sound-categories-list [data-music-category].active')?.dataset.musicCategory || "(none)",
          activeSource:document.querySelector('#soundSourceFilter [data-source].active')?.dataset.source || "(none)",
          gridExists:Boolean(diagnosticGrid),
          gridSignature:diagnosticGrid?.dataset.soundListSignature || "(missing)",
          gridRowCount:musicButtons().length,
          gridText:String(diagnosticGrid?.textContent || "").trim().slice(0,400),
          renderedRows:renderedRows.slice(0,12)
        }));
    }
    record("music_builtin_source_filter", true,
      "The Built-in filter waited for a non-empty list and every rendered row belongs to the bundled application catalogue.");

    importedSource.click();
    await waitFor("Imported filter to render only imported music", function () {
      const rows = musicButtons();
      return importedSource.classList.contains("active") &&
        rows.length === 2 &&
        rows.every(button => rowText(button).includes("Imported locally")) &&
        visibleHas(config.track_titles[0]) && visibleHas(config.track_titles[1]);
    }, 12000);
    record("music_imported_source_filter", true,
      "The Imported filter rendered exactly the two imported fixture tracks and no bundled rows.");

    allSource.click();
    await waitFor("All source filter to restore bundled and imported music", function () {
      const rows = musicButtons();
      const texts = rows.map(rowText);
      return allSource.classList.contains("active") &&
        rows.length >= 3 &&
        texts.some(text => text.includes("Bundled with application")) &&
        texts.some(text => text.includes("Imported locally")) &&
        visibleHas(config.track_titles[0]) && visibleHas(config.track_titles[1]);
    }, 12000);
    record("music_all_source_filter", true,
      "All restored both bundled starter tracks and imported music together.");

    const fantasy = document.querySelector('#sound .sound-categories-list [data-music-category="fantasy-adventure"]');
    fantasy.click();
    await waitFor("Fantasy category to render only Fantasy adventure tracks", function () {
      const rows = musicButtons();
      return fantasy.classList.contains("active") &&
        rows.length > 0 &&
        rows.every(button => rowText(button).includes("Fantasy adventure")) &&
        visibleHas(config.track_titles[0]) && visibleHas(config.track_titles[1]);
    }, 12000);
    const search = document.querySelector("#soundTrackSearch");
    must(search, "Music Library search field is missing.");
    search.value = config.track_titles[0];
    search.dispatchEvent(new Event("input", { bubbles: true }));
    await waitFor("Music Library search results", function () {
      return visibleHas(config.track_titles[0]) && !visibleHas(config.track_titles[1]);
    }, 10000);
    search.value = "";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    await waitFor("cleared Music Library search", function () {
      return visibleHas(config.track_titles[0]) && visibleHas(config.track_titles[1]);
    }, 10000);
    record("music_source_category_and_search_filters", true, "Built-in/Imported source filters, Fantasy category filter, and live title search returned the expected tracks.");

    let alphaButton = findTrackButton(alpha.path);
    let betaButton = findTrackButton(beta.path);
    must(alphaButton && betaButton, "Imported music track Select buttons are missing.");
    alphaButton.click();
    await waitFor("Alpha selected-track details", function () {
      const title = document.querySelector("#selectedSoundTitle");
      return title && title.textContent.includes(config.track_titles[0]);
    }, 8000);
    const musicMeta = document.querySelector("#selectedSoundMeta");
    must(musicMeta && musicMeta.textContent.includes("Imported locally") &&
      musicMeta.textContent.toLowerCase().includes(".wav") &&
      musicMeta.textContent.includes("12.0 sec"),
      "The Selected Track panel did not display Alpha's actual source, format, and duration.");
    record("music_track_selection", true, "Selected Track displays the real imported track name, source, WAV format, and duration.");

    const volume = document.querySelector("#advancedMusicVolume");
    const initialMixState = await invoke("sound.chapter_bgm.get", {});
    must(volume && Number(volume.max) === 50, "The BGM slider does not enforce the 50 percent maximum.");
    must(volume.value === "18" && Math.abs(Number(initialMixState.default_volume) - 0.18) < 0.005,
      "The documented 18% master BGM default was not hydrated from saved project data.");
    // Match an actual user edit: the production summary deliberately hydrates
    // the last saved value when this control is not focused. Keep it focused
    // through input/change so that summary refreshes preserve the live edit.
    volume.focus();
    must(document.activeElement === volume, "The BGM range control did not receive focus before editing.");
    volume.value = String(config.expected_volume * 100);
    volume.dispatchEvent(new Event("input", { bubbles: true }));
    must(document.activeElement === volume, "The BGM range control lost focus during its input update.");
    must(volume.value === "42" &&
      document.querySelector("#advancedMusicVolumeValue").textContent.trim() === "42%",
      "The BGM slider's live value did not remain at 42% after the input update.");
    volume.dispatchEvent(new Event("change", { bubbles: true }));
    await waitFor("42 percent BGM value save", async function () {
      const saved = await invoke("sound.chapter_bgm.get", {});
      return Math.abs(Number(saved.default_volume) - config.expected_volume) < 0.005;
    }, 15000);
    must(volume.value === "42" &&
      document.querySelector("#advancedMusicVolumeValue").textContent.trim() === "42%",
      "The saved BGM slider value is not still visibly 42%.");
    record("music_volume_control", true, "BGM volume maximum remained 50%; 42% was shown and saved through the app.");

    const preview = document.querySelector("#previewSelectedTrack");
    must(preview && !preview.disabled, "Preview Selected Track is disabled after selecting music.");
    preview.click();
    const alphaAudio = await waitForRealPlayback("Alpha audio media playback", alpha.path);
    await waitFor("Alpha preview playback control", function () {
      return preview.textContent.includes(pauseLabel);
    }, 10000);
    preview.click();
    const alphaPausedAt = await waitForPausedAudio("Alpha music pause", alphaAudio);
    preview.click();
    await waitFor("Alpha audio preview resume", function () {
      return preview.textContent.includes(pauseLabel) && !alphaAudio.paused &&
        alphaAudio.currentTime > alphaPausedAt + 0.05;
    }, 10000);
    record("music_audio_preview_play_pause_resume", true,
      "The imported WAV decoded and advanced in WebEngine; pause stopped media time and resume continued the same file.");

    betaButton = findTrackButton(beta.path);
    must(betaButton, "Beta disappeared from the catalogue before switching preview.");
    betaButton.click();
    await waitFor("Beta selected-track details and stopped prior preview", function () {
      const title = document.querySelector("#selectedSoundTitle");
      return title && title.textContent.includes(config.track_titles[1]) &&
        alphaAudio.paused && !preview.textContent.includes(pauseLabel);
    }, 8000);
    preview.click();
    const betaAudio = await waitForRealPlayback("Beta audio media playback", beta.path);
    must(betaAudio !== alphaAudio && audioUsesPath(betaAudio, beta.path),
      "Switching to Beta did not create playback from Beta's own audio file.");
    record("music_preview_track_switch", true,
      "Selecting Beta stopped Alpha; the next actual media element used Beta's local WAV file.");

    alphaButton = findTrackButton(alpha.path);
    must(alphaButton, "Alpha disappeared before explicit default save.");
    alphaButton.click();
    await waitFor("Alpha reselected", function () {
      return document.querySelector("#selectedSoundTitle").textContent.includes(config.track_titles[0]);
    }, 8000);
    document.querySelector("#setBookDefaultTrack").click();
    await waitFor("explicit book-default save", async function () {
      const saved = await invoke("sound.chapter_bgm.get", {});
      return String(saved.default_path || "") === String(alpha.path);
    }, 15000);
    record("explicit_book_default_save", true, "Set as book default BGM persisted Alpha through the real UI action and native bridge.");

    betaButton = findTrackButton(beta.path);
    betaButton.click();
    const afterCandidate = await invoke("sound.chapter_bgm.get", {});
    must(String(afterCandidate.default_path || "") === String(alpha.path),
      "Selecting Beta silently replaced the saved Alpha book default.");
    record("candidate_selection_does_not_overwrite_default", true, "Selecting Beta changed the candidate panel but left the saved Alpha book default unchanged.");


    document.querySelector('#sound .sound-tabs [data-sound-tab="cues"]').click();
    await waitFor("Opening & Cues view", function () {
      const view = document.querySelector('#sound .sound-view[data-sound-view="cues"]');
      return view && view.classList.contains("active");
    }, 8000);
    const importCues = document.querySelector("#importCueClips");
    must(importCues && !importCues.disabled, "Import effect clips control is missing or disabled.");
    config.reject_long_cue_import = true;
    importCues.click();
    await waitFor("six-second cue rejection", function () {
      return document.querySelector("#toasts")?.textContent.includes("5 seconds or shorter");
    }, 10000);
    const afterLongCueAttempt = await invoke("sound.catalog", {});
    must(!afterLongCueAttempt.some(track => String(track.path || "").includes("CUE_TOO_LONG")),
      "A cue longer than five seconds was accepted into the native cue catalogue.");
    record("cue_import_rejects_over_five_seconds", true,
      "The real cue-import action rejected a six-second audio fixture and did not add it to the catalogue.");
    importCues.click();
    let cueCatalog = [];
    await waitFor("two imported cue fixtures", async function () {
      cueCatalog = await invoke("sound.catalog", {});
      const matches = (config.cue_track_titles || []).map(title => cueCatalog.find(track =>
        track.title === title && String(track.role || "").toLowerCase() === "cue"));
      return matches.length === 2 && matches.every(Boolean);
    }, 30000);
    const cueAlpha = cueCatalog.find(track => track.title === config.cue_track_titles[0] &&
      String(track.role || "").toLowerCase() === "cue");
    const cueBeta = cueCatalog.find(track => track.title === config.cue_track_titles[1] &&
      String(track.role || "").toLowerCase() === "cue");
    must(cueAlpha && cueBeta, "The imported cue clips are missing from the native cue catalogue.");
    must(cueAlpha.source === "Imported locally" && cueBeta.source === "Imported locally" &&
      cueAlpha.format === ".wav" && cueBeta.format === ".wav",
      "Imported cue catalogue records do not contain their real source and format information.");
    must(!visibleHas(config.cue_track_titles[0]) && !visibleHas(config.cue_track_titles[1]),
      "A cue asset leaked into the Music Library track grid.");
    const cueSourceAll = document.querySelector('#cueSourceFilter [data-cue-source="all"]');
    const cueSourceBuiltIn = document.querySelector('#cueSourceFilter [data-cue-source="built-in"]');
    const cueSourceImported = document.querySelector('#cueSourceFilter [data-cue-source="imported"]');
    must(cueSourceAll && cueSourceBuiltIn && cueSourceImported, "Cue source filters are incomplete.");
    cueSourceBuiltIn.click();
    await waitFor("Built-in cue source results", function () {
      const rows = Array.from(document.querySelectorAll("#cueGrid [data-cue-path]"));
      return rows.length > 0 && rows.every(card => card.textContent.includes("Bundled with application")) &&
        !rows.some(card => card.textContent.includes(config.cue_track_titles[0]) ||
          card.textContent.includes(config.cue_track_titles[1]));
    }, 12000);
    cueSourceImported.click();
    await waitFor("Imported cue source results", function () {
      const rows = Array.from(document.querySelectorAll("#cueGrid [data-cue-path]"));
      return rows.length === 2 && rows.every(card => card.textContent.includes("Imported locally")) &&
        rows.some(card => String(card.dataset.cuePath || "") === String(cueAlpha.path)) &&
        rows.some(card => String(card.dataset.cuePath || "") === String(cueBeta.path));
    }, 12000);
    cueSourceAll.click();
    await waitFor("All cue source results", function () {
      const rows = Array.from(document.querySelectorAll("#cueGrid [data-cue-path]"));
      return rows.some(card => String(card.dataset.cuePath || "") === String(cueAlpha.path)) &&
        rows.some(card => String(card.dataset.cuePath || "") === String(cueBeta.path)) &&
        rows.some(card => card.textContent.includes("Bundled with application"));
    }, 12000);
    record("cue_library_source_classification", true, "Built-in, Imported and All cue filters returned only the correct real cue assets.");
    try {
      await waitFor("two imported cue cards to render", function () {
        const rows = Array.from(document.querySelectorAll("#cueGrid [data-cue-path]"));
        return rows.some(card => String(card.dataset.cuePath || "") === String(cueAlpha.path)) &&
          rows.some(card => String(card.dataset.cuePath || "") === String(cueBeta.path));
      }, 15000);
    } catch (renderError) {
      const diagnosticCueCatalog = await invoke("sound.catalog", {});
      const cueRoleCounts = {};
      for (const track of Array.isArray(diagnosticCueCatalog) ? diagnosticCueCatalog : []) {
        const role = String(track?.role || track?.metadata?.role || "music").trim().toLowerCase();
        cueRoleCounts[role] = (cueRoleCounts[role] || 0) + 1;
      }
      const diagnosticCueGrid = document.querySelector("#cueGrid");
      const visibleCueRows = Array.from(document.querySelectorAll("#cueGrid [data-cue-path]"));
      throw new Error("Imported cue cards did not render after native catalogue import. " +
        JSON.stringify({
          cause:String(renderError),
          catalogCount:Array.isArray(diagnosticCueCatalog) ? diagnosticCueCatalog.length : -1,
          cueRoleCounts,
          expectedCuePaths:[cueAlpha.path,cueBeta.path],
          renderedCuePaths:visibleCueRows.map(card => card.dataset.cuePath),
          gridExists:Boolean(diagnosticCueGrid),
          gridSignature:diagnosticCueGrid?.dataset.cueListSignature || "(missing)",
          gridText:String(diagnosticCueGrid?.textContent || "").trim().slice(0,500),
          activeSource:document.querySelector('#cueSourceFilter [data-cue-source].active')?.dataset.cueSource || "(none)",
          search:String(document.querySelector("#cueSearch")?.value || "")
        }));
    }
    const cueCards = Array.from(document.querySelectorAll("#cueGrid [data-cue-path]"));
    const cueCardAlpha = cueCards.find(card => String(card.dataset.cuePath || "") === String(cueAlpha.path));
    const cueCardBeta = cueCards.find(card => String(card.dataset.cuePath || "") === String(cueBeta.path));
    must(cueCardAlpha && cueCardBeta, "The two imported cue cards did not remain rendered after the cue-grid wait.");

    function inspectCueCard(card, track) {
      const title = card.querySelector("h3");
      const metadata = card.querySelector("p");
      must(title && metadata, "A cue card is missing its title or metadata element.");
      must(title.textContent.trim() === track.title, "Cue card title does not match the selected catalogue record.");
      must(metadata.textContent.includes("Imported locally") && metadata.textContent.includes(".wav"),
        "Cue card metadata does not show the actual source and audio format.");
      const cardRect = card.getBoundingClientRect();
      const titleRect = title.getBoundingClientRect();
      const metadataRect = metadata.getBoundingClientRect();
      must(titleRect.width > 0 && metadataRect.width > 0 &&
        titleRect.bottom <= metadataRect.top + 1 &&
        metadataRect.bottom <= cardRect.bottom + 1,
        "Cue card title and metadata overlap or extend outside the card.");
    }
    inspectCueCard(cueCardAlpha, cueAlpha);
    inspectCueCard(cueCardBeta, cueBeta);
    cueCardAlpha.click();
    await waitFor("selected cue title and metadata", function () {
      const title = document.querySelector("#selectedCueTitle");
      const meta = document.querySelector("#selectedCueMeta");
      return title && title.textContent.trim() === cueAlpha.title &&
        meta && meta.textContent.includes("Imported locally") && meta.textContent.includes(".wav");
    }, 8000);
    must(cueCardAlpha.getAttribute("aria-pressed") === "true" &&
      cueCardAlpha.classList.contains("selected"),
      "The selected cue card does not show its selected state.");
    record("cue_card_readability_and_selected_track_details", true,
      "Cue title, source, WAV format, selected state and non-overlapping title/metadata layout match the real imported catalogue record.");

    const playCue = document.querySelector("#playSelectedCue");
    const pauseCue = document.querySelector("#pauseSelectedCue");
    const replayCue = document.querySelector("#replaySelectedCue");
    must(playCue && pauseCue && replayCue, "Cue Play, Pause or Replay control is missing.");
    playCue.click();
    const cueAlphaAudio = await waitForRealPlayback("Alpha cue media playback", cueAlpha.path);
    pauseCue.click();
    const cuePausedAt = await waitForPausedAudio("Alpha cue pause", cueAlphaAudio);
    playCue.click();
    await waitFor("Alpha cue resume", function () {
      return !cueAlphaAudio.paused && cueAlphaAudio.currentTime > cuePausedAt + 0.05;
    }, 8000);
    const beforeReplay = window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__.length;
    replayCue.click();
    await waitFor("Alpha cue replay creates a new selected-file media element", function () {
      const audio = latestAcceptanceAudio();
      return window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__.length > beforeReplay &&
        audio && audioUsesPath(audio, cueAlpha.path) && audio.readyState >= 2 &&
        !audio.paused && audio.currentTime < 0.75;
    }, 10000);
    const replayedCueAudio = latestAcceptanceAudio();
    must(!replayedCueAudio.paused && audioUsesPath(replayedCueAudio, cueAlpha.path),
      "Replay did not restart the individually selected Alpha cue.");

    cueCardBeta.click();
    await waitFor("Beta cue selection stops Alpha", function () {
      const title = document.querySelector("#selectedCueTitle");
      return title && title.textContent.trim() === cueBeta.title && replayedCueAudio.paused &&
        cueCardBeta.getAttribute("aria-pressed") === "true";
    }, 8000);
    playCue.click();
    const cueBetaAudio = await waitForRealPlayback("Beta cue media playback", cueBeta.path);
    must(cueBetaAudio !== replayedCueAudio && audioUsesPath(cueBetaAudio, cueBeta.path),
      "Selecting Beta did not switch the cue preview to Beta's actual audio file.");
    record("cue_audio_preview_play_pause_replay", true,
      "The selected cue's real media source played, paused, resumed and replayed from the beginning.");
    record("cue_preview_track_switch", true,
      "Selecting Beta stopped Alpha and the Play action opened Beta's own audio file.");


    // Import one additional real fixture into each non-Fantasy category.
    document.querySelector('#sound .sound-tabs [data-sound-tab="music"]').click();
    await waitFor("Music Library for category matrix", function () {
      return document.querySelector('#sound .sound-view[data-sound-view="music"]')?.classList.contains("active");
    }, 8000);
    const categoryImport = document.querySelector("#musicImportCategory");
    const categoryImportButton = document.querySelector("#importMusicTracks");
    must(categoryImport && categoryImportButton, "Music category import controls are missing.");
    for (const fixture of (config.category_imports || [])) {
      must(Array.from(categoryImport.options || []).some(option => option.value === fixture.category),
        "Music import category is missing: " + fixture.category);
      categoryImport.value = fixture.category;
      categoryImport.dispatchEvent(new Event("change", {bubbles:true}));
      categoryImportButton.click();
      await waitFor("native import of category " + fixture.category, async function () {
        const rows = await invoke("sound.catalog", {});
        return rows.some(track => String(track.path || "") === String(fixture.path) &&
          String(track.role || "").toLowerCase() === "music" &&
          String(track.category || "").toLowerCase() === fixture.category);
      }, 20000);
    }
    record("music_import_all_eight_categories", true,
      "The actual Music import action saved Fantasy, Battle, Mystery, Horror, Romance, Sci-fi, Calm narration and Others metadata.");

    const allMusicCategory = document.querySelector('#sound .sound-categories-list [data-music-category="all"]');
    const allMusicSource = document.querySelector('#soundSourceFilter [data-source="all"]');
    const importedMusicSource = document.querySelector('#soundSourceFilter [data-source="imported"]');
    const builtInMusicSource = document.querySelector('#soundSourceFilter [data-source="built-in"]');
    must(allMusicCategory && allMusicSource && importedMusicSource && builtInMusicSource,
      "Music Library category/source filters are incomplete.");
    allMusicCategory.click();
    allMusicSource.click();
    await waitFor("all nine imported Music fixtures", function () {
      return musicButtons().length >= 9 &&
        config.track_titles.every(visibleHas) &&
        (config.category_imports || []).every(item => visibleHas(item.title));
    }, 15000);
    const categoryMatrix = [
      {filter:"fantasy-adventure",titles:config.track_titles.slice()},
      ...(config.category_imports || []).map(item => ({filter:item.filter,title:item.title}))
    ];
    for (const entry of categoryMatrix) {
      const button = document.querySelector('#sound .sound-categories-list [data-music-category="' + entry.filter + '"]');
      must(button, "Music category button is missing: " + entry.filter);
      button.click();
      await waitFor("Music category " + entry.filter + " real results", function () {
        const expected = entry.titles || [entry.title];
        const excluded = (config.category_imports || [])
          .filter(item => !expected.includes(item.title))
          .some(item => visibleHas(item.title));
        return button.classList.contains("active") &&
          expected.every(title => visibleHas(title)) && !excluded;
      }, 12000);
    }
    allMusicCategory.click();
    importedMusicSource.click();
    await waitFor("Imported filter contains exactly nine imported music files", function () {
      const rows = musicButtons();
      return rows.length === 9 && rows.every(button => rowText(button).includes("Imported locally"));
    }, 12000);
    builtInMusicSource.click();
    await waitFor("Built-in filter contains only bundled music", function () {
      const rows = musicButtons();
      return rows.length > 0 && rows.every(button => rowText(button).includes("Bundled with application")) &&
        !config.track_titles.some(visibleHas) &&
        !(config.category_imports || []).some(item => visibleHas(item.title));
    }, 12000);
    allMusicSource.click();
    await waitFor("All source filter restores the complete Music Library", function () {
      return config.track_titles.every(visibleHas) &&
        (config.category_imports || []).every(item => visibleHas(item.title));
    }, 12000);
    record("music_all_eight_category_results", true,
      "All eight actual categories returned matching imported tracks, and Built-in/Imported/All source filters remained accurate.");

    // Chapter BGM has its own source/category controls but must use the same
    // actual Music catalogue and never display cue-role assets.
    document.querySelector('#sound .sound-tabs [data-sound-tab="chapters"]').click();
    await waitFor("Chapter BGM view", function () {
      return document.querySelector('#sound .sound-view[data-sound-view="chapters"]')?.classList.contains("active");
    }, 8000);
    await waitFor("Chapter BGM picker and generated controls", function () {
      return document.querySelector("#chapterBgmFilterControls") &&
        document.querySelectorAll("#chapterBgmList [data-chapter-bgm]").length === 3 &&
        document.querySelectorAll("#chapterTrackPicker [data-chapter-track]").length > 0;
    }, 12000);
    const strategyCustom = document.querySelector('#sound [data-bgm-strategy="custom"]');
    must(strategyCustom, "Chapter-Based BGM strategy control is missing.");
    strategyCustom.click();
    await waitFor("Chapter-Based strategy save", async function () {
      return (await invoke("sound.chapter_bgm.get", {})).strategy === "custom";
    }, 15000);
    const chapterSourceAll = document.querySelector('#chapterBgmSourceFilter [data-chapter-source="all"]');
    const chapterSourceBuiltIn = document.querySelector('#chapterBgmSourceFilter [data-chapter-source="built-in"]');
    const chapterSourceImported = document.querySelector('#chapterBgmSourceFilter [data-chapter-source="imported"]');
    must(chapterSourceAll && chapterSourceBuiltIn && chapterSourceImported,
      "Chapter BGM Built-in/Imported/All controls are missing.");
    chapterSourceBuiltIn.click();
    await waitFor("Chapter BGM Built-in rows", function () {
      const rows = Array.from(document.querySelectorAll("#chapterTrackPicker [data-chapter-track]"));
      return rows.length > 0 && rows.every(row => row.textContent.includes("Bundled with application")) &&
        !config.track_titles.some(title => rows.some(row => row.textContent.includes(title))) &&
        !(config.category_imports || []).some(item => rows.some(row => row.textContent.includes(item.title)));
    }, 12000);
    chapterSourceImported.click();
    await waitFor("Chapter BGM Imported rows", function () {
      const rows = Array.from(document.querySelectorAll("#chapterTrackPicker [data-chapter-track]"));
      return rows.length === 9 && rows.every(row => row.textContent.includes("Imported locally"));
    }, 12000);
    chapterSourceAll.click();
    const chapterCategoryMatrix = [
      {filter:"fantasy-adventure",titles:config.track_titles.slice()},
      ...(config.category_imports || []).map(item => ({filter:item.filter,title:item.title}))
    ];
    for (const entry of chapterCategoryMatrix) {
      const button = document.querySelector('#chapterBgmCategoryFilter [data-chapter-category="' + entry.filter + '"]');
      must(button, "Chapter BGM category button is missing: " + entry.filter);
      button.click();
      await waitFor("Chapter BGM category " + entry.filter, function () {
        const rows = Array.from(document.querySelectorAll("#chapterTrackPicker [data-chapter-track]"));
        const expected = entry.titles || [entry.title];
        const excluded = (config.category_imports || [])
          .filter(item => !expected.includes(item.title))
          .some(item => rows.some(row => row.textContent.includes(item.title)));
        return button.classList.contains("active") &&
          expected.every(title => rows.some(row => row.textContent.includes(title))) && !excluded;
      }, 12000);
    }
    document.querySelector('#chapterBgmCategoryFilter [data-chapter-category="all"]').click();
    await waitFor("All Chapter BGM candidate rows", function () {
      return document.querySelectorAll("#chapterTrackPicker [data-chapter-track]").length >= 9;
    }, 12000);
    record("chapter_bgm_all_eight_category_results", true,
      "Chapter BGM returned the matching results for all eight categories and all three source filters.");

    async function selectChapter(number) {
      const chapterRowSelector = '#chapterBgmList [data-chapter-bgm="' + number + '"]';
      const rowToSelect = document.querySelector(chapterRowSelector);
      must(rowToSelect, "Chapter BGM row is missing for chapter " + number + ".");
      rowToSelect.click();
      // The real click handler calls renderChapterBgm(), which replaces the chapter
      // list via innerHTML. Re-query the live DOM during every wait poll rather than
      // checking the detached button instance that received the click.
      await waitFor("Chapter " + number + " selection", function () {
        const selectedRow = document.querySelector(chapterRowSelector);
        return selectedRow?.classList.contains("active") === true &&
          document.querySelector("#chapterBgmTitle")?.textContent.includes("Chapter " + number);
      }, 12000);
    }
    async function chooseChapterCandidate(trackPath, trackTitle) {
      const candidate = Array.from(document.querySelectorAll("#chapterTrackPicker [data-chapter-track]"))
        .find(button => String(button.dataset.chapterTrack || "") === String(trackPath));
      must(candidate, "Chapter BGM candidate is missing: " + trackTitle);
      candidate.click();
      await waitFor("candidate-only panel for " + trackTitle, function () {
        return document.querySelector("#selectedChapterBgmTrackTitle")?.textContent.trim() === trackTitle &&
          document.querySelector("#selectedChapterBgmTrackState")?.textContent.includes("Candidate only");
      }, 8000);
      const confirm = document.querySelector("#confirmChapterBgmTrack");
      must(confirm && !confirm.disabled, "Explicit Select is disabled for " + trackTitle);
    }
    async function setChapterTimingAndVolume(value, startIndex, endIndex) {
      const volumeInput = document.querySelector("#chapterVolume");
      const startInput = document.querySelector("#chapterStartOffset");
      const endInput = document.querySelector("#chapterEndBehavior");
      must(volumeInput && Number(volumeInput.max) === 50 && startInput && endInput,
        "Chapter volume, start-offset or end-behaviour controls are missing or incorrectly bounded.");
      volumeInput.value = String(value);
      volumeInput.dispatchEvent(new Event("input", {bubbles:true}));
      startInput.selectedIndex = startIndex;
      startInput.dispatchEvent(new Event("change", {bubbles:true}));
      endInput.selectedIndex = endIndex;
      endInput.dispatchEvent(new Event("change", {bubbles:true}));
      must(volumeInput.value === String(value) &&
        document.querySelector("#chapterVolumeValue")?.textContent.trim() === value + "%",
        "Chapter BGM live volume percentage did not match the edit.");
    }
    function chapterOverrideFor(state, number) {
      const chapter = (state?.chapters || []).find(row => Number(row.number) === Number(number));
      const chapterId = String(chapter?.chapter_id || "").trim();
      if (chapterId && state?.overrides?.[chapterId] && typeof state.overrides[chapterId] === "object") {
        return state.overrides[chapterId];
      }
      // Older project/API compatibility only; modern projects use the stable ID above.
      const legacy = state?.overrides?.[String(number)];
      return legacy && typeof legacy === "object" ? legacy : {};
    }

    async function waitForChapterSaveComplete(number, rule, expectedPath, expectedValues) {
      let latestState = null;
      await waitFor("Chapter " + number + " save completion and re-enabled editor", async function () {
        latestState = await invoke("sound.chapter_bgm.get", {});
        const row = chapterOverrideFor(latestState, number);
        const controls = [
          document.querySelector("#chapterVolume"),
          document.querySelector("#chapterStartOffset"),
          document.querySelector("#chapterEndBehavior"),
          document.querySelector("#saveChapterBgm")
        ];
        const editorReady = controls.every(control => control && !control.disabled);
        const status = document.querySelector("#chapterBgmSaveState")?.textContent.trim() || "";
        const trackMatches = Boolean(row && row.rule === rule &&
          (expectedPath == null || String(row.path || "") === String(expectedPath)));
        const valuesMatch = !expectedValues || Boolean(row &&
          Math.abs(Number(row.volume) - expectedValues.volume) < 0.005 &&
          row.start_offset === expectedValues.start_offset &&
          row.end_behavior === expectedValues.end_behavior);
        return trackMatches && valuesMatch && editorReady && status === "Chapter assignment saved.";
      }, 18000);
      return latestState;
    }
    async function saveChapter(number, rule, expectedPath, expectedValues) {
      const saveButton = document.querySelector("#saveChapterBgm");
      must(saveButton && !saveButton.disabled,
        "Chapter " + number + " Save control remained disabled before the explicit save.");
      saveButton.click();
      try {
        return await waitForChapterSaveComplete(number, rule, expectedPath, expectedValues);
      } catch (error) {
        const state = await invoke("sound.chapter_bgm.get", {});
        const row = chapterOverrideFor(state, number);
        const status = document.querySelector("#chapterBgmSaveState")?.textContent.trim() || "(missing)";
        throw new Error("Chapter " + number + " values were not confirmed saved. " +
          JSON.stringify({expected:expectedValues || null, actual:row, status, cause:String(error)}));
      }
    }

    await selectChapter(1);
    const stateBeforeCandidate = await invoke("sound.chapter_bgm.get", {});
    await chooseChapterCandidate(alpha.path, config.track_titles[0]);
    const stateAfterCandidate = await invoke("sound.chapter_bgm.get", {});
    must(JSON.stringify(chapterOverrideFor(stateAfterCandidate, 1)) === JSON.stringify(chapterOverrideFor(stateBeforeCandidate, 1)),
      "Candidate selection overwrote Chapter One's saved assignment before confirmation.");
    document.querySelector("#confirmChapterBgmTrack").click();
    // Select saves the candidate asynchronously and disables the editor controls
    // until its backend save + refresh has completed. Do not edit disabled controls
    // or race that refresh with programmatic changes.
    await waitForChapterSaveComplete(1, "custom", alpha.path);
    await setChapterTimingAndVolume(37, 1, 1);
    await saveChapter(1, "custom", alpha.path, {
      volume:0.37, start_offset:"after_first_paragraph", end_behavior:"continue_to_transition"
    });

    await selectChapter(2);
    await chooseChapterCandidate(beta.path, config.track_titles[1]);
    document.querySelector("#confirmChapterBgmTrack").click();
    await waitForChapterSaveComplete(2, "custom", beta.path);
    await setChapterTimingAndVolume(29, 2, 2);
    await saveChapter(2, "custom", beta.path, {
      volume:0.29, start_offset:"after_10_seconds", end_behavior:"stop_immediately"
    });

    await selectChapter(3);
    const noBgmRule = document.querySelector('#sound .chapter-rule [data-chapter-rule="none"]');
    must(noBgmRule, "Chapter No BGM rule is missing.");
    noBgmRule.click();
    await setChapterTimingAndVolume(15, 0, 0);
    await saveChapter(3, "none", null, {
      volume:0.15, start_offset:"immediate", end_behavior:"fade_before_end"
    });
    let savedChapterState = await invoke("sound.chapter_bgm.get", {});
    const chapterOneSaved = chapterOverrideFor(savedChapterState, 1);
    const chapterTwoSaved = chapterOverrideFor(savedChapterState, 2);
    const chapterThreeSaved = chapterOverrideFor(savedChapterState, 3);
    must(chapterOneSaved.start_offset === "after_first_paragraph" &&
      chapterOneSaved.end_behavior === "continue_to_transition" &&
      Math.abs(Number(chapterOneSaved.volume) - 0.37) < 0.005 &&
      chapterTwoSaved.start_offset === "after_10_seconds" &&
      chapterTwoSaved.end_behavior === "stop_immediately" &&
      Math.abs(Number(chapterTwoSaved.volume) - 0.29) < 0.005 &&
      chapterThreeSaved.rule === "none",
      "Chapter track, volume, offset, end behaviour or explicit No BGM did not persist: " +
      JSON.stringify(savedChapterState.overrides));
    record("chapter_bgm_assignment_volume_offsets_end_and_no_fallback", true,
      "Chapter One/Two assignments, independent levels, paragraph/ten-second offsets, end policies and Chapter Three No BGM were saved.");

    document.querySelector('#sound [data-bgm-strategy="same"]').click();
    await waitFor("Same BGM restore", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.strategy === "same" && String(state.default_path || "") === String(alpha.path);
    }, 15000);
    savedChapterState = await invoke("sound.chapter_bgm.get", {});
    must(chapterOverrideFor(savedChapterState, 1).path === alpha.path &&
      chapterOverrideFor(savedChapterState, 2).path === beta.path &&
      chapterOverrideFor(savedChapterState, 3).rule === "none",
      "Same BGM switching erased Chapter-Based assignments.");
    document.querySelector('#sound [data-bgm-strategy="custom"]').click();
    await waitFor("Chapter-Based restored after strategy switch", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.strategy === "custom" &&
        String(chapterOverrideFor(state, 1).path || "") === String(alpha.path) &&
        String(chapterOverrideFor(state, 2).path || "") === String(beta.path);
    }, 15000);
    record("same_and_chapter_strategy_round_trip", true,
      "Same BGM restored the book-default preference; Chapter-Based restored the explicit assignments without fallback or loss.");

    document.querySelector('#sound .sound-tabs [data-sound-tab="cues"]').click();
    await waitFor("cue slot assignment view", function () {
      return document.querySelector('#sound .sound-view[data-sound-view="cues"]')?.classList.contains("active");
    }, 8000);
    async function stageCueAssignment(slot, track) {
      const change = document.querySelector('#sound [data-assign-cue="' + slot + '"]');
      must(change, "Cue Change control is missing for " + slot + ".");
      change.click();
      const card = Array.from(document.querySelectorAll("#cueGrid [data-cue-path]"))
        .find(button => String(button.dataset.cuePath || "") === String(track.path));
      must(card, "Cue asset is missing for " + slot + ": " + track.title);
      card.click();
      await waitFor("staged " + slot + " cue assignment", function () {
        const nameId = slot === "opening" ? "openingCueName" : slot === "chapter" ? "chapterCueName" : "closingCueName";
        return document.querySelector("#" + nameId)?.textContent.includes(track.title);
      }, 8000);
    }
    async function waitForCuePath(slot, trackPath) {
      await waitFor("saved " + slot + " cue path", async function () {
        const state = await invoke("sound.cues.get", {});
        return String(state[slot]?.path || "") === String(trackPath || "");
      }, 15000);
    }
    await stageCueAssignment("opening", cueAlpha);
    await waitForCuePath("opening", cueAlpha.path);
    await stageCueAssignment("chapter", cueBeta);
    await waitForCuePath("chapter", cueBeta.path);
    await stageCueAssignment("closing", cueAlpha);
    await waitForCuePath("closing", cueAlpha.path);
    record("cue_three_slot_autosave_and_production_fields", true,
      "Opening, Next Chapter and Closing cue assignments autosaved into the three supported production fields.");

    config.reject_next_cue_save = true;
    await stageCueAssignment("opening", cueBeta);
    await waitFor("cue-save error remains visible", function () {
      return document.querySelector("#cueSaveState")?.textContent.includes("Save failed");
    }, 12000);
    // Force a second real catalogue refresh while the failed draft is still
    // pending. The failure message and retryable draft must survive it.
    const cueAllSource = document.querySelector('#cueSourceFilter [data-cue-source="all"]');
    must(cueAllSource, "Cue source All filter is missing during save-failure recovery.");
    cueAllSource.click();
    await waitFor("cue-save error survives cue catalogue refresh", function () {
      return document.querySelector("#cueSaveState")?.textContent.includes("Save failed");
    }, 8000);
    const cueStateOnFailure = await invoke("sound.cues.get", {});
    must(String(cueStateOnFailure.opening?.path || "") === String(cueAlpha.path) &&
      document.querySelector("#openingCueName")?.textContent.includes("Unsaved") &&
      document.querySelector("#saveCueChanges").disabled === false,
      "Failed cue save overwrote the previous saved slot, lost the retryable draft, or disabled retry.");
    document.querySelector("#saveCueChanges").click();
    await waitForCuePath("opening", cueBeta.path);
    await waitFor("successful cue-save retry status", function () {
      return document.querySelector("#cueSaveState")?.textContent.includes("All cue changes saved");
    }, 8000);
    await waitFor("cue save debounce and in-flight persistence settle", function () {
      return document.querySelector("#saveCueChanges")?.disabled === true &&
        document.querySelector("#cueSaveState")?.textContent.includes("All cue changes saved");
    }, 12000);
    const cueStateAfterRetry = await invoke("sound.cues.get", {});
    must(String(cueStateAfterRetry.opening?.path || "") === String(cueBeta.path),
      "The explicit cue retry did not persist the new Opening slot.");
    record("cue_save_failure_retains_retryable_changes", true,
      "An injected auto-save failure retained the old assignment and retryable draft through catalogue refresh, then persisted the new slot on explicit retry.");

    document.querySelector("#clearAllCues").click();
    await waitFor("Clear All staged state", function () {
      return document.querySelector("#cueSaveState")?.textContent.includes("Clear All is staged");
    }, 8000);
    const savedBeforeClear = await invoke("sound.cues.get", {});
    must(Boolean(savedBeforeClear.opening?.path && savedBeforeClear.chapter?.path && savedBeforeClear.closing?.path),
      "Clear All removed saved cue assignments before explicit Save Cue Changes.");
    document.querySelector("#saveCueChanges").click();
    await waitFor("explicit Clear All commit", async function () {
      const state = await invoke("sound.cues.get", {});
      return !state.opening?.path && !state.chapter?.path && !state.closing?.path;
    }, 15000);
    await stageCueAssignment("opening", cueBeta);
    await waitForCuePath("opening", cueBeta.path);
    await stageCueAssignment("chapter", cueBeta);
    await waitForCuePath("chapter", cueBeta.path);
    await stageCueAssignment("closing", cueAlpha);
    await waitForCuePath("closing", cueAlpha.path);
    record("cue_clear_all_explicit_and_persisted", true,
      "Clear All remained staged until explicit save, cleared all three slots, and the required final assignments were restored.");
    const cueStateBeforeMix = await invoke("sound.cues.get", {});
    must(String(cueStateBeforeMix.opening?.path || "") === String(cueBeta.path) &&
      String(cueStateBeforeMix.chapter?.path || "") === String(cueBeta.path) &&
      String(cueStateBeforeMix.closing?.path || "") === String(cueAlpha.path),
      "The mixer started before all three cue assignments had reached durable project state.");

    const mixTab = document.querySelector('#sound .sound-tabs [data-sound-tab="mix"]');
    must(mixTab, "Mix & Production Sync tab is missing.");
    mixTab.click();
    await waitFor("Mix & Production Sync view", function () {
      return document.querySelector('#sound .sound-view[data-sound-view="mix"]')?.classList.contains("active");
    }, 8000);
    function editMixLevel(id, value) {
      const input = document.querySelector("#" + id);
      must(input, "Mix level control is missing: " + id);
      input.focus();
      input.value = String(value);
      input.dispatchEvent(new Event("input", {bubbles:true}));
      input.dispatchEvent(new Event("change", {bubbles:true}));
    }
    editMixLevel("advancedMusicVolume", 42);
    editMixLevel("narrationVolume", 82);
    editMixLevel("cueVolume", 30);
    await waitFor("saved BGM/narration/cue levels", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return Math.abs(Number(state.default_volume) - 0.42) < 0.005 &&
        Math.abs(Number(state.narration_volume) - 0.82) < 0.005 &&
        Math.abs(Number(state.cue_volume) - 0.30) < 0.005;
    }, 20000);
    const mixSummarySnapshot = () => ({
      strategy: document.querySelector("#mixStrategy")?.textContent.trim() || "",
      overrides: document.querySelector("#mixOverrides")?.textContent.trim() || "",
      effectiveTracks: document.querySelector("#mixEffectiveTracks")?.textContent.trim() || "",
      bgmVolume: document.querySelector("#advancedMusicVolumeValue")?.textContent.trim() || "",
      narrationVolume: document.querySelector("#narrationVolumeValue")?.textContent.trim() || "",
      cueVolume: document.querySelector("#cueVolumeValue")?.textContent.trim() || ""
    });
    try {
      await waitFor("Mix summary live effective values", function () {
        return document.querySelector("#mixStrategy")?.textContent.includes("Chapter-Based BGM") &&
          document.querySelector("#mixOverrides")?.textContent.includes("3 chapters") &&
          document.querySelector("#mixEffectiveTracks")?.textContent.includes(config.track_titles[0]) &&
          document.querySelector("#mixEffectiveTracks")?.textContent.includes(config.track_titles[1]) &&
          document.querySelector("#advancedMusicVolumeValue")?.textContent.trim() === "42%" &&
          document.querySelector("#narrationVolumeValue")?.textContent.trim() === "82%" &&
          document.querySelector("#cueVolumeValue")?.textContent.trim() === "30%";
      }, 12000);
    } catch (error) {
      throw new Error((error?.message || String(error)) +
        ". Actual Mix Summary: " + JSON.stringify(mixSummarySnapshot()));
    }
    const chapterSummaryState = await invoke("sound.chapter_bgm.get", {});
    const productionMusicSummary = document.querySelector("#productionMusicSummary")?.textContent.trim() || "";
    must(Number(chapterSummaryState.explicit_chapter_track_count) === 2 &&
      productionMusicSummary === "Chapter-Based BGM · 2 unique assigned tracks",
      "Production Studio did not report exactly two unique explicitly assigned chapter tracks. " +
      JSON.stringify({explicit_chapter_track_count:chapterSummaryState.explicit_chapter_track_count,summary:productionMusicSummary}));
    record("mix_summary_and_saved_three_levels", true,
      "Mix summary reflected two effective chapter tracks, three rules, numeric unique-track Production count, and saved 42%/82%/30% levels.");

    async function renderFullBookPreview(label) {
      const button = document.querySelector("#soundPreviewBook");
      must(button, "Full-book Sound Design preview action is missing.");
      window.__RYU_SOUND_UI_ACCEPTANCE_PREVIEW_JOB_ID__ = null;
      button.click();
      await waitFor(label + " job start", function () {
        return Boolean(window.__RYU_SOUND_UI_ACCEPTANCE_PREVIEW_JOB_ID__);
      }, 20000);
      const jobId = window.__RYU_SOUND_UI_ACCEPTANCE_PREVIEW_JOB_ID__;
      let completed = null;
      await waitFor(label + " job completion", async function () {
        const jobs = await invoke("job.list", {include_hidden:false});
        const job = Array.isArray(jobs) ? jobs.find(item => String(item.job_id) === String(jobId)) : null;
        if (!job) return false;
        if (job.state === "failed" || job.state === "cancelled") {
          throw new Error(label + " failed: " + String(job.message || job.state));
        }
        if (job.state === "completed") { completed = job; return true; }
        return false;
      }, 240000);
      const result = completed && completed.result ? completed.result : {};
      const duration = Number(result.duration_seconds || 0);
      must(duration > 0 && (result.output_path || completed.output_path),
        label + " did not create a measurable full-book audio file.");
      const audio = latestAcceptanceAudio();
      if (audio && !audio.paused) audio.pause();
      return {duration, output_path:result.output_path || completed.output_path, sound_configuration:result.sound_configuration || {}};
    }

    document.querySelector('#sound [data-bgm-strategy="same"]').click();
    await waitFor("Same BGM ready for real mixer", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.strategy === "same" && String(state.default_path || "") === String(alpha.path);
    }, 15000);
    const samePreview = await renderFullBookPreview("Same BGM preview");
    must(samePreview.duration >= 45, "Same BGM preview omitted the saved cue sequence.");
    must(samePreview.sound_configuration.background_audio_mode === "manual" &&
      samePreview.sound_configuration.fixed_cues_enabled === true &&
      Object.values(samePreview.sound_configuration.effective_cue_slots || {}).every(Boolean),
      "Same BGM preview did not pass all saved fixed cue slots to the mixer: " +
      JSON.stringify(samePreview.sound_configuration));
    document.querySelector('#sound [data-bgm-strategy="custom"]').click();
    await waitFor("Chapter-Based restored for full preview", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.strategy === "custom" &&
        String(state.overrides?.["1"]?.path || "") === String(alpha.path) &&
        String(state.overrides?.["2"]?.path || "") === String(beta.path);
    }, 15000);
    const chapterPreview = await renderFullBookPreview("Chapter-Based preview");
    must(chapterPreview.duration >= 45 &&
      Math.abs(chapterPreview.duration - samePreview.duration) <= 2.0,
      "Chapter-Based preview did not preserve the same narration/cue duration as Same BGM.");
    must(chapterPreview.sound_configuration.background_audio_mode === "manual" &&
      chapterPreview.sound_configuration.fixed_cues_enabled === true &&
      Object.values(chapterPreview.sound_configuration.effective_cue_slots || {}).every(Boolean),
      "Chapter-Based preview did not pass all saved fixed cue slots to the mixer: " +
      JSON.stringify(chapterPreview.sound_configuration));
    record("same_and_chapter_based_real_full_book_preview", true,
      "Both strategies rendered real full-book M4B previews from saved narration using the shared FFmpeg mixer.");

    const voiceOnly = document.querySelector('#sound [data-bgm-enabled="false"]');
    must(voiceOnly, "Sound Design Voice Only toggle is missing.");
    voiceOnly.click();
    await waitFor("Voice Only mode persisted", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.bgm_enabled === false && state.background_audio_mode === "off";
    }, 15000);
    const voiceOnlyPreview = await renderFullBookPreview("Voice Only preview");
    const voiceOnlyConfig = voiceOnlyPreview.sound_configuration || {};
    must(voiceOnlyConfig.background_audio_mode === "off" &&
      voiceOnlyConfig.background_audio_enabled === false &&
      voiceOnlyConfig.fixed_cues_enabled === false &&
      Object.values(voiceOnlyConfig.effective_cue_slots || {}).every(value => value === false),
      "Voice Only preview passed saved BGM/cues to the mixer: " + JSON.stringify(voiceOnlyConfig));
    const removedCueSeconds = chapterPreview.duration - voiceOnlyPreview.duration;
    must(removedCueSeconds >= 11.5,
      "Voice Only duration did not remove the three saved fixed cue slots within 0.5s AAC tolerance: " +
      "chapterPreview=" + chapterPreview.duration.toFixed(3) + "s; " +
      "voiceOnlyPreview=" + voiceOnlyPreview.duration.toFixed(3) + "s; " +
      "removed=" + removedCueSeconds.toFixed(3) + "s; " +
      "configuration=" + JSON.stringify(voiceOnlyConfig));
    record("voice_only_removes_bgm_and_cues_from_real_preview", true,
      "Voice Only excluded all saved fixed cues; measured timeline reduction was " +
      removedCueSeconds.toFixed(3) + "s.");

    document.querySelector('#sound [data-bgm-enabled="true"]').click();
    await waitFor("Use BGM restored", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.bgm_enabled === true && state.background_audio_mode === "manual";
    }, 15000);

    const narrationInput = document.querySelector("#narrationVolume");
    narrationInput.focus();
    narrationInput.value = "82";
    narrationInput.dispatchEvent(new Event("input", {bubbles:true}));
    config.fail_next_manifest_save = true;
    document.querySelector("#applySoundToProduction").click();
    await sleep(1500);
    must(document.querySelector("#sound")?.classList.contains("active") &&
      !document.querySelector("#generate")?.classList.contains("active"),
      "Production handoff navigated despite a sound-manifest save failure.");
    must(document.querySelector("#mixLevelsSaveState")?.textContent.includes("Unsaved") ||
      document.querySelector("#mixOverallSaveState")?.textContent.includes("Unsaved"),
      "Failed Production handoff did not retain a visible unsaved status.");
    document.querySelector("#applySoundToProduction").click();
    await waitFor("successful Production handoff retry", function () {
      return document.querySelector("#generate")?.classList.contains("active");
    }, 15000);
    const handedOff = await invoke("sound.chapter_bgm.get", {});
    must(Math.abs(Number(handedOff.narration_volume) - 0.82) < 0.005 &&
      document.querySelector("#productionMusicSummary")?.textContent.includes("Chapter-Based BGM") &&
      document.querySelector("#productionSoundReady")?.textContent.includes("Synced"),
      "Production handoff did not persist the latest mix level or display saved Chapter-Based BGM.");
    const activeProductionProject = await invoke("project.get_active", {});
    must(activeProductionProject && activeProductionProject.folder,
      "Production handoff left no active saved project.");
    await waitFor("source-backed Production project summary", function () {
      return document.querySelector("#productionBookTitle")?.textContent.trim() ===
        String(activeProductionProject.title || "Untitled audiobook");
    }, 12000);
    const productionText = document.querySelector("#generate")?.textContent || "";
    must(!productionText.includes("Slime Vol. 2") &&
      !productionText.includes("Fuse · English") &&
      !productionText.includes("20 / 23") &&
      !productionText.includes("Partial audio found for Chapter 18"),
      "Production Studio still shows hard-coded prototype project/readiness values.");
    must(document.querySelector("#productionBookMetadata")?.textContent.includes(
      String(activeProductionProject.author || "Author not set")) &&
      document.querySelector("#productionOutputSummary")?.textContent.includes(
      String(activeProductionProject.output_target_path || activeProductionProject.output_path || "")),
      "Production Studio did not display saved book metadata and its actual output target.");
    must(document.querySelector("#productionBookImported") &&
      document.querySelector("#productionChaptersReady") &&
      document.querySelector("#productionNarratorReady") &&
      document.querySelector("#productionCharacterVoices") &&
      document.querySelector("#productionPronunciationReady") &&
      document.querySelector("#productionOutputReady"),
      "Production Studio readiness summary is missing one or more live project fields.");
    must(document.querySelector("#productionMusicSummary")?.textContent.trim() ===
      "Chapter-Based BGM · 2 unique assigned tracks",
      "Production Studio unique assigned-track summary is incorrect after handoff.");
    record("production_handoff_save_error_gate_and_retry", true,
      "A failed save blocked navigation; retry opened Production with live metadata, output destination, readiness fields and exact unique chapter-track count.");

    const narratorProfileName = String(config.narrator_profile_name || "").trim();
    must(narratorProfileName, "The packaged Voice Studio narrator profile fixture is missing.");
    const selectedNarrator = await invoke("voice.select", {
      profile_name:narratorProfileName, backend:"automatic"
    });
    must(selectedNarrator && selectedNarrator.saved === true &&
      String(selectedNarrator.name || "") === narratorProfileName,
      "Voice Studio did not save the selected narrator profile through its real bridge command.");
    await waitFor("real selected narrator in active project summary", async function () {
      const refreshed = await invoke("project.get_active", {});
      return String(refreshed.narrator || "") === narratorProfileName &&
        String(refreshed.voice_profile || "") === narratorProfileName &&
        refreshed.narrator_profile_available === true;
    }, 12000);
    // The bridge command above is the saved project selection. Keep the visible
    // Voice Studio profile field synchronized as well, because Production's
    // start guard reads the visible current profile before the backend resolves
    // the authoritative saved narrator again.
    const activeProfileInput = document.querySelector("#profileName");
    must(activeProfileInput, "Voice Studio selected profile field is missing.");
    activeProfileInput.value = narratorProfileName;
    activeProfileInput.dispatchEvent(new Event("input", {bubbles:true}));
    const metadataButton = document.querySelector("#openProjectDetails");
    must(metadataButton, "Production Studio Input Project Details button is missing.");
    metadataButton.click();
    await waitFor("Input Project Details dialog", function () {
      return Boolean(document.querySelector("#inputProjectDetailsDialog")?.open);
    }, 12000);

    const metadataFields = [
      "metadataTitle", "metadataAuthor", "metadataNarrator", "metadataPublisher",
      "metadataSeries", "metadataSeriesVolume", "metadataLanguage", "metadataYear",
      "metadataGenre", "metadataCoverPath"
    ];
    for (const id of metadataFields) {
      must(document.getElementById(id), "Input Project Details field is missing: " + id);
    }
    must(document.querySelector("#metadataNarrator")?.readOnly === true &&
      String(document.querySelector("#metadataNarrator")?.value || "") === narratorProfileName,
      "Narrator must display the actual selected Voice Studio profile in a read-only field.");
    const history = config.metadata_history || {};
    const historyFields = [
      ["metadataHistoryAuthor", history.author],
      ["metadataHistoryPublisher", history.publisher],
      ["metadataHistorySeries", history.series],
      ["metadataHistorySeries_volume", history.series_volume],
      ["metadataHistoryLanguage", history.language],
      ["metadataHistoryYear", history.year],
      ["metadataHistoryGenre", history.genre]
    ];
    for (const [id, expected] of historyFields) {
      const values = [...(document.getElementById(id)?.querySelectorAll("option") || [])].map(option => option.value);
      must(values.includes(String(expected || "")), "A real saved historical value was not loaded into " + id + ".");
    }

    const expectedMetadata = config.metadata || {};
    const metadataInputValues = {
      metadataTitle:expectedMetadata.title,
      metadataAuthor:expectedMetadata.author,
      metadataPublisher:expectedMetadata.publisher,
      metadataSeries:expectedMetadata.series,
      metadataSeriesVolume:expectedMetadata.series_volume,
      metadataLanguage:expectedMetadata.language,
      metadataYear:expectedMetadata.year,
      metadataGenre:expectedMetadata.genre,
      metadataCoverPath:config.metadata_cover_path
    };
    for (const [id, value] of Object.entries(metadataInputValues)) {
      const element = document.getElementById(id);
      element.value = String(value || "");
      element.dispatchEvent(new Event("input", {bubbles:true}));
    }
    must(document.querySelector("#productionMetadataStatus")?.textContent.includes("Unsaved changes"),
      "Unsaved project metadata did not mark the Production completion gate as pending.");
    must(document.querySelector("#startGenerate")?.disabled === true,
      "Full generation remained enabled while metadata edits were unsaved/incomplete.");
    must(document.querySelector("#previewGenerate")?.disabled !== true,
      "Preview generation was incorrectly blocked by incomplete metadata.");

    config.fail_next_metadata_save = true;
    document.querySelector("#projectMetadataSave").click();
    await waitFor("metadata save failure status", function () {
      return document.querySelector("#projectMetadataStatus")?.textContent.includes("Save failed");
    }, 12000);
    const afterFailedSave = await invoke("project.get_active", {});
    must(String(afterFailedSave.title || "") === String(config.original_project_title || "") &&
      !String(afterFailedSave.author || "").trim(),
      "A failed metadata save changed the active project's saved metadata.");
    must(document.querySelector("#inputProjectDetailsDialog")?.open === true &&
      document.querySelector("#productionMetadataStatus")?.textContent.includes("Unsaved changes"),
      "A failed metadata save closed the editor or lost the unsaved state.");

    document.querySelector("#projectMetadataSave").click();
    await waitFor("metadata save success and dialog close", function () {
      return document.querySelector("#inputProjectDetailsDialog")?.open === false &&
        document.querySelector("#productionBookTitle")?.textContent.trim() === String(expectedMetadata.title || "");
    }, 15000);
    const savedMetadata = await invoke("project.get_active", {});
    const normalizedSavedCoverPath = String(savedMetadata.cover_path || "")
      .split(String.fromCharCode(92)).join("/").toLowerCase();
    const expectedSavedMetadata = {
      title:String(expectedMetadata.title || ""),
      author:String(expectedMetadata.author || ""),
      publisher:String(expectedMetadata.publisher || ""),
      series:String(expectedMetadata.series || ""),
      series_volume:String(expectedMetadata.series_volume || ""),
      language:String(expectedMetadata.language || ""),
      year:String(expectedMetadata.year || ""),
      genre:String(expectedMetadata.genre || "")
    };
    const metadataMismatches = Object.entries(expectedSavedMetadata)
      .filter(([key, value]) => String(savedMetadata[key] || "") !== value)
      .map(([key, value]) => key + ": expected " + JSON.stringify(value) +
        ", received " + JSON.stringify(savedMetadata[key]));
    if (!normalizedSavedCoverPath.endsWith("/assets/cover.png")) {
      metadataMismatches.push("cover_path: expected project-local /assets/cover.png, received " +
        JSON.stringify(savedMetadata.cover_path));
    }
    must(metadataMismatches.length === 0,
      "The metadata save response did not reflect saved project fields: " +
      metadataMismatches.join("; "));
    must(String(savedMetadata.narrator || "") === narratorProfileName,
      "The metadata save did not preserve the selected Voice Studio narrator profile.");
    must(savedMetadata.metadata_complete === false &&
      (savedMetadata.metadata_missing_fields || []).includes("Publisher"),
      "The saved metadata gate did not identify the intentionally missing required Publisher field.");
    must(document.querySelector("#startGenerate")?.disabled === true &&
      document.querySelector("#previewGenerate")?.disabled !== true &&
      document.querySelector("#productionMetadataStatus")?.textContent.includes("Publisher"),
      "After saving partial metadata, full generation was not blocked with the exact missing Publisher field while Preview remained available.");
    record("production_metadata_dialog_history_save_error_and_gate", true,
      "The packaged dialog loaded historical values, displayed a real selected Voice Studio narrator, surfaced a forced save error, succeeded on retry, persisted a validated project cover and blocked full generation for the missing required Publisher field.");

    const productionVoiceOnly = document.querySelector('#generate [data-bgm-enabled="false"]');
    must(productionVoiceOnly, "Production Studio Voice Only mode toggle is missing.");
    productionVoiceOnly.click();
    await waitFor("Production Voice Only synchronization", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.bgm_enabled === false && state.background_audio_mode === "off";
    }, 15000);
    const productionUseBgm = document.querySelector('#generate [data-bgm-enabled="true"]');
    must(productionUseBgm, "Production Studio Use BGM mode toggle is missing.");
    productionUseBgm.click();
    await waitFor("Production Use BGM synchronization", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.bgm_enabled === true && state.background_audio_mode === "manual";
    }, 15000);
    record("production_mode_toggles_share_sound_manifest", true,
      "Production Studio Voice Only and Use BGM controls persisted through the same Sound Design state.");
    await waitFor("all Sound Design preview jobs have reached terminal state before Stage 5.4", async function () {
      const jobs = await invoke("job.list", {include_hidden:true});
      return Array.isArray(jobs) && jobs.every(job =>
        job.type !== "sound-design-preview" ||
        !["queued","running","pause_requested","paused","cancel_requested","retrying"].includes(String(job.state || "")));
    }, 30000);
    const durableMixStateBeforeStage54 = await invoke("sound.chapter_bgm.get", {});
    must(durableMixStateBeforeStage54.bgm_enabled === true &&
      durableMixStateBeforeStage54.background_audio_mode === "manual" &&
      String(durableMixStateBeforeStage54.overrides?.["1"]?.path || "") === String(alpha.path) &&
      String(durableMixStateBeforeStage54.overrides?.["2"]?.path || "") === String(beta.path),
      "The Sound Design project did not return to its durable Chapter-Based state before Stage 5.4 job-control acceptance.");

    const productionPronunciationToggle = document.querySelector("#productionPronunciationToggle");
    must(productionPronunciationToggle,
      "Production Studio global Pronunciation ON/OFF control is missing.");
    const initialPronunciationState = await invoke("pronunciation.settings.get", {});
    must(typeof initialPronunciationState?.enabled === "boolean",
      "The active project's saved global pronunciation setting is not available.");
    productionPronunciationToggle.checked = false;
    productionPronunciationToggle.dispatchEvent(new Event("change", {bubbles:true}));
    await waitFor("Production global pronunciation OFF persistence and peer synchronization", async function () {
      const settings = await invoke("pronunciation.settings.get", {});
      return settings.enabled === false &&
        productionPronunciationToggle.checked === false &&
        document.querySelector("#pronunciationGlobalToggle")?.checked === false;
    }, 15000);
    productionPronunciationToggle.checked = true;
    productionPronunciationToggle.dispatchEvent(new Event("change", {bubbles:true}));
    await waitFor("Production global pronunciation ON persistence and peer synchronization", async function () {
      const settings = await invoke("pronunciation.settings.get", {});
      return settings.enabled === true &&
        productionPronunciationToggle.checked === true &&
        document.querySelector("#pronunciationGlobalToggle")?.checked === true;
    }, 15000);
    record("stage5_production_global_pronunciation_toggle_persistence", true,
      "The actual Production Studio switch saved OFF then ON to the active project and synchronized the Pronunciation Studio switch both ways.");

    async function openProjectFromDashboard(folder, label) {
      window.go("dashboard");
      await waitFor("Dashboard recent project cards", function () {
        return Boolean(document.querySelector("#dashboard .recent-grid [data-project-folder]"));
      }, 15000);
      let card = Array.from(document.querySelectorAll("#dashboard .recent-grid [data-project-folder]"))
        .find(node => String(node.dataset.projectFolder || "") === String(folder));
      if (card) {
        card.click();
      } else {
        // The Dashboard intentionally shows only the latest three projects.
        // New acceptance fixtures may not be in that recent slice; use the full
        // Library grid's normal Open project action instead of treating this as
        // a product failure or bypassing the project's UI-open lifecycle.
        window.go("library");
        await waitFor("Library project card list", function () {
          return Boolean(document.querySelector("#libraryGrid [data-project-folder]"));
        }, 15000);
        card = Array.from(document.querySelectorAll("#libraryGrid [data-project-folder]"))
          .find(node => String(node.dataset.projectFolder || "") === String(folder));
        must(card, label + " project is missing from the full local Library list.");
        const openButton = card.querySelector("[data-open-project]");
        must(openButton, label + " Library card has no real Open project action.");
        openButton.click();
        record("stage54_library_open_fallback", true,
          "A Stage 5.4 fixture outside Dashboard's three recent cards was opened through the full Library grid's real Open project action.");
      }
      await waitFor(label + " project active after UI navigation", async function () {
        const active = await invoke("project.get_active", {});
        return String(active?.folder || "") === String(folder);
      }, 20000);
    }
    await openProjectFromDashboard(config.secondary_project_folder, "Secondary");
    await waitFor("Secondary project active", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return Array.isArray(state.chapters) && state.chapters.length === 1;
    }, 20000);
    const secondaryCues = await invoke("sound.cues.get", {});
    must(!secondaryCues.opening?.path && !secondaryCues.chapter?.path && !secondaryCues.closing?.path,
      "Secondary project inherited another book's fixed cue assignments.");
    const globalCatalogue = await invoke("sound.catalog", {});
    const missingGlobal = (config.category_imports || []).filter(item =>
      !globalCatalogue.some(track => String(track.path || "") === String(item.path)));
    must(missingGlobal.length === 0,
      "Imported Music Library assets disappeared after switching projects: " + missingGlobal.map(item => item.title).join(", "));
    record("project_switch_isolates_book_settings_and_keeps_global_library", true,
      "Dashboard project switch isolated cue settings while all imported Music Library categories remained globally available.");

    await openProjectFromDashboard(config.project_folder, "Primary");
    await waitFor("Primary project restored", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return Array.isArray(state.chapters) && state.chapters.length === 3 &&
        state.strategy === "custom" &&
        String(state.overrides?.["1"]?.path || "") === String(alpha.path) &&
        String(state.overrides?.["2"]?.path || "") === String(beta.path);
    }, 20000);
    const primaryCues = await invoke("sound.cues.get", {});
    must(primaryCues.opening?.path === cueBeta.path &&
      primaryCues.chapter?.path === cueBeta.path &&
      primaryCues.closing?.path === cueAlpha.path,
      "Returning from the secondary project changed the primary book's cue assignments.");
    record("project_switch_restores_primary_sound_design", true,
      "Returning through Dashboard restored the original strategy, chapter BGM settings and all three cue slots.");

    // Stage 5.2 packaged Production Preview acceptance: use the actual frozen
    // application's Production chapter selector, preview worker, job monitor,
    // sound renderer and audio controls (not a mocked bridge response).
    window.go("generate");
    await waitFor("Production Studio chapter preview controls", function () {
      return document.querySelector("#generate")?.classList.contains("active") === true &&
        Boolean(document.querySelector("#productionPreviewChapterSelect")) &&
        Boolean(document.querySelector("#previewGenerate"));
    }, 20000);
    const savedPreviewChapters = await invoke("chapter.list", {});
    must(Array.isArray(savedPreviewChapters) && savedPreviewChapters.length === 3,
      "Production Preview did not load the three saved chapter records.");
    const chosenPreviewChapter = savedPreviewChapters.find(chapter => Number(chapter.number) === 2);
    must(chosenPreviewChapter && String(chosenPreviewChapter.text || "").trim(),
      "The Production Preview acceptance chapter has no saved narration text.");
    const chosenPreviewChapterId = String(chosenPreviewChapter.chapter_id || chosenPreviewChapter.id || "");
    const productionChapterPicker = document.querySelector("#productionPreviewChapterSelect");
    await waitFor("Production Preview saved chapter options loaded", function () {
      const options = Array.from(productionChapterPicker?.options || []);
      return options.length === savedPreviewChapters.length &&
        savedPreviewChapters.every(chapter => options.some(option =>
          option.value === String(chapter.number) &&
          option.textContent.includes(String(chapter.title || ""))));
    }, 12000);
    async function selectProductionPreviewChapter(number, expectedTitle) {
      const optionFor = chapterNumber => Array.from(productionChapterPicker.options || [])
        .find(option => option.value === String(chapterNumber));
      const waitForSelection = async chapterNumber => {
        const expectedOption = optionFor(chapterNumber);
        const expectedChapter = savedPreviewChapters.find(item => Number(item.number) === Number(chapterNumber));
        await waitFor("Production-owned Chapter " + chapterNumber + " selection", function () {
          const optionText = productionChapterPicker.selectedOptions?.[0]?.textContent || "";
          const statusText = document.querySelector("#productionPreviewStatus")?.textContent || "";
          return productionChapterPicker.value === String(chapterNumber) &&
            Boolean(expectedOption && expectedOption.selected) &&
            optionText.includes("Chapter " + chapterNumber) &&
            (!expectedChapter?.title || optionText.includes(String(expectedChapter.title))) &&
            statusText.includes("Chapter " + chapterNumber + " selected.");
        }, 10000);
      };
      // If Chapter 2 is already auto-selected, a change to the same value is
      // intentionally a no-op in the production UI. Select another saved
      // chapter first so the target selection event is genuinely fired.
      if (Number(productionChapterPicker.value) === Number(number)) {
        const alternate = savedPreviewChapters.find(item => Number(item.number) !== Number(number));
        must(alternate, "Production Preview needs at least two saved chapters to exercise chapter selection.");
        productionChapterPicker.value = String(alternate.number);
        productionChapterPicker.dispatchEvent(new Event("change", {bubbles:true}));
        await waitForSelection(Number(alternate.number));
      }
      productionChapterPicker.value = String(number);
      productionChapterPicker.dispatchEvent(new Event("change", {bubbles:true}));
      await waitForSelection(Number(number));
      const selectedOption = optionFor(number);
      must(selectedOption && (!expectedTitle || selectedOption.textContent.includes(expectedTitle)),
        "Production Preview selected a chapter option with the wrong saved title.");
    }
    await selectProductionPreviewChapter(2, String(chosenPreviewChapter.title || ""));
    const durationButtons = Array.from(document.querySelectorAll("#generate .segmented button"));
    const supportedPreviewDurations = ["10s", "30s", "60s", "90s"];
    const durationControls = supportedPreviewDurations.map(label =>
      durationButtons.find(button => String(button.textContent || "").trim().includes(label))
    );
    must(durationControls.every(Boolean),
      "Production Preview must expose all 10/30/60/90-second duration options.");
    for (let index = 0; index < durationControls.length; index++) {
      durationControls[index].click();
      await waitFor("Production Preview " + supportedPreviewDurations[index] + " duration selection", function () {
        return durationControls[index].classList.contains("active");
      }, 5000);
    }
    durationControls[0].click();
    await waitFor("Production Preview 10-second duration restored", function () {
      return durationControls[0].classList.contains("active");
    }, 5000);

    const productionVoiceOnlyToggle = document.querySelector('#generate [data-bgm-enabled="false"]');
    must(productionVoiceOnlyToggle, "Production Preview acceptance cannot find its Voice Only configuration.");
    productionVoiceOnlyToggle.click();
    await waitFor("Production Preview saved Voice Only mode", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.background_audio_mode === "off" && state.bgm_enabled === false;
    }, 15000);

    const productionPreviewStart = document.querySelector("#previewGenerate");
    must(productionPreviewStart && !productionPreviewStart.disabled,
      "The real Production Preview action is not enabled for a saved chapter and narrator.");
    productionPreviewStart.click();
    let productionPreviewJob = null;
    await waitFor("real Production Preview job start", async function () {
      const jobs = await invoke("job.list", {include_hidden:true});
      productionPreviewJob = Array.isArray(jobs)
        ? jobs.find(job => job.type === "production-preview" &&
            Number(job.current_chapter || 0) === 2 &&
            ["queued", "running", "cancel_requested"].includes(String(job.state || "").toLowerCase()))
        : null;
      return Boolean(productionPreviewJob && productionPreviewJob.job_id);
    }, 20000);
    must(String(productionPreviewJob.project_folder || "") === String((await invoke("project.get_active", {})).folder || ""),
      "Production Preview job was not scoped to the active project.");
    must(!chosenPreviewChapterId || String(productionPreviewJob.current_chapter_id || "") === chosenPreviewChapterId,
      "Production Preview job did not preserve the selected stable chapter identity.");
    // A job can finish while the user has navigated away from Production.
    // The monitor is page-scoped and intentionally stops repainting while hidden.
    // Re-open Generate before asserting its visible snapshot, then allow the page
    // observer/job poll to synchronize the latest backend job into the monitor.
    if (!document.querySelector("#generate")?.classList.contains("active")) {
      window.go("generate");
    }
    await waitFor("Production Preview monitor page is visible", function () {
      const page = document.querySelector("#generate");
      return Boolean(page && page.classList.contains("active") &&
        !page.classList.contains("hidden") && page.getClientRects().length > 0);
    }, 15000);
    try {
      await waitFor("Production Preview monitor selected chapter identity", function () {
        const label = String(document.querySelector("#productionPreviewChapter")?.textContent || "");
        const expectedTitle = String(chosenPreviewChapter.title || "");
        const page = document.querySelector("#generate");
        return Boolean(page && page.classList.contains("active") &&
          label.includes("Chapter 2") && (!expectedTitle || label.includes(expectedTitle)));
      }, 15000);
    } catch (error) {
      const latestJobs = await invoke("job.list", {include_hidden:true});
      const latestPreviewJob = Array.isArray(latestJobs)
        ? latestJobs.find(job => String(job.job_id || "") === String(productionPreviewJob.job_id || ""))
        : null;
      throw new Error(String(error?.message || error) + ". Production preview monitor diagnostic=" + JSON.stringify({
        monitorChapter:document.querySelector("#productionPreviewChapter")?.textContent || null,
        monitorStatus:document.querySelector("#productionPreviewStatus")?.textContent || null,
        generatePageActive:document.querySelector("#generate")?.classList.contains("active") || false,
        selectedChapter:document.querySelector("#productionPreviewChapterSelect")?.value || null,
        jobState:latestPreviewJob?.state || null,
        jobStage:latestPreviewJob?.stage || null,
        jobChapter:latestPreviewJob?.current_chapter || null,
        jobChapterTitle:latestPreviewJob?.current_chapter_title || null,
        jobChapterId:latestPreviewJob?.current_chapter_id || null,
        jobProject:latestPreviewJob?.project_folder || null
      }));
    }
    const productionPreviewJobId = String(productionPreviewJob.job_id);
    let completedProductionPreview = null;
    await waitFor("real Production Preview audio completion", async function () {
      const jobs = await invoke("job.list", {include_hidden:true});
      const latest = Array.isArray(jobs)
        ? jobs.find(job => String(job.job_id || "") === productionPreviewJobId)
        : null;
      if (!latest) return false;
      const state = String(latest.state || "").toLowerCase();
      if (state === "failed" || state === "cancelled") {
        throw new Error("Production chapter preview ended " + state + ": " + String(latest.message || ""));
      }
      if (state === "completed") {
        completedProductionPreview = latest;
        return true;
      }
      return false;
    }, 360000);
    const productionPreviewResult = completedProductionPreview.result || {};
    const productionPreviewPath = String(productionPreviewResult.output_path || completedProductionPreview.output_path || "");
    const productionPlaybackUrl = String(productionPreviewResult.file_url || "").toLowerCase();
    const productionPlaybackPath = String(productionPreviewResult.playback_output_path || "");
    const initialPreviewSeconds = Number(productionPreviewResult.actual_duration_seconds || 0);
    const previewOwnerFolder = String(productionPreviewJob.project_folder || "");
    const previewOwnerChapterId = String(productionPreviewJob.current_chapter_id || "");
    must(previewOwnerFolder === String((await invoke("project.get_active", {})).folder || "") &&
      (!chosenPreviewChapterId || previewOwnerChapterId === String(chosenPreviewChapterId)) &&
      String(completedProductionPreview.project_folder || "") === previewOwnerFolder &&
      String(completedProductionPreview.current_chapter_id || "") === previewOwnerChapterId &&
      Boolean(productionPreviewPath),
      "Completed Production Preview changed project/chapter ownership or lost its registered output: " +
        JSON.stringify({
          started:productionPreviewJob,
          completed:completedProductionPreview,
          expectedChapterId:chosenPreviewChapterId
        }));
    record("stage6_chapter_preview_owner_project_and_stable_chapter_identity", true,
      "The real completed Production Preview retained its originating project folder, stable Chapter Studio identity and registered preview output.");
    must(Number(productionPreviewResult.requested_duration_seconds || 0) === 10 &&
      initialPreviewSeconds >= 5 && initialPreviewSeconds <= 15 &&
      productionPreviewPath.toLowerCase().endsWith(".m4a") &&
      productionPlaybackUrl.startsWith("file:") &&
      productionPlaybackUrl.endsWith(".wav") &&
      productionPlaybackPath.toLowerCase().endsWith(".wav") &&
      productionPreviewResult.playback_format === "wav",
      "Production Preview 10-second request must return a measured 5–15 second M4A and verified PCM WAV playback copy: " +
        JSON.stringify(productionPreviewResult));
    must(productionPreviewResult.sound_configuration?.background_audio_mode === "off" &&
      productionPreviewResult.sound_configuration?.fixed_cues_enabled === false,
      "Production Preview did not apply the saved Voice Only configuration: " +
        JSON.stringify(productionPreviewResult.sound_configuration));
    try {
      await waitFor("Production Preview playable/downloadable UI", function () {
        const play = document.querySelector("#productionPreviewPlay");
        const save = document.querySelector("#productionPreviewDownload");
        return document.querySelector("#productionPreviewStatus")?.textContent.includes("Preview ready") &&
          play && !play.disabled && save && !save.disabled;
      }, 30000);
    } catch (error) {
      const jobs = await invoke("job.list", {include_hidden:true});
      const snapshot = Array.isArray(jobs)
        ? jobs.find(job => String(job.job_id || "") === productionPreviewJobId)
        : null;
      throw new Error(String(error?.message || error) + ". Production Preview diagnostic=" + JSON.stringify({
        status:document.querySelector("#productionPreviewStatus")?.textContent || null,
        playDisabled:document.querySelector("#productionPreviewPlay")?.disabled ?? null,
        saveDisabled:document.querySelector("#productionPreviewDownload")?.disabled ?? null,
        voicePreviewState:document.querySelector("#previewState")?.textContent || null,
        validation:document.querySelector("#validation")?.textContent || null,
        jobState:snapshot?.state || null,
        jobMessage:snapshot?.message || null,
        jobChapter:snapshot?.current_chapter || null,
        jobChapterId:snapshot?.current_chapter_id || null,
        jobFolder:snapshot?.project_folder || null,
        result:snapshot?.result || null
      }));
    }
    const productionPreviewPlay = document.querySelector("#productionPreviewPlay");
    const productionPreviewStop = document.querySelector("#productionPreviewStop");
    const productionPreviewReplay = document.querySelector("#productionPreviewReplay");
    must(productionPreviewStop && productionPreviewReplay,
      "Production Preview Play/Stop/Replay controls are incomplete.");
    productionPreviewPlay.click();
    await waitFor("Production Preview real playback start", function () {
      return document.querySelector("#productionPreviewPlay")?.textContent.includes("Pause preview");
    }, 12000);
    productionPreviewPlay.click();
    await waitFor("Production Preview playback pause", function () {
      return document.querySelector("#productionPreviewPlay")?.textContent.includes("Play preview");
    }, 8000);
    productionPreviewStop.click();
    productionPreviewReplay.click();
    await waitFor("Production Preview replay", function () {
      return document.querySelector("#productionPreviewPlay")?.textContent.includes("Pause preview");
    }, 12000);
    productionPreviewStop.click();
    const productionPreviewSaveButton = document.querySelector("#productionPreviewDownload");
    must(productionPreviewSaveButton && !productionPreviewSaveButton.disabled,
      "Save Production Preview remained disabled after the validated chapter audio completed.");
    document.querySelector("#toasts")?.classList.remove("show");
    productionPreviewSaveButton.click();
    await waitFor("Production Preview actual Save As copy", function () {
      return String(document.querySelector("#toasts")?.textContent || "")
        .includes("Production chapter preview saved to");
    }, 20000);
    record("stage5_production_preview_real_save_as", true,
      "The packaged Production Save button invoked the native validated-job save bridge and completed a real M4A copy into the isolated acceptance output folder.");
    record("stage5_production_preview_real_chapter_audio_playback_and_duration_controls", true,
      "The frozen app generated Chapter Two only, returned measured M4A audio with a PCM WAV playback URL, applied saved Voice Only mode, and passed Play/Pause/Stop/Replay with all four duration controls available.");

    // Verify additional real output targets rather than only cycling the
    // duration buttons. The long saved Chapter Two fixture contains enough
    // narration to exercise both the 30s performance target and 60s cap.
    let previousDurationJobId = productionPreviewJobId;
    for (const target of [
      {label:"30s",seconds:30,button:durationControls[1]},
      {label:"60s",seconds:60,button:durationControls[2]},
      {label:"90s",seconds:90,button:durationControls[3]}
    ]) {
      target.button.click();
      await waitFor("Production Preview " + target.label + " real duration selection", function () {
        return target.button.classList.contains("active");
      }, 5000);
      productionPreviewStart.click();
      let targetJobId = "";
      await waitFor("Production Preview " + target.label + " job start", async function () {
        const jobs = await invoke("job.list", {include_hidden:true});
        const active = Array.isArray(jobs)
          ? jobs.find(job => job.type === "production-preview" &&
              Number(job.current_chapter || 0) === 2 &&
              ["queued", "running"].includes(String(job.state || "").toLowerCase()) &&
              String(job.job_id || "") !== previousDurationJobId)
          : null;
        if (!active) return false;
        targetJobId = String(active.job_id || "");
        return Boolean(targetJobId);
      }, 20000);
      let targetJob = null;
      await waitFor("Production Preview " + target.label + " real audio completion", async function () {
        const jobs = await invoke("job.list", {include_hidden:true});
        targetJob = Array.isArray(jobs)
          ? jobs.find(job => String(job.job_id || "") === targetJobId)
          : null;
        if (!targetJob) return false;
        const state = String(targetJob.state || "").toLowerCase();
        if (state === "failed" || state === "cancelled") {
          throw new Error("Production Preview " + target.label + " ended " + state + ": " + String(targetJob.message || ""));
        }
        return state === "completed";
      }, 360000);
      const targetResult = targetJob.result || {};
      const targetOutput = String(targetResult.output_path || targetJob.output_path || "");
      const targetPlaybackUrl = String(targetResult.file_url || "").toLowerCase();
      const actualSeconds = Number(targetResult.actual_duration_seconds || 0);
      const durationTolerance = Math.max(5, target.seconds * 0.2);
      must(Number(targetResult.requested_duration_seconds || 0) === target.seconds &&
        actualSeconds > 0 &&
        targetOutput.toLowerCase().endsWith(".m4a") &&
        targetPlaybackUrl.startsWith("file:") && targetPlaybackUrl.endsWith(".wav") &&
        targetResult.playback_format === "wav" &&
        actualSeconds >= target.seconds - 5 &&
        actualSeconds <= target.seconds + durationTolerance,
        "Production Preview " + target.label + " did not produce a valid M4A and matching WAV within the bounded chapter-segment duration tolerance: " +
          JSON.stringify({target_seconds:target.seconds,actual_seconds:actualSeconds,tolerance_seconds:durationTolerance,result:targetResult}));
      await waitFor("Production Preview " + target.label + " playback readiness", function () {
        return document.querySelector("#productionPreviewStatus")?.textContent.includes("Preview ready") &&
          document.querySelector("#productionPreviewPlay") && !document.querySelector("#productionPreviewPlay").disabled;
      }, 20000);
      record("stage5_production_preview_real_" + target.seconds + "_second_audio", true,
        "The frozen app generated a measured " + Number(targetResult.actual_duration_seconds).toFixed(2) +
          "s chapter-only M4A with separate PCM WAV playback for the " + target.label + " target.");
      previousDurationJobId = targetJobId;
    }

    // Exercise a real cancellation request against a second, longer target.
    // The chapter worker is deliberately started through the actual Production
    // button so the dedicated job ID, Cancel Preview control and terminal state
    // all use the real backend worker rather than a direct mocked call.
    const cancellationChapter = savedPreviewChapters.find(chapter => Number(chapter.number) === 3);
    must(cancellationChapter && String(cancellationChapter.text || "").trim(),
      "The Production Preview cancellation chapter has no saved narration text.");
    await selectProductionPreviewChapter(3, String(cancellationChapter.title || ""));
    durationControls[3].click();
    await waitFor("Production Preview 90-second cancellation target", function () {
      return durationControls[3].classList.contains("active");
    }, 5000);
    productionPreviewStart.click();
    let cancelPreviewJobId = "";
    await waitFor("Production Preview cancellation control enabled", async function () {
      const cancel = document.querySelector("#productionPreviewCancel");
      if (!cancel || cancel.disabled) return false;
      const jobs = await invoke("job.list", {include_hidden:true});
      const active = Array.isArray(jobs)
        ? jobs.find(job => job.type === "production-preview" &&
            Number(job.current_chapter || 0) === 3 &&
            ["queued", "running", "cancel_requested"].includes(String(job.state || "").toLowerCase()) &&
            String(job.job_id || "") !== productionPreviewJobId)
        : null;
      if (!active) return false;
      cancelPreviewJobId = String(active.job_id || "");
      return Boolean(cancelPreviewJobId);
    }, 15000);
    const cancelPreviewButton = document.querySelector("#productionPreviewCancel");
    cancelPreviewButton.click();
    let cancelledPreviewJob = null;
    await waitFor("Production Preview real cancellation completion", async function () {
      const jobs = await invoke("job.list", {include_hidden:true});
      cancelledPreviewJob = Array.isArray(jobs)
        ? jobs.find(job => String(job.job_id || "") === cancelPreviewJobId)
        : null;
      if (!cancelledPreviewJob) return false;
      const state = String(cancelledPreviewJob.state || "").toLowerCase();
      if (state === "failed") throw new Error("Production Preview cancellation failed: " + String(cancelledPreviewJob.message || ""));
      return state === "cancelled" || state === "completed";
    }, 120000);
    must(String(cancelledPreviewJob.state || "").toLowerCase() === "cancelled",
      "Production Preview worker completed before its cancel request was honored.");
    record("stage5_production_preview_real_cancellation", true,
      "The Production Preview Cancel control cancelled its own in-flight production-preview job.");

    // Preview acceptance deliberately switched the saved project to Voice Only
    // to prove that BGM and cues were excluded. Restore the fixture's original
    // enabled Chapter-Based mode before the native post-run persistence validator
    // and restart phase execute. This is test cleanup, not a product-state change
    // hidden from the real UI: use the same Production master control and verify
    // the persisted project state through the native bridge.
    const restoreProductionUseBgm = document.querySelector('#generate [data-bgm-enabled="true"]');
    must(restoreProductionUseBgm,
      "Production Studio Use BGM control is missing for restoration after preview acceptance.");
    restoreProductionUseBgm.click();
    await waitFor("Restore original enabled Chapter-Based BGM after preview acceptance", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.bgm_enabled === true &&
        state.background_audio_mode === "manual" &&
        ["custom", "chapter-based", "chapter_based", "chapter"].includes(String(state.strategy || "").toLowerCase()) &&
        restoreProductionUseBgm.classList.contains("active");
    }, 15000);
    record("stage5_production_preview_restores_sound_master_state_for_restart_validation", true,
      "After Voice Only parity tests and cancellation, the real Production master control restored the saved enabled Chapter-Based BGM state before process restart.");

    // Stage 5.3 GEN-01 packaged runtime acceptance: move to an isolated
    // one-chapter project and run the real frozen-app full-generation command
    // using the saved bundled Piper voice. No generation bridge responses are
    // faked here; only the later UI-state rendering test uses synthetic job rows.
    await openProjectFromDashboard(config.full_generation_project_folder, "Stage 5.3 full-generation");
    await waitFor("Stage 5.3 full-generation project activation", async function () {
      const active = await invoke("project.get_active", {});
      return String(active.folder || "") === String(config.full_generation_project_folder || "");
    }, 20000);
    const savedGenerationNarrator = await invoke("voice.select", {
      profile_name:narratorProfileName, backend:"automatic"
    });
    must(savedGenerationNarrator && savedGenerationNarrator.saved === true &&
      String(savedGenerationNarrator.name || "") === narratorProfileName,
      "The Stage 5.3 generation project could not persist its selected Offline Neural narrator.");
    const generationProject = await invoke("project.get_active", {});
    must(String(generationProject.voice_profile || generationProject.narrator || "") === narratorProfileName,
      "The full-generation project did not retain the saved narrator profile.");
    must(String(generationProject.publisher || "").trim() &&
      String(generationProject.author || "").trim() &&
      String(generationProject.cover_path || "").trim(),
      "The isolated full-generation project is missing required saved metadata or cover details.");
    window.go("generate");
    await waitFor("Stage 5.3 Production full-generation controls", function () {
      return document.querySelector("#generate")?.classList.contains("active") === true &&
        Boolean(document.querySelector("#startGenerate"));
    }, 20000);
    await waitFor("Stage 5.3 full-generation metadata gate", function () {
      const button = document.querySelector("#startGenerate");
      return Boolean(button && !button.disabled);
    }, 20000);
    const jobsBeforeFullGeneration = await invoke("job.list", {include_hidden:true});
    const priorGenerationIds = new Set((Array.isArray(jobsBeforeFullGeneration) ? jobsBeforeFullGeneration : [])
      .filter(job => job.type === "audiobook-generation")
      .map(job => String(job.job_id || "")));
    document.querySelector("#startGenerate").click();
    let fullGenerationJobId = "";
    await waitFor("real packaged full-generation job start", async function () {
      const jobs = await invoke("job.list", {include_hidden:true});
      const job = Array.isArray(jobs) ? jobs.find(item =>
        item.type === "audiobook-generation" &&
        String(item.project_folder || "") === String(config.full_generation_project_folder || "") &&
        !priorGenerationIds.has(String(item.job_id || "")) &&
        Boolean(item.job_id)) : null;
      if (!job) return false;
      fullGenerationJobId = String(job.job_id);
      return true;
    }, 30000);
    let fullGenerationJob = null;
    await waitFor("real packaged full-generation completion", async function () {
      const jobs = await invoke("job.list", {include_hidden:true});
      fullGenerationJob = Array.isArray(jobs)
        ? jobs.find(item => String(item.job_id || "") === fullGenerationJobId) : null;
      if (!fullGenerationJob) return false;
      const state = String(fullGenerationJob.state || "").toLowerCase();
      if (state === "failed" || state === "cancelled") {
        throw new Error("Packaged full generation ended " + state + ": " +
          String(fullGenerationJob.error?.message || fullGenerationJob.message || ""));
      }
      return state === "completed";
    }, 360000);
    const generationHistory = await invoke("history.list", {});
    const historyGenerationJob = Array.isArray(generationHistory)
      ? generationHistory.find(item => String(item.job_id || "") === fullGenerationJobId) : null;
    const completedGenerationProject = await invoke("project.get_active", {});
    const normalizeOutputPath = value => String(value || "").replace(/\\/g, "/").toLowerCase();
    const expectedGenerationOutput = normalizeOutputPath(config.full_generation_output_path);
    must(fullGenerationJob.state === "completed" &&
      normalizeOutputPath(fullGenerationJob.output_path) === expectedGenerationOutput &&
      Number(fullGenerationJob.result?.chapters_total || 0) === 2 &&
      Number(fullGenerationJob.result?.chapters_completed || 0) === 2 &&
      Number(fullGenerationJob.result?.empty_chapters_skipped || 0) === 1 &&
      Number(fullGenerationJob.result?.excluded_chapters_skipped || 0) === 1,
      "The full-generation job did not complete two eligible chapters in order while skipping one empty and one excluded chapter: " +
        JSON.stringify({job:fullGenerationJob, expected:config.full_generation_output_path}));
    must(historyGenerationJob && historyGenerationJob.state === "completed" &&
      String(historyGenerationJob.job_id || "") === fullGenerationJobId &&
      String(historyGenerationJob.project_folder || "") === String(config.full_generation_project_folder || "") &&
      normalizeOutputPath(historyGenerationJob.output_path) === expectedGenerationOutput,
      "The completed full-generation job and durable History do not share the same job/project/output identity.");
    must(String(completedGenerationProject.folder || "") === String(config.full_generation_project_folder || "") &&
      completedGenerationProject.completed === true &&
      String(completedGenerationProject.status || "").toLowerCase() === "completed" &&
      Number(completedGenerationProject.completed_chapter_count || 0) === 2 &&
      Number(completedGenerationProject.empty_chapters_skipped || 0) === 1 &&
      Number(completedGenerationProject.excluded_chapters_skipped || 0) === 1 &&
      normalizeOutputPath(completedGenerationProject.output_path) === expectedGenerationOutput,
      "The completed two-chapter output and empty/excluded counts were not visible on its owning project summary.");
    record("stage54_packaged_real_multi_chapter_full_generation", true,
      "The frozen Windows app synthesized two eligible chapters in saved order with the saved bundled Offline Neural narrator, skipped one empty and one excluded chapter, completed one GenerationManager job, persisted its identical History job ID, and associated the M4B output only with its owning project.");

    // Stage 5.5 GEN-05 / Audiobooks handoff: inspect the finished file itself,
    // not project.json fallback chapter names, then play and seek the embedded M4B.
    const finalM4b = await invoke("player.get_active", {
      folder:String(config.full_generation_project_folder || "")
    });
    const finalM4bChapters = Array.isArray(finalM4b.chapters) ? finalM4b.chapters : [];
    must(normalizeOutputPath(finalM4b.output_path) === expectedGenerationOutput &&
      String(finalM4b.format || "").toLowerCase() === ".m4b" &&
      finalM4bChapters.length === 2 &&
      finalM4bChapters.every(chapter =>
        String(chapter.title || "").trim() &&
        Number.isFinite(Number(chapter.start_seconds)) &&
        Number.isFinite(Number(chapter.end_seconds)) &&
        Number(chapter.end_seconds) > Number(chapter.start_seconds)),
      "The finished M4B did not return its actual timed chapter-marker table to the Audiobooks player: " +
        JSON.stringify({format:finalM4b.format,output_path:finalM4b.output_path,chapters:finalM4bChapters}));
    must(Math.abs(Number(finalM4bChapters[0].start_seconds)) <= 0.15 &&
      Number(finalM4bChapters[1].start_seconds) > Number(finalM4bChapters[0].start_seconds) &&
      Math.abs(Number(finalM4bChapters[1].start_seconds) - Number(finalM4bChapters[0].end_seconds)) <= 1.5,
      "The embedded chapter markers are not ordered at contiguous chapter boundaries: " +
        JSON.stringify(finalM4bChapters));
    record("stage55_final_m4b_embedded_chapters", true,
      "The backend read two actual embedded M4B chapter markers with titles and valid ordered start/end timing from the completed output file.");

    window.go("player");
    await waitFor("Stage 5.5 Audiobooks page activation", function () {
      const page = document.querySelector("#player");
      return Boolean(page && page.classList.contains("active"));
    }, 15000);
    let finishedBookButton = null;
    await waitFor("completed M4B appears in Premium V2 Audiobooks library", function () {
      finishedBookButton = Array.from(document.querySelectorAll("#player [data-play-project-folder]"))
        .find(button => String(button.dataset.playProjectFolder || "") === String(config.full_generation_project_folder || ""));
      return Boolean(finishedBookButton);
    }, 20000);
    finishedBookButton.click();
    must(normalizeOutputPath(finalM4b.playback_output_path) &&
      String(finalM4b.playback_format || "").toLowerCase() === "mp3" &&
      String(finalM4b.source_file_url || "").toLowerCase().includes(
        String(config.full_generation_output_path || "").split(/[\\/]/).pop().toLowerCase()
      ),
      "Audiobooks did not return a browser-compatible playback copy linked to the authoritative M4B: " +
        JSON.stringify({output_path:finalM4b.output_path,source_file_url:finalM4b.source_file_url,
          playback_output_path:finalM4b.playback_output_path,playback_format:finalM4b.playback_format}));
    record("stage55_browser_compatible_playback_source", true,
      "The original chaptered AAC M4B remains the library asset; the player received a cached MP3 decoded from that exact source for Qt WebEngine compatibility.");
    const finishedM4bAudio = await waitForRealPlayback(
      "real completed M4B audio through the Audiobooks player",
      finalM4b.playback_output_path
    );
    await waitFor("Audiobooks renders actual embedded chapter rows", function () {
      const rows = Array.from(document.querySelectorAll("#player [data-audiobook-chapter-start]"));
      return rows.length === 2 && rows.every(row => row.getAttribute("aria-disabled") !== "true");
    }, 15000);
    const embeddedChapterRows = Array.from(document.querySelectorAll("#player [data-audiobook-chapter-start]"));
    const expectedSecondStart = Number(finalM4bChapters[1].start_seconds);
    embeddedChapterRows[1].click();
    await waitFor("Audiobooks chapter navigation seeks to second embedded chapter", function () {
      return Number.isFinite(Number(finishedM4bAudio.currentTime)) &&
        Math.abs(Number(finishedM4bAudio.currentTime) - expectedSecondStart) <= 1.25;
    }, 10000);
    finishedM4bAudio.pause();
    await waitFor("Audiobooks stores project-scoped listening position", async function () {
      const refreshed = await invoke("player.get_active", {
        folder:String(config.full_generation_project_folder || "")
      });
      return Number(refreshed.playback_position_seconds || 0) >= expectedSecondStart - 0.15;
    }, 15000);

    // Stage 6 Step 3 — verify full-player stage6Controls and embedded chapter playback.
    const stage6PlayerPage=document.querySelector("#player"), stage6MainPlay=document.querySelector("#mainPlay"),
      stage6Timeline=document.querySelector("#playerTimeline"), stage6TimeLabels=document.querySelector("#currentTime")?.parentElement?.querySelectorAll("span"),
      stage6Volume=stage6PlayerPage?.querySelector(".player-grid .toolbar input.range"),
      stage6SpeedButtons=Array.from(stage6PlayerPage?.querySelectorAll(".player-grid .toolbar .segmented button")||[]),
      stage6Controls=Array.from(stage6PlayerPage?.querySelectorAll(".player-controls button")||[]);
    must(stage6MainPlay&&stage6Timeline&&stage6TimeLabels?.length>=2&&stage6Volume&&stage6SpeedButtons.length>=2&&stage6Controls.length>=5,
      "Stage 6 AB-03 stage6Controls missing from full player.");
    const stage6ActualDuration=Number(finishedM4bAudio.duration);
    must(Number.isFinite(stage6ActualDuration)&&stage6ActualDuration>0,"Actual decoded audio duration unavailable.");
    const stage6FmtTime=seconds=>{const n=Math.max(0,Math.floor(Number(seconds)||0)),h=Math.floor(n/3600),m=Math.floor(n%3600/60),s=n%60;
      return h?h+":"+String(m).padStart(2,"0")+":"+String(s).padStart(2,"0"):m+":"+String(s).padStart(2,"0");};
    must(stage6TimeLabels[1].textContent.trim()===stage6FmtTime(stage6ActualDuration),"Total-time label differs from actual duration.");
    record("stage6_player_seek_and_time_display",true,"Time display uses the actual decoded audio duration.");
    if (finishedM4bAudio.paused) {
      stage6MainPlay.click();
      await waitFor("selected audiobook is playing before Pause/Resume acceptance",()=>
        !finishedM4bAudio.paused,5000);
    }
    const stage6BeforeAudioCount=(window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__||[]).length;
    stage6MainPlay.click();
    await waitFor("Pause affects actual audio",()=>finishedM4bAudio.paused&&stage6MainPlay.textContent.trim()==="▶",5000);
    stage6MainPlay.click();
    await waitFor("Play resumes same audio",()=>!finishedM4bAudio.paused&&stage6MainPlay.textContent.trim()!=="▶",5000);
    must((window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__||[]).length===stage6BeforeAudioCount,"Play/Pause created duplicate audio.");
    record("stage6_player_full_controls_actual_audio",true,"Play/Pause control toggled the actual decoded media element.");
    window.go("dashboard");
    const stage6MiniDock=document.querySelector("#miniPlayer");
    await waitFor("mini-player becomes visible outside the Audiobooks page",()=>
      Boolean(stage6MiniDock&&!stage6MiniDock.classList.contains("hidden")&&stage6MiniDock.getClientRects().length),5000);
    const stage6MiniPlay=stage6MiniDock.querySelector("#miniPlay");
    must(stage6MiniPlay,"Persistent mini-player Play/Pause button is missing.");
    stage6MiniPlay.click();
    await waitFor("visible mini-player pauses the selected audio",()=>finishedM4bAudio.paused&&
      stage6MainPlay.textContent.trim()==="▶"&&stage6MiniPlay.textContent.trim()==="▶",5000);
    stage6MiniPlay.click();
    await waitFor("visible mini-player resumes the same audio",()=>!finishedM4bAudio.paused&&
      stage6MainPlay.textContent.trim()!=="▶"&&stage6MiniPlay.textContent.trim()!=="▶",5000);
    must((window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__||[]).length===stage6BeforeAudioCount,
      "Mini-player Play/Pause created a second Audio element.");
    record("stage6_mini_player_shares_full_player_audio_session",true,
      "The visible Dashboard mini-player and full-player controls operate the same real Audio object and synchronize their icons.");
    window.go("player");
    await waitFor("Audiobooks page returns after mini-player acceptance",()=>
      document.querySelector("#player")?.classList.contains("active")===true,5000);

    stage6Timeline.value="10"; stage6Timeline.dispatchEvent(new Event("input",{bubbles:true}));
    await waitFor("seek slider changes real currentTime",()=>Math.abs(finishedM4bAudio.currentTime-stage6ActualDuration*0.1)<1,5000);
    await waitFor("elapsed label follows the actual seek position",()=>
      stage6TimeLabels[0].textContent.trim()===stage6FmtTime(finishedM4bAudio.currentTime),5000);
    stage6Volume.value="0"; stage6Volume.dispatchEvent(new Event("input",{bubbles:true}));
    must(Math.abs(finishedM4bAudio.volume)<0.01,"Volume slider does not support 0%.");
    stage6Volume.value="100"; stage6Volume.dispatchEvent(new Event("input",{bubbles:true}));
    must(Math.abs(finishedM4bAudio.volume-1)<0.01,"Volume slider does not support 100%.");
    stage6Volume.value="37"; stage6Volume.dispatchEvent(new Event("input",{bubbles:true}));
    stage6Volume.dispatchEvent(new Event("change",{bubbles:true}));
    must(Math.abs(finishedM4bAudio.volume-0.37)<0.02,"Volume control did not update actual media.");
    let stage6SavedPreferences=null;
    await waitFor("player volume preference persists",async()=>{
      const [settings,player]=await Promise.all([
        invoke("settings.get",{}),
        invoke("player.get_active",{folder:String(config.full_generation_project_folder||"")})
      ]);
      stage6SavedPreferences={settings,player};
      return Math.abs(Number(settings.player_volume)-0.37)<0.02&&
        Math.abs(Number(player.playback_volume)-0.37)<0.02;
    },8000);
    const stage6Rate=stage6SpeedButtons.find(b=>Math.abs(Number(b.textContent.replace("×","").trim())-1.25)<0.01);
    must(stage6Rate,"No 1.25× speed option."); stage6Rate.click();
    must(Math.abs(finishedM4bAudio.playbackRate-1.25)<0.01&&stage6Rate.classList.contains("active"),"Rate not applied to real media.");
    await waitFor("player playback speed preference persists",async()=>{
      const [settings,player]=await Promise.all([
        invoke("settings.get",{}),
        invoke("player.get_active",{folder:String(config.full_generation_project_folder||"")})
      ]);
      stage6SavedPreferences={settings,player};
      return Math.abs(Number(settings.player_rate)-1.25)<0.01&&
        Math.abs(Number(player.playback_rate)-1.25)<0.01;
    },8000);
    record("stage6_player_volume_and_rate_affect_audio",true,"Volume and playback speed modify actual audio and both preferences persist.");
    finishedM4bAudio.currentTime=5; stage6Controls[0].click();
    await waitFor("rewind clamps to start",()=>finishedM4bAudio.currentTime<=0.15,5000);
    finishedM4bAudio.currentTime=Math.max(0,stage6ActualDuration-2); stage6Controls[4].click();
    await waitFor("forward clamps to end",()=>Math.abs(finishedM4bAudio.currentTime-stage6ActualDuration)<=0.15,5000);
    record("stage6_player_15_second_seek_clamps",true,"15-second skip stage6Controls clamp to actual audio boundaries.");
    const stage6ChapterRows=Array.from(document.querySelectorAll("#player [data-audiobook-chapter-start]"));
    must(stage6ChapterRows.length===finalM4bChapters.length&&stage6ChapterRows.every((row,i)=>
      Math.abs(Number(row.dataset.audiobookChapterStart)-Number(finalM4bChapters[i].start_seconds))<0.001&&
      Math.abs(Number(row.dataset.audiobookChapterEnd)-Number(finalM4bChapters[i].end_seconds))<0.001),
      "Chapter intervals differ from embedded M4B marker table.");
    must(stage6ChapterRows.every((row,i)=>{
      const timeLabel=row.querySelector('[data-audiobook-chapter-time="true"]');
      return Boolean(timeLabel) &&
        timeLabel.textContent.includes(stage6FmtTime(finalM4bChapters[i].start_seconds)) &&
        timeLabel.textContent.includes(stage6FmtTime(finalM4bChapters[i].end_seconds));
    }),"Visible chapter timestamps do not match the embedded M4B start/end markers.");
    record("stage6_chapter_embedded_timestamps_visible",true,
      "Each chapter row visibly displays its embedded M4B start and end timestamp.");
    const stage6ActiveRow=()=>stage6ChapterRows.find(row=>row.classList.contains("active")&&row.getAttribute("aria-current")==="true"&&row.getAttribute("aria-pressed")==="true");
    const stage6Heading=()=>document.querySelector("#player .player-grid > .card:nth-child(2) h2")?.textContent.trim()||"";
    finishedM4bAudio.pause(); finishedM4bAudio.currentTime=Number(finalM4bChapters[0].start_seconds);
    await waitFor("chapter one highlighted from playhead",()=>stage6ActiveRow()===stage6ChapterRows[0],5000);
    stage6ChapterRows[1].click();
    await waitFor("chapter selection seeks and starts real audio",()=>!finishedM4bAudio.paused&&
      Math.abs(finishedM4bAudio.currentTime-Number(finalM4bChapters[1].start_seconds))<1&&stage6ActiveRow()===stage6ChapterRows[1]&&
      stage6Heading().includes(String(finalM4bChapters[1].title)),8000);
    record("stage6_chapter_select_seeks_to_embedded_marker",true,"Selecting chapter seeks and starts actual playback at embedded time.");
    finishedM4bAudio.pause(); finishedM4bAudio.currentTime=Number(finalM4bChapters[0].start_seconds);
    await waitFor("chapter highlight follows seek",()=>stage6ActiveRow()===stage6ChapterRows[0]&&stage6Heading().includes(String(finalM4bChapters[0].title)),5000);
    record("stage6_chapter_playhead_highlight_tracks_boundaries",true,"Current chapter row and stage6Heading track embedded marker interval.");
    const stage6FirstStart=Number(finalM4bChapters[0].start_seconds);
    const stage6SecondStart=Number(finalM4bChapters[1].start_seconds);
    const stage6ApproachGap=Math.min(0.8,Math.max(0.15,(stage6SecondStart-stage6FirstStart)/2));
    finishedM4bAudio.currentTime=Math.max(stage6FirstStart,stage6SecondStart-stage6ApproachGap);
    await waitFor("first chapter active before continuous boundary crossing",()=>stage6ActiveRow()===stage6ChapterRows[0],5000);
    await finishedM4bAudio.play();
    await waitFor("continuous playback crosses into next embedded chapter",()=>!finishedM4bAudio.paused&&
      finishedM4bAudio.currentTime>=stage6SecondStart&&stage6ActiveRow()===stage6ChapterRows[1]&&
      stage6Heading().includes(String(finalM4bChapters[1].title)),10000);
    record("stage6_chapter_continuous_playback_updates_active_row",true,
      "While real audio played across the embedded boundary, the active chapter row and heading moved to the next chapter.");
    finishedM4bAudio.pause();

    stage6ChapterRows[1].dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}));
    await waitFor("keyboard Enter selects and plays embedded chapter",()=>!finishedM4bAudio.paused&&
      Math.abs(finishedM4bAudio.currentTime-Number(finalM4bChapters[1].start_seconds))<1&&
      stage6ActiveRow()===stage6ChapterRows[1],8000);
    record("stage6_chapter_keyboard_activation_starts_audio",true,
      "Keyboard Enter starts actual audio at the selected embedded chapter marker.");
    finishedM4bAudio.pause();
    finishedM4bAudio.currentTime=Number(finalM4bChapters[0].start_seconds);
    await waitFor("first chapter active before Space activation",()=>stage6ActiveRow()===stage6ChapterRows[0],5000);
    stage6ChapterRows[1].dispatchEvent(new KeyboardEvent("keydown",{key:" ",bubbles:true}));
    await waitFor("keyboard Space selects and plays embedded chapter",()=>!finishedM4bAudio.paused&&
      Math.abs(finishedM4bAudio.currentTime-Number(finalM4bChapters[1].start_seconds))<1&&
      stage6ActiveRow()===stage6ChapterRows[1],8000);
    record("stage6_chapter_space_activation_starts_audio",true,
      "Keyboard Space starts actual audio at the selected embedded chapter marker.");
    finishedM4bAudio.pause();
    stage6Controls[3].click();
    await waitFor("Next Chapter",()=>Math.abs(finishedM4bAudio.currentTime-Number(finalM4bChapters[1].start_seconds))<1,5000);
    stage6Controls[1].click();
    await waitFor("Previous Chapter",()=>Math.abs(finishedM4bAudio.currentTime-Number(finalM4bChapters[0].start_seconds))<1,5000);
    stage6Controls[1].click();
    await waitFor("Previous at first chapter remains at the first marker",()=>
      Math.abs(finishedM4bAudio.currentTime-Number(finalM4bChapters[0].start_seconds))<1,5000);
    stage6Controls[3].click();
    await waitFor("Next moves to the last embedded chapter",()=>
      Math.abs(finishedM4bAudio.currentTime-Number(finalM4bChapters[1].start_seconds))<1,5000);
    stage6Controls[3].click();
    await waitFor("Next at last chapter remains within the final marker",()=>
      finishedM4bAudio.currentTime>=Number(finalM4bChapters[1].start_seconds)-0.15,5000);
    stage6Controls[1].click();
    await waitFor("Previous returns to first chapter boundary",()=>
      Math.abs(finishedM4bAudio.currentTime-Number(finalM4bChapters[0].start_seconds))<1,5000);
    record("stage6_previous_next_chapter_navigation",true,
      "Previous/Next navigate actual embedded chapter order and remain within first/last chapter boundaries.");
    const stage6OtherBook=Array.from(document.querySelectorAll("#player [data-open-project-folder]"))
      .find(b=>String(b.dataset.openProjectFolder||"")!==String(config.full_generation_project_folder||""));
    must(stage6OtherBook,"Second completed book unavailable for stale-event test.");
    const stage6StaleAudio=finishedM4bAudio; stage6OtherBook.click();
    await waitFor("book switch renders replacement chapter data",()=>latestAcceptanceAudio()!==stage6StaleAudio&&
      document.querySelectorAll("#player [data-audiobook-chapter-start]").length===1,15000);
    const stage6NewHeading=stage6Heading(),stage6NewTime=document.querySelector("#currentTime")?.textContent||"";
    stage6StaleAudio.currentTime=Math.min(Number(stage6StaleAudio.duration)||0,0.5); stage6StaleAudio.dispatchEvent(new Event("timeupdate"));
    must(stage6Heading()===stage6NewHeading&&(document.querySelector("#currentTime")?.textContent||"")===stage6NewTime,
      "Stale old-player event mutated the new book UI.");
    record("stage6_switching_book_clears_previous_chapter_selection",true,"Switch clears old chapters and stale audio events cannot mutate new player.");
    latestAcceptanceAudio()?.pause(); stage6StaleAudio.pause();

    record("stage55_audiobooks_real_playback_chapter_seek_and_position", true,
      "The real finished M4B played in Premium V2, chapter navigation sought to its embedded second marker, and the owning project's playback position was persisted.");

    // Stage 6 AB-01: verify multiple compact cards against real completed M4B outputs,
    // then exercise Open (load paused), Play (actual audio), and switching book identity.
    const libraryFixtures = Array.isArray(config.audiobook_library_fixtures) ? config.audiobook_library_fixtures : [];
    must(libraryFixtures.length >= 2, "Stage 6 Audiobooks Library requires two completed M4B fixtures.");
    window.go("player");
    await waitFor("Stage 6 Premium V2 Audiobooks library page", function () {
      return document.querySelector("#player")?.classList.contains("active") === true;
    }, 15000);
    await waitFor("Stage 6 multiple completed audiobook cards", function () {
      const cards = Array.from(document.querySelectorAll("#backendAudiobookLibrary .audiobook-library-card"));
      return libraryFixtures.every(fixture => cards.some(card =>
        String(card.dataset.projectFolder || "") === String(fixture.folder || "")));
    }, 20000);
    const libraryCards = Array.from(document.querySelectorAll("#backendAudiobookLibrary .audiobook-library-card"));
    for (const fixture of libraryFixtures) {
      const card = libraryCards.find(item =>
        String(item.dataset.projectFolder || "") === String(fixture.folder || ""));
      must(card, "A completed audiobook card is missing for " + fixture.title + ".");
      const status = card.querySelector("[data-audiobook-status]");
      const cover = card.querySelector(".audiobook-card-cover");
      const openButton = card.querySelector("[data-open-project-folder]");
      const playButton = card.querySelector("[data-play-project-folder]");
      must(card.querySelector(".audiobook-card-title")?.textContent.trim() === fixture.title &&
        status?.dataset.status === "completed" && status.textContent.trim() === "Completed" &&
        cover && Boolean(cover.style.backgroundImage) &&
        cover.style.backgroundImage.includes(fixture.cover_file_name) &&
        openButton && playButton,
        "Audiobook card title, actual status, cover association or Open/Play actions are incorrect: " +
          JSON.stringify({title:fixture.title,status:status?.textContent,cover:cover?.style.backgroundImage}));
    }
    record("stage6_audiobooks_compact_multiple_real_output_cards", true,
      "Multiple compact Premium V2 audiobook cards show each fixture's own cover, title, backend completion status and separate Open/Play actions.");

    const firstFixture = libraryFixtures[0];
    const firstCard = libraryCards.find(item =>
      String(item.dataset.projectFolder || "") === String(firstFixture.folder || ""));
    const existingAudioBeforeOpen = latestAcceptanceAudio();
    const existingAudioFolder = String(existingAudioBeforeOpen?.dataset?.projectFolder || "");
    const sameBookAlreadyLoaded = Boolean(existingAudioBeforeOpen?.src &&
      existingAudioFolder === String(firstFixture.folder || ""));
    const audioCountBeforeOpen = (window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || []).length;
    must(firstCard, "First completed audiobook card is unavailable for the Open-action test.");
    firstCard.querySelector("[data-open-project-folder]").click();
    await waitFor("Stage 6 Open loads the selected audiobook without autoplay", function () {
      const audio = latestAcceptanceAudio();
      const audioCount = (window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || []).length;
      const sameAudioReused = sameBookAlreadyLoaded && audio === existingAudioBeforeOpen;
      const newAudioLoaded = !sameBookAlreadyLoaded && audio && audio !== existingAudioBeforeOpen && audioCount > audioCountBeforeOpen;
      const title = document.querySelector("#player .player-grid > .card:first-child h2");
      return Boolean(audio && (sameAudioReused || newAudioLoaded) && audio.readyState >= 1 && audio.paused &&
        title && title.textContent.trim() === firstFixture.title);
    }, 20000).catch(error => {
      const audio = latestAcceptanceAudio();
      const title = document.querySelector("#player .player-grid > .card:first-child h2")?.textContent.trim() || "";
      const audioCount = (window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || []).length;
      throw new Error("Open-state diagnostics: " + JSON.stringify({
        expectedFolder:firstFixture.folder, existingAudioFolder, sameBookAlreadyLoaded,
        audioCountBeforeOpen, audioCount, latestAudioFolder:String(audio?.dataset?.projectFolder || ""),
        readyState:audio?.readyState ?? null, paused:audio?.paused ?? null,
        mediaErrorCode:audio?.error?.code ?? null, source:audio?.currentSrc || audio?.src || "", title
      }) + "; " + (error?.message || String(error)));
    });
    const firstOpenedAudio = latestAcceptanceAudio();
    must(String(firstOpenedAudio?.dataset?.projectFolder || "") === String(firstFixture.folder || "") && firstOpenedAudio.paused,
      "Open did not leave the selected project's own audio session loaded and paused.");
    const firstOpenedData = await invoke("player.get_active", {folder:firstFixture.folder});
    must(normalizeOutputPath(firstOpenedData.output_path) === normalizeOutputPath(firstFixture.output_path) &&
      String(firstOpenedData.title || "") === firstFixture.title &&
      String(firstOpenedData.author || "") === firstFixture.author &&
      String(firstOpenedData.narrator || "") === firstFixture.narrator &&
      String(firstOpenedData.playback_format || "").toLowerCase() === "mp3" &&
      String(firstOpenedData.format || "").toLowerCase() === ".m4b" &&
      Array.isArray(firstOpenedData.chapters) && firstOpenedData.chapters.length === 1 &&
      String(firstOpenedData.chapters[0].title || "") === firstFixture.chapter_title &&
      normalizeOutputPath(firstOpenedData.cover_path).endsWith(normalizeOutputPath(firstFixture.cover_file_name)),
      "Open mapped the selected book to the wrong output, metadata, cover, narrator or embedded chapter: " +
        JSON.stringify(firstOpenedData));
    must(String(firstOpenedAudio.src || "").toLowerCase().endsWith(".mp3"),
      "Open did not attach the browser-compatible playback derivative for the selected M4B.");
    record("stage6_audiobooks_open_loads_correct_book_paused", true,
      "Open selected the exact project and authoritative M4B output, resolved its checked MP3 playback derivative, retained cover/title/author/narrator/chapter association, and remained paused.");

    const refreshedFirstCard = Array.from(document.querySelectorAll("#backendAudiobookLibrary .audiobook-library-card"))
      .find(card => String(card.dataset.projectFolder || "") === String(firstFixture.folder || ""));
    must(refreshedFirstCard, "The first audiobook card disappeared after Open refreshed the selected-card state.");
    refreshedFirstCard.querySelector("[data-play-project-folder]").click();
    await waitFor("Stage 6 Play starts actual audiobook audio", function () {
      return Boolean(firstOpenedAudio.readyState >= 2 && firstOpenedAudio.currentTime > 0.05 &&
        !firstOpenedAudio.paused && !firstOpenedAudio.error);
    }, 20000);
    firstOpenedAudio.pause();
    record("stage6_audiobooks_play_action_starts_real_audio", true,
      "The card's Play action started the selected book's actual decoded local audio; it was not a decorative or metadata-only control.");

    const secondFixture = libraryFixtures[1];
    const secondCard = Array.from(document.querySelectorAll("#backendAudiobookLibrary .audiobook-library-card"))
      .find(item => String(item.dataset.projectFolder || "") === String(secondFixture.folder || ""));
    must(secondCard, "The second audiobook card disappeared after selecting the first book.");
    const audioCountBeforeSwitch = (window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || []).length;
    secondCard.querySelector("[data-open-project-folder]").click();
    await waitFor("Stage 6 switching to the second audiobook", function () {
      const audio = latestAcceptanceAudio();
      const title = document.querySelector("#player .player-grid > .card:first-child h2");
      return Boolean((window.__RYU_SOUND_UI_ACCEPTANCE_AUDIOS__ || []).length > audioCountBeforeSwitch &&
        audio && audio.readyState >= 1 && audio.paused &&
        title && title.textContent.trim() === secondFixture.title);
    }, 20000);
    const secondOpenedData = await invoke("player.get_active", {folder:secondFixture.folder});
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
