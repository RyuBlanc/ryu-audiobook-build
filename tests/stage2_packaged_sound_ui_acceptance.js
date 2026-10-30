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
    const wrappedBridge = Object.freeze({
      invoke: function (command, payload) {
        const request = Object.assign({}, payload || {});
        if (command === "sound.import" && request.target_kind === "music" &&
            (!Array.isArray(request.paths) || !request.paths.length)) {
          request.paths = Array.isArray(config.music_paths) ? config.music_paths.slice() : [];
          if (!request.paths.length) throw new Error("No generated Music Library fixture paths were provided.");
        } else if (command === "sound.import" && request.target_kind === "cue" &&
            (!Array.isArray(request.paths) || !request.paths.length)) {
          request.paths = Array.isArray(config.cue_paths) ? config.cue_paths.slice() : [];
          if (!request.paths.length) throw new Error("No generated cue fixture paths were provided.");
        }
        return originalInvoke(command, request);
      },
      bootstrap: originalBootstrap
    });
    Object.defineProperty(window, "ryuBackend", {
      configurable: true, enumerable: true, writable: true, value: wrappedBridge
    });
    record("native_bridge", true, "Real Qt WebChannel bridge connected; the UI import action delegates to the native backend.");

    const initial = await invoke("sound.chapter_bgm.get", {});
    must(initial && Array.isArray(initial.chapters) && initial.chapters.length >= 2,
      "The isolated two-chapter acceptance project did not load.");
    record("active_project", true, "The packaged app loaded an isolated project with two real chapter records.");

    must(typeof window.go === "function", "The Premium V2 navigation function is unavailable.");
    window.go('sound');
    await waitFor("Sound Design page", function () {
      const page = document.querySelector("#sound");
      return page && page.classList.contains("active");
    }, 12000);

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
    await waitFor("Built-in source filter", function () {
      return builtInSource.classList.contains("active") &&
        !visibleHas(config.track_titles[0]) && !visibleHas(config.track_titles[1]);
    }, 10000);
    if (musicButtons().length === 0) {
      const diagnosticCatalog = await invoke("sound.catalog", {});
      const sourceCounts = {};
      const categoryCounts = {};
      const roleCounts = {};
      const examples = [];
      for (const track of Array.isArray(diagnosticCatalog) ? diagnosticCatalog : []) {
        const metadata = track && typeof track.metadata === "object" ? track.metadata : {};
        const role = String(track?.role || metadata.role || "music").trim().toLowerCase();
        const source = String(track?.source || "(missing source)");
        const category = String(track?.category || metadata.category || "(missing category)");
        sourceCounts[source] = (sourceCounts[source] || 0) + 1;
        categoryCounts[category] = (categoryCounts[category] || 0) + 1;
        roleCounts[role] = (roleCounts[role] || 0) + 1;
        if (examples.length < 14 && (role !== "cue" || source.toLowerCase().includes("bundled"))) {
          examples.push({title:track?.title,source,category,role,path:String(track?.path || "").slice(-100)});
        }
      }
      const activeCategory = document.querySelector('#sound .sound-categories-list [data-music-category].active')?.dataset.musicCategory || "(none)";
      const activeSource = document.querySelector('#soundSourceFilter [data-source].active')?.dataset.source || "(none)";
      throw new Error("Packaged starter music is missing from the Built-in filter. Runtime catalogue diagnostics: " +
        JSON.stringify({
          catalogCount:Array.isArray(diagnosticCatalog) ? diagnosticCatalog.length : -1,
          sourceCounts, categoryCounts, roleCounts, examples,
          activeCategory, activeSource,
          renderedMusicRows:musicButtons().map(rowText).slice(0,8)
        }));
    }
    importedSource.click();
    await waitFor("Imported source filter", function () {
      return importedSource.classList.contains("active") &&
        visibleHas(config.track_titles[0]) && visibleHas(config.track_titles[1]);
    }, 10000);
    allSource.click();
    await waitFor("All source filter", function () {
      return allSource.classList.contains("active") &&
        visibleHas(config.track_titles[0]) && visibleHas(config.track_titles[1]);
    }, 10000);

    const fantasy = document.querySelector('#sound .sound-categories-list [data-music-category="fantasy-adventure"]');
    fantasy.click();
    await waitFor("Fantasy filter results", function () {
      return fantasy.classList.contains("active") &&
        visibleHas(config.track_titles[0]) && visibleHas(config.track_titles[1]);
    }, 10000);
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
    must(volume && Number(volume.max) === 50, "The BGM slider does not enforce the 50 percent maximum.");
    volume.value = String(config.expected_volume * 100);
    volume.dispatchEvent(new Event("input", { bubbles: true }));
    volume.dispatchEvent(new Event("change", { bubbles: true }));
    await waitFor("42 percent BGM value save", async function () {
      const saved = await invoke("sound.chapter_bgm.get", {});
      return Math.abs(Number(saved.default_volume) - config.expected_volume) < 0.005;
    }, 15000);
    must(document.querySelector("#advancedMusicVolumeValue").textContent.trim() === "42%",
      "The BGM slider's visible percentage did not update to 42%.");
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
    const cueCards = Array.from(document.querySelectorAll("#cueGrid [data-cue-path]"));
    const cueCardAlpha = cueCards.find(card => String(card.dataset.cuePath || "") === String(cueAlpha.path));
    const cueCardBeta = cueCards.find(card => String(card.dataset.cuePath || "") === String(cueBeta.path));
    must(cueCardAlpha && cueCardBeta, "The imported cue cards are not rendered in the Opening & Cues library.");

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

    publish("passed");
  } catch (error) {
    errors.push(String(error && error.stack || error));
    publish("failed");
  }
})();
