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
            request.paths = Array.isArray(config.cue_paths) ? config.cue_paths.slice() : [];
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
      must(String(cues.opening && cues.opening.path || "") === String(config.cue_paths[1]) &&
        String(cues.chapter && cues.chapter.path || "") === String(config.cue_paths[1]) &&
        String(cues.closing && cues.closing.path || "") === String(config.cue_paths[0]),
        "Opening, Next Chapter or Closing cue assignments were not restored.");
      record("application_restart_music_library_persistence", true, "All imported Music Library assets and categories remained available after a new frozen-app process.");
      record("application_restart_chapter_bgm_persistence", true, "Strategy, default preference, assignments, No BGM, offsets, end policies and chapter volume survived restart.");
      record("application_restart_mix_and_cue_persistence", true, "Narration/BGM/cue levels and all three cue slots survived restart.");
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
    async function saveChapter(number, rule, expectedPath) {
      document.querySelector("#saveChapterBgm").click();
      await waitFor("saved Chapter " + number + " assignment", async function () {
        const state = await invoke("sound.chapter_bgm.get", {});
        const row = state.overrides && state.overrides[String(number)];
        return Boolean(row && row.rule === rule &&
          (expectedPath == null || String(row.path || "") === String(expectedPath)));
      }, 15000);
    }

    await selectChapter(1);
    const stateBeforeCandidate = await invoke("sound.chapter_bgm.get", {});
    await chooseChapterCandidate(alpha.path, config.track_titles[0]);
    const stateAfterCandidate = await invoke("sound.chapter_bgm.get", {});
    must(JSON.stringify(stateAfterCandidate.overrides["1"] || {}) === JSON.stringify(stateBeforeCandidate.overrides["1"] || {}),
      "Candidate selection overwrote Chapter One's saved assignment before confirmation.");
    document.querySelector("#confirmChapterBgmTrack").click();
    await waitFor("Chapter One explicit selection", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return String(state.overrides?.["1"]?.path || "") === String(alpha.path);
    }, 15000);
    await setChapterTimingAndVolume(37, 1, 1);
    await saveChapter(1, "custom", alpha.path);

    await selectChapter(2);
    await chooseChapterCandidate(beta.path, config.track_titles[1]);
    document.querySelector("#confirmChapterBgmTrack").click();
    await waitFor("Chapter Two explicit selection", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return String(state.overrides?.["2"]?.path || "") === String(beta.path);
    }, 15000);
    await setChapterTimingAndVolume(29, 2, 2);
    await saveChapter(2, "custom", beta.path);

    await selectChapter(3);
    const noBgmRule = document.querySelector('#sound .chapter-rule [data-chapter-rule="none"]');
    must(noBgmRule, "Chapter No BGM rule is missing.");
    noBgmRule.click();
    await setChapterTimingAndVolume(15, 0, 0);
    await saveChapter(3, "none", null);
    let savedChapterState = await invoke("sound.chapter_bgm.get", {});
    must(savedChapterState.overrides["1"].start_offset === "after_first_paragraph" &&
      savedChapterState.overrides["1"].end_behavior === "continue_to_transition" &&
      Math.abs(Number(savedChapterState.overrides["1"].volume) - 0.37) < 0.005 &&
      savedChapterState.overrides["2"].start_offset === "after_10_seconds" &&
      savedChapterState.overrides["2"].end_behavior === "stop_immediately" &&
      Math.abs(Number(savedChapterState.overrides["2"].volume) - 0.29) < 0.005 &&
      savedChapterState.overrides["3"].rule === "none",
      "Chapter track, volume, offset, end behaviour or explicit No BGM did not persist.");
    record("chapter_bgm_assignment_volume_offsets_end_and_no_fallback", true,
      "Chapter One/Two assignments, independent levels, paragraph/ten-second offsets, end policies and Chapter Three No BGM were saved.");

    document.querySelector('#sound [data-bgm-strategy="same"]').click();
    await waitFor("Same BGM restore", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.strategy === "same" && String(state.default_path || "") === String(alpha.path);
    }, 15000);
    savedChapterState = await invoke("sound.chapter_bgm.get", {});
    must(savedChapterState.overrides["1"]?.path === alpha.path &&
      savedChapterState.overrides["2"]?.path === beta.path &&
      savedChapterState.overrides["3"]?.rule === "none",
      "Same BGM switching erased Chapter-Based assignments.");
    document.querySelector('#sound [data-bgm-strategy="custom"]').click();
    await waitFor("Chapter-Based restored after strategy switch", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.strategy === "custom" &&
        String(state.overrides?.["1"]?.path || "") === String(alpha.path) &&
        String(state.overrides?.["2"]?.path || "") === String(beta.path);
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
    const cueStateOnFailure = await invoke("sound.cues.get", {});
    must(String(cueStateOnFailure.opening?.path || "") === String(cueAlpha.path) &&
      document.querySelector("#saveCueChanges").disabled === false,
      "Failed cue save overwrote the previous saved slot or prevented retry.");
    document.querySelector("#saveCueChanges").click();
    await waitForCuePath("opening", cueBeta.path);
    record("cue_save_failure_retains_retryable_changes", true,
      "Injected cue-save failure preserved the old slot and draft; an explicit retry succeeded.");

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
    await waitFor("Mix summary live effective values", function () {
      return document.querySelector("#mixStrategy")?.textContent.includes("Chapter-Based BGM") &&
        document.querySelector("#mixOverrides")?.textContent.includes("3 chapters") &&
        document.querySelector("#mixEffectiveTracks")?.textContent.includes(config.track_titles[0]) &&
        document.querySelector("#mixEffectiveTracks")?.textContent.includes(config.track_titles[1]) &&
        document.querySelector("#advancedMusicVolumeValue")?.textContent.trim() === "42%" &&
        document.querySelector("#narrationVolumeValue")?.textContent.trim() === "82%" &&
        document.querySelector("#cueVolumeValue")?.textContent.trim() === "30%";
    }, 12000);
    record("mix_summary_and_saved_three_levels", true,
      "Mix summary reflected two effective chapter tracks, three rules, and the real saved 42%/82%/30% levels.");

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
      return {duration, output_path:result.output_path || completed.output_path};
    }

    document.querySelector('#sound [data-bgm-strategy="same"]').click();
    await waitFor("Same BGM ready for real mixer", async function () {
      const state = await invoke("sound.chapter_bgm.get", {});
      return state.strategy === "same" && String(state.default_path || "") === String(alpha.path);
    }, 15000);
    const samePreview = await renderFullBookPreview("Same BGM preview");
    must(samePreview.duration >= 45, "Same BGM preview omitted the saved cue sequence.");
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
    must(chapterPreview.duration - voiceOnlyPreview.duration >= 12,
      "Voice Only did not remove the saved Opening/Next Chapter/Closing cue audio from the preview timeline.");
    record("voice_only_removes_bgm_and_cues_from_real_preview", true,
      "Voice Only rendered the same saved narration with BGM and all fixed cues excluded.");

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
    record("production_handoff_save_error_gate_and_retry", true,
      "A failed shared-state save blocked navigation; retry flushed pending settings and opened Production with the real saved summary.");

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

    async function openProjectFromDashboard(folder, label) {
      window.go("dashboard");
      await waitFor("Dashboard recent project cards", function () {
        return Boolean(document.querySelector("#dashboard .recent-grid [data-project-folder]"));
      }, 15000);
      const card = Array.from(document.querySelectorAll("#dashboard .recent-grid [data-project-folder]"))
        .find(node => String(node.dataset.projectFolder || "") === String(folder));
      must(card, label + " project card is missing from the real Dashboard recent-project list.");
      card.click();
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

    publish("passed");
  } catch (error) {
    errors.push(String(error && error.stack || error));
    publish("failed");
  }
})();
