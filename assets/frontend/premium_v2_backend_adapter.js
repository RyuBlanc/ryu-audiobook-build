(() => {
  'use strict';
  window.__ryuPremiumAdapterReady = false;
  window.__ryuPremiumAdapterFailure = '';
  const $ = id => document.getElementById(id);
  let narratorOnlySavePromise = Promise.resolve();

  // Job polling runs every 1.5 seconds. Avoid writing the same values back to
  // Chromium's DOM/style system when nothing changed; this keeps layout work
  // proportional to real state changes rather than polling frequency.
  function writeTextIfChanged(node, value) {
    if (!node) return false;
    const next = String(value ?? '');
    if (node.textContent === next) return false;
    node.textContent = next;
    return true;
  }
  function writeStyleIfChanged(node, property, value) {
    if (!node?.style) return false;
    const next = String(value ?? '');
    if (node.style[property] === next) return false;
    node.style[property] = next;
    return true;
  }
  function writeCssVariableIfChanged(node, property, value) {
    if (!node?.style?.getPropertyValue || !node.style.setProperty) return false;
    const next = String(value ?? '');
    if (node.style.getPropertyValue(property) === next) return false;
    node.style.setProperty(property, next);
    return true;
  }
  function writeAttributeIfChanged(node, name, value) {
    if (!node?.getAttribute || !node?.setAttribute) return false;
    const next = String(value ?? '');
    if (node.getAttribute(name) === next) return false;
    node.setAttribute(name, next);
    return true;
  }
  function writeBooleanIfChanged(node, property, value) {
    if (!node || !(property in node)) return false;
    const next = Boolean(value);
    if (node[property] === next) return false;
    node[property] = next;
    return true;
  }
  function isVisiblePage(pageId) {
    const page = $(pageId);
    if (!page || !page.classList.contains('active') || page.classList.contains('hidden')) return false;
    const style = window.getComputedStyle(page);
    return style.display !== 'none' && style.visibility !== 'hidden' && page.getClientRects().length > 0;
  }
  let ryuUiTextScale = 100;
  let ryuUiTextObserver = null;
  const ryuUiScalePendingRoots = new Set();
  let ryuUiScaleFramePending = false;
  let ryuUiTextBaselinesReady = false;
  const RYU_UI_TEXT_SCALES = new Set([85, 90, 100, 110, 120, 130, 140]);

  function ensureUiTextScaleStyles() {
    if ($('ryuUiTextScaleStyles')) return;
    const style = document.createElement('style');
    style.id = 'ryuUiTextScaleStyles';
    style.textContent = [
      'html[data-ryu-text-scale-active="1"][data-ryu-font-scaled="1"],',
      'html[data-ryu-text-scale-active="1"] [data-ryu-font-scaled="1"] {',
      'font-size: calc(var(--ryu-base-font-px, 14px) * var(--ryu-ui-text-scale, 1)) !important;',
      '}'
    ].join('\n');
    (document.head || document.documentElement).appendChild(style);
  }

  function captureUiFontBaselines(root) {
    if (!root || root.nodeType !== 1) return;
    // Read computed sizes first and write baseline variables afterwards. Interleaving
    // getComputedStyle() with per-node font-size writes forces repeated style/layout
    // recalculation and was a source of pauses on larger Character Studio chapters.
    const rows = [];
    const scaleFactor = ryuUiTextScale !== 100 &&
      document.documentElement?.dataset?.ryuTextScaleActive === '1'
      ? ryuUiTextScale / 100 : 1;
    const skipTags = new Set(['SCRIPT','STYLE','LINK','META','NOSCRIPT','TEMPLATE','SVG','CANVAS','VIDEO','AUDIO']);
    const visit = (node, parentBase = null, parentCurrent = NaN) => {
      if (!node || node.nodeType !== 1 || skipTags.has(node.tagName)) return;
      const computed = Number.parseFloat(getComputedStyle(node).fontSize) || 14;
      // New elements inserted after the user picks (say) 120% inherit computed
      // sizes that already include the CSS scale. Divide that out before saving
      // a baseline; otherwise every new render progressively grows text again.
      const current = computed / scaleFactor;
      const stored = Number.parseFloat(node.style.getPropertyValue('--ryu-base-font-px'));
      let base = Number.isFinite(stored) && stored > 0 ? stored : NaN;
      if (!Number.isFinite(base)) {
        const inherits = Number.isFinite(parentBase) && Number.isFinite(parentCurrent) &&
          Math.abs(current - parentCurrent) < 0.25;
        base = inherits ? parentBase : current;
      }
      rows.push({node, base});
      for (const child of node.children) visit(child, base, current);
    };
    visit(root);
    for (const row of rows) {
      row.node.style.setProperty('--ryu-base-font-px', String(row.base) + 'px');
      row.node.dataset.ryuFontScaled = '1';
    }
  }

  function queueUiTextScaleBaselineCapture(node) {
    if (!node || node.nodeType !== 1) return;
    // At the default size there is nothing to scale. Do not walk newly-rendered
    // chapters, cards or dialogs until the user has actually enabled text scaling.
    if (ryuUiTextScale === 100 && !ryuUiTextBaselinesReady) return;
    // Coalesce nested insertions. A chapter render often adds a panel and all of
    // its descendants in one mutation batch; measure it once as a subtree.
    for (const existing of ryuUiScalePendingRoots) {
      if (existing === node || existing.contains(node)) return;
    }
    for (const existing of Array.from(ryuUiScalePendingRoots)) {
      if (node.contains(existing)) ryuUiScalePendingRoots.delete(existing);
    }
    ryuUiScalePendingRoots.add(node);
    if (ryuUiScaleFramePending) return;
    ryuUiScaleFramePending = true;
    requestAnimationFrame(() => {
      ryuUiScaleFramePending = false;
      const roots = Array.from(ryuUiScalePendingRoots);
      ryuUiScalePendingRoots.clear();
      // Baseline capture uses a read phase followed by a write phase. The text
      // scale is a single CSS variable, not hundreds of inline font mutations.
      for (const pendingRoot of roots) {
        if (pendingRoot.isConnected) captureUiFontBaselines(pendingRoot);
      }
    });
  }

  function applyUiTextScale(value) {
    const parsed = Number(value);
    ryuUiTextScale = RYU_UI_TEXT_SCALES.has(parsed) ? parsed : 100;
    const root = document.documentElement;
    if (!root) return;
    ensureUiTextScaleStyles();
    if (ryuUiTextScale !== 100 && !ryuUiTextBaselinesReady) {
      captureUiFontBaselines(root);
      ryuUiTextBaselinesReady = true;
    }
    root.dataset.ryuTextScale = String(ryuUiTextScale);
    root.style.setProperty('--ryu-ui-text-scale', String(ryuUiTextScale / 100));
    if (ryuUiTextScale === 100) delete root.dataset.ryuTextScaleActive;
    else root.dataset.ryuTextScaleActive = '1';
    const select = $('uiTextScale');
    if (select && select.value !== String(ryuUiTextScale)) select.value = String(ryuUiTextScale);
  }

  function installUiTextScaleRuntime() {
    if (window.__ryuUiTextScaleInstalled) return;
    window.__ryuUiTextScaleInstalled = true;
    ensureUiTextScaleStyles();
    // Block Chromium/browser zoom shortcuts and Ctrl+mousewheel. The app's text
    // size and window resolution are controlled only through Settings.
    window.addEventListener('keydown', event => {
      if (event.ctrlKey && ['+', '=', '-', '_', '0'].includes(String(event.key || ''))) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
    window.addEventListener('wheel', event => {
      if (event.ctrlKey) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, {capture:true, passive:false});
    if (typeof MutationObserver === 'function') {
      ryuUiTextObserver = new MutationObserver(records => {
        for (const record of records) {
          for (const node of record.addedNodes) queueUiTextScaleBaselineCapture(node);
        }
      });
      ryuUiTextObserver.observe(document.documentElement, {childList:true, subtree:true});
    }
    applyUiTextScale(ryuUiTextScale);
    const selector = $('uiTextScale');
    if (selector && !selector.dataset.ryuTextScaleBound) {
      selector.dataset.ryuTextScaleBound = '1';
      selector.addEventListener('change', () => applyUiTextScale(selector.value));
    }
  }
  function installReducedMotionStyles() {
    if ($('ryuReducedMotionStyles')) return;
    const style = document.createElement('style');
    style.id = 'ryuReducedMotionStyles';
    style.textContent = [
      'html[data-ryu-reduce-motion="1"] *,',
      'html[data-ryu-reduce-motion="1"] *::before,',
      'html[data-ryu-reduce-motion="1"] *::after {',
      'animation-duration:0.01ms!important;',
      'animation-iteration-count:1!important;',
      'transition-duration:0.01ms!important;',
      'transition-delay:0ms!important;',
      'scroll-behavior:auto!important;',
      'backdrop-filter:none!important;',
      '-webkit-backdrop-filter:none!important;',
      '}'
    ].join('\n');
    (document.head || document.documentElement).appendChild(style);
  }

  function applyVisualStabilityPreferences(settings = {}) {
    installReducedMotionStyles();
    const root = document.documentElement;
    // Persisted settings must drive the CSS attributes as well as the controls.
    // Assigning a select's value alone does not activate the matching theme/effect rules.
    const themeRaw = String(
      settings.theme ?? $('themeSelectAdvanced')?.value ?? root?.dataset.theme ?? 'dark'
    ).trim().toLowerCase();
    const theme = themeRaw === 'light' ? 'light' : 'dark';
    const effectsRaw = String(
      settings.effects ?? $('effectsModeAdvanced')?.value ?? root?.dataset.effects ?? 'high'
    ).trim().toLowerCase();
    const effects = effectsRaw === 'normal' ? 'normal' : 'high';
    if (root) {
      if (root.dataset.theme !== theme) root.dataset.theme = theme;
      if (root.dataset.effects !== effects) root.dataset.effects = effects;
    }
    const themeControl = $('themeSelectAdvanced');
    if (themeControl && themeControl.value !== theme) themeControl.value = theme;
    const effectsControl = $('effectsModeAdvanced');
    if (effectsControl && effectsControl.value !== effects) effectsControl.value = effects;
    const effectsLabel = $('aboutEffects');
    if (effectsLabel) writeTextIfChanged(
      effectsLabel, effects === 'high' ? 'High Glass' : 'Normal Smooth Blur'
    );
    const raw = settings.reduce_motion;
    const reduce = typeof raw === 'boolean' ? raw : Boolean($('reduceMotionAdvanced')?.checked);
    if (root) root.dataset.ryuReduceMotion = reduce ? '1' : '0';
    const checkbox = $('reduceMotionAdvanced');
    if (checkbox && checkbox.checked !== reduce) checkbox.checked = reduce;
  }

  const call = async (command, payload = {}) => {
    if (!window.ryuBackend?.invoke) throw new Error('Local backend bridge is unavailable.');
    const response = await window.ryuBackend.invoke(command, payload);
    if (!response?.success) throw new Error(response?.error?.message || command + ' failed.');
    const data = response.data;
    // Project-open refreshes are owned by openProjectWithPreservedDraft().
    // Starting a second fire-and-forget active-project read here can race the
    // caller's verified transition and briefly re-apply stale identity.
    if (command === 'project.rename') {
      void refreshCurrentProjectCard('Renamed · saved locally').catch(() => {});
    }
    return data;
  };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const message = (text, error = false) => {
    // Global notifications must not overwrite a different workflow's status.
    // Only surface inline validation on the page the user is currently viewing.
    const activeValidation = document.querySelector('.page.active #validation');
    if (error && activeValidation) writeTextIfChanged(activeValidation, text);
    const toasts = $('toasts');
    if (toasts) {
      writeTextIfChanged(toasts, text);
      toasts.classList.add('show');
    }
    if (error) console.error('[Ryu backend]', text);
  };
  const act = fn => async event => { event?.preventDefault?.(); try { await fn(event); } catch (e) { message(e?.message || String(e), true); } };
  let selectedVoice = null, selectedVoiceId = null, selectedVoiceProvider = null, profileEditOriginalName = '', activeJob = null, activeJobType = null, poll = null, monitorEpoch = 0, jobsRefreshPromise = null, jobsRefreshRequested = false, chapterListEpoch = 0, chapterSelectionEpoch = 0, cueListEpoch = 0, cueSearchTimer = null, previewAudio = null, lastVoicePreviewPath = null, lastVoicePreviewProfileName = '', lastVoicePreviewChapterNumber = null, lastVoicePreviewChapterTitle = '', voicePreviewValid = false, voicePreviewEpoch = 0, previewVolume = 0.85, voiceAssignmentEpoch = 0, playerAudio = null, soundPreviewAudio = null, cueSearchUnavailableNotified = false, chapterSaveTimer = null, chapterSavePromise = Promise.resolve(), activePlayerChapters = [], playerPositionSaveAt = 0, playerRate = 1, playerVolume = 0.8, productionFullJobId = null, productionPreviewJobId = null, productionJobSnapshots = {full:null,preview:null}, productionJobMonitors = {full:null,preview:null}, productionMonitorEpochs = {full:0,preview:0}, productionPreviewRequestProjectFolder = '', productionPreviewSelectionProjectFolder = '', productionPreviewSelectedChapter = null, productionPreviewSelectedChapterId = '', productionPreviewSelectedChapterSignature = '', productionPreviewRequestChapterNumber = 0, productionPreviewRequestChapterId = '';
  let elevenCandidates = [], selectedElevenCandidate = null, elevenDesignSeed = 7300;
  let chapters = [], characters = [], voices = [], terms = [], projects = [], sounds = [], pronunciationEnabled = true, activePronunciationSeries = '', lastPronunciationPreview = null, pronunciationRowPreviewState = new Map(), pronunciationSelectionKeys = new Set(), selectedSoundPath = null, selectedCuePath = null, pendingCueSlot = null, pendingCueAssignments = Object.create(null), cueChangesDirty = false, cueSaveError = '', cueAssignments = {}, chapterBgmState = {strategy:'same',overrides:{}}, selectedBgmChapter = null, selectedBgmTrackPath = null, chapterBgmDraftDirty = false, mixLevelsDirty = false, soundPreviewKind = null, soundPreviewPath = null;
  let chapterBgmCandidateTrackPath = null, chapterBgmCandidateChapter = null, chapterBgmSavePromise = null, cueSavePromise = null;
  let chapterStrategySavePromise = null;
  let chapterBgmAutoSaveTimer = null, cueAutoSaveTimer = null, chapterBgmDraftRevision = 0;
  let mixLevelsRevision = 0, mixLevelsSavePromise = null;
  let soundManifestSavePromise = null, soundManifestSaveRevision = 0, soundManifestPendingOverrides = Object.create(null);
  let cueClearAllStaged = false;
  let modelInventoryLoadPromise = null, modelInventoryScanRequested = false, modelInventoryLoadedAt = 0, forceModelInventoryRefreshPending = false;
  let soundCatalogLoadPromise = null, soundCatalogScanRequested = false, soundCatalogLoadedAt = 0, forceSoundCatalogRefreshPending = false;
  let providerCatalogs = Object.create(null), providerCatalogEpochs = Object.create(null), voiceListEpoch = 0, modelListEpoch = 0, projectListEpoch = 0, characterListEpoch = 0, termsListEpoch = 0, soundListEpoch = 0, historyListEpoch = 0, librarySearchTimer = null, soundSearchTimer = null;
  let dashboardProject = null, selectedAudiobookFolder = null, miniPlayerDismissed = false;
  let metadataDialogProjectFolder = '', metadataDialogDirty = false, metadataDialogEpoch = 0;
  let activeProjectCardFolder = null, projectCardStatusObserver = null;
  let activeProjectCardEpoch = 0;
  const soundCategoryGroups = Object.freeze({
    'fantasy':'fantasy-adventure', 'adventure':'fantasy-adventure',
    'fantasy-adventure':'fantasy-adventure', 'fantasy adventure':'fantasy-adventure',
    'action':'battle-warfare', 'battle':'battle-warfare',
    'battle-warfare':'battle-warfare', 'battle & warfare':'battle-warfare',
    'battle warfare':'battle-warfare',
    'mystery':'mystery', 'horror':'horror', 'romance':'romance', 'sci-fi':'sci-fi',
    'calm':'calm-narration', 'universal':'calm-narration',
    'calm-narration':'calm-narration', 'calm narration':'calm-narration',
    'emotional':'others', 'others':'others', 'slice-of-life':'others', 'comedy':'others'
  });
  function soundCategoryGroup(track) {
    const metadata = track && typeof track === 'object' && track.metadata && typeof track.metadata === 'object'
      ? track.metadata : {};
    const raw = typeof track === 'string'
      ? track : (track?.category || metadata.category || track?.category_label || 'universal');
    const category = String(raw).trim().toLowerCase().replace(/_/g, '-').replace(/\s+/g, ' ');
    return soundCategoryGroups[category] || 'others';
  }
  function soundAssetRole(track) {
    const metadata = track && typeof track === 'object' && track.metadata && typeof track.metadata === 'object'
      ? track.metadata : {};
    const role = String(track?.role || metadata.role || 'music').trim().toLowerCase();
    return ['opening','page','ending','closing','chapter'].includes(role) ? 'cue' : role;
  }
  function isCueSoundAsset(track) { return soundAssetRole(track) === 'cue'; }
  function isMusicSoundAsset(track) { return !isCueSoundAsset(track); }
  function soundSourceKind(track) {
    const source = String(track?.source || '').trim().toLowerCase();
    if (source.includes('bundled') || source.includes('built-in') || source.includes('built in') || source.includes('starter')) return 'built-in';
    if (source.includes('imported') || source.includes('local import')) return 'imported';
    return 'unknown';
  }
  function markMixLevelsDirty() {
    mixLevelsDirty = true;
    mixLevelsRevision += 1;
    soundManifestSaveRevision += 1;
  }
  function setChapterBgmSaveStatus(value) {
    const status = $('chapterBgmSaveState');
    if (status) status.textContent = String(value || '');
  }
  function scheduleChapterBgmAutoSave() {
    if (chapterBgmAutoSaveTimer) clearTimeout(chapterBgmAutoSaveTimer);
    chapterBgmAutoSaveTimer = null;
    if (!chapterBgmDraftDirty) return;
    const chapterBased = ['custom','chapter-based','chapter_based','chapter'].includes(
      String(chapterBgmState.strategy || 'same').toLowerCase()
    );
    if (!chapterBased) return;
    const activeRule = document.querySelector('#sound .chapter-rule [data-chapter-rule].active')?.dataset.chapterRule || 'none';
    if (activeRule === 'custom' && !selectedBgmTrackPath) {
      setChapterBgmSaveStatus('Choose a track and press Select before this chapter assignment can be saved.');
      return;
    }
    setChapterBgmSaveStatus('Unsaved chapter changes — saving automatically shortly.');
    chapterBgmAutoSaveTimer = setTimeout(async () => {
      chapterBgmAutoSaveTimer = null;
      try {
        const saved = await saveCurrentChapterBgmDraft();
        if (saved) message('Chapter BGM changes saved automatically.');
      } catch (error) {
        setChapterBgmSaveStatus('Save failed. Unsaved chapter changes have been retained.');
        message(error?.message || String(error), true);
      }
    }, 700);
  }
  function markChapterBgmDraftDirty() {
    chapterBgmDraftDirty = true;
    chapterBgmDraftRevision += 1;
    setChapterBgmSaveStatus('Unsaved chapter changes.');
    scheduleChapterBgmAutoSave();
  }
  const resumeCheckpointKey = 'ryu.project.resume-checkpoints.v1';
  const resumeStages = new Set(['import','chapters','narrator','characters','sound','production','player']);
  const resumeStageRoutes = {
    import:'import', chapters:'chapters', narrator:'voice', characters:'characters',
    sound:'sound', production:'production', player:'player'
  };
  function readResumeCheckpoints() {
    try {
      const raw = JSON.parse(localStorage.getItem(resumeCheckpointKey) || '{}');
      return raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
    } catch (_) { return {}; }
  }
  function writeResumeCheckpoint(folder, stage) {
    if (!folder || !resumeStages.has(stage)) return;
    const checkpoints = readResumeCheckpoints();
    checkpoints[folder] = {stage, updated_at:new Date().toISOString()};
    try { localStorage.setItem(resumeCheckpointKey, JSON.stringify(checkpoints)); } catch (_) {}
  }
  function savedResumeStage(project) {
    if (!project?.folder) return '';
    const stage = String(readResumeCheckpoints()[project.folder]?.stage || '').trim().toLowerCase();
    return resumeStages.has(stage) ? stage : '';
  }
  function routeForResume(project) {
    const saved = savedResumeStage(project);
    if (saved) return saved;
    if (project?.completed && project?.output_path) return 'player';
    if (!project?.source_exists || !project?.chapter_count) return 'import';
    if (!project?.voice_profile) return 'narrator';
    if (!project?.character_analysis_done) return 'characters';
    if (!project?.sound_design_configured) return 'sound';
    if (!project?.output_configured) return 'production';
    return 'chapters';
  }
  function navigateToProjectStage(project, stage = routeForResume(project)) {
    const target = resumeStageRoutes[stage] || 'chapters';
    if (project?.folder) writeResumeCheckpoint(project.folder, stage);
    if (typeof window.go === 'function') window.go(target);
    return target;
  }
  const chapterUndoStacks = new Map(), chapterRedoStacks = new Map();
  let chapterLastText = '', chapterHistoryGroupOpen = false, chapterHistoryGroupTimer = null, chapterHistoryApplying = false;
  let libraryCharacters = [], libraryEditorId = null, libraryEditorActive = false;
  let characterDialogueSuggestions = [], characterSuggestionsEpoch = 0;
  let characterNarrationSegments = [];
  let characterAnalysisStatus = {analyzed:false, updated_at:null, dialogue_total:0, unassigned_dialogue:0, suggestion_count:0};
  let characterStudioSelectedChapter = null, characterStudioSelectedSeries = '', characterStudioRenderEpoch = 0;
  let characterManualFormBound = false, characterAssignedActionsBound = false, characterStudioCaptureBound = false;
  // The approved HTML ships legacy prototype listeners. Replace only sound controls
  // whose actions are handled by the real backend adapter; visual markup is unchanged.
  ['importMusicTracks','importCueClips','previewSelectedTrack','setBookDefaultTrack',
   'saveChapterBgm','previewCueSequence','clearAllCues','soundPreviewBook',
   'applySoundToProduction','advancedMusicVolume','playSelectedCue','pauseSelectedCue',
   'replaySelectedCue','saveCueChanges','chapterBgmList','chapterTrackPicker'].forEach(id => {
    const node = $(id);
    if (node?.parentNode) node.replaceWith(node.cloneNode(true));
  });
  // The legacy reference HTML attaches prototype handlers to the Sound Design tab strip.
  // Remove those handlers while preserving the approved markup and current active classes.
  const legacySoundTabs = document.querySelector('#sound .sound-tabs');
  if (legacySoundTabs?.parentNode) {
    const cleanSoundTabs = legacySoundTabs.cloneNode(true);
    cleanSoundTabs.querySelectorAll('[onclick]').forEach(button => button.removeAttribute('onclick'));
    legacySoundTabs.replaceWith(cleanSoundTabs);
  }
  // Chapter strategy/rule controls also exist in the prototype HTML. Replace their
  // nodes so old direct/inline listeners cannot compete with the backend adapter.
  ['#sound .chapter-bgm-strategy', '#sound .chapter-rule'].forEach(selector => {
    const node = document.querySelector(selector);
    if (node?.parentNode) {
      const cleanNode = node.cloneNode(true);
      cleanNode.querySelectorAll('[onclick]').forEach(button => button.removeAttribute('onclick'));
      node.replaceWith(cleanNode);
    }
  });
  if ($('musicImportInput')) $('musicImportInput').onchange = null;
  if ($('cueImportInput')) $('cueImportInput').onchange = null;
  const fadeSeconds = id => {
    const label = String($(id)?.selectedOptions?.[0]?.textContent || '').trim();
    if (!label || /^none$/i.test(label)) return 0;
    const match = label.match(/\d+/);
    return match ? Math.max(0, Math.min(30, Number(match[0]))) : 0;
  };
  const selectedChapter = () => chapters.find(c => c.number === window.ryuPremiumSelectedChapter) || chapters[0];
  function ensureDialogueUnassignButton() {
    const confirmButton = $('confirmAiCharacter');
    if (!confirmButton) return null;
    let button = $('removeAiCharacterAssignment');
    if (!button) {
      button = document.createElement('button');
      button.id = 'removeAiCharacterAssignment';
      button.type = 'button';
      button.className = confirmButton.className || 'btn small secondary';
      button.textContent = 'Remove saved assignment';
      confirmButton.insertAdjacentElement('afterend', button);
    }
    return button;
  }
  function renderDialogueReview() {
    const queue = $('aiQueue');
    const storyDocument = documentRef();
    const title = $('aiQueue')?.closest('.ai-layout')?.querySelector('.ai-story .story-head h2');
    const subtitle = $('aiQueue')?.closest('.ai-layout')?.querySelector('.ai-story .story-head p');
    const progressText = $('aiProgressText');
    const progressBar = $('aiProgressBar');
    const progressLabel = $('aiProgressText')?.parentElement?.querySelector('span');
    const pendingBadge = $('aiQueue')?.closest('.ai-queue-panel')?.querySelector('.badge.warn');
    const items = [];
    for (const chapter of chapters) {
      for (const row of characterDialogueRowsForChapter(chapter)) {
        items.push({...row, chapter_number:Number(chapter.number), chapter_title:String(chapter.title || '')});
      }
    }
    const analyzedIds = new Set(characterDialogueSuggestions.map(row => String(row.id || '')));
    const analyzedItems = items.filter(item =>
      item.source === 'local-dialogue-analysis' || analyzedIds.has(String(item.id || ''))
    );
    const selectedNumber = Number(window.ryuPremiumAiChapterNumber || characterStudioSelectedChapter || window.ryuPremiumSelectedChapter || chapters[0]?.number || 0);
    const selectedChapter = chapters.find(chapter => Number(chapter.number) === selectedNumber) || chapters[0] || null;
    const pendingQueue = analyzedItems.filter(item =>
      Number(item.chapter_number) === Number(selectedChapter?.number) &&
      !item.assigned && !item.skipped
    );
    const queueSignature = String(selectedChapter?.number || 0) + '|' +
      pendingQueue.map(item => String(item.id || '')).join('|');
    if (window.ryuPremiumDialogueReviewQueueSignature !== queueSignature) {
      window.ryuPremiumDialogueReviewQueueSignature = queueSignature;
      window.ryuPremiumDialogueReviewVisibleCount = 120;
    }
    const visibleCount = Math.min(
      pendingQueue.length,
      Math.max(120, Number(window.ryuPremiumDialogueReviewVisibleCount || 120))
    );
    const nextVisibleCount = Math.min(pendingQueue.length, visibleCount + 120);
    let chapterNav = $('aiChapterNavigator');
    if (queue && !chapterNav) {
      chapterNav = document.createElement('div');
      chapterNav.id = 'aiChapterNavigator';
      chapterNav.className = 'ryu-ai-chapter-navigator';
      chapterNav.style.cssText = 'display:grid;gap:6px;max-height:230px;overflow:auto;margin:0 0 12px;padding-right:3px;';
      queue.parentElement?.insertBefore(chapterNav, queue);
    }
    if (chapterNav) {
      const priorScroll = chapterNav.scrollTop;
      const chapterFilter = String(window.ryuPremiumAiChapterFilter || '').trim().toLocaleLowerCase();
      const statusFilter = String(window.ryuPremiumAiChapterStatusFilter || 'all');
      const chapterButtons = chapters.map(chapter => {
        const number = Number(chapter.number);
        const chapterPassages = items.filter(item => Number(item.chapter_number) === number);
        const assignedCount = chapterPassages.filter(item => item.assigned && !item.skipped).length;
        const aiSuggestedCount = chapterPassages.filter(item =>
          !item.skipped && Array.isArray(item.suggestions) && item.suggestions.length > 0
        ).length;
        const skippedCount = chapterPassages.filter(item => item.skipped).length;
        const pendingRows = chapterPassages.filter(item => !item.assigned && !item.skipped);
        const wordCount = Math.max(
          0,
          Number(chapter.word_count) ||
            String(chapter.text || '').trim().split(/\s+/).filter(Boolean).length
        );
        const status = !characterAnalysisStatus.analyzed ? 'Not analysed yet' :
          (pendingRows.length ? 'Needs review' : 'Review complete');
        const statusKey = !characterAnalysisStatus.analyzed ? 'not-analysed' :
          (pendingRows.length ? 'needs-review' : 'complete');
        const searchText = (number + ' ' + String(chapter.title || '')).toLocaleLowerCase();
        const matchesSearch = !chapterFilter || searchText.includes(chapterFilter);
        const matchesStatus = statusFilter === 'all' || statusFilter === statusKey;
        const hidden = matchesSearch && matchesStatus ? '' : ' hidden';
        const active = number === Number(selectedChapter?.number);
        return '<button type="button" class="chapter-pick ' + (active ? 'active' : '') +
          '" data-ai-chapter-number="' + number + '" data-ai-chapter-status="' + statusKey +
          '" data-ai-chapter-search="' + esc(searchText) + '" aria-current="' + (active ? 'page' : 'false') + '"' + hidden +
          ' style="display:flex;flex-direction:column;align-items:flex-start;gap:3px;width:100%;text-align:left;padding:9px 11px;border-radius:9px;border:1px solid ' +
          (active ? 'var(--accent,#c92c57)' : 'var(--border,#303744)') +
          ';background:' + (active ? 'rgba(197,39,82,.16)' : 'rgba(255,255,255,.02)') +
          ';color:inherit;cursor:pointer"><b>Chapter ' + number + ' · ' +
          esc(String(chapter.title || 'Untitled chapter')) + '</b><small>' +
          esc(status + ' · ' + pendingRows.length + ' pending') +
          '</small><small style="white-space:normal;line-height:1.45">' +
          esc(wordCount.toLocaleString() + ' words · ' + chapterPassages.length + ' detected · ' +
            assignedCount + ' assigned · ' + aiSuggestedCount + ' AI suggestions · ' +
            pendingRows.length + ' needs review · ' + skippedCount + ' skipped') +
          '</small></button>';
      }).join('');
      const statusOptions = [
        ['all', 'All statuses'],
        ['not-analysed', 'Not analysed'],
        ['needs-review', 'Needs review'],
        ['complete', 'Review complete']
      ].map(([value, label]) =>
        '<option value="' + value + '"' + (statusFilter === value ? ' selected' : '') + '>' + label + '</option>'
      ).join('');
      chapterNav.innerHTML =
        '<div class="ryu-character-subsection">Chapters · select to review</div>' +
        '<label style="display:grid;gap:4px"><span class="muted">Search chapter number or title</span>' +
        '<input type="search" data-ai-chapter-filter aria-label="Search chapters by number or title" placeholder="Search chapters…" value="' +
        esc(String(window.ryuPremiumAiChapterFilter || '')) + '" style="width:100%;min-width:0"></label>' +
        '<label style="display:grid;gap:4px"><span class="muted">Filter by review status</span>' +
        '<select data-ai-chapter-status-filter aria-label="Filter chapters by review status" style="width:100%;min-width:0">' +
        statusOptions + '</select></label>' +
        (chapterButtons || '<div class="ryu-character-empty">No chapters are loaded.</div>') +
        '<div data-ai-chapter-filter-empty hidden class="ryu-character-empty">No chapters match these filters.</div>';
      chapterNav.scrollTop = priorScroll;
      if (!chapterNav.dataset.liveBound) {
        chapterNav.dataset.liveBound = '1';
        const applyChapterFilters = () => {
          const term = String(window.ryuPremiumAiChapterFilter || '').trim().toLocaleLowerCase();
          const selectedStatus = String(window.ryuPremiumAiChapterStatusFilter || 'all');
          let visible = 0;
          chapterNav.querySelectorAll('[data-ai-chapter-number]').forEach(button => {
            const matchesSearch = !term || String(button.dataset.aiChapterSearch || '').includes(term);
            const matchesStatus = selectedStatus === 'all' || button.dataset.aiChapterStatus === selectedStatus;
            button.hidden = !(matchesSearch && matchesStatus);
            if (!button.hidden) visible++;
          });
          const empty = chapterNav.querySelector('[data-ai-chapter-filter-empty]');
          if (empty) empty.hidden = visible > 0;
        };
        chapterNav.addEventListener('input', event => {
          const input = event.target.closest('[data-ai-chapter-filter]');
          if (!input) return;
          window.ryuPremiumAiChapterFilter = String(input.value || '');
          applyChapterFilters();
        });
        chapterNav.addEventListener('change', event => {
          const select = event.target.closest('[data-ai-chapter-status-filter]');
          if (!select) return;
          window.ryuPremiumAiChapterStatusFilter = String(select.value || 'all');
          applyChapterFilters();
        });
        chapterNav.addEventListener('click', event => {
          const button = event.target.closest('[data-ai-chapter-number]');
          if (!button) return;
          const number = Number(button.dataset.aiChapterNumber);
          if (!chapters.some(chapter => Number(chapter.number) === number)) return;
          window.ryuPremiumAiChapterNumber = number;
          window.ryuPremiumSelectedChapter = number;
          characterStudioSelectedChapter = number;
          window.ryuPremiumSelectedDialogueId = '';
          renderDialogueReview();
        });
      }
    }
    const renderSignature = JSON.stringify([
      characterAnalysisStatus.analyzed, selectedChapter?.number, queueSignature, visibleCount, items.map(item => [
        item.id,item.chapter_number,item.start,item.end,item.text,item.speakers,item.assigned,
        item.assignmentSource,item.skipped,(item.suggestions||[]).map(candidate=>[candidate.name,candidate.confidence,candidate.evidence])
      ])
    ]);
    window.ryuPremiumDialogueReviewItems = items;
    if (window.__ryuDialogueReviewRenderSignature === renderSignature) {
      renderAiChapterDocument();
      return;
    }
    window.__ryuDialogueReviewRenderSignature = renderSignature;
    const counted = analyzedItems.filter(item => !item.skipped);
    const assignedCount = counted.filter(item => item.assigned).length;
    const remaining = Math.max(0, counted.length - assignedCount);
    const percent = counted.length ? Math.round(assignedCount / counted.length * 100) : 0;
    if (progressText) {
      if (!characterAnalysisStatus.analyzed) progressText.textContent = 'Analysis has not run for this project';
      else if (!counted.length) progressText.textContent = 'No dialogue suggestions found';
      else progressText.textContent = assignedCount + ' of ' + counted.length + ' analyzed dialogue passages assigned';
    }
    if (progressBar) progressBar.style.width = characterAnalysisStatus.analyzed ? percent + '%' : '0%';
    if (progressLabel) progressLabel.textContent = !characterAnalysisStatus.analyzed
      ? 'Run Analyze book' : (counted.length ? percent + '% assigned' : 'No suggestions');
    if (pendingBadge) pendingBadge.textContent = characterAnalysisStatus.analyzed ? remaining + ' left' : 'Not analyzed';
    if (title) title.textContent = selectedChapter
      ? 'Chapter ' + selectedChapter.number + ' · ' + String(selectedChapter.title || 'Untitled chapter')
      : 'Dialogue review';
    if (subtitle) subtitle.textContent = !characterAnalysisStatus.analyzed
      ? 'Run Analyze book to create source-backed suggestions. Existing saved assignments remain visible in green.'
      : (selectedChapter
        ? 'Green passages are saved assignments; orange passages have real analysis suggestions; plain passages have no saved assignment or supported prediction.'
        : 'Open a local project to review its source text and dialogue assignments.');
    if (queue) {
      if (!characterAnalysisStatus.analyzed) {
        queue.innerHTML = '<div class="ryu-character-empty"><b>Analysis has not run</b>Select Run analysis again to create review suggestions from the active project. Manual source-text assignment is still available.</div>';
      } else {
        const visibleRows = pendingQueue.slice(0, visibleCount).map(item => {
          const preview = item.text.length > 75 ? item.text.slice(0, 72) + '…' : item.text;
          const candidate = item.suggestions?.[0];
          const note = candidate
            ? 'Suggested: ' + candidate.name + ' · ' + Math.round(Number(candidate.confidence || 0) * 100) + '%'
            : 'No supported candidate yet · manual review';
          return '<button type="button" class="ai-queue-item' + (window.ryuPremiumSelectedDialogueId === item.id ? ' active' : '') +
            '" data-ai-line="' + esc(item.id) + '" data-dialogue-id="' + esc(item.id) + '">' +
            '<span>Chapter ' + Number(item.chapter_number) + ' · ' + esc(item.chapter_title) + '</span><b>' + esc(preview) +
            '</b><small>' + esc(note) + '</small></button>';
        }).join('');
        const remaining = Math.max(0, pendingQueue.length - visibleCount);
        const loadMore = remaining > 0
          ? '<button type="button" class="btn small secondary" data-ai-load-more data-ai-next-count="' + nextVisibleCount +
            '" aria-label="Show more passages; ' + remaining + ' remaining" style="width:100%;margin-top:8px">Show more passages · ' +
            Math.min(120, remaining) + ' more (' + remaining + ' remaining)</button>'
          : '';
        queue.innerHTML = (visibleRows + loadMore) ||
          '<div class="ryu-character-empty"><b>Review queue is clear</b>All analyzed passages are assigned or skipped, or the analysis found no suggestions. Run analysis again to refresh suggestions.</div>';
      }
    }
    renderAiChapterDocument();
  }
  function renderAiChapterDocument() {
    const storyDocument = documentRef();
    if (!storyDocument) return;
    const selectedNumber = Number(window.ryuPremiumAiChapterNumber || characterStudioSelectedChapter || window.ryuPremiumSelectedChapter || chapters[0]?.number || 0);
    const chapter = chapters.find(item => Number(item.number) === selectedNumber) || chapters[0] || null;
    const heading = storyDocument.closest('.ai-story')?.querySelector('.story-head h2');
    const subheading = storyDocument.closest('.ai-story')?.querySelector('.story-head p');
    if (heading) heading.textContent = chapter ? 'Chapter ' + chapter.number + ' · ' + String(chapter.title || 'Untitled chapter') : 'No project selected';
    if (subheading) subheading.textContent = 'Green = manually assigned · gold = AI-assigned · orange = unconfirmed AI suggestion · plain text = no saved assignment or supported prediction.';
    if (!chapter || !String(chapter.text || '').trim()) {
      storyDocument.innerHTML = '<div class="ryu-character-empty"><b>No chapter text to analyze</b>Open a project with imported chapters, then run Analyze book.</div>';
      return;
    }
    const source = String(chapter.text || '');
    const rows = characterDialogueRowsForChapter(chapter);
    const signature = JSON.stringify([chapter.number,source,rows.map(row=>[row.start,row.end,row.speakers,row.assignmentSource,row.skipped,row.suggestions])]);
    if (storyDocument.dataset.liveSignature === signature) return;
    let html = '', cursor = 0;
    for (const row of rows) {
      if (row.start < cursor) continue;
      html += esc(source.slice(cursor,row.start)).replace(/\n/g,'<br>');
      let klass = 'ai-sentence';
      let label = '';
      if (row.assigned) {
        const sourceKind = row.assignmentSource === 'ai' ? 'ai' : 'manual';
        klass += ' confirmed confirmed-' + sourceKind;
        label = (sourceKind === 'ai' ? 'AI-assigned: ' : 'Manually assigned: ') + row.speakers.join(' + ');
      } else if (!row.skipped && row.suggestions?.length) {
        klass += ' review';
        const candidate = row.suggestions[0];
        label = 'Suggested: ' + candidate.name + ' · ' + Math.round(Number(candidate.confidence || 0) * 100) + '% · Review';
      } else if (row.skipped) {
        klass += ' unassigned';
        label = 'Skipped for this analysis';
      } else {
        klass += ' unassigned';
        label = 'Unassigned · select to review';
      }
      const active = window.ryuPremiumSelectedDialogueId === row.id ? ' active' : '';
      html += '<button type="button" class="' + klass + active + '" data-ai-sentence="source-backed" data-dialogue-id="' + esc(row.id) +
        '" data-chapter-number="' + Number(chapter.number) + '" data-start="' + row.start + '" data-end="' + row.end +
        '" title="' + esc(label) + '"><span class="ai-speaker">' + esc(label) + '</span>' + esc(row.text) + '</button>';
      cursor = row.end;
    }
    html += esc(source.slice(cursor)).replace(/\n/g,'<br>');
    storyDocument.innerHTML = html;
    storyDocument.dataset.liveSignature = signature;
  }
  function documentRef() {
    return document.querySelector('.char-view[data-char-view="ai"] .ai-document') ||
      document.querySelector('#chapters .ai-document');
  }
  const renderSelect = (select, rows, value, label) => {
    if (!select) return;
    const previous = select.value;
    const renderedRows = rows.map(row => [String(row[value] ?? ''), String(label(row) ?? '')]);
    const signature = JSON.stringify(renderedRows);
    if (select.dataset.backendOptionsSignature === signature && select.options.length === renderedRows.length) {
      if (renderedRows.some(([optionValue]) => optionValue === previous)) select.value = previous;
      return;
    }
    select.innerHTML = renderedRows.map(([optionValue, optionLabel]) =>
      '<option value="' + esc(optionValue) + '">' + esc(optionLabel) + '</option>'
    ).join('');
    select.dataset.backendOptionsSignature = signature;
    if (renderedRows.some(([optionValue]) => optionValue === previous)) select.value = previous;
  };
  const dashboardText = value => String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  function dashboardLeaves(root) {
    return root ? [...root.querySelectorAll('h1,h2,h3,h4,p,span,small,b,strong,label,button,div,a')].filter(node => !node.children.length) : [];
  }
  function dashboardFindText(root, text) {
    const target = dashboardText(text);
    return dashboardLeaves(root).find(node => dashboardText(node.textContent) === target) || null;
  }
  function dashboardHero(root) {
    const eyebrow = dashboardFindText(root, 'continue project');
    let node = eyebrow?.parentElement || null;
    while (node && node !== root) {
      const text = dashboardText(node.textContent);
      const actions = [...node.querySelectorAll('button,[role="button"],a')];
      if (actions.some(button => ['continue project','create new project'].includes(dashboardText(button.textContent))) &&
          text.includes('prepared') && text.includes('chapters')) return node;
      node = node.parentElement;
    }
    return root?.querySelector('.continue-project,.continue-card,.dashboard-continue,[data-dashboard-continue]') || null;
  }
  function projectFileUrl(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const normalized = raw.replace(/\\/g, '/');
    return encodeURI(normalized.startsWith('/') ? 'file://' + normalized : 'file:///' + normalized).replace(/#/g, '%23').replace(/\?/g, '%3F');
  }
  function applyProjectCover(element, path) {
    if (!element) return;
    const url = projectFileUrl(path);
    if (element.tagName === 'IMG') {
      if (url) { element.src = url; element.hidden = false; } else element.removeAttribute('src');
    } else if (url) {
      element.style.backgroundImage = 'url("' + url.replace(/"/g, '%22') + '")';
      element.style.backgroundSize = 'cover';
      element.style.backgroundPosition = 'center';
      element.style.backgroundRepeat = 'no-repeat';
      element.classList.add('has-project-cover');
    } else {
      element.style.removeProperty('background-image');
      element.classList.remove('has-project-cover');
    }
  }
  function applyProjectCovers(root) {
    if (!root) return;
    root.querySelectorAll('[data-cover-path]').forEach(card => {
      applyProjectCover(card.querySelector('.book-cover,.project-cover,[data-project-cover],img[alt*="cover" i]'), card.dataset.coverPath || '');
    });
  }
  function refreshDashboardFlow(project) {
    const flow = document.querySelector('.production-flow');
    if (!flow) return;
    const title = flow.querySelector('.flow-summary > div:first-child b');
    const readinessParts = [...(flow.querySelectorAll('.flow-readiness span,.flow-readiness strong') || [])];
    const readinessLabel = readinessParts.find(node => node.tagName.toLowerCase() === 'span');
    const readinessPercent = readinessParts.find(node => node.tagName.toLowerCase() === 'strong');
    const stages = [...flow.querySelectorAll('.flow-stage')];
    const links = [...flow.querySelectorAll('.flow-link')];
    const defaultDetails = [
      'Book & metadata', 'Structure & text', 'Voice profile',
      'Character voices', 'Names & terms', 'Music & effects', 'Build audiobook'
    ];
    if (title) title.textContent = project?.title || 'No project selected';

    if (!project) {
      if (readinessLabel) readinessLabel.textContent = '0 of 7 stages ready';
      if (readinessPercent) readinessPercent.textContent = '0%';
      stages.forEach((stage,index) => {
        stage.classList.remove('is-done','has-warning');
        const check = stage.querySelector('.flow-check');
        const detail = stage.querySelector('.flow-copy small');
        if (check) check.textContent = '';
        if (detail) detail.textContent = defaultDetails[index] || '';
      });
      links.forEach(link => link.classList.remove('is-done','has-warning'));
      return;
    }

    const chapterCount = Number(project.chapter_count || 0);
    const preparedChapters = Number(project.prepared_chapter_count || 0);
    const eligibleChapters = Math.max(0, Number(
      project.eligible_chapter_count ?? project.prepared_chapter_count ?? 0
    ));
    const emptyChapters = Math.max(0, Number(project.empty_chapter_count || 0));
    const excludedChapters = Math.max(0, Number(project.excluded_chapter_count || 0));
    const chaptersReady = eligibleChapters > 0;
    const metadataComplete = project.metadata_complete === true;
    const metadataMissing = Array.isArray(project.metadata_missing_fields)
      ? project.metadata_missing_fields : [];
    const narratorName = String(project.narrator || project.voice_profile || '').trim();
    const narratorReady = project.narrator_voice_configured === true &&
      project.narrator_profile_available === true && Boolean(String(project.voice_profile || '').trim());
    const narratorOnlyRequested = project.narrator_only_generation === true;
    const configuredCharacterVoiceCount = Math.max(0, Number(
      project.configured_character_voice_profile_count ?? project.character_voice_count ?? 0
    ));
    const narratorOnlyEligibilityInvalid = narratorOnlyRequested && configuredCharacterVoiceCount > 0;
    const narratorOnly = narratorOnlyRequested && configuredCharacterVoiceCount === 0;
    const characterCount = Number(project.character_count || 0);
    const characterVoiceCount = Math.max(0, Number(project.character_voice_count || 0));
    const dialogueIndexReady = project.dialogue_index_ready === true;
    const dialogueReviewComplete = project.dialogue_review_complete === true;
    const characterAssignmentIssues = Math.max(0, Number(project.character_assignment_issue_count || 0));
    const pendingDialogue = Math.max(0, Number(project.pending_dialogue_count || 0));
    const conflictingDialogue = Math.max(0, Number(project.conflicting_dialogue_count || 0));
    const dialogueIndexIssues = Math.max(0, Number(project.dialogue_index_issue_count || 0));
    const charactersReady = !narratorOnlyEligibilityInvalid && (
      narratorOnly || (
        dialogueIndexReady && dialogueReviewComplete && characterAssignmentIssues === 0
      )
    );
    const charactersDetail = narratorOnly
      ? '0 configured character voice profiles · saved narrator reads all passages'
      : (narratorOnlyRequested && configuredCharacterVoiceCount > 0
        ? configuredCharacterVoiceCount + ' configured profile(s) · switch to multi-character review'
        : (!dialogueIndexReady
          ? 'Dialogue index unavailable · refresh Character Studio'
          : (characterAssignmentIssues
            ? characterAssignmentIssues + ' saved character assignment(s) need attention'
            : (!dialogueReviewComplete
              ? pendingDialogue + ' passage(s) need review · ' + conflictingDialogue
                + ' conflict(s) · ' + dialogueIndexIssues + ' index issue(s)'
              : (characterCount === 0
                ? 'No character dialogue needs review'
                : characterVoiceCount + ' / ' + characterCount + ' character voice assignment(s)')))));
    const outputReady = project.output_configured === true &&
      project.output_folder_ready === true && project.output_format_supported === true;
    const canGenerate = chaptersReady && metadataComplete && narratorReady && outputReady && charactersReady;
    const pronunciationCount = Number(project.pronunciation_rule_count || 0);
    const soundConfigured = Boolean(project.sound_design_configured);
    const chapterDetail = chaptersReady
      ? eligibleChapters + ' eligible chapter(s)' +
        (emptyChapters || excludedChapters
          ? ' · skip ' + emptyChapters + ' empty / ' + excludedChapters + ' excluded' : '')
      : (chapterCount ? 'No eligible chapters' : 'No chapters imported');
    const metadataDetail = metadataComplete ? 'Book & metadata' :
      ('Missing: ' + (metadataMissing.slice(0, 3).join(', ') || 'required project details') +
        (metadataMissing.length > 3 ? ' +' + (metadataMissing.length - 3) + ' more' : ''));

    const stageState = [
      {key:'import', ready:metadataComplete, detail:metadataDetail},
      {key:'chapters', ready:chaptersReady, detail:chapterDetail},
      {key:'voices', ready:narratorReady, detail:narratorReady ? (narratorName || project.voice_profile) : 'Choose an available saved narrator'},
      {key:'characters', ready:charactersReady, detail:charactersDetail},
      {key:'pronunciation', ready:true, detail:pronunciationCount ? pronunciationCount + ' saved rules' : 'Names & terms'},
      {key:'sound', ready:true, detail:soundConfigured ? 'Configured' : 'Music & effects'},
      {key:'generate', ready:canGenerate, detail:project.completed && project.output_path ? 'Audiobook ready' :
        (canGenerate ? 'Build audiobook' : 'Complete the required setup')}
    ];
    const readyCount = stageState.filter(stage => stage.ready).length;
    if (readinessLabel) readinessLabel.textContent = readyCount + ' of ' + stageState.length + ' stages ready';
    if (readinessPercent) readinessPercent.textContent = Math.round(readyCount / stageState.length * 100) + '%';

    stages.forEach((stage,index) => {
      const current = stageState[index];
      if (!current) return;
      stage.classList.toggle('is-done', current.ready);
      stage.classList.toggle('has-warning', !current.ready);
      const check = stage.querySelector('.flow-check');
      const detail = stage.querySelector('.flow-copy small');
      if (check) check.textContent = current.ready ? '✓' : '!';
      if (detail) detail.textContent = current.detail;
      stage.dataset.projectReady = current.ready ? 'true' : 'false';
    });
    links.forEach((link,index) => {
      link.classList.toggle('is-done', Boolean(stageState[index]?.ready));
      link.classList.toggle('has-warning', Boolean(!stageState[index]?.ready && stageState[index+1]?.ready));
    });
  }
  async function refreshDashboardHero(rows = projects) {
    const dash = $('dashboard');
    if (!dash) return null;
    let active = null;
    try { active = await call('project.get_active'); } catch (_) {}
    const ordered = [...rows].sort((a,b) => (Date.parse(b.modified_at || '') || 0) - (Date.parse(a.modified_at || '') || 0));
    dashboardProject = (active && ordered.find(project => project.folder === active.folder)) ||
      ordered.find(project => !project.completed && Number(project.chapter_count || 0) > 0) ||
      ordered.find(project => Number(project.chapter_count || 0) > 0) || null;
    const hero = dashboardHero(dash);
    if (hero) {
      const project = dashboardProject;
      const heading = [...hero.querySelectorAll('h1,h2,h3,h4')]
        .find(node => !['continue project','production status'].includes(dashboardText(node.textContent)));
      if (heading) heading.textContent = project?.title || 'Start a new audiobook project';
      const subtitle = [...hero.querySelectorAll('p,span,small,div')]
        .filter(node => {
          const text = dashboardText(node.textContent);
          return text.includes('chapters') && (text.includes('narrator') || text.includes('character voices')) && node.querySelectorAll('*').length <= 2;
        }).sort((a,b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length)[0];
      if (subtitle) subtitle.textContent = project
        ? 'Narrator ' + (project.narrator || '—') + ' · ' + Number(project.chapter_count || 0) +
          ' chapters · ' + Number(project.character_voice_count || 0) + ' character voices'
        : '— chapters · — character voices';
      const percent = project ? Math.max(0, Math.min(100, Number(project.prepared_percent || 0))) : 0;
      // Keep the source HTML's existing bold percentage and adjacent label.
      const preparedLine = hero.querySelector('.meta-row > span:first-child');
      const preparedValue = preparedLine?.querySelector('b,strong');
      if (preparedValue) preparedValue.textContent = percent + '%';
      else if (preparedLine) preparedLine.textContent = percent + '% prepared';

      // Update only the bold chapter number so the "last edited" typography stays intact.
      const editedLine = hero.querySelector('.meta-row > span:nth-child(2)');
      const editedValue = editedLine?.querySelector('b,strong');
      const editedChapter = project?.last_edited_chapter_number || '—';
      if (editedValue) editedValue.textContent = 'Chapter ' + editedChapter;
      else if (editedLine) editedLine.textContent = 'Chapter ' + editedChapter + ' last edited';
      const progress = hero.querySelector('.progress i,.progress-fill,.progress-bar-fill,[role="progressbar"],progress,[style*="width:"]');
      if (progress) {
        progress.style.width = percent + '%';
        progress.setAttribute('aria-valuenow', String(percent));
        if (progress.tagName === 'PROGRESS') progress.value = percent;
      }
      applyProjectCover(hero.querySelector('.book-cover,.project-cover,[data-project-cover],img[alt*="cover" i]'), project?.cover_path || '');
      hero.dataset.dashboardProjectFolder = project?.folder || '';
      const action = [...hero.querySelectorAll('button,[role="button"],a')]
        .find(button => ['continue project','create new project'].includes(dashboardText(button.textContent)));
      if (action) {
        action.textContent = project ? 'Continue Project' : 'Create New Project';
        action.dataset.continueProjectFolder = project?.folder || '';
        action.disabled = false;
      }
    }
    const context = dashboardLeaves(document).find(node =>
      dashboardText(node.textContent).endsWith('· local project') && !node.closest('#dashboard'));
    if (context) context.textContent = dashboardProject ? dashboardProject.title + ' · Local project' : 'No project selected · Local project';
    refreshDashboardFlow(dashboardProject);
    return dashboardProject;
  }
  function renderAudiobookLibrary(rows = projects) {
    const page = $('player');
    if (!page) return;
    let container = $('backendAudiobookLibrary');
    if (!container) {
      container = document.createElement('section');
      container.id = 'backendAudiobookLibrary';
      container.className = 'section audiobook-library-section';
      const pageHead = page.querySelector(':scope > .page-head');
      if (pageHead && pageHead.parentElement === page) pageHead.insertAdjacentElement('afterend', container);
      else page.insertBefore(container, page.firstElementChild);
    }
    const available = (Array.isArray(rows) ? rows : []).filter(project =>
      Boolean(project && project.completed === true &&
        typeof project.output_path === 'string' && project.output_path.trim())
    );
    const signature = JSON.stringify({
      rows:available.map(project => [
        project.folder,project.title,project.status,project.output_path,project.author,
        project.narrator,project.chapter_count,project.cover_path
      ]),
      selected:selectedAudiobookFolder
    });
    if (container.dataset.audiobookLibrarySignature === signature) return;
    container.dataset.audiobookLibrarySignature = signature;
    const cards = available.map(project => {
      const folder = String(project.folder || '');
      const statusValue = String(project.status || 'completed').trim().toLowerCase();
      const statusLabel = statusValue.replace(/[_-]+/g,' ')
        .replace(/\b\w/g, letter => letter.toUpperCase());
      const title = String(project.title || 'Untitled audiobook');
      const author = String(project.author || '').trim();
      const narrator = String(project.narrator || '').trim();
      const details = [
        author,
        narrator ? 'Narrated by ' + narrator : '',
        Number(project.chapter_count || 0) + ' chapters'
      ].filter(Boolean).join(' · ');
      const selectedClass = folder && folder === selectedAudiobookFolder ? ' is-selected' : '';
      return '<article class="card audiobook-library-card' + selectedClass +
        '" data-project-folder="' + esc(folder) + '" data-cover-path="' + esc(project.cover_path || '') + '">' +
        '<div class="book-cover audiobook-card-cover" role="img" aria-label="Cover for ' + esc(title) + '"></div>' +
        '<div class="audiobook-card-content"><div class="audiobook-card-status-row">' +
        '<span class="badge" data-audiobook-status data-status="' + esc(statusValue) + '">' + esc(statusLabel) + '</span>' +
        '<span class="audiobook-card-playable">Ready to play</span></div>' +
        '<h3 class="audiobook-card-title" title="' + esc(title) + '">' + esc(title) + '</h3>' +
        '<p class="audiobook-card-meta">' + esc(details) + '</p>' +
        '<div class="audiobook-card-actions">' +
        '<button class="btn small secondary" type="button" data-open-project-folder="' + esc(folder) +
        '" aria-label="Open ' + esc(title) + ' in the audiobook player">Open</button>' +
        '<button class="btn small" type="button" data-play-project-folder="' + esc(folder) +
        '" aria-label="Play ' + esc(title) + '">Play</button></div></div></article>';
    }).join('');
    container.innerHTML = '<div class="audiobook-library-head"><div><p class="eyebrow">YOUR LIBRARY</p>' +
      '<h2>Generated audiobooks</h2></div><p class="muted">' + available.length +
      ' completed · ready to play</p></div>' +
      (cards ? '<div class="audiobook-library-grid">' + cards + '</div>' :
        '<p class="audiobook-library-empty">No finished audiobooks yet. Generate a book in Production Studio to see it here.</p>');
    applyProjectCovers(container);
  }
  function dashboardGenerationCard(root) {
    const title = dashboardFindText(root, 'production status') || dashboardFindText(root, 'active generation');
    let node = title?.parentElement || null;
    while (node && node !== root) {
      const text = dashboardText(node.textContent);
      const buttons = [...node.querySelectorAll('button,[role="button"],a')];
      if (text.includes('current chapter') && text.includes('processing stage') &&
          buttons.some(button => button.dataset.dashboardGenerationControl === '1' ||
            ['view job','pause','resume'].includes(dashboardText(button.textContent)))) return node;
      node = node.parentElement;
    }
    return null;
  }
  function setDashboardRow(root, label, value) {
    const leaf = dashboardFindText(root, label);
    if (!leaf) return;
    let node = leaf;
    for (let depth = 0; depth < 4 && node.parentElement; depth++) {
      const parent = node.parentElement;
      const siblings = [...parent.children].filter(child => child !== node && dashboardText(child.textContent) !== dashboardText(label));
      if (siblings.length) { writeTextIfChanged(siblings[siblings.length - 1], value); return; }
      node = parent;
    }
  }
  function refreshDashboardGeneration(jobs = []) {
    const root = $('dashboard');
    const card = root && dashboardGenerationCard(root);
    if (!card) return;
    const resumableStates = ['queued','running','pause_requested','paused','cancel_requested','retrying'];
    const active = jobs.filter(job => String(job.type || '').toLowerCase() === 'audiobook-generation' &&
      resumableStates.includes(String(job.state || '').toLowerCase()))
      .sort((a,b) => (Date.parse(b.updated_at || b.queued_at || '') || 0) - (Date.parse(a.updated_at || a.queued_at || '') || 0));
    const job = active[0] || null;
    // Bind by position within the static job card. These spans are deliberately
    // cleared when there is no job, so searching for their display text breaks
    // the next time generation starts.
    const progressLine = [...card.querySelectorAll('.job-line')][2] || null;
    const percentLabel = progressLine?.children?.[0] || null;
    const etaLabel = progressLine?.children?.[1] || null;
    const track = card.querySelector('.progress,.progress-track,.progress-bar,progress,[role="progressbar"]');
    const fill = card.querySelector('.progress i,.progress-fill,.progress-bar-fill,[role="progressbar"],progress,[style*="width:"]');
    const buttons = [...card.querySelectorAll('button,[role="button"],a')];
    const view = buttons.find(button => dashboardText(button.textContent) === 'view job');
    const control = buttons.find(button => button.dataset.dashboardGenerationControl === '1' ||
      ['pause','resume'].includes(dashboardText(button.textContent)));
    if (control) control.dataset.dashboardGenerationControl = '1';
    if (!job) {
      const selectedProject = dashboardProject || null;
      setDashboardRow(card, 'current chapter', selectedProject
        ? (Number(selectedProject.completed_chapter_count || 0) + ' chapters prepared')
        : 'No project selected');
      setDashboardRow(card, 'processing stage', selectedProject
        ? (selectedProject.completed && selectedProject.output_path ? 'Audiobook ready' :
          ('Setup checkpoint · ' + (savedResumeStage(selectedProject) || routeForResume(selectedProject))))
        : 'No active generation job');
      writeTextIfChanged(percentLabel, '');
      writeTextIfChanged(etaLabel, '');
      writeStyleIfChanged(fill, 'width', '0%');
      writeAttributeIfChanged(fill, 'aria-valuenow', '0');
      if (fill?.tagName === 'PROGRESS' && fill.value !== 0) fill.value = 0;
      writeStyleIfChanged(track, 'visibility', 'hidden');
      if (view) {
        writeBooleanIfChanged(view, 'disabled', true);
        if (view.dataset.dashboardJobId) delete view.dataset.dashboardJobId;
      }
      if (control) {
        writeBooleanIfChanged(control, 'disabled', true);
        if (control.dataset.dashboardJobId) delete control.dataset.dashboardJobId;
        if (control.dataset.dashboardGenerationAction) delete control.dataset.dashboardGenerationAction;
      }
      return;
    }
    const project = projects.find(row => row.folder === job.project_folder);
    const total = Number(job.chapters_total || project?.chapter_count || 0);
    const current = Number(job.current_chapter || 0);
    setDashboardRow(card, 'current chapter', current > 0 ? current + ' of ' + (total || '—') : (total ? '0 of ' + total : '—'));
    setDashboardRow(card, 'processing stage', job.stage || job.message || 'Working');
    const percent = Math.max(0, Math.min(100, Math.round(Number(job.progress || 0))));
    writeTextIfChanged(percentLabel, percent + '% complete');
    const eta = Number(job.eta_seconds);
    writeTextIfChanged(etaLabel, Number.isFinite(eta) && eta > 0 ? Math.floor(eta/60) + 'm ' + String(Math.floor(eta%60)).padStart(2,'0') + 's remaining' : '');
    writeStyleIfChanged(track, 'visibility', '');
    writeStyleIfChanged(fill, 'width', percent + '%');
    writeAttributeIfChanged(fill, 'aria-valuenow', String(percent));
    if (fill?.tagName === 'PROGRESS' && fill.value !== percent) fill.value = percent;
    if (view) {
      writeBooleanIfChanged(view, 'disabled', false);
      writeAttributeIfChanged(view, 'data-dashboard-job-id', job.job_id || '');
    }
    if (control) {
      const controlState = String(job.state || '').toLowerCase();
      const controlAction = controlState === 'running' ? 'pause' :
        controlState === 'paused' ? 'resume' : '';
      const controlLabel = controlState === 'pause_requested' ? 'Pausing…' :
        controlState === 'cancel_requested' ? 'Cancelling…' :
        controlState === 'queued' ? 'Queued…' :
        controlState === 'retrying' ? 'Retrying…' :
        controlState === 'paused' ? 'Resume' : 'Pause';
      writeTextIfChanged(control, controlLabel);
      writeBooleanIfChanged(control, 'disabled', !controlAction);
      if (controlAction) writeAttributeIfChanged(control, 'data-dashboard-generation-action', controlAction);
      else if (control.dataset.dashboardGenerationAction) delete control.dataset.dashboardGenerationAction;
      writeAttributeIfChanged(control, 'data-dashboard-job-id', job.job_id || '');
    }
  }
  function audiobookPageActive() {
    // Rendered page state is authoritative. Sidebar labels can be stale during
    // navigation and must not keep the dock hidden after Dashboard is visible.
    const page = $('player');
    if (!page || page.hidden || page.classList.contains('hidden')) return false;
    const style = window.getComputedStyle(page);
    return style.display !== 'none' && style.visibility !== 'hidden' && page.getClientRects().length > 0;
  }
  function syncMiniPlayer() {
    const dock = $('miniPlayer');
    const visible = Boolean(playerAudio && playerAudio.src && !miniPlayerDismissed && !audiobookPageActive());
    if (dock && dock.classList.contains('hidden') === visible) {
      dock.classList.toggle('hidden', !visible);
    }
    const body = document.body;
    if (body && body.classList.contains('ryu-mini-player-visible') !== visible) {
      body.classList.toggle('ryu-mini-player-visible', visible);
    }
  }
  function dashboardPageActive() {
    const page = $('dashboard');
    if (!page || page.hidden || page.classList.contains('hidden')) return false;
    const style = window.getComputedStyle(page);
    return style.display !== 'none' && style.visibility !== 'hidden' && page.getClientRects().length > 0;
  }
  function bindMiniPlayerNavigation() {
    if (typeof window.go === 'function' && !window.go.__ryuMiniPlayerWrapped) {
      const original = window.go;
      const wrapped = function(...args) {
        const result = original.apply(this,args);
        const page = String(args[0] || '').trim().toLowerCase();
        const aliases = {
          import:'import', chapters:'chapters', voice:'narrator', narrator:'narrator',
          characters:'characters', character:'characters', sound:'sound', sounds:'sound',
          production:'production', generator:'production', generation:'production', player:'player'
        };
        const stage = aliases[page];
        if (stage && dashboardProject?.folder) writeResumeCheckpoint(dashboardProject.folder, stage);
        setTimeout(() => {
          syncMiniPlayer();
          // Project cards are only rendered by Dashboard and Library. Do not
          // scan the whole project collection while navigating Voice, Chapters,
          // Production, Models, History or other unrelated modules.
          if (page === 'dashboard' || page === 'library') {
            refreshProjects().catch(() => {});
          }
          if (page === 'history') refreshHistory().catch(() => {});
        },0);
        return result;
      };
      wrapped.__ryuMiniPlayerWrapped = true;
      window.go = wrapped;
    }
    if (!window.__ryuMiniPlayerNavBound) {
      window.__ryuMiniPlayerNavBound = true;
      document.addEventListener('click', event => {
        if (event.target.closest('nav,aside,.sidebar,[data-page],[data-view]')) {
          setTimeout(syncMiniPlayer,0);
        }
      }, true);
    }
    if (!window.__ryuDashboardProjectTimer) {
      window.__ryuDashboardProjectTimer = setInterval(() => {
        if (dashboardPageActive()) refreshProjects().catch(() => {});
      }, 15000);
    }
  }
  function updateProjectDeleteButton() {
    const count = selectedProjectFolders.size;
    const trashButton = $('deleteSelectedProjects');
    if (trashButton) {
      trashButton.textContent = 'Move to Trash (' + count + ')';
      trashButton.disabled = count === 0;
      trashButton.title = count ? 'Move ' + count + ' selected book(s) to recoverable Deleted Books' : 'Select one or more books first';
      trashButton.style.opacity = count ? '1' : '.55';
    }
    const permanentButton = $('permanentlyDeleteSelectedProjects');
    if (permanentButton) {
      permanentButton.textContent = 'Permanently Delete (' + count + ')';
      permanentButton.disabled = count === 0;
      permanentButton.title = count ? 'Permanently delete ' + count + ' selected book(s); History and shared Character Library data are retained' : 'Select one or more books first';
      permanentButton.style.opacity = count ? '1' : '.55';
    }
  }

  async function deleteSelectedProjects() {
    const selected = projects.filter(project => selectedProjectFolders.has(String(project.folder)));
    if (!selected.length) {
      selectedProjectFolders.clear();
      updateProjectDeleteButton();
      return;
    }
    const titles = selected.slice(0, 8).map(project => '• ' + (project.title || 'Untitled')).join('\n');
    const remaining = selected.length > 8 ? '\n• … and ' + (selected.length - 8) + ' more' : '';
    if (!window.confirm('Move ' + selected.length + ' selected book(s) to Deleted Books? You can restore them later.\n\n' + titles + remaining)) return;
    const button = $('deleteSelectedProjects');
    if (button) button.disabled = true;
    let moved = 0;
    const failures = [];
    for (const project of selected) {
      try {
        await call('project.trash', {folder: project.folder});
        selectedProjectFolders.delete(String(project.folder));
        moved += 1;
      } catch (error) {
        failures.push((project.title || 'Untitled') + ': ' + (error?.message || String(error)));
      }
    }
    await refreshProjects();
    updateProjectDeleteButton();
    if (failures.length) {
      message('Moved ' + moved + ' book(s) to Deleted Books. Not moved: ' + failures.join(' | '), true);
    } else {
      message('Moved ' + moved + ' book(s) to Deleted Books. Their saved work is recoverable until permanently purged.');
    }
  }
  async function deleteSelectedProjectsPermanently() {
    const selected = projects.filter(project => selectedProjectFolders.has(String(project.folder)));
    if (!selected.length) {
      selectedProjectFolders.clear();
      updateProjectDeleteButton();
      return;
    }
    const titles = selected.slice(0, 8).map(project => '• ' + (project.title || 'Untitled')).join('\n');
    const remaining = selected.length > 8 ? '\n• … and ' + (selected.length - 8) + ' more' : '';
    const confirmed = window.confirm(
      'Permanently delete ' + selected.length + ' selected book(s)? This cannot be undone.\n\n' +
      titles + remaining +
      '\n\nProject/source files and saved generated output will be removed. History records and shared Character Library data will be retained.'
    );
    if (!confirmed) return;
    const button = $('permanentlyDeleteSelectedProjects');
    if (button) button.disabled = true;
    let deleted = 0;
    const failures = [];
    for (const project of selected) {
      try {
        await call('project.delete', {folder: project.folder});
        selectedProjectFolders.delete(String(project.folder));
        deleted += 1;
      } catch (error) {
        failures.push((project.title || 'Untitled') + ': ' + (error?.message || String(error)));
      }
    }
    await refreshProjects();
    updateProjectDeleteButton();
    if (failures.length) {
      message('Permanently deleted ' + deleted + ' book(s). Not deleted: ' + failures.join(' | '), true);
    } else {
      message('Permanently deleted ' + deleted + ' book(s). History records and shared Character Library data were retained.');
    }
  }

  function ensureProjectTrashControl() {
    const root = $('library');
    if (!root) return;
    const search = $('librarySearch');
    const filters = $('libraryFilters');
    const parent = filters?.parentElement || search?.parentElement || root;
    if (!$('deleteSelectedProjects')) {
      const deleteButton = document.createElement('button');
      deleteButton.id = 'deleteSelectedProjects';
      deleteButton.type = 'button';
      deleteButton.className = 'btn small ghost library-delete';
      deleteButton.textContent = 'Move to Trash (0)';
      deleteButton.title = 'Select one or more books first';
      deleteButton.style.cssText = 'margin-left:8px;white-space:nowrap;';
      deleteButton.addEventListener('click', () => deleteSelectedProjects().catch(err => message(err?.message || String(err), true)));
      parent.appendChild(deleteButton);
    }
    if (!$('permanentlyDeleteSelectedProjects')) {
      const permanentButton = document.createElement('button');
      permanentButton.id = 'permanentlyDeleteSelectedProjects';
      permanentButton.type = 'button';
      permanentButton.className = 'btn small danger library-delete';
      permanentButton.textContent = 'Permanently Delete (0)';
      permanentButton.title = 'Select one or more books first';
      permanentButton.style.cssText = 'margin-left:8px;white-space:nowrap;';
      permanentButton.addEventListener('click', () => deleteSelectedProjectsPermanently().catch(err => message(err?.message || String(err), true)));
      parent.appendChild(permanentButton);
    }
    if (!$('openProjectTrashBin')) {
      const button = document.createElement('button');
      button.id = 'openProjectTrashBin';
      button.type = 'button';
      button.className = 'btn small secondary';
      button.textContent = 'Deleted Books / Recover';
      button.title = 'Restore a book or permanently purge it from managed Trash';
      button.style.cssText = 'margin-left:8px;white-space:nowrap;';
      button.addEventListener('click', () => openProjectTrashBin().catch(err => message(err?.message || String(err), true)));
      parent.appendChild(button);
    }
    updateProjectDeleteButton();
  }
  function ensureProjectTrashModal() {
    let modal = $('projectTrashModal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'projectTrashModal';
    modal.style.cssText = 'display:none;position:fixed;inset:0;z-index:100001;background:rgba(4,7,12,.84);backdrop-filter:blur(7px);align-items:center;justify-content:center;padding:22px;box-sizing:border-box;';
    modal.innerHTML = '<div role="dialog" aria-modal="true" aria-labelledby="projectTrashTitle" style="width:min(760px,96vw);max-height:84vh;overflow:auto;background:#10141d;border:1px solid #343b49;border-radius:16px;padding:22px;box-shadow:0 24px 80px rgba(0,0,0,.5);color:#f4f5f8"><div style="display:flex;justify-content:space-between;align-items:center;gap:12px"><div><h2 id="projectTrashTitle" style="margin:0">Deleted Books</h2><p class="muted" style="margin:6px 0 0">Restore a book to the active Library or permanently purge it when you are sure.</p></div><button type="button" class="btn small secondary" data-close-project-trash>Close</button></div><div id="projectTrashEntries" style="display:grid;gap:10px;margin-top:18px"></div></div>';
    modal.addEventListener('click', async event => {
      if (event.target === modal || event.target.closest('[data-close-project-trash]')) {
        modal.style.display = 'none';
        return;
      }
      const restore = event.target.closest('[data-restore-project]');
      const purge = event.target.closest('[data-purge-project]');
      if (!restore && !purge) return;
      const button = restore || purge;
      const id = button.dataset.restoreProject || button.dataset.purgeProject;
      const record = projectTrashEntries.find(item => String(item.id) === String(id));
      button.disabled = true;
      try {
        if (restore) {
          await call('project.trash.restore', {id});
          message('Restored "' + (record?.title || 'book') + '" to the active Library.');
        } else {
          if (!window.confirm('Permanently delete "' + (record?.title || 'this book') + '" and its trashed generated files? This cannot be undone.')) return;
          await call('project.trash.purge', {id});
          message('Permanently purged "' + (record?.title || 'book') + '".');
        }
        await refreshProjects();
        await loadProjectTrashEntries(modal);
      } catch (error) {
        message(error?.message || String(error), true);
      } finally {
        button.disabled = false;
      }
    });
    document.body.appendChild(modal);
    return modal;
  }
  let projectTrashEntries = [];
  let selectedProjectFolders = new Set();
  async function loadProjectTrashEntries(modal) {
    projectTrashEntries = await call('project.trash.list');
    const list = $('projectTrashEntries');
    if (list) list.innerHTML = projectTrashEntries.map(item => {
      const when = item.deleted_at ? new Date(item.deleted_at).toLocaleString() : 'Deletion date unavailable';
      return '<article class="card" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:14px"><div><b>' + esc(item.title || 'Untitled book') + '</b><div class="muted" style="margin-top:4px">Moved to Trash · ' + esc(when) + '</div></div><div style="display:flex;gap:8px;flex-wrap:wrap"><button type="button" class="btn small secondary" data-restore-project="' + esc(item.id) + '">Restore</button><button type="button" class="btn small ghost library-delete" data-purge-project="' + esc(item.id) + '">Delete permanently</button></div></article>';
    }).join('') || '<div class="card" style="padding:18px"><b>Deleted Books is empty</b><p class="muted">Books moved from the active Library will appear here and can be restored.</p></div>';
    if (modal) modal.style.display = 'flex';
  }
  async function openProjectTrashBin() {
    const modal = ensureProjectTrashModal();
    await loadProjectTrashEntries(modal);
  }

  function setProjectCardStatus(status) {
    const card = document.querySelector('.project-mini');
    const parts = card?.querySelectorAll('.pm-body small');
    const statusNode = parts?.length ? parts[parts.length - 1] : null;
    const text = String(status || '').trim();
    if (statusNode && text && statusNode.textContent !== text) statusNode.textContent = text;
  }

  async function refreshCurrentProjectCard(statusOverride = '') {
    const requestToken = ++activeProjectCardEpoch;
    let active = null;
    try { active = await call('project.get_active'); }
    catch (_) {
      if (requestToken !== activeProjectCardEpoch) return window.ryuPremiumActiveProject || null;
      return null; // Preserve the last confirmed UI state on a transient bridge error.
    }
    // Concurrent open/rename/hydration calls can complete out of order. Ignore
    // stale results before they can replace the project's current identity.
    if (requestToken !== activeProjectCardEpoch) return window.ryuPremiumActiveProject || null;
    if (active) window.ryuPremiumActiveProject = active;
    const card = document.querySelector('.project-mini');
    const titleNode = card?.querySelector('.pm-body b');
    const crumb = document.querySelector('.topbar .crumb span');
    const previousTitle = String(titleNode?.textContent || '');
    const folder = String(active?.folder || '');
    const title = String(active?.title || '').trim();
    if (!active || !folder || !title) {
      window.ryuPremiumActiveProject = null;
      activeProjectCardFolder = null;
      if (titleNode && titleNode.textContent !== 'No project selected') titleNode.textContent = 'No project selected';
      if (titleNode) titleNode.title = 'Open a project from Library to begin';
      if (crumb && crumb.textContent !== 'No project selected') crumb.textContent = 'No project selected';
      setProjectCardStatus('No project selected');
      return null;
    }
    const changedProject = folder !== activeProjectCardFolder;
    const renamed = !changedProject && previousTitle && previousTitle !== title;
    if (changedProject) {
      // Do not let old-project chapter selections, casts or queued suggestions
      // remain visible while the newly opened project is being hydrated.
      chapterListEpoch++;
      chapterSelectionEpoch++;
      characterListEpoch++;
      characterSuggestionsEpoch++;
      chapters = [];
      characters = [];
      characterDialogueSuggestions = [];
      characterNarrationSegments = [];
      characterAnalysisStatus = {analyzed:false, updated_at:null, dialogue_total:0, unassigned_dialogue:0, suggestion_count:0};
      characterStudioSelectedChapter = null;
      characterStudioSelectedSeries = '';
      window.ryuPremiumSelectedCharacter = '';
      window.ryuPremiumSelectedCharacterSeries = '';
      window.ryuPremiumSelectedAssignedDialogueKey = '';
      window.ryuPremiumSelectedChapter = null;
      window.ryuPremiumSelectedDialogueId = '';
      window.ryuPremiumAiChapterNumber = null;
      window.ryuPremiumDialogueReviewItems = [];
      const manualStory = $('manualStory');
      if (manualStory) manualStory.dataset.liveSignature = '';
      const aiStory = document.querySelector('#characters .ai-document');
      if (aiStory) aiStory.dataset.liveSignature = '';
      renderCharacterStudioLive();
      renderDialogueReview();
    }
    activeProjectCardFolder = folder;
    if (titleNode && titleNode.textContent !== title) titleNode.textContent = title;
    if (titleNode) {
      titleNode.title = title;
      titleNode.setAttribute('aria-label', 'Current project: ' + title);
    }
    if (crumb && crumb.textContent !== title + ' · Local project') crumb.textContent = title + ' · Local project';
    if (statusOverride) setProjectCardStatus(statusOverride);
    else if (changedProject) setProjectCardStatus('Project open · saved locally');
    else if (renamed) setProjectCardStatus('Renamed · saved locally');
    await refreshSeriesNarratorControls();
    return active;
  }

  function installProjectCardStatusObserver() {
    if (projectCardStatusObserver) projectCardStatusObserver.disconnect();
    const saveState = $('saveState');
    if (!saveState || typeof MutationObserver === 'undefined') return;
    projectCardStatusObserver = new MutationObserver(() => {
      const status = String(saveState.textContent || '').replace(/\\s+/g, ' ').trim();
      if (status && activeProjectCardFolder) setProjectCardStatus(status);
    });
    projectCardStatusObserver.observe(saveState, {subtree:true,childList:true,characterData:true});
  }

  async function refreshLatestImport() {
    const page = $('import');
    if (!page) return null;
    let card = $('latestImportCard');
    if (!card) {
      card = document.createElement('section');
      card.id = 'latestImportCard';
      card.className = 'card';
      card.style.marginBottom = '16px';
      const header = page.querySelector('.page-head');
      if (header && header.parentElement === page) header.insertAdjacentElement('afterend', card);
      else page.prepend(card);
    }
    let record = null;
    try { record = await call('import.latest.get'); }
    catch (error) {
      card.hidden = true;
      card.innerHTML = '';
      return null;
    }
    if (!record || !record.project_folder) {
      card.hidden = true;
      card.innerHTML = '';
      delete card.dataset.latestImportSignature;
      return null;
    }
    const signature = JSON.stringify([
      record.project_folder, record.title, record.source_name,
      record.chapter_count, record.imported_at
    ]);
    if (card.dataset.latestImportSignature !== signature) {
      card.dataset.latestImportSignature = signature;
      const importedAt = new Date(record.imported_at);
      const importedLabel = Number.isNaN(importedAt.getTime())
        ? String(record.imported_at || 'Recently')
        : importedAt.toLocaleString();
      card.innerHTML =
        '<div class="section-head" style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap">' +
          '<div><span class="eyebrow">Recent import</span><h3 style="margin:4px 0">' + esc(record.title || 'Imported book') + '</h3>' +
          '<p class="muted" style="margin:0">' + esc(record.source_name || 'Source file unavailable') + ' · ' +
          Number(record.chapter_count || 0) + ' chapters · ' + esc(importedLabel) + '</p></div>' +
          '<button class="btn small" type="button" data-open-latest-import>Open imported project</button></div>';
      card.querySelector('[data-open-latest-import]')?.addEventListener('click', async () => {
        try {
          await call('project.open', {folder:record.project_folder});
          await refreshProjects();
          window.go('library');
          showToast('Opened ' + String(record.title || 'the imported project') + '.');
        } catch (error) {
          showToast(error.message || 'Could not open the imported project.', 'error');
        }
      });
    }
    card.hidden = false;
    return record;
  }

  async function refreshProjects() {
    const requestToken = ++projectListEpoch;
    const loadedProjects = await call('project.list');
    if (requestToken !== projectListEpoch) return projects;
    projects = (Array.isArray(loadedProjects) ? loadedProjects : []).sort((a,b) => (Date.parse(b.modified_at || '') || 0) - (Date.parse(a.modified_at || '') || 0));
    selectedProjectFolders = new Set([...selectedProjectFolders].filter(folder => projects.some(project => String(project.folder) === folder)));
    const grid = $('libraryGrid');
    ensureProjectTrashControl();
    const search = ($('librarySearch')?.value || '').trim().toLowerCase();
    const filter = $('libraryFilters')?.querySelector('button.active')?.textContent?.trim().toLowerCase() || 'all';
    const visible = projects.filter(p => {
      const complete = Boolean(p.completed), status = String(p.status || '').toLowerCase();
      const matchesFilter = filter === 'all' || (filter === 'completed' && complete) ||
        (filter === 'active' && !complete && !['failed','error','attention'].includes(status)) ||
        (filter === 'attention' && (['failed','error','attention'].includes(status) || !Number(p.chapter_count || 0)));
      return matchesFilter && (!search || (p.title + ' ' + (p.source_path || '') + ' ' + status).toLowerCase().includes(search));
    });
    const librarySignature = JSON.stringify({
      rows:visible.map(p => [p.folder,p.title,p.completed,p.status,p.source_path,p.chapter_count,p.cover_path,p.modified_at]),
      search, filter, selected:[...selectedProjectFolders].sort()
    });
    if (grid && grid.dataset.projectRenderSignature !== librarySignature) {
      grid.dataset.projectRenderSignature = librarySignature;
      grid.innerHTML = visible.map(p => {
        const complete = Boolean(p.completed), status = complete ? 'Completed' : (p.status || 'New');
        return '<article class="card project-card" data-name="' + esc(p.title) + '" data-project-folder="' + esc(p.folder) +
          '" data-cover-path="' + esc(p.cover_path || '') + '"><div class="book-cover"></div><div class="project-pad"><span class="badge ' +
          (complete ? '' : 'info') + '">' + esc(status) + '</span><h3>' + esc(p.title) + '</h3><p class="muted">' +
          Number(p.chapter_count || 0) + ' chapters · Local project</p><p class="muted">' + esc(p.source_path || 'Source path unavailable') +
          '</p><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px"><label style="display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#abb4c4;cursor:pointer"><input type="checkbox" data-select-project="' + esc(p.folder) + '" ' + (selectedProjectFolders.has(String(p.folder)) ? 'checked' : '') + ' aria-label="Select ' + esc(p.title) + ' for bulk deletion" style="accent-color:#c62951"> Select</label><button class="btn small" type="button" data-open-project="' + esc(p.folder) + '">Open project</button><button class="btn small ghost library-delete" type="button" data-delete-project="' + esc(p.folder) + '" aria-label="Move ' + esc(p.title) + ' to Deleted Books">Delete</button></div></div></article>';
      }).join('') || '<p class="muted">No local projects found. Import a book to start your library.</p>';
      applyProjectCovers(grid);
    }
    const dash = $('dashboard');
    if (dash) {
      const metrics = dash.querySelectorAll('.metrics .metric strong');
      const completed = projects.filter(p => p.completed).length;
      const active = projects.filter(p => !p.completed && !['failed','error','attention'].includes(String(p.status || '').toLowerCase())).length;
      const attention = projects.filter(p => ['failed','error','attention'].includes(String(p.status || '').toLowerCase()) || !Number(p.chapter_count || 0)).length;
      [projects.length, completed, active, attention].forEach((value, index) => { if (metrics[index]) metrics[index].textContent = value; });
      const recent = dash.querySelector('.recent-grid');
      const recentSignature = JSON.stringify(projects.slice(0, 3).map(p => [p.folder,p.title,p.status,p.chapter_count,p.completed,p.cover_path]));
      if (recent && recent.dataset.projectRenderSignature !== recentSignature) {
        recent.dataset.projectRenderSignature = recentSignature;
        recent.innerHTML = projects.slice(0, 3).map(p => {
          const status = String(p.status || 'new').toLowerCase();
          const badge = p.completed ? 'Completed' : (['failed','error','attention'].includes(status) || !Number(p.chapter_count || 0) ? 'Attention' : 'Active');
          const badgeClass = badge === 'Completed' ? '' : (badge === 'Attention' ? 'warn' : 'info');
          return '<article class="card project-card" data-project-folder="' + esc(p.folder) + '" data-cover-path="' +
            esc(p.cover_path || '') + '"><div class="book-cover"></div><div class="project-pad"><span class="badge ' +
            badgeClass + '">● ' + badge + '</span><h3>' + esc(p.title) + '</h3><p class="muted">' +
            Number(p.chapter_count || 0) + ' chapters · ' + esc(p.status || 'Local project') + '</p></div></article>';
        }).join('') || '<p class="muted">No local projects yet. Import a book to see it here.</p>';
        applyProjectCovers(recent);
      }
    }
    await refreshDashboardHero(projects);
    await refreshCurrentProjectCard();
    await refreshLatestImport();
    renderAudiobookLibrary(projects);
    if (!playerAudio || !playerAudio.src) clearAudiobookPlayerDisplay();
    if (isVisiblePage('generate')) await refreshProductionSummary();
    return projects;
  }
  const voiceLibraryTitles = {
    offline:'Offline Neural Voices', sapi:'Windows SAPI', customvoice:'Qwen CustomVoice',
    voicedesign:'Qwen VoiceDesign', qwenclone:'Qwen Voice Clone', customref:'Chatterbox Reference Voice',
    edge:'Edge TTS', eleven:'ElevenLabs'
  };
  function voiceLanguageFacet(row) {
    const raw = String(row.language_name || row.language || row.locale || row.locale_code || '').trim();
    if (!raw) return 'Unknown';
    const normalized = raw.replace(/_/g, '-');
    if (/^[a-z]{2,3}(?:-[a-z0-9]+)*$/i.test(normalized)) {
      const code = normalized.split('-')[0].toLowerCase();
      return ({en:'English',af:'Afrikaans',ja:'Japanese',zh:'Chinese',cmn:'Chinese',es:'Spanish',fr:'French',de:'German',hi:'Hindi',ko:'Korean',it:'Italian',pt:'Portuguese',ru:'Russian',ar:'Arabic',nl:'Dutch',sv:'Swedish',da:'Danish',no:'Norwegian',fi:'Finnish',pl:'Polish',tr:'Turkish',uk:'Ukrainian',vi:'Vietnamese',th:'Thai',id:'Indonesian',ms:'Malay',he:'Hebrew',el:'Greek',cs:'Czech',ro:'Romanian',hu:'Hungarian',bn:'Bengali',ta:'Tamil',te:'Telugu'}[code] || code.toUpperCase());
    }
    return raw.replace(/\s*\([^)]*\)\s*$/, '').trim() || raw;
  }
  function voiceRegionFacet(row) {
    const explicit = String(row.region_name || row.region || row.accent || '').trim();
    const locale = String(row.locale || row.locale_code || '').trim();
    const raw = explicit || locale;
    if (!raw) return 'Unknown';
    if (/^[a-z]{2,3}-[a-z]{2,4}$/i.test(raw)) {
      const code = raw.split('-').pop().toUpperCase();
      return ({US:'United States',GB:'United Kingdom',UK:'United Kingdom',ZA:'South Africa',IN:'India',AU:'Australia',CA:'Canada',NZ:'New Zealand',IE:'Ireland',SG:'Singapore',NG:'Nigeria',KE:'Kenya',AL:'Albania',BA:'Bosnia and Herzegovina',BR:'Brazil',MX:'Mexico',FR:'France',DE:'Germany',IT:'Italy',ES:'Spain',JP:'Japan',KR:'South Korea',CN:'China',TW:'Taiwan',HK:'Hong Kong',PH:'Philippines',MY:'Malaysia',ID:'Indonesia'}[code] || code);
    }
    const code = raw.toUpperCase();
    return ({US:'United States',GB:'United Kingdom',UK:'United Kingdom',ZA:'South Africa',IN:'India',AU:'Australia',CA:'Canada',NZ:'New Zealand',IE:'Ireland',SG:'Singapore',NG:'Nigeria',KE:'Kenya',AL:'Albania',BA:'Bosnia and Herzegovina',BR:'Brazil',MX:'Mexico'}[code] || raw);
  }
  function voiceGenderFacet(row) {
    const raw = String(row.gender || row.voice_metadata || row.metadata || 'Unknown').trim().toLowerCase();
    if (/female|woman|girl/.test(raw)) return 'Female';
    if (/male|man|boy/.test(raw)) return 'Male';
    if (/neutral|androgyn/.test(raw)) return 'Neutral';
    return raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : 'Unknown';
  }
  function voiceCategories(row) {
    // Provider payloads often include an empty categories array alongside a useful
    // category/use_case/personality field. Combine all present fields instead of
    // letting the first empty array hide the remaining metadata.
    const values = [];
    for (const raw of [row.categories, row.category, row.use_case, row.personalities, row.styles]) {
      if (Array.isArray(raw)) values.push(...raw);
      else if (raw != null) values.push(...String(raw).split(/[,;|]/));
    }
    return [...new Set(values.map(value => String(value || '').trim()).filter(Boolean))];
  }
  function renderProviderCatalog(providerKey, result) {
    const panel = document.querySelector('#voices .provider[data-provider="' + providerKey + '"]');
    if (!panel || !result) return;
    const rows = Array.isArray(result.voices) ? result.voices : [];
    const title = voiceLibraryTitles[providerKey] || providerKey;
    const health = panel.querySelector('.health');
    const healthTitle = health?.querySelector('b');
    const inventoryStatus = String(result.model_inventory?.status || '');
    const providerStatus = !result.ready
      ? (['Missing','Not configured','Partially installed','Unhealthy','Unsupported','Location unavailable','Unavailable','Not assessed'].includes(inventoryStatus) ? inventoryStatus : 'Provider unavailable')
      : inventoryStatus === 'Installed' ? 'Installed · functional verification pending' : inventoryStatus || 'Ready';
    if (healthTitle) healthTitle.textContent = title + ' · ' + providerStatus;
    let healthDetail = health?.querySelector('small,.muted');
    if (!healthDetail && healthTitle?.parentElement) {
      healthDetail = document.createElement('small');
      healthDetail.className = 'muted';
      healthDetail.style.cssText = 'display:block;margin-top:4px;line-height:1.45';
      healthTitle.parentElement.appendChild(healthDetail);
    }
    if (healthDetail) healthDetail.textContent = [result.model_inventory?.message, result.message || (result.count + ' live catalogue entries')].filter(Boolean).join(' · ');
    updateVoiceHealthIndicator(providerKey,result);
    if (providerKey === 'eleven' && $('apiState')) $('apiState').textContent = result.ready ? 'API key connected · ' + providerStatus : (result.message || 'API key not configured');
    if (providerKey === 'eleven') {
      const createPanel = panel.querySelector('[data-epanel="create"]');
      if (createPanel) {
        let note = createPanel.querySelector('.voice-setup-note');
        if (!note) { note = document.createElement('p'); note.className = 'voice-setup-note muted'; createPanel.prepend(note); }
        note.textContent = result.ready
          ? (result.message || 'ElevenLabs is connected. Voice creation uses your account and may consume credits.')
          : (result.message || 'ElevenLabs API key is not configured.') +
            ' You can still create and download audio manually on the ElevenLabs website; Ryu cannot fetch account audio without supported API access.';
        let website = createPanel.querySelector('#openElevenLabsWebsite');
        if (!website) {
          website = document.createElement('button'); website.id = 'openElevenLabsWebsite';
          website.type = 'button'; website.className = 'btn secondary'; website.textContent = 'Open ElevenLabs Website';
          website.dataset.openElevenlabsWeb = 'studio';
          website.style.cssText = 'margin:8px 0 12px';
          createPanel.appendChild(website);
        }
      }
      for (const id of ['generateCandidates','generateMore']) {
        const button = $(id);
        if (button) {
          button.disabled = !result.ready;
          button.title = result.ready ? 'Generate temporary voice candidates using your connected account'
            : 'Connect an ElevenLabs API key to generate voices inside Ryu. Website-based generation is available separately.';
        }
      }
      if (!result.ready && $('addPremium')) {
        $('addPremium').disabled = true;
        $('addPremium').title = 'Connect an ElevenLabs API key before creating and saving a voice in Ryu.';
      }
    }

    const form = panel.querySelector('.form3');
    if (!form && providerKey !== 'eleven') return;
    let filtered = rows;
    // ElevenLabs uses its form5 as voice-design configuration, not catalogue
    // filters. Render its My Voices catalogue directly without mutating those controls.
    if (form) {
      let categoryLabel = form.querySelector(':scope > .voice-category-filter');
      const categoryValues = [...new Set(rows.flatMap(voiceCategories))].sort((a,b)=>a.localeCompare(b));
      if (categoryValues.length && !categoryLabel) {
        categoryLabel=document.createElement('label');categoryLabel.className='voice-category-filter';
        const caption=document.createElement('span');caption.textContent='Category';
        const select=document.createElement('select');select.className='select';
        categoryLabel.append(caption,select);form.appendChild(categoryLabel);
      } else if (!categoryValues.length && categoryLabel) { categoryLabel.remove();categoryLabel=null; }
      const facets=[...form.querySelectorAll('select')];
      const languageValues=[...new Set(rows.map(voiceLanguageFacet).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
      const genderValues=[...new Set(rows.map(voiceGenderFacet).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
      const regionValues=[...new Set(rows.map(voiceRegionFacet).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
      const optionsFor=(select,defaultLabel,values,defaultValue)=>{
        if(!select)return;
        const previous=select.value;
        const optionRows=[[defaultValue,defaultLabel],...values.map(value=>[value,value])];
        const signature=JSON.stringify(optionRows);
        // Retain the existing native select options when the provider metadata
        // is unchanged. Recreating these controls on every polling refresh causes
        // a visible flash and can steal keyboard focus from the active filter.
        if(select.dataset.voiceFacetOptionsSignature!==signature){
          select.replaceChildren();
          for(const [value,label] of optionRows){
            const option=document.createElement('option');option.value=value;option.textContent=label;select.appendChild(option);
          }
          select.dataset.voiceFacetOptionsSignature=signature;
        }
        select.value=values.find(value=>value.toLowerCase()===String(previous).toLowerCase())||defaultValue;
        select.onchange=()=>renderProviderCatalog(providerKey,providerCatalogs[providerKey]);
      };
      optionsFor(facets[0],'All languages',languageValues,'All languages');
      optionsFor(facets[1],'All',genderValues,'All');
      optionsFor(facets[2],'All regions',regionValues,'All regions');
      optionsFor(categoryLabel?.querySelector('select'),'All categories',categoryValues,'All categories');
      const languageFilter=facets[0]?.value||'All languages';
      const genderFilter=facets[1]?.value||'All';
      const regionFilter=facets[2]?.value||'All regions';
      const categoryFilter=categoryLabel?.querySelector('select')?.value||'All categories';
      const same=(a,b)=>String(a||'').trim().toLowerCase()===String(b||'').trim().toLowerCase();
      filtered=rows.filter(row=>
        (languageFilter==='All languages'||same(voiceLanguageFacet(row),languageFilter))&&
        (genderFilter==='All'||same(voiceGenderFacet(row),genderFilter))&&
        (regionFilter==='All regions'||same(voiceRegionFacet(row),regionFilter))&&
        (categoryFilter==='All categories'||voiceCategories(row).some(value=>same(value,categoryFilter)))
      );
    }
    const recommended = panel.querySelector('input[type="checkbox"]');
    if (providerKey === 'offline' && recommended?.checked) {
      filtered = filtered.slice().sort((a,b) => {
        const score = row => /amy|ryan|serena|aiden/i.test(String(row.name || '')) ? 0 : 1;
        return score(a)-score(b) || String(a.name).localeCompare(String(b.name));
      });
      recommended.onchange = () => renderProviderCatalog(providerKey, providerCatalogs[providerKey]);
    }

    let listHost;
    if (providerKey === 'eleven') {
      listHost = panel.querySelector('[data-epanel="mine"]');
      if (!listHost) return;
    } else {
      listHost = panel.querySelector(':scope > .voice-catalog-live');
      if (!listHost) {
        listHost = document.createElement('div');
        listHost.className = 'voice-catalog-live';
        listHost.style.cssText = 'max-height:340px;overflow-y:auto;overscroll-behavior:contain;display:grid;gap:7px;margin-top:10px;padding-right:4px;min-height:0';
        const form = panel.querySelector('.form3');
        if (form) form.insertAdjacentElement('afterend', listHost);
        else panel.appendChild(listHost);
      }
    }
    const renderKey=JSON.stringify(filtered.map(row=>[
      row.voice_id||row.name,row.name,row.provider,row.language,row.language_name,row.locale,row.locale_code,
      row.region,row.region_name,row.accent,row.gender,row.category,row.use_case,
      voiceCategories(row),Boolean(row.saved),row.description
    ]));
    // Keep the catalogue DOM intact when a refresh returns the same filtered rows.
    // Replacing hundreds of voice cards unnecessarily caused visible flashes and lost scroll.
    if(listHost.dataset.catalogRenderKey===renderKey)return;
    const previousScrollTop=listHost.scrollTop;
    listHost.dataset.catalogRenderKey=renderKey;
    listHost.querySelectorAll(':scope > .voice-row').forEach(row=>row.remove());
    if(providerKey!=='eleven')panel.querySelectorAll(':scope > .voice-row').forEach(row=>row.remove());
    listHost.querySelectorAll(':scope > .voice-catalog-empty').forEach(node=>node.remove());
    if (!filtered.length) {
      const empty = document.createElement('p');
      empty.className = 'voice-catalog-empty muted';
      empty.textContent = rows.length ? 'No voices match these filters.' : (result.message || 'No voices are currently available from this provider.');
      empty.style.cssText = 'padding:10px 2px;font-size:13px;line-height:1.5';
      listHost.appendChild(empty);
    }
    for (const row of filtered) {
      const voiceRow = document.createElement('div');
      voiceRow.className = 'voice-row';
      voiceRow.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:0';
      const info = document.createElement('div');
      info.style.cssText = 'min-width:0;overflow-wrap:anywhere';
      const name = document.createElement('b'); name.textContent = String(row.name || row.voice_id || 'Unnamed voice');
      const detail = document.createElement('small'); detail.className = 'muted';
      const detailParts = [];
      const language=String(row.language_name||row.language||row.locale||'').trim();
      const gender=voiceGenderFacet(row);
      const region=String(row.region_name||row.region||row.accent||row.locale||'').trim();
      const categories=voiceCategories(row);
      if(language)detailParts.push(language);
      if(gender&&gender.toLowerCase()!=='unknown')detailParts.push(gender);
      if(region&&region!==language)detailParts.push(region);
      if(categories.length)detailParts.push('Category: '+categories.join(', '));
      if(row.saved)detailParts.push('Saved profile');
      if(row.description)detailParts.push(String(row.description).slice(0,110));
      detail.textContent = detailParts.join(' · ') || 'Available in the selected provider';
      info.append(name, document.createElement('br'), detail);
      const choose = document.createElement('button');
      choose.className = 'btn choose'; choose.type = 'button'; choose.textContent = row.saved ? 'Load / Select' : 'Select';
      choose.dataset.voice = String(row.voice_id || row.name || '');
      choose.dataset.voiceProvider = String(row.provider || ({offline:'piper',sapi:'windows-sapi',customvoice:'qwen-character',voicedesign:'qwen-character',qwenclone:'qwen-character',customref:'chatterbox',edge:'edge-tts',eleven:'elevenlabs'}[providerKey] || ''));
      choose.dataset.voiceLabel = String(row.name || row.voice_id || '');
      choose.dataset.voiceSaved = row.saved ? 'true' : 'false';
      if (row.saved) choose.dataset.voiceProfileName = String(row.name || '');
      choose.title = row.saved ? 'Load this saved profile and its settings' : 'Select this installed or live catalogue voice';
      voiceRow.append(info, choose); listHost.appendChild(voiceRow);
    }
    listHost.scrollTop=previousScrollTop;
    // ElevenLabs setup guidance and native browser button are maintained above,
    // regardless of whether saved voices happen to exist in the catalogue.
  }
  async function refreshProviderCatalog(providerKey, refresh = false) {
    // Several lifecycle screens can refresh catalogues at the same time. Only
    // the newest request for a provider may publish rows into that provider card.
    const requestToken = (providerCatalogEpochs[providerKey] || 0) + 1;
    providerCatalogEpochs[providerKey] = requestToken;
    const result = await call('voice.catalog', {provider:providerKey,refresh:Boolean(refresh)});
    if (providerCatalogEpochs[providerKey] !== requestToken) return providerCatalogs[providerKey] || result;
    providerCatalogs[providerKey] = result;
    renderProviderCatalog(providerKey, result);
    return result;
  }

  function providerPanelForProfile(profile) {
    return ({
      piper:'offline',kokoro:'offline','windows-sapi':'sapi',
      'qwen-character':profile?.qwen_mode==='design'?'voicedesign':/clone/i.test(profile?.qwen_mode||'')?'qwenclone':'customvoice',
      chatterbox:'customref','edge-tts':'edge',elevenlabs:'eleven'
    })[profile?.provider]||'';
  }
  function currentVoiceName(){return String(selectedVoice||$('profileName')?.value||'').trim();}
  function clearSavedProfileSelection(){
    const select=document.querySelector('#voices .panel[data-panel="3"] .toolbar select');
    if(select)select.value='';
  }
  function updateVoiceBeingConfigured(value){
    const name=String(value||'').trim();
    for(const label of document.querySelectorAll('small,span,label,p,div')){
      if(label.children.length||String(label.textContent||'').trim().toLowerCase()!=='voice being configured')continue;
      const valueNode=label.parentElement?.querySelector('b,strong,h2,h3');
      if(valueNode&&valueNode!==label)valueNode.textContent=name;
    }
  }
  function providerDisplayName(profile) {
    const provider=String(profile?.provider||'').trim();
    return ({
      'qwen-character':'Qwen Voice Studio','edge-tts':'Edge TTS','elevenlabs':'ElevenLabs',
      'windows-sapi':'Windows SAPI','piper':'Piper','kokoro':'Kokoro','chatterbox':'Chatterbox'
    })[provider]||provider;
  }
  function ensureVoiceProfileDetails() {
    const grid=document.querySelector('#voices .panel[data-panel="3"] .detail-grid');
    if(!grid)return;
    const ids={
      'Provider':'detailProvider','Mode':'detailMode','Voice ID':'detailVoiceId','Language':'detailLanguage',
      'Reference':'detailReference','Backend':'detailBackend','Model':'detailModel',
      'Design seed':'detailSeed','Authorization':'detailAuthorization'
    };
    for(const [labelText,id] of Object.entries(ids)){
      const label=[...grid.querySelectorAll('span')].find(node=>String(node.textContent||'').trim()===labelText);
      const value=label?.nextElementSibling;
      if(value&&!value.id)value.id=id;
    }
    const profileHealthRow=[...document.querySelectorAll('#voices .panel[data-panel="3"] .form2 .ready')]
      .find(row=>String(row.querySelector('span')?.textContent||'').trim()==='Health');
    const profileHealth=profileHealthRow?.querySelector('b');
    if(profileHealth&&!profileHealth.id)profileHealth.id='profileHealth';
    const sideHealthRow=[...document.querySelectorAll('#voices aside.summary .ready')]
      .find(row=>String(row.querySelector('span')?.textContent||'').trim()==='Provider health');
    const sideHealth=sideHealthRow?.querySelector('b');
    if(sideHealth&&!sideHealth.id)sideHealth.id='sumProviderHealth';
  }
  function updateVoiceHealthIndicator(providerKey,result) {
    ensureVoiceProfileDetails();
    const profile=selectedVoice?voices.find(item=>item.saved===true&&item.name.toLowerCase()===selectedVoice.toLowerCase()):null;
    const selectedKey=profile?providerPanelForProfile(profile):(document.querySelector('#voices .provider.active')?.dataset.provider||providerKey||'');
    if(!providerKey||!selectedKey||providerKey!==selectedKey)return;
    const inventoryStatus=String(result?.model_inventory?.status||'');
    const blockedStatuses=['Missing','Not configured','Partially installed','Unhealthy','Unsupported','Location unavailable','Unavailable','Not assessed'];
    const label=!result?'Checking…':!result.ready?(blockedStatuses.includes(inventoryStatus)?inventoryStatus:'Provider unavailable'):
      inventoryStatus==='Installed'?'Installed · functional verification pending':inventoryStatus||'Ready';
    const color=!result?'var(--muted)':!result.ready?'var(--amber)':inventoryStatus==='Ready'?'var(--green)':'var(--muted)';
    for(const id of ['profileHealth','sumProviderHealth']){
      const node=$(id);if(node){node.textContent=label;node.style.color=color;}
    }
  }
  function updateVoiceProfileDetails(profile) {
    ensureVoiceProfileDetails();
    const provider=String(profile?.provider||'').trim();
    const language=String(profile?.language||'').trim();
    let model=String(profile?.model_id||'').trim();
    if(provider==='qwen-character'){
      model=profile?.qwen_mode==='design'?'VoiceDesign':/clone/i.test(profile?.qwen_mode||'')?'Voice Clone':(model&&model!=='auto'&&model!=='automatic'?model:'CustomVoice');
    } else if(!model||['auto','automatic'].includes(model.toLowerCase())) model=providerDisplayName(profile);
    const qwenLanguage=document.querySelector('#voices .provider[data-provider="voicedesign"] .form2 select')?.value||'English';
    const defaultSpeaker=({English:'Ryan',Japanese:'Ono_Anna',Chinese:'Serena',Korean:'Sohee'}[qwenLanguage]||'Ryan');
    const reference=profile?.sample_path?'Reference audio imported':profile?.reference_text?'Reference text saved':'Not required';
    const values={
      detailProvider:profile?providerDisplayName(profile):'',
      detailMode:!profile?'':provider==='qwen-character'?(profile.qwen_mode==='design'?'VoiceDesign':/clone/i.test(profile.qwen_mode||'')?'Voice Clone':'CustomVoice'):'Standard provider',
      detailVoiceId:!profile?'':String(profile.voice_id||((provider==='qwen-character'&&profile.qwen_mode==='design')?defaultSpeaker:selectedVoiceId)||''),
      detailLanguage:language,
      detailReference:profile?reference:'',
      detailBackend:profile?String(profile.backend||'Automatic'):'',
      detailModel:model,
      detailSeed:profile?(profile.qwen_seed==null||profile.qwen_seed===''||Number(profile.qwen_seed)===0?'Automatic / natural variation':String(profile.qwen_seed)):'',
      detailAuthorization:!profile?'':profile.authorized?'Authorized':(provider==='qwen-character'&&profile.qwen_mode==='design'?'Not required':'Not recorded')
    };
    for(const [id,value] of Object.entries(values))if($(id))$(id).textContent=String(value||'');
  }
  function voiceDisplayName(profile) {
    if(!profile)return '';
    const provider=String(profile.provider||'').trim().toLowerCase();
    if(provider==='qwen-character'&&String(profile.qwen_mode||'').toLowerCase()==='design'){
      const prompt=String(profile.qwen_prompt||'').toLowerCase();
      const presetName=String(profile.name||'').toLowerCase().replace(/[·•]/g,' ');
      // Native and web presets use slightly different, but equivalent,
      // descriptions. Resolve the preset identity from either source.
      if(prompt.includes('anime heroine timbre')||presetName.includes('anime heroine'))return 'Anime Heroine';
      if(prompt.includes('anime hero timbre')||prompt.includes('anime protagonist timbre')||presetName.includes('anime hero'))return 'Anime Hero';
      if(prompt.includes('anime rival presence')||prompt.includes('anime rival timbre')||presetName.includes('anime rival'))return 'Anime Rival';
      if(prompt.includes('fictional anime villain')||prompt.includes('anime villain timbre')||presetName.includes('anime villain'))return 'Anime Villain';
      if(prompt.includes('anime healer presence')||prompt.includes('anime healer timbre')||presetName.includes('anime healer'))return 'Anime Healer';
      return String(profile.display_voice||'Custom VoiceDesign');
    }
    const voiceId=String(profile.voice_id||selectedVoiceId||'').trim().toLowerCase();
    const providerKey=providerPanelForProfile(profile);
    const catalog=Array.isArray(providerCatalogs[providerKey]?.voices)?providerCatalogs[providerKey].voices:[];
    const match=catalog.find(row=>String(row.voice_id||'').trim().toLowerCase()===voiceId&&
      String(row.provider||profile.provider||'').trim().toLowerCase()===provider);
    return String(profile.display_voice||profile.voice_name||match?.name||profile.voice_id||profile.name||'').trim();
  }
  function updatePreviewTarget(profile,libraryLabel,key) {
    const name=String(profile?.name||'').trim();
    const providerLabel=providerDisplayName(profile);
    const voice=voiceDisplayName(profile);
    let model=String(profile?.model_id||'').trim();
    if(profile?.provider==='qwen-character'){
      model=profile?.qwen_mode==='design'?'VoiceDesign':/clone/i.test(profile?.qwen_mode||'')?'Voice Clone':(model&&model!=='auto'&&model!=='automatic'?model:'CustomVoice');
    } else if(!model||['auto','automatic'].includes(model.toLowerCase())) {
      model=profile?.provider==='edge-tts'?'Neural TTS':profile?.provider==='piper'?'Piper model':profile?.provider==='kokoro'?'Kokoro model':providerLabel;
    }
    const values={
      profileLibrary:libraryLabel||'',
      profileVoice:voice||'',
      previewLibrary:libraryLabel||'',
      previewProvider:providerLabel,
      previewVoice:voice,
      previewModel:model,
      previewProfile:name
    };
    for(const [id,value] of Object.entries(values))if($(id))$(id).textContent=String(value||'');
    updateVoiceProfileDetails(profile);
  }
  function updateVoiceSummary(profile=null,options={}){
    const name=String(profile?.name||'').trim(),key=providerPanelForProfile(profile);
    const libraryLabel=name?(voiceLibraryTitles[key]||({
      piper:'Offline Neural Voices',kokoro:'Offline Neural Voices','qwen-character':profile.qwen_mode==='design'?'Qwen VoiceDesign':/clone/i.test(profile.qwen_mode||'')?'Qwen Voice Clone':'Qwen CustomVoice',
      'edge-tts':'Edge TTS','windows-sapi':'Windows SAPI',elevenlabs:'ElevenLabs',chatterbox:'Reference Voice'
    }[profile.provider]||profile.provider||'')):'';
    updatePreviewTarget(profile,libraryLabel,key);
    const healthKey=key||document.querySelector('#voices .provider.active')?.dataset.provider||'';
    updateVoiceHealthIndicator(healthKey,providerCatalogs[healthKey]||null);
    if($('workingSide'))$('workingSide').textContent=name;
    if($('sumLibrary'))$('sumLibrary').textContent=libraryLabel;
    if($('sumProfile'))$('sumProfile').textContent=name?(options.saved?'Saved':'Unsaved'):'';
    if($('sumPreview'))$('sumPreview').textContent=options.previewReady?'Ready':(name?'Not generated':'');
    if($('sumAssign'))$('sumAssign').textContent=String(options.assignment||'').trim();
    updateVoiceBeingConfigured(name);
    const side=$('assignedSide'),p=side?.closest('p'),heading=p?.previousElementSibling;
    if(heading&&/^currently assigned/i.test(String(heading.textContent||'').trim()))heading.textContent='Currently assigned character';
    if(p)p.hidden=!String(side?.textContent||'').trim();
  }
  function updateVoiceActionButtons(){
    const current=currentVoiceName();
    const saved=Boolean(selectedVoice&&voices.some(item=>item.saved===true&&item.name.toLowerCase()===selectedVoice.toLowerCase()));
    if($('saveOnly'))$('saveOnly').disabled=!current;
    if($('playPreview'))$('playPreview').disabled=!voicePreviewValid;
    if($('useNarrator'))$('useNarrator').disabled=!voicePreviewValid;
    if($('assignCharacter'))$('assignCharacter').disabled=!voicePreviewValid||!saved;
    if($('downloadPreview'))$('downloadPreview').disabled=!voicePreviewValid||!lastVoicePreviewPath;
    syncProductionPreviewControls();
  }
  function normalizeProjectFolderIdentity(value){
    return String(value||'').trim().replace(/\\/g,'/').replace(/\/+$/,'').toLowerCase();
  }
  function syncProductionPreviewControls(){
    const playable=Boolean(voicePreviewValid&&previewAudio);
    const playing=Boolean(playable&&!previewAudio.paused);
    const play=$('productionPreviewPlay'),stop=$('productionPreviewStop'),download=$('productionPreviewDownload');
    const replay=$('productionPreviewReplay');
    if(play){play.disabled=!playable;play.textContent=playing?'Ⅱ Pause preview':'▶ Play preview';}
    if(stop)stop.disabled=!playable;
    if(replay)replay.disabled=!playable;
    if(download)download.disabled=!voicePreviewValid||!lastVoicePreviewPath||!productionPreviewJobId||String(productionJobSnapshots.preview?.state||'').toLowerCase()!=='completed';
    const status=$('productionPreviewStatus');
    const previewJobState=String(productionJobSnapshots.preview?.state||'').toLowerCase();
    const previewJobOwnsStatus=PRODUCTION_ACTIVE_JOB_STATES.has(previewJobState)||['failed','cancelled'].includes(previewJobState);
    const selectedNumber=Number(productionPreviewSelectedChapter||0);
    const previewChapterNumber=Number(lastVoicePreviewChapterNumber||0);
    const productionPreviewMatchesSelection=Boolean(
      voicePreviewValid && productionPreviewJobId && selectedNumber>0 &&
      previewChapterNumber===selectedNumber
    );
    if(status&&productionPreviewMatchesSelection){
      status.textContent='Preview ready · Chapter '+selectedNumber+' · '+
        (Number(previewAudio?.duration)>0?Number(previewAudio.duration).toFixed(1)+' seconds':'loading duration');
    }else if(status&&!previewJobOwnsStatus){
      status.textContent=selectedNumber>0
        ? 'Chapter '+selectedNumber+' selected. Generate a new preview for this chapter.'
        : 'Select a saved chapter before generating a preview.';
    }
  }
  function invalidateVoicePreview(){
    voicePreviewEpoch++;voicePreviewValid=false;lastVoicePreviewPath=null;lastVoicePreviewProfileName='';lastVoicePreviewChapterNumber=null;lastVoicePreviewChapterTitle='';
    if(previewAudio){try{previewAudio.pause();previewAudio.removeAttribute('src');previewAudio.load();}catch(_){}previewAudio=null;}
    if($('playPreview')){$('playPreview').disabled=true;$('playPreview').textContent='▶ Play';}
    if($('downloadPreview'))$('downloadPreview').disabled=true;
    if($('previewProgress'))$('previewProgress').style.width='0%';
    if($('previewState'))$('previewState').textContent=currentVoiceName()?'Not generated':'';
    if($('previewPlaybackTime'))$('previewPlaybackTime').textContent='00:00 / 00:00';
    if($('wave'))$('wave').classList.remove('playing');
    if($('validation'))$('validation').textContent='No validated preview yet.';
    if($('sumPreview'))$('sumPreview').textContent=currentVoiceName()?'Not generated':'';
    updateVoiceActionButtons();
  }
  async function refreshAssignedCharacterForProfile(profile){
    const token=++voiceAssignmentEpoch,side=$('assignedSide');
    if(side)side.textContent='';
    if($('sumAssign'))$('sumAssign').textContent='';
    const p=side?.closest('p'),heading=p?.previousElementSibling;
    if(heading&&/^currently assigned/i.test(String(heading.textContent||'').trim()))heading.textContent='Currently assigned character';
    if(p)p.hidden=true;
    if(!profile?.saved||!profile?.name)return;
    try{
      const rows=await call('character_library.list');
      if(token!==voiceAssignmentEpoch)return;
      libraryCharacters=Array.isArray(rows)?rows:[];
      const wanted=profile.name.trim().toLowerCase();
      const matches=libraryCharacters.filter(item=>String(item.voice_profile||item.voice||'').trim().toLowerCase()===wanted);
      const chosen=matches[0],primary=String(chosen?.primary_name||chosen?.name||'').trim();
      if(side)side.textContent=primary;
      if($('sumAssign'))$('sumAssign').textContent=primary;
      if(p)p.hidden=!primary;
    }catch(error){if(token===voiceAssignmentEpoch)console.warn('[Ryu character assignment summary]',error);}
  }
  function ensureVoiceStudioRuntimeControls(){
    const panel=document.querySelector('#voices .panel[data-panel="4"]'),toolbar=$('playPreview')?.parentElement;
    if(toolbar){
      let timer=$('previewPlaybackTime');
      if(!timer){timer=document.createElement('span');timer.id='previewPlaybackTime';timer.className='muted';timer.textContent='00:00 / 00:00';timer.style.cssText='font-variant-numeric:tabular-nums;min-width:86px;text-align:center';$('playPreview')?.insertAdjacentElement('afterend',timer);}
      let download=$('downloadPreview');
      if(!download){download=document.createElement('button');download.id='downloadPreview';download.type='button';download.className='btn secondary';download.textContent='↓ Download Preview';download.disabled=true;timer.insertAdjacentElement('afterend',download);}
      const volume=toolbar.querySelector('input[type="range"]');
      if(volume){volume.id='previewVolume';volume.min='0';volume.max='100';volume.step='1';
        if(!volume.dataset.previewVolumeBound){volume.dataset.previewVolumeBound='true';previewVolume=Math.max(0,Math.min(1,Number(volume.value||85)/100));volume.addEventListener('input',()=>{previewVolume=Math.max(0,Math.min(1,Number(volume.value||0)/100));if(previewAudio)previewAudio.volume=previewVolume;volume.setAttribute('aria-valuetext',Math.round(previewVolume*100)+' percent');});}
      }
    }
    if (!selectedVoice) {
      const initialName=String($('profileName')?.value||'').trim();
      if (/^(?:Offline Neural|Qwen VoiceDesign|Qwen CustomVoice|Edge TTS|Microsoft|ElevenLabs|Windows SAPI)\s*[·•-]/i.test(initialName)) {
        if($('profileName'))$('profileName').value='';
        if($('premiumName'))$('premiumName').value='';
      }
      updateVoiceSummary(null,{saved:false,previewReady:false,assignment:''});
      const assigned=$('assignedSide');if(assigned)assigned.textContent='';
      const assignedParagraph=assigned?.closest('p');if(assignedParagraph)assignedParagraph.hidden=true;
    }
    const previewTextarea=panel&&[...panel.querySelectorAll('textarea')].find(el=>/preview text/i.test(String(el.closest('label')?.textContent||'')));
    if(previewTextarea&&!previewTextarea.dataset.previewIdentityBound){previewTextarea.dataset.previewIdentityBound='true';previewTextarea.addEventListener('input',()=>invalidateVoicePreview());}
    const designPanel=document.querySelector('#voices .provider[data-provider="voicedesign"]');
    if(designPanel){
      const prompt=designPanel.querySelector('textarea'),language=designPanel.querySelector('select'),seed=designPanel.querySelector('input[type="number"]');
      const detachForEdit=()=>{
        if(selectedVoice){
          const profile=voices.find(item=>item.saved===true&&item.name.toLowerCase()===selectedVoice.toLowerCase());
          if(profile&&profile.provider==='qwen-character'&&profile.qwen_mode==='design'){
            // Editing the VoiceDesign prompt/preset creates a new draft by
            // default. Do not retain the prior saved profile as a hidden rename
            // target; that could overwrite the selected saved voice when saving
            // a new Anime Hero preset. Updating/renaming an existing profile
            // remains available through an explicit originalNameOverride.
            profileEditOriginalName='';selectedVoice=null;selectedVoiceId=null;selectedVoiceProvider='qwen-character';
            updateVoiceSummary({name:$('profileName')?.value||profile.name,provider:'qwen-character',qwen_mode:'design'},{saved:false,previewReady:false,assignment:''});
          }
        }
        invalidateVoicePreview();
      };
      for(const node of [prompt,language,seed])if(node&&!node.dataset.voiceDesignIdentityBound){node.dataset.voiceDesignIdentityBound='true';node.addEventListener('input',detachForEdit);node.addEventListener('change',detachForEdit);}
    }
    updateVoiceActionButtons();
  }
  async function openVoiceCharacterAssignment(){
    if(!voicePreviewValid||!lastVoicePreviewPath)throw new Error('Generate a valid preview for the selected voice before assigning it.');
    const name=currentVoiceName(),profile=voices.find(item=>item.saved===true&&item.name.toLowerCase()===name.toLowerCase());
    if(!profile)throw new Error('Save this voice profile first, then generate a fresh preview before assigning it to a character.');
    libraryCharacters=await call('character_library.list');
    const overlay=document.createElement('div');overlay.id='ryuVoiceCharacterAssignDialog';
    overlay.style.cssText='position:fixed;inset:0;z-index:100001;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(3,5,10,.82);backdrop-filter:blur(7px)';
    const modal=document.createElement('section');modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby','ryuVoiceCharacterAssignTitle');
    modal.style.cssText='box-sizing:border-box;width:min(580px,100%);max-height:min(86vh,760px);overflow:auto;background:#151a25;border:1px solid rgba(255,255,255,.13);border-radius:18px;box-shadow:0 24px 80px rgba(0,0,0,.5);padding:22px;color:#f4f5f8';
    const title=document.createElement('h2');title.id='ryuVoiceCharacterAssignTitle';title.textContent='Assign Voice to Character';title.style.cssText='margin:0 0 5px;font-size:22px';
    const hint=document.createElement('p');hint.className='muted';hint.textContent='Profile: '+profile.name+'. Choose a series and its primary character name. This assignment is saved to Character Library and shared with Character Studio.';hint.style.cssText='margin:0 0 18px;line-height:1.5';
    const field=(textValue,control)=>{const label=document.createElement('label');label.style.cssText='display:block;margin:12px 0 5px;color:#aeb6c5;font-size:12px';label.textContent=textValue;label.appendChild(control);control.style.cssText='box-sizing:border-box;display:block;width:100%;margin-top:6px;padding:11px;border-radius:10px;border:1px solid #343b4a;background:#0c1018;color:#f6f7fa;font:inherit';return label;};
    const seriesSelect=document.createElement('select'),characterSelect=document.createElement('select');
    const seriesInput=document.createElement('input');seriesInput.type='text';seriesInput.maxLength=300;seriesInput.placeholder='Enter a series name';seriesInput.hidden=true;
    const characterInput=document.createElement('input');characterInput.type='text';characterInput.maxLength=300;characterInput.placeholder='Primary character name';characterInput.hidden=true;
    const seriesCaption=document.createElement('label');seriesCaption.style.cssText='display:block;margin-top:5px;font-size:12px;color:#aeb6c5';seriesCaption.textContent='New series name';seriesCaption.appendChild(seriesInput);
    const charCaption=document.createElement('label');charCaption.style.cssText='display:block;margin-top:5px;font-size:12px;color:#aeb6c5';charCaption.textContent='New primary character';charCaption.appendChild(characterInput);
    const narratorPanel=document.createElement('section');narratorPanel.id='ryuCreateSeriesNarratorSetup';narratorPanel.hidden=true;
    narratorPanel.style.cssText='margin:14px 0;padding:14px;border:1px solid rgba(201,32,80,.4);border-radius:12px;background:rgba(201,32,80,.06)';
    const narratorHeading=document.createElement('div');narratorHeading.textContent='Series Narrator Voice';narratorHeading.style.cssText='font-weight:800;margin-bottom:5px';
    const narratorHint=document.createElement('p');narratorHint.className='muted';narratorHint.textContent='Choose a saved Voice Studio profile for every project in this series and preview it before saving. You may also save a draft series without a narrator; audiobook generation will remain blocked until one is configured.';narratorHint.style.cssText='font-size:12px;line-height:1.45;margin:0 0 10px';
    const narratorProfileSelect=document.createElement('select');narratorProfileSelect.id='ryuCreateSeriesNarratorProfile';
    const narratorSamples=characterSavedProfiles();
    const addNarratorOption=(value,label)=>{const option=document.createElement('option');option.value=value;option.textContent=label;narratorProfileSelect.appendChild(option);};
    addNarratorOption('','Choose a saved Voice Studio profile');
    for(const savedProfile of narratorSamples)addNarratorOption(savedProfile.name,characterSavedProfileLabel(savedProfile));
    narratorProfileSelect.style.cssText='box-sizing:border-box;width:100%;padding:10px;border-radius:9px;border:1px solid #343b4a;background:#0c1018;color:#f6f7fa;font:inherit';
    const narratorSampleText=document.createElement('textarea');narratorSampleText.id='ryuCreateSeriesNarratorSample';narratorSampleText.rows=3;
    narratorSampleText.value='Long ago, beneath a sky of silver stars, a new journey began.';
    narratorSampleText.style.cssText='box-sizing:border-box;width:100%;margin-top:9px;padding:10px;border-radius:9px;border:1px solid #343b4a;background:#0c1018;color:#f6f7fa;font:inherit;resize:vertical';
    const narratorDuration=document.createElement('select');narratorDuration.id='ryuCreateSeriesNarratorDuration';
    for(const seconds of [10,30,60,90]){const option=document.createElement('option');option.value=String(seconds);option.textContent=seconds+' seconds';narratorDuration.appendChild(option);}
    narratorDuration.value='30';narratorDuration.style.cssText='padding:9px;border-radius:9px;border:1px solid #343b4a;background:#0c1018;color:#f6f7fa;font:inherit';
    const narratorPreviewButton=document.createElement('button');narratorPreviewButton.type='button';narratorPreviewButton.className='btn small';narratorPreviewButton.textContent='Preview Narrator';
    const narratorPlayButton=document.createElement('button');narratorPlayButton.type='button';narratorPlayButton.className='btn small secondary';narratorPlayButton.textContent='Play Narrator Preview';narratorPlayButton.disabled=true;
    const narratorStopButton=document.createElement('button');narratorStopButton.type='button';narratorStopButton.className='btn small ghost';narratorStopButton.textContent='Stop';narratorStopButton.disabled=true;
    const narratorDraftButton=document.createElement('button');narratorDraftButton.type='button';narratorDraftButton.className='btn small ghost';narratorDraftButton.textContent='Save Draft Without Narrator';
    narratorDraftButton.addEventListener('click',()=>{
      narratorDraftWithoutVoice=true;
      validatedSeriesNarratorPreview=null;
      narratorPlayButton.disabled=true;
      narratorStopButton.disabled=true;
      narratorPlayButton.textContent='Play Narrator Preview';
      narratorPreviewStatus.textContent='Draft series · narrator not configured. Production Studio will block audiobook generation until a valid series narrator is saved.';
    });
    const narratorPreviewStatus=document.createElement('p');narratorPreviewStatus.className='muted';narratorPreviewStatus.id='ryuCreateSeriesNarratorStatus';narratorPreviewStatus.textContent='Narrator preview required before saving this new series.';narratorPreviewStatus.style.cssText='font-size:12px;line-height:1.4;margin:9px 0 0';
    let validatedSeriesNarratorPreview=null;
    let narratorDraftWithoutVoice=false;
    const clearSeriesNarratorPreview=(reason='Narrator settings changed. Preview again before saving.')=>{
      validatedSeriesNarratorPreview=null;
      narratorDraftWithoutVoice=false;
      narratorPreviewStatus.textContent=reason;
      narratorPlayButton.disabled=true;
      narratorStopButton.disabled=true;
      narratorPlayButton.textContent='Play Narrator Preview';
    };
    narratorProfileSelect.addEventListener('change',()=>clearSeriesNarratorPreview());
    narratorSampleText.addEventListener('input',()=>clearSeriesNarratorPreview());
    narratorDuration.addEventListener('change',()=>clearSeriesNarratorPreview());
    narratorPreviewButton.addEventListener('click',async()=>{
      const profileName=String(narratorProfileSelect.value||'').trim();
      const sampleText=String(narratorSampleText.value||'');
      const seconds=Number(narratorDuration.value||30);
      const selectedProfile=narratorSamples.find(item=>item.name===profileName&&item.saved===true);
      narratorPreviewButton.disabled=true;narratorPreviewButton.textContent='Checking…';
      try{
        if(!selectedProfile)throw new Error('Choose an available saved Voice Studio narrator profile.');
        if(!sampleText.trim())throw new Error('Enter sample narration text before previewing.');
        narratorPreviewButton.textContent='Generating…';
        clearSeriesNarratorPreview('Generating narrator preview · '+profileName);
        const started=await call('narrator.preview',{
          series_setup_preview:true,profile_name:profileName,text:sampleText,duration_seconds:seconds
        });
        if(!started?.job_id)throw new Error('The narrator preview did not return a job ID.');
        const preview=await waitForNarratorPreviewJob(started.job_id,seconds,profileName);
        validatedSeriesNarratorPreview={
          profileName,
          sampleText,
          durationSeconds:seconds,
          outputPath:preview.outputPath
        };
        narratorPreviewStatus.textContent='Preview ready · '+profileName+' · '+seconds+' seconds requested. Play it before saving the series.';
        narratorPlayButton.disabled=false;narratorStopButton.disabled=false;
        if(previewAudio)previewAudio.addEventListener('ended',()=>{narratorPlayButton.textContent='Play Narrator Preview';},{once:true});
      }catch(error){
        clearSeriesNarratorPreview(error?.message||String(error));
        message(error?.message||String(error),true);
      }finally{
        narratorPreviewButton.disabled=false;narratorPreviewButton.textContent='Preview Narrator';
      }
    });
    narratorPlayButton.addEventListener('click',async()=>{
      try{
        if(!validatedSeriesNarratorPreview||!voicePreviewValid||!previewAudio)throw new Error('Generate a valid narrator preview first.');
        if(!previewAudio.paused){previewAudio.pause();narratorPlayButton.textContent='Play Narrator Preview';}
        else{await previewAudio.play();narratorPlayButton.textContent='Pause Narrator Preview';}
      }catch(error){message('Narrator preview playback failed: '+(error?.message||String(error)),true);}
    });
    narratorStopButton.addEventListener('click',()=>{
      if(previewAudio){previewAudio.pause();previewAudio.currentTime=0;}
      narratorPlayButton.textContent='Play Narrator Preview';
    });
    const narratorDurationRow=document.createElement('div');narratorDurationRow.style.cssText='display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:9px';
    const narratorDurationLabel=document.createElement('span');narratorDurationLabel.textContent='Preview length';narratorDurationLabel.style.cssText='font-size:12px;color:#aeb6c5';
    narratorDurationRow.append(narratorDurationLabel,narratorDuration,narratorPreviewButton,narratorPlayButton,narratorStopButton,narratorDraftButton);
    narratorPanel.append(narratorHeading,narratorHint,field('Narrator Voice',narratorProfileSelect),field('Sample Narration',narratorSampleText),narratorDurationRow,narratorPreviewStatus);
    const seriesNames=[...new Set(libraryCharacters.map(item=>String(item.series||'').trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    const addOption=(select,value,label)=>{const option=document.createElement('option');option.value=value;option.textContent=label;select.appendChild(option);};
    addOption(seriesSelect,'','Choose a series');for(const series of seriesNames)addOption(seriesSelect,series,series);addOption(seriesSelect,'__new_series__','＋ Create a new series…');
    const refreshCharactersForSeries=()=>{
      const createSeries=seriesSelect.value==='__new_series__',series=(createSeries?seriesInput.value:seriesSelect.value).trim();
      seriesInput.hidden=!createSeries;
      narratorPanel.hidden=!createSeries;
      if(!createSeries)clearSeriesNarratorPreview('Choose Create a new series to configure its narrator.');
      characterSelect.replaceChildren();addOption(characterSelect,'','Choose a character');
      for(const item of libraryCharacters.filter(c=>String(c.series||'').trim().toLowerCase()===series.toLowerCase()))addOption(characterSelect,String(item.id||''),String(item.primary_name||item.name||'Unnamed character'));
      addOption(characterSelect,'__new_character__','＋ Add a new primary character…');
      if(createSeries)characterSelect.value='__new_character__';
      characterInput.hidden=!(createSeries||characterSelect.value==='__new_character__');
    };
    seriesSelect.addEventListener('change',refreshCharactersForSeries);
    seriesInput.addEventListener('input',refreshCharactersForSeries);
    characterSelect.addEventListener('change',()=>{characterInput.hidden=!(seriesSelect.value==='__new_series__'||characterSelect.value==='__new_character__');});
    const meta=document.createElement('p');meta.className='muted';meta.style.cssText='font-size:12px;line-height:1.45;margin:12px 0 0';meta.textContent='Only the primary name is required. Aliases, dialogue samples and pronunciation rules remain available in Character Library.';
    const actions=document.createElement('div');actions.style.cssText='display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap;margin-top:20px';
    const cancel=document.createElement('button');cancel.type='button';cancel.className='btn secondary';cancel.textContent='Cancel';
    const assign=document.createElement('button');assign.type='button';assign.className='btn';assign.textContent='Assign Voice';
    const close=()=>overlay.remove();cancel.addEventListener('click',close);overlay.addEventListener('click',event=>{if(event.target===overlay)close();});
    assign.addEventListener('click',async()=>{
      assign.disabled=true;assign.textContent='Saving…';
      try{
        const isNewSeries=seriesSelect.value==='__new_series__',series=(isNewSeries?seriesInput.value:seriesSelect.value).trim();
        if(!series)throw new Error('Choose or enter a series name.');
        if(isNewSeries){
          const narratorProfileName=String(narratorProfileSelect.value||'').trim();
          const currentSample=String(narratorSampleText.value||'');
          const currentDuration=Number(narratorDuration.value||30);
          const previewMatches=validatedSeriesNarratorPreview
            && validatedSeriesNarratorPreview.profileName===narratorProfileName
            && validatedSeriesNarratorPreview.sampleText===currentSample
            && validatedSeriesNarratorPreview.durationSeconds===currentDuration
            && voicePreviewValid
            && lastVoicePreviewPath===validatedSeriesNarratorPreview.outputPath;
          if(previewMatches){
            const savedNarrator=await call('narrator.series.default.save',{series,profile_name:narratorProfileName});
            if(!savedNarrator?.saved)throw new Error('The series narrator default was not saved. The new series was not completed.');
          }else if(!narratorDraftWithoutVoice){
            throw new Error('Preview and listen to a saved narrator profile, or explicitly choose Save Draft Without Narrator.');
          }
        }
        let character=libraryCharacters.find(item=>String(item.id||'')===characterSelect.value);
        if(characterSelect.value==='__new_character__'||isNewSeries){
          const primary=characterInput.value.trim();if(!primary)throw new Error('Enter the primary character name.');
          const saved=await call('character_library.save',{name:primary,series,scope:'Series · '+series,short:primary.split(/\s+/)[0],aliases:[],notes:'',dialogue_sample:''});
          character=saved.character;libraryCharacters.push(character);
        }
        if(!character)throw new Error('Choose a character from the selected series.');
        const assigned=await call('character_library.save',{
          id:character.id,name:character.primary_name||character.name,series:String(character.series||series),
          scope:'Series · '+String(character.series||series),short:character.short||'',aliases:character.aliases||[],
          notes:character.notes||'',dialogue_sample:character.dialogue_sample||'',voice_profile:profile.name
        });
        const primaryName=assigned.character.primary_name||assigned.character.name;
        const projectCharacter = characters.find(item =>
          String(item.name || '').toLowerCase() === String(primaryName).toLowerCase() &&
          characterSeries(item).toLowerCase() === String(assigned.character.series || series).toLowerCase());
        if (projectCharacter) {
          await call('character.assign', {name:primaryName,series:characterSeries(projectCharacter),profile_name:profile.name});
          await refreshCharacters();
        }
        await refreshCharacterLibrary();await refreshVoices();await refreshAssignedCharacterForProfile({...profile,saved:true});
        close();
        const draftWarning=isNewSeries&&narratorDraftWithoutVoice
          ?' · Draft series: narrator setup incomplete; audiobook generation is blocked until a narrator is configured.'
          :'';
        message('Assigned '+profile.name+' to '+primaryName+' · '+(assigned.character.series||series)+'.'+draftWarning);
      }catch(error){message(error?.message||String(error),true);assign.disabled=false;assign.textContent='Assign Voice';}
    });
    modal.append(title,hint,field('Series',seriesSelect),seriesCaption,narratorPanel,field('Character',characterSelect),charCaption,meta,actions);
    actions.append(cancel,assign);overlay.appendChild(modal);document.body.appendChild(overlay);refreshCharactersForSeries();
    seriesInput.hidden=true;characterInput.hidden=true;seriesSelect.focus();
  }

  function applySavedVoiceProfile(profile, announce = true) {
    if (!profile || profile.saved !== true) return false;
    invalidateVoicePreview();
    selectedVoice=profile.name;profileEditOriginalName=profile.name;
    selectedVoiceId=profile.voice_id;selectedVoiceProvider=profile.provider;
    if($('profileName'))$('profileName').value=profile.name;
    if($('premiumName'))$('premiumName').value=profile.name;
    if($('profileLibrary'))$('profileLibrary').textContent=({
      piper:'Offline Neural Voices',kokoro:'Offline Neural Voices','qwen-character':profile.qwen_mode==='design'?'Qwen VoiceDesign':/clone/i.test(profile.qwen_mode||'')?'Qwen Voice Clone':'Qwen CustomVoice',
      'windows-sapi':'Windows SAPI','edge-tts':'Edge TTS','elevenlabs':'ElevenLabs',chatterbox:'Reference Voice'
    })[profile.provider]||profile.provider;
    if($('profileVoice'))$('profileVoice').textContent=profile.voice_id||profile.name;
    if($('previewProfile'))$('previewProfile').textContent=profile.name;
    const providerPanel=providerPanelForProfile(profile);
    document.querySelectorAll('#voices .provider').forEach(panel=>panel.classList.toggle('active',panel.dataset.provider===providerPanel));
    const designPanel=document.querySelector('.provider[data-provider="voicedesign"]');
    if(designPanel){
      const prompt=designPanel.querySelector('textarea'),language=designPanel.querySelector('select'),seed=designPanel.querySelector('input[type="number"]');
      if(prompt&&profile.qwen_prompt!=null)prompt.value=profile.qwen_prompt;
      if(language&&profile.language)language.value=profile.language;
      if(seed)seed.value=profile.qwen_seed??'';
      designPanel.querySelectorAll('.preset').forEach(item=>item.classList.toggle('active',
        String(item.textContent||'').trim().toLowerCase()===String(profile.name||'').replace(/^.*?[·•]\s*/,'').trim().toLowerCase()));
    }
    const transcript=document.querySelector('.provider[data-provider="qwenclone"] textarea');
    if(transcript&&profile.reference_text!=null)transcript.value=profile.reference_text;
    const style=document.querySelector('.provider[data-provider="customref"] select');
    if(style&&profile.style_preset)style.value=profile.style_preset;
    const select=document.querySelector('#voices .panel[data-panel="3"] .toolbar select');if(select)select.value=profile.name;
    const detailValues={detailProvider:profile.provider,detailVoiceId:profile.voice_id||'',detailLanguage:profile.language||'',detailModel:profile.model_id||'',detailDescription:profile.qwen_prompt||profile.notes||''};
    for(const [id,value] of Object.entries(detailValues))if($(id))$(id).textContent=String(value||'—');
    updateVoiceSummary(profile,{saved:true,previewReady:false,assignment:''});
    void refreshAssignedCharacterForProfile(profile);updateVoiceActionButtons();
    if(announce)message('Loaded saved voice profile: '+profile.name+'. Provider, voice ID and saved settings are restored. Generate a fresh preview before playback or assignment.');
    return true;
  }

  async function refreshVoices() {
    const requestToken = ++voiceListEpoch;
    // Load the lightweight persisted profile list first so Voice Studio can
    // render immediately. A cold Models scan is useful for provider-health
    // badges, but must never hold the screen-navigation path open.
    const inventoryTask = loadModelInventory(false).catch(error => {
      console.warn('[Ryu model inventory]', error?.message || error);
      return null;
    });
    const loadedVoices = await call('voice.list');
    if (requestToken !== voiceListEpoch) return voices;
    voices = Array.isArray(loadedVoices) ? loadedVoices : [];
    const rows = voices.map(v => ({...v, label: v.name + ' · ' + v.provider}));
    renderSelect($('editCharacterVoice'), [{name:'',label:'Unassigned'}, ...rows], 'name', v => v.label || 'Unassigned');
    if ($('characterEditorModal')?.classList.contains('show') && $('editCharacterVoice')) $('editCharacterVoice').disabled = true;
    renderSelect($('pronQuickVoice'), rows, 'name', v => v.label);
    const profileSelect = document.querySelector('#voices .panel[data-panel="3"] .toolbar select');
    const profileSearch = document.querySelector('#voices .panel[data-panel="3"] .form2 input[placeholder^="Profile, provider"]');
    const updateSavedProfileOptions = () => {
      if (!profileSelect) return;
      const previous = profileSelect.value;
      const term = String(profileSearch?.value || '').trim().toLowerCase();
      const saved = voices.filter(v => v.saved === true && (!term ||
        [v.name,v.provider,v.language,v.voice_id,v.notes,v.qwen_prompt].some(value => String(value || '').toLowerCase().includes(term))));
      const optionSignature = JSON.stringify(saved.map(item => [item.name,item.provider]));
      if (profileSelect.dataset.savedOptionsSignature !== optionSignature) {
        profileSelect.replaceChildren();
        const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = 'Select saved profile';
        profileSelect.appendChild(placeholder);
        for (const item of saved) {
          const option = document.createElement('option');
          option.value = item.name; option.textContent = item.name + ' · ' + item.provider;
          profileSelect.appendChild(option);
        }
        profileSelect.dataset.savedOptionsSignature = optionSignature;
      }
      profileSelect.value = saved.some(v => v.name === previous) ? previous : '';
      profileSelect.disabled = saved.length === 0;
      profileSelect.title = saved.length ? 'Choose a saved voice profile to load' : 'No saved profiles match this search.';
    };
    if (profileSearch && !profileSearch.dataset.savedProfileSearchBound) {
      profileSearch.dataset.savedProfileSearchBound = 'true';
      profileSearch.addEventListener('input', updateSavedProfileOptions);
    }
    updateSavedProfileOptions();
    const activeProviderKey = document.querySelector('#voices .provider.active')?.dataset.provider || 'offline';
    void inventoryTask.then(() => {
      if (requestToken !== voiceListEpoch) return null;
      return refreshProviderCatalog(activeProviderKey, false);
    }).catch(error => console.warn('[Ryu voice catalogue]', error));
    // A catalogue selection is not a saved custom profile; the profile name is supplied by the user.
    renderCharacterStudioLive();
    // Keep Pronunciation Studio's per-row preview selector in sync with saved
    // Voice Studio profiles after create, edit, import, or delete operations.
    renderPronunciationRows();
    return voices;
  }
  function renderLiveChapterInsights() {
    const host = $('chapters');
    if (!host) return;
    const heading = [...host.querySelectorAll('h1,h2,h3,h4,h5,[role="heading"]')]
      .find(node => String(node.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase() === 'chapter insights');
    if (!heading) return;
    const panel = heading.closest('.card') || heading.parentElement;
    if (!panel) return;

    const title = document.createElement('h3');
    title.textContent = 'Chapter insights';
    title.style.cssText = 'margin:0 0 12px;font-size:16px;font-weight:750;color:var(--text,#f3f4f6)';
    const root = document.createElement('div');
    root.id = 'liveChapterInsights';
    root.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px';
    const wordCount = chapter => Number(chapter.word_count || String(chapter.text || '').trim().split(/\s+/).filter(Boolean).length);
    const totalWords = chapters.reduce((sum, chapter) => sum + wordCount(chapter), 0);
    const emptyCount = chapters.filter(chapter => !String(chapter.text || '').trim()).length;
    const reviewCount = chapters.filter(chapter => String(chapter.review_status || 'needs_review') !== 'reviewed').length;
    const skippedCount = chapters.filter(chapter => chapter.skip_for_generation === true).length;
    const selected = selectedChapter();
    const selectedWords = selected ? wordCount(selected) : 0;
    const minutes = Math.max(0, Math.round(totalWords / 145));
    const formatTime = value => value >= 60 ? Math.floor(value / 60) + 'h ' + (value % 60) + 'm' : value + ' min';
    const cards = [
      ['Chapters', chapters.length.toLocaleString()],
      ['Total words', totalWords.toLocaleString()],
      ['Estimated narration', formatTime(minutes)],
      ['Needs review', reviewCount.toLocaleString()],
      ['Empty chapters', emptyCount.toLocaleString()],
      ['Selected chapter', selected ? selectedWords.toLocaleString() + ' words' : '—']
    ];
    if (skippedCount) cards.push(['Excluded from generation', skippedCount.toLocaleString()]);
    const insightsSignature = JSON.stringify({selected:Number(selected?.number || 0),cards});
    if (panel.dataset.ryuLiveInsightsSignature === insightsSignature) return;
    root.innerHTML = cards.map(([label,value]) =>
      '<div style="background:rgba(9,12,18,.72);border:1px solid rgba(148,163,184,.15);border-radius:10px;padding:10px 12px;min-width:0">' +
      '<div style="font-size:11px;letter-spacing:.04em;color:var(--muted,#9ca3af);margin-bottom:6px">' + esc(label) + '</div>' +
      '<div style="font-size:17px;font-weight:750;overflow-wrap:anywhere;color:var(--text,#f3f4f6)">' + esc(value) + '</div></div>'
    ).join('');
    // Chapter Insights is a read-only metrics card; remove placeholder values
    // and render only current backend-derived measurements inside the same card.
    panel.dataset.ryuLiveInsightsSignature = insightsSignature;
    panel.replaceChildren(title, root);
  }

  function syncCurrentChapterPreviewText(chapter) {
    const modeGroup = [...document.querySelectorAll('#voices .seg')].find(el =>
      [...el.querySelectorAll('button')].some(button => /Current Chapter|Selected Passage|Custom Text/.test(button.textContent))
    );
    const mode = modeGroup?.querySelector('button.active')?.textContent.trim() || 'Current Chapter';
    if (!/Current Chapter/i.test(mode)) return;
    const box = [...document.querySelectorAll('#voices textarea')].find(el =>
      /Preview text/i.test(el.closest('label')?.textContent || '')
    );
    if (!box || !chapter) return;
    const chapterNumber = String(Number(chapter.number || 0));
    const sourceText = String(chapter.text || '');
    const previousChapterNumber = String(box.dataset.ryuSourceChapterNumber || '');
    const previousSourceText = String(box.dataset.ryuSourceText || '');
    const sameChapter = previousChapterNumber === chapterNumber;
    // Keep deliberate preview-text edits. Only hydrate a newly selected chapter,
    // or update the source copy when it was not separately edited by the user.
    if (sameChapter && (box.value !== previousSourceText || document.activeElement === box)) return;
    if (sameChapter && previousSourceText === sourceText && box.value === sourceText) return;
    if (box.value !== sourceText) box.value = sourceText;
    box.dataset.ryuSourceChapterNumber = chapterNumber;
    box.dataset.ryuSourceText = sourceText;
  }

  async function flushChapterDraftBeforeSwitch() {
    // A project switch is allowed only when the editor, the in-memory chapter
    // record, and the last successful backend save reach a stable fixed point.
    // Limit retries so continuous typing or a broken autosave cannot hang the UI.
    for (let attempt = 0; attempt < 5; attempt++) {
      const number = Number(window.ryuPremiumSelectedChapter || 0);
      if (!number) {
        if (chapterSaveTimer) {
          throw new Error('A chapter save is pending but no chapter is selected. Stay in Chapter Studio and save the draft before switching projects.');
        }
        try { await chapterSavePromise; }
        catch (error) {
          throw new Error('A chapter save did not complete, so the project switch was stopped: ' + (error?.message || String(error)));
        }
        if (!Number(window.ryuPremiumSelectedChapter || 0) && !chapterSaveTimer) return;
        continue;
      }

      if (chapterSaveTimer) {
        clearTimeout(chapterSaveTimer);
        chapterSaveTimer = null;
      }

      let previousSaveFailed = false;
      try { await chapterSavePromise; }
      catch (_) { previousSaveFailed = true; }

      // Selection can change while an in-flight save completes. Re-read it on
      // the next pass rather than writing one chapter's text into another.
      if (Number(window.ryuPremiumSelectedChapter || 0) !== number) continue;

      const chapter = chapters.find(item => Number(item.number) === number);
      const editor = $('chapterEditor');
      if (!chapter || !editor) {
        throw new Error('The current chapter draft could not be verified. Stay in Chapter Studio and retry the Save before switching projects.');
      }

      // Read the latest editor values only after any earlier save has settled.
      // If the user typed during that save, the mismatch forces another save.
      const text = String(editor.value ?? chapter.text ?? '');
      const title = String($('chapterTitle')?.textContent || chapter.title || '');
      const savedText = String(chapter.text ?? '');
      const savedTitle = String(chapter.title ?? '');
      const saveLabel = String($('saveState')?.textContent || '');
      const hasUnsavedDraft = text !== savedText || title !== savedTitle;
      const saveStateNeedsRetry = /unsaved changes|saving|autosave failed/i.test(saveLabel);
      const needsSave = Boolean(
        previousSaveFailed || chapterSaveTimer || hasUnsavedDraft || saveStateNeedsRetry
      );
      if (!needsSave) return;

      if (chapterSaveTimer) {
        clearTimeout(chapterSaveTimer);
        chapterSaveTimer = null;
      }
      const saveTask = Promise.resolve(chapterSavePromise).catch(() => {}).then(async () => {
        const result = await call('chapter.update', {number, title, text});
        const saved = chapters.find(item => Number(item.number) === number);
        if (saved) {
          saved.text = text;
          saved.title = result?.title || title;
          saved.word_count = result?.word_count ?? (text.trim() ? text.trim().split(/\s+/).filter(Boolean).length : 0);
        }
        if (window.ryuPremiumSelectedChapter === number && $('saveState')) {
          $('saveState').textContent = 'Autosaved just now';
        }
        return result;
      });
      chapterSavePromise = saveTask;
      try { await saveTask; }
      catch (error) {
        if (window.ryuPremiumSelectedChapter === number && $('saveState')) $('saveState').textContent = 'Autosave failed';
        message('Chapter draft was not saved, so chapter switching was stopped: ' + (error?.message || String(error)), true);
        throw error;
      } finally {
        if (chapterSavePromise === saveTask) chapterSavePromise = Promise.resolve();
      }
      // Re-evaluate the editor after the save: never assume the snapshot stayed
      // current while the backend request was in flight.
    }
    throw new Error('The chapter kept changing while it was being saved. The project switch was stopped to protect your edits; wait for editing to settle and retry.');
  }

  function chapterDeleteSelection() {
    if (!(window.ryuPremiumChapterDeleteSelection instanceof Set)) {
      window.ryuPremiumChapterDeleteSelection = new Set();
    }
    return window.ryuPremiumChapterDeleteSelection;
  }

  function refreshChapterDeleteControls(list = $('chapterList')) {
    const selected = chapterDeleteSelection();
    const known = new Set(chapters.map(item => Number(item.number)));
    for (const number of [...selected]) if (!known.has(number)) selected.delete(number);
    if (list) list.querySelectorAll('[data-chapter-select]').forEach(input => {
      input.checked = selected.has(Number(input.dataset.chapterSelect));
    });
    const count = selected.size;
    const selectedButton = $('ryuDeleteSelectedChapters');
    const currentButton = $('ryuDeleteCurrentChapter');
    if (selectedButton) {
      selectedButton.textContent = 'Delete selected (' + count + ')';
      selectedButton.disabled = count === 0 || count >= chapters.length;
      selectedButton.title = count >= chapters.length
        ? 'At least one chapter must remain in the project.'
        : count ? 'Delete the selected chapters' : 'Select one or more chapters first';
    }
    if (currentButton) {
      currentButton.disabled = chapters.length <= 1 || !selectedChapter();
      currentButton.title = chapters.length <= 1
        ? 'At least one chapter must remain in the project.'
        : 'Delete the currently open chapter';
    }
  }

  function ensureChapterDeleteControls(list) {
    if (!list) return;
    let toolbar = $('ryuChapterDeleteToolbar');
    if (!toolbar) {
      toolbar = document.createElement('div');
      toolbar.id = 'ryuChapterDeleteToolbar';
      toolbar.setAttribute('aria-label', 'Chapter delete actions');
      toolbar.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 8px;';
      const style = document.createElement('style');
      style.id = 'ryuChapterDeleteStyle';
      style.textContent = [
        '#ryuChapterDeleteToolbar button{border:1px solid rgba(148,163,184,.24);border-radius:8px;padding:7px 10px;background:rgba(148,163,184,.08);color:inherit;font:inherit;font-size:12px;cursor:pointer;transition:background-color .16s ease,color .16s ease,border-color .16s ease,transform .16s ease}',
        '#ryuChapterDeleteToolbar button:hover:not(:disabled){transform:translateY(-1px);border-color:rgba(212,55,93,.65)}',
        '#ryuChapterDeleteToolbar button[data-danger="true"]{border-color:rgba(212,55,93,.45)}',
        '#ryuChapterDeleteToolbar button:disabled{opacity:.42;cursor:not-allowed}',
        '#chapterList [data-chapter-select]{accent-color:#d4375d;flex:0 0 auto;width:15px;height:15px;margin:0 2px 0 0;cursor:pointer}'
      ].join('');
      document.head.appendChild(style);
      const currentButton = document.createElement('button');
      currentButton.id = 'ryuDeleteCurrentChapter';
      currentButton.type = 'button';
      currentButton.textContent = 'Delete current';
      currentButton.title = 'Delete the currently open chapter';
      currentButton.addEventListener('click', () => {
        const current = selectedChapter();
        if (current) deleteChapterNumbers([current.number], 'current');
      });
      const selectedButton = document.createElement('button');
      selectedButton.id = 'ryuDeleteSelectedChapters';
      selectedButton.type = 'button';
      selectedButton.textContent = 'Delete selected (0)';
      selectedButton.dataset.danger = 'true';
      selectedButton.addEventListener('click', () => {
        deleteChapterNumbers([...chapterDeleteSelection()], 'selected');
      });
      toolbar.append(currentButton, selectedButton);
    }
    if (toolbar.parentElement !== list.parentElement || toolbar.nextElementSibling !== list) {
      list.insertAdjacentElement('beforebegin', toolbar);
    }
    refreshChapterDeleteControls(list);
  }

  async function deleteChapterNumbers(values, source) {
    const knownNumbers = new Set(chapters.map(item => Number(item.number)));
    const numbers = [...new Set((values || []).map(Number))]
      .filter(number => Number.isInteger(number) && knownNumbers.has(number))
      .sort((a,b) => b-a);
    if (!numbers.length) return;
    if (numbers.length >= chapters.length) {
      message('Keep at least one chapter in the project. Select fewer chapters to delete.', true);
      return;
    }
    const titles = numbers.map(number => {
      const item = chapters.find(chapter => Number(chapter.number) === number);
      return item ? 'Chapter ' + number + ' · ' + item.title : 'Chapter ' + number;
    });
    const description = numbers.length === 1 ? titles[0] : numbers.length + ' selected chapters';
    if (!window.confirm('Permanently delete ' + description + '? This cannot be undone.')) return;
    try {
      await flushChapterDraftBeforeSwitch();
    } catch (_) {
      return;
    }
    const priorCurrent = Number(window.ryuPremiumSelectedChapter || 0);
    let deleted = 0;
    try {
      // Delete highest numbers first, so any automatic renumbering cannot change
      // the identity of a later chapter in the selected batch.
      for (const number of numbers) {
        await call('chapter.delete', {number});
        deleted += 1;
      }
      const remaining = await call('chapter.list');
      chapters = Array.isArray(remaining) ? remaining : [];
      chapterDeleteSelection().clear();
      const next = chapters.find(chapter => Number(chapter.number) === priorCurrent) ||
        chapters.find(chapter => Number(chapter.number) >= Math.min(...numbers)) ||
        chapters[chapters.length - 1];
      if (next) window.ryuPremiumSelectedChapter = Number(next.number);
      await refreshChapters();
      message('Deleted ' + deleted + ' chapter' + (deleted === 1 ? '' : 's') + '.');
    } catch (error) {
      try {
        const remaining = await call('chapter.list');
        chapters = Array.isArray(remaining) ? remaining : chapters;
        chapterDeleteSelection().clear();
        if (!chapters.some(chapter => Number(chapter.number) === priorCurrent)) {
          const fallbackIndex = Math.max(0, Math.min(numbers[numbers.length - 1] - 1, chapters.length - 1));
          window.ryuPremiumSelectedChapter = Number(chapters[fallbackIndex]?.number || chapters[0]?.number || 0);
        }
        await refreshChapters();
      } catch (_) {}
      message((deleted ? 'Deleted ' + deleted + ' chapter(s), but the remaining deletion batch stopped: ' : 'Could not delete the chapter(s): ') + (error?.message || String(error)), true);
    }
  }

  async function refreshChapters() {
    const requestToken = ++chapterListEpoch;
    const editorBeforeRefresh = $('chapterEditor');
    const titleBeforeRefresh = $('chapterTitle');
    const selectedBeforeRefresh = Number(window.ryuPremiumSelectedChapter || 0);
    const saveLabelBeforeRefresh = String($('saveState')?.textContent || '');
    // Preserve the editor draft if it has focus or a debounce/save is in progress.
    // A job finishing in the background must never make a pending user edit vanish.
    const draftIsPending = Boolean(editorBeforeRefresh && selectedBeforeRefresh && (
      document.activeElement === editorBeforeRefresh ||
      document.activeElement === titleBeforeRefresh ||
      Boolean(chapterSaveTimer) ||
      /unsaved changes|saving|autosave failed/i.test(saveLabelBeforeRefresh)
    ));
    const draft = draftIsPending ? {
      number: selectedBeforeRefresh,
      text: editorBeforeRefresh.value,
      title: String(titleBeforeRefresh?.textContent || '')
    } : null;
    const chaptersBeforeRefresh = chapters;
    let loaded;
    let noActiveProject = false;
    try {
      loaded = await call('chapter.list');
    } catch (error) {
      if (requestToken !== chapterListEpoch) return chapters;
      const detail = String(error?.message || error || '');
      if (!/open a local project from the Library first|active project is no longer available in the local library/i.test(detail)) {
        throw error;
      }
      noActiveProject = true;
      loaded = [];
      // The host clears an invalid active-folder setting before returning this
      // error. Clear old project identity and cached cast data, not the source
      // files, if this is a genuine no-project state.
      window.ryuPremiumActiveProject = null;
      activeProjectCardEpoch++;
      activeProjectCardFolder = null;
      characters = [];
      characterDialogueSuggestions = [];
      characterAnalysisStatus = {analyzed:false, updated_at:null, dialogue_total:0, unassigned_dialogue:0, suggestion_count:0};
      window.ryuPremiumCharacterDialogueSuggestions = [];
      window.ryuPremiumCharacterAnalysisStatus = characterAnalysisStatus;
      window.ryuPremiumSelectedCharacter = '';
      window.ryuPremiumSelectedDialogueId = '';
      const projectTitleNode = document.querySelector('.project-mini .pm-body b');
      const projectCrumb = document.querySelector('.topbar .crumb span');
      writeTextIfChanged(projectTitleNode, 'No project selected');
      writeTextIfChanged(projectCrumb, 'No project selected');
      setProjectCardStatus('No project selected');
    }
    if (requestToken !== chapterListEpoch) return chapters;
    chapters = Array.isArray(loaded) ? loaded : [];
    ensureProductionPreviewMonitorUi();
    syncProductionPreviewChapterSelector();
    // Narrator spans are a derived view over the authoritative chapter source.
    // Refresh only after the new chapter text has been loaded so stale offsets
    // cannot be displayed for an edited/reordered/split/merged chapter.
    await refreshCharacterNarrationSegments();
    if (draft) {
      const pendingChapter = chapters.find(chapter => Number(chapter.number) === draft.number);
      if (pendingChapter) {
        pendingChapter.text = draft.text;
        pendingChapter.word_count = String(draft.text || '').trim().split(/\s+/).filter(Boolean).length;
        if (draft.title.trim()) pendingChapter.title = draft.title.trim();
      }
    }
    // If a refresh unexpectedly returns no chapters while a user has a pending
    // edit, retain the visible source instead of silently discarding the draft.
    if (!chapters.length && draft && chaptersBeforeRefresh.some(c => Number(c.number) === draft.number)) {
      chapters = chaptersBeforeRefresh;
      const preserved = chapters.find(c => Number(c.number) === draft.number);
      if (preserved) {
        preserved.text = draft.text;
        preserved.word_count = String(draft.text || '').trim().split(/\s+/).filter(Boolean).length;
        if (draft.title.trim()) preserved.title = draft.title.trim();
      }
      window.ryuPremiumChapters = chapters;
      writeTextIfChanged($('saveState'), 'Draft preserved locally — chapter refresh needs attention');
      message('The chapter list returned empty while edits were pending. Your visible draft was preserved; reopen the project and save it before continuing.', true);
      renderDialogueReview();
      renderCharacterStudioLive();
      if (typeof renderLiveChapterInsights === 'function') renderLiveChapterInsights();
      return chapters;
    }
    window.ryuPremiumChapters = chapters;
    if (noActiveProject) {
      characterDialogueSuggestions = [];
      characterAnalysisStatus = {analyzed:false, updated_at:null, dialogue_total:0, unassigned_dialogue:0, suggestion_count:0};
      window.ryuPremiumCharacterDialogueSuggestions = [];
      window.ryuPremiumCharacterAnalysisStatus = characterAnalysisStatus;
    } else {
      await refreshCharacterDialogueSuggestions();
    }
    if (!chapters.length) {
      const list = $('chapterList'), editor = $('chapterEditor'), title = $('chapterTitle');
      const activeProject = window.ryuPremiumActiveProject;
      const hasActiveProject = Boolean(activeProject && activeProject.folder);
      const emptyMessage = hasActiveProject
        ? 'No saved chapters yet. Add a chapter or re-import the source book.'
        : 'No project selected. Import a book or open one from Library to begin.';
      const emptySignature = 'empty:' + String(activeProject?.folder || 'none');
      if (list && list.dataset.chapterListSignature !== emptySignature) {
        list.innerHTML = '<p class="muted" data-chapter-empty-state="1">' + esc(emptyMessage) + '</p>';
        list.dataset.chapterListSignature = emptySignature;
      }
      window.ryuPremiumSelectedChapter = null;
      window.ryuPremiumSelectedDialogueId = '';
      window.ryuPremiumChapters = [];
      if (editor) {
        if (editor.value !== '') editor.value = '';
        editor.disabled = true;
        editor.placeholder = hasActiveProject ? 'Add a chapter before editing text.' : 'Import or open a project before editing chapters.';
      }
      writeTextIfChanged(title, hasActiveProject ? 'No chapter selected' : 'No project selected');
      writeTextIfChanged($('wordCount'), '0');
      writeTextIfChanged($('saveState'), hasActiveProject ? 'No chapter selected' : 'Import or open a project to begin');
      const search = $('chapterSearch');
      if (search) writeBooleanIfChanged(search, 'disabled', true);
      for (const id of ['saveChapter', 'cleanText']) {
        const button = $(id);
        if (button) writeBooleanIfChanged(button, 'disabled', true);
      }
      chapterDeleteSelection().clear();
      chapterHistoryGroupOpen = false;
      if (chapterHistoryGroupTimer) { clearTimeout(chapterHistoryGroupTimer); chapterHistoryGroupTimer = null; }
      renderDialogueReview();
      renderCharacterStudioLive();
      if (typeof renderLiveChapterInsights === 'function') renderLiveChapterInsights();
      return chapters;
    }
    if (!chapters.some(c => Number(c.number) === Number(window.ryuPremiumSelectedChapter))) window.ryuPremiumSelectedChapter = chapters[0].number;
    const current = selectedChapter(), list = $('chapterList'), editor = $('chapterEditor'), title = $('chapterTitle');
    if (editor) { writeBooleanIfChanged(editor, 'disabled', false); editor.removeAttribute('placeholder'); }
    if ($('chapterSearch')) writeBooleanIfChanged($('chapterSearch'), 'disabled', false);
    if ($('saveChapter')) writeBooleanIfChanged($('saveChapter'), 'disabled', false);
    if ($('cleanText')) writeBooleanIfChanged($('cleanText'), 'disabled', false);
    if (list) {
      ensureChapterDeleteControls(list);
      list.style.maxHeight = 'calc(100vh - 270px)';
      list.style.overflowY = 'auto';
      list.style.overscrollBehavior = 'contain';
      list.style.minHeight = '0';
      list.style.paddingRight = '4px';
      list.setAttribute('aria-label', 'Scrollable chapter list');
      const listSignature = chapters.map(c => String(c.number) + '\u001f' + String(c.title || '')).join('\u001e');
      if (list.dataset.chapterListSignature !== listSignature) {
        const previousScrollTop = list.scrollTop;
        list.innerHTML = chapters.map(c => '<div class="list-item ' + (Number(c.number) === Number(current.number) ? 'active' : '') + '" data-chapter-number="' + Number(c.number) + '" style="display:flex;align-items:center;gap:8px;min-width:0"><input type="checkbox" data-chapter-select="' + Number(c.number) + '" aria-label="Select chapter ' + Number(c.number) + '" style="accent-color:#d4375d;flex:0 0 auto;width:15px;height:15px;margin:0 2px 0 0;cursor:pointer"><span style="flex:1;min-width:0">' + esc('Chapter ' + c.number + ' · ' + c.title) + '</span></div>').join('');
        list.dataset.chapterListSignature = listSignature;
        list.querySelectorAll('[data-chapter-select]').forEach(input => {
          input.checked = chapterDeleteSelection().has(Number(input.dataset.chapterSelect));
          input.addEventListener('click', event => event.stopPropagation());
          input.addEventListener('change', () => {
            const number = Number(input.dataset.chapterSelect);
            if (input.checked) chapterDeleteSelection().add(number);
            else chapterDeleteSelection().delete(number);
            refreshChapterDeleteControls(list);
          });
        });
        list.querySelectorAll('[data-chapter-number]').forEach(el => el.addEventListener('click', async (event) => {
          if (event?.target?.closest?.('[data-chapter-select]')) return;
          const targetNumber = Number(el.dataset.chapterNumber);
          const selectionToken = ++chapterSelectionEpoch;
          try { await flushChapterDraftBeforeSwitch(); }
          catch (_) { return; }
          if (selectionToken !== chapterSelectionEpoch) return;
          const c = chapters.find(x => Number(x.number) === targetNumber); if (!c) return;
          window.ryuPremiumSelectedChapter = c.number;
          if (title) title.textContent = c.title; if (editor) editor.value = c.text;
          syncCurrentChapterPreviewText(c);
          if ($('wordCount')) $('wordCount').textContent = c.word_count;
          chapterLastText = c.text || ''; chapterHistoryGroupOpen = false;
          if (chapterHistoryGroupTimer) { clearTimeout(chapterHistoryGroupTimer); chapterHistoryGroupTimer = null; }
          list.querySelectorAll('.list-item').forEach(x => x.classList.toggle('active', x === el));
          renderLiveChapterInsights();
        }));
        list.scrollTop = previousScrollTop;
      } else {
        list.querySelectorAll('[data-chapter-number]').forEach(el =>
          el.classList.toggle('active', Number(el.dataset.chapterNumber) === Number(current.number))
        );
      }
      refreshChapterDeleteControls(list);
    }
    if (title && document.activeElement !== title) title.textContent = current.title;
    if (editor && document.activeElement !== editor) editor.value = current.text;
    syncCurrentChapterPreviewText(current);
    if ($('wordCount')) $('wordCount').textContent = current.word_count;
    chapterLastText = current.text || '';
    if (!draft) {
      chapterHistoryGroupOpen = false;
      if (chapterHistoryGroupTimer) { clearTimeout(chapterHistoryGroupTimer); chapterHistoryGroupTimer = null; }
    }
    renderDialogueReview();
    renderCharacterStudioLive();
    renderLiveChapterInsights();
    return chapters;
  }
  async function refreshCharacters() {
    const requestToken = ++characterListEpoch;
    const loaded = await call('character.list');
    if (requestToken !== characterListEpoch) return characters;
    characters = Array.isArray(loaded) ? loaded : [];
    await refreshCharacterNarrationSegments();
    const selectedName = String(window.ryuPremiumSelectedCharacter || '').trim().toLowerCase();
    const selectedSeries = String(window.ryuPremiumSelectedCharacterSeries || '').trim().toLowerCase();
    if (!characters.some(c => characterCanonical(c).toLowerCase() === selectedName &&
        (!selectedSeries || characterSeries(c).toLowerCase() === selectedSeries))) {
      window.ryuPremiumSelectedCharacter = '';
      window.ryuPremiumSelectedCharacterSeries = '';
    }
    renderCharacterStudioLive();
    return characters;
  }
  const librarySeriesName = c => {
    const raw = String(c?.series || c?.scope || '').trim();
    return raw.replace(/^Series\s*[·:-]\s*/i, '').replace(/^Global character library$/i, '').trim();
  };
  let seriesNarratorDefault = null;
  async function refreshSeriesNarratorControls() {
    const project = window.ryuPremiumActiveProject || null;
    const series = String(project?.series_name || project?.series || project?.title || '').trim();
    const panel = $('voices') || $('voice');
    if (!series || !panel) { seriesNarratorDefault = null; return null; }
    try { seriesNarratorDefault = await call('narrator.series.default.get', {series}); }
    catch (error) { console.warn('[Ryu series narrator default]', error); seriesNarratorDefault = null; }
    let card = $('seriesNarratorDefaultCard');
    if (!card) {
      card = document.createElement('section');
      card.id = 'seriesNarratorDefaultCard';
      card.className = 'card';
      card.style.cssText = 'margin:14px 0;padding:14px;border:1px solid rgba(150,160,180,.22);border-radius:12px;';
      const anchor = $('useNarrator')?.closest('.card') || $('useNarrator')?.parentElement || panel.firstElementChild;
      if (anchor?.parentNode) anchor.parentNode.insertBefore(card, anchor.nextSibling);
      else panel.appendChild(card);
    }
    const savedName = String(seriesNarratorDefault?.profile_name || '');
    const effectiveName = String(seriesNarratorDefault?.effective_profile_name || project?.voice_profile || '');
    const projectNarratorName = effectiveName;
    const sourceLabel = ({
      project_override:'Project Override',
      series_default:'Series Default',
      none:'Not Configured'
    })[String(seriesNarratorDefault?.source || project?.narrator_profile_source || 'none')] || 'Not Configured';
    const narratorSetupLabel = seriesNarratorDefault?.effective_profile_name
      ? (seriesNarratorDefault?.profile_available
        ? 'Narrator setup ready'
        : 'Narrator profile unavailable · generation blocked')
      : 'Incomplete narration setup · choose a narrator before generation';
    const profileOptions = characterSavedProfiles().map(profile =>
      '<option value="' + esc(profile.name) + '">' + esc(characterSavedProfileLabel(profile)) + '</option>'
    ).join('');
    const seriesOptions = characterSavedProfiles().map(profile =>
      '<option value="' + esc(profile.name) + '"' + (profile.name === savedName ? ' selected' : '') + '>' + esc(characterSavedProfileLabel(profile)) + '</option>'
    ).join('');
    card.innerHTML = '<div style="font-weight:750;margin-bottom:5px">Project Narrator</div>' +
      '<div class="muted" style="font-size:12px;margin-bottom:8px">Active project: ' + esc(String(project?.title || '')) +
      ' · Current narrator: ' + esc(projectNarratorName || 'Not selected') +
      ' · Source: ' + esc(sourceLabel) +
      ' · ' + esc(narratorSetupLabel) + '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px">' +
      '<select id="projectNarratorProfile" class="input" style="min-width:220px;flex:1">' +
      '<option value="">Choose a saved narrator profile</option>' + profileOptions + '</select>' +
      '<button class="btn small" type="button" id="saveProjectNarrator">Use for This Book</button>' +
      '<button class="btn small ghost" type="button" id="resetProjectNarrator">Reset to Series Default</button></div>' +
      '<div style="font-weight:750;margin-bottom:5px">Series Narrator Default</div>' +
      '<div class="muted" style="font-size:12px;margin-bottom:10px">Series: ' + esc(series) +
      ' · Projects inherit this voice unless they have an explicit project override. Updating this default refreshes every inheriting project.</div>' +
      '<select id="seriesNarratorProfile" class="input" style="width:100%;margin-bottom:8px">' +
      '<option value="">Choose a saved voice profile</option>' + seriesOptions + '</select>' +
      '<div class="muted" style="font-size:12px;margin-bottom:9px">Saved default: ' + esc(savedName || 'Not set') +
      ' · Effective narrator for this book: ' + esc(effectiveName || 'Not set') +
      ' · Source: ' + esc(sourceLabel) + '</div>' +
      '<div class="muted" style="font-size:12px;margin:8px 0">To audition the effective narrator, select narration-only text in Chapter Studio first. Uses the Preview Length control above.</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn small" type="button" id="previewProjectNarrator">Preview Selected Narration</button>' +
      '<button class="btn small" type="button" id="saveSeriesNarratorDefault">Save Series Default</button></div>';
    $('saveProjectNarrator')?.addEventListener('click', async () => {
      const profileName = String($('projectNarratorProfile')?.value || '').trim();
      if (!profileName) { message('Select a saved narrator profile first.', true); return; }
      try {
        const selected = await call('voice.select', {profile_name:profileName});
        await refreshCurrentProjectCard();
        await refreshSeriesNarratorControls();
        message('Project narrator saved: ' + selected.name);
      } catch (error) { message(error?.message || String(error), true); }
    });
    $('saveSeriesNarratorDefault')?.addEventListener('click', async () => {
      const profileName = String($('seriesNarratorProfile')?.value || '').trim();
      if (!profileName) { message('Select a saved voice profile first.', true); return; }
      try {
        const saved = await call('narrator.series.default.save', {series, profile_name:profileName});
        await refreshSeriesNarratorControls();
        message('Series narrator default saved: ' + saved.profile_name);
      } catch (error) { message(error?.message || String(error), true); }
    });
    $('resetProjectNarrator')?.addEventListener('click', async () => {
      try {
        const reset = await call('narrator.project.reset', {series});
        await refreshProjects();
        await refreshCurrentProjectCard();
        await refreshSeriesNarratorControls();
        const messageText = reset.profile_name
          ? 'Project narrator reset. It now inherits ' + reset.profile_name + ' from the series.'
          : 'Project narrator override cleared. Configure a series narrator before generation.';
        message(messageText, !reset.profile_available);
      } catch (error) { message(error?.message || String(error), true); }
    });
    $('previewProjectNarrator')?.addEventListener('click', async () => {
      try {
        const chapter = selectedChapter();
        const editor = $('chapterEditor');
        if (!chapter || !editor) throw new Error('Open a chapter in Chapter Studio before previewing narration.');
        const start = Number(editor.selectionStart), end = Number(editor.selectionEnd);
        if (!Number.isInteger(start) || !Number.isInteger(end) || end <= start) {
          throw new Error('Select narration-only text in Chapter Studio first.');
        }
        const selectedText = editor.value.slice(start, end);
        if (!selectedText.trim()) throw new Error('The selected narration passage is empty.');

        // Flush pending chapter edits before sending source offsets to the backend.
        if (chapterSaveTimer) { clearTimeout(chapterSaveTimer); chapterSaveTimer = null; }
        await chapterSavePromise.catch(() => {});
        const chapterTitleValue = $('chapterTitle')?.textContent || chapter.title;
        // This handler is outside wire()'s lexical scope, so persist through the
        // public backend bridge rather than calling wire()'s local helper.
        const savedChapter = await call('chapter.update', {
          number:chapter.number,
          title:chapterTitleValue,
          text:editor.value
        });
        const cachedChapter = chapters.find(item => Number(item.number) === Number(chapter.number));
        if (cachedChapter) {
          cachedChapter.title = savedChapter.title || chapterTitleValue;
          cachedChapter.text = editor.value;
          cachedChapter.word_count = savedChapter.word_count;
        }
        const saveState = $('saveState');
        if (saveState) saveState.textContent = 'Saved just now';

        const lengthGroup = [...document.querySelectorAll('#voices .toolbar')].find(el => /Length/.test(el.textContent));
        const duration = Number(lengthGroup?.querySelector('.seg button.active')?.textContent.match(/\d+/)?.[0] || 30);
        const result = await call('narrator.preview', {
          chapter_number:chapter.number, start, end, text:selectedText, duration_seconds:duration
        });
        if (!result?.job_id || !result.profile_name) throw new Error('Narrator Preview did not return a valid preview job.');
        await waitForNarratorPreviewJob(result.job_id, duration, result.profile_name);
      } catch (error) { message(error?.message || String(error), true); }
    });
    return seriesNarratorDefault;
  }
  function activeCharacterProjectSeries() {
    const active = window.ryuPremiumActiveProject || {};
    return String(active.series_name || active.series || active.title || '').trim();
  }
  function characterSavedProfiles() {
    return voices.filter(item => item && item.saved === true && String(item.name || '').trim());
  }
  function characterSavedProfileLabel(profile) {
    const name = String(profile?.name || '').trim();
    const provider = String(profile?.provider || '').trim();
    const model = String(profile?.model_id || profile?.model_name || profile?.model || '').trim();
    return [name, provider, model].filter(Boolean).join(' · ');
  }
  function characterProfileByName(name) {
    const key = String(name || '').trim().toLowerCase();
    return characterSavedProfiles().find(item => String(item.name || '').trim().toLowerCase() === key) || null;
  }
  function characterAliases(item) {
    const values = Array.isArray(item?.aliases) ? item.aliases : [];
    return values.map(value => String(value || '').trim()).filter(Boolean);
  }
  function characterCanonical(item) {
    return String(item?.name || item?.primary_name || '').trim();
  }
  function characterSeries(item) {
    return librarySeriesName(item || {}) || activeCharacterProjectSeries() || 'Unassigned series';
  }
  function characterRowForName(name, series) {
    const key = String(name || '').trim().toLowerCase();
    const seriesKey = String(series || '').trim().toLowerCase();
    const matches = characters.filter(item => characterCanonical(item).toLowerCase() === key ||
      characterAliases(item).some(alias => alias.toLowerCase() === key));
    if (seriesKey) {
      const scoped = matches.filter(item => characterSeries(item).toLowerCase() === seriesKey);
      return scoped.length === 1 ? scoped[0] : null;
    }
    return matches.length === 1 ? matches[0] : null;
  }
  function selectedCharacterRow() {
    return characterRowForName(window.ryuPremiumSelectedCharacter, window.ryuPremiumSelectedCharacterSeries);
  }
  function characterAssignmentKey(name, series) {
    return String(name || '').trim().toLowerCase() + '::' + String(series || '').trim().toLowerCase();
  }
  function characterAssignmentsFor(chapter) {
    return Array.isArray(chapter?.dialogue_assignments) ? chapter.dialogue_assignments.filter(item => item && typeof item === 'object') : [];
  }
  function characterDialogueRowsForChapter(chapter) {
    if (!chapter) return [];
    const source = String(chapter.text || '');
    const candidates = new Map();
    for (const item of characterDialogueSuggestions.filter(row => Number(row.chapter_number) === Number(chapter.number))) {
      const start = Number(item.start), end = Number(item.end);
      if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > source.length) continue;
      const exact = source.slice(start, end);
      if (exact !== String(item.source_text || item.text || '')) continue;
      candidates.set(start + ':' + end, {...item, start, end, source_text:exact, text:exact});
    }
    // Manual assignment remains usable before analysis has been run. Discover
    // only quoted source spans here; predictions are never fabricated.
    const quotePattern = /“[^”]{2,}”|「[^」]{2,}」|『[^』]{2,}』|"[^"\n]{2,}"/g;
    quotePattern.lastIndex = 0;
    let match;
    while ((match = quotePattern.exec(source))) {
      const start = match.index, end = start + match[0].length, key = start + ':' + end;
      if (!candidates.has(key)) candidates.set(key, {
        id:'dialogue-' + Number(chapter.number) + '-' + start + '-' + end,
        chapter_number:Number(chapter.number), chapter_title:String(chapter.title || ''),
        start, end, source_text:match[0], text:match[0], suggestions:[], suggested_speaker:'',
        confidence:0, skipped:false, assignmentSeries:'', source:'quoted-source-span'
      });
    }
    const assignments = characterAssignmentsFor(chapter);
    // Any persisted assignment is source data even when the passage has no
    // quotation marks and was selected manually. Include it in the visual source
    // map so green assignment highlights never disappear on refresh.
    for (const assignment of assignments) {
      const start = Number(assignment?.start), end = Number(assignment?.end);
      if (!Number.isInteger(start) || !Number.isInteger(end) ||
          start < 0 || end <= start || end > source.length) continue;
      const exact = source.slice(start, end);
      if (!exact || (assignment?.text && String(assignment.text) !== exact)) continue;
      const key = start + ':' + end;
      if (!candidates.has(key)) candidates.set(key, {
        id:'assignment-' + Number(chapter.number) + '-' + start + '-' + end,
        chapter_number:Number(chapter.number), chapter_title:String(chapter.title || ''),
        start, end, source_text:exact, text:exact, suggestions:[],
        suggested_speaker:'', confidence:0, skipped:false, source:'saved-assignment'
      });
    }
    const result = [];
    for (const row of [...candidates.values()].sort((a,b) => a.start - b.start)) {
      const assignment = assignments.find(item => Number(item.start) === row.start && Number(item.end) === row.end &&
        source.slice(row.start, row.end) === String(item.text || source.slice(row.start, row.end)));
      const rawSpeakers = Array.isArray(assignment?.speakers) ? assignment.speakers :
        (assignment?.speaker ? [assignment.speaker] : []);
      const suggestions = Array.isArray(row.suggestions) ? row.suggestions.filter(item => item && item.name) : [];
      const fallback = row.suggested_speaker ? [{
        name:String(row.suggested_speaker), confidence:Number(row.confidence || 0),
        evidence:'Local dialogue-context analysis'
      }] : [];
      result.push({
        ...row,
        chapter_number:Number(chapter.number),
        chapter_title:String(chapter.title || ''),
        text:source.slice(row.start, row.end),
        speakers:rawSpeakers.map(value => String(value || '').trim()).filter(Boolean),
        assigned:Boolean(rawSpeakers.length),
        assignmentPresent:Boolean(assignment),
        assignmentSeries:String(assignment?.series || ''),
        assignmentSource:assignment
          ? (String(assignment.source || 'manual').trim().toLowerCase() === 'ai' ? 'ai' : 'manual')
          : '',
        suggestions:suggestions.length ? suggestions : fallback
      });
    }
    // Include all unresolved source spans from the authoritative segmentation
    // feed, even when the browser's simple quote pattern does not recognize
    // dash-style or smart-single-quoted dialogue.
    const reviewSegments = characterNarrationSegments.filter(row =>
      Number(row.chapter_number) === Number(chapter.number) && row.kind === 'needs_speaker_review'
    );
    for (const segment of reviewSegments) {
      const start = Number(segment.start), end = Number(segment.end);
      if (!Number.isInteger(start) || !Number.isInteger(end) ||
          start < 0 || end <= start || end > source.length) continue;
      const exact = source.slice(start, end);
      if (!exact || exact !== String(segment.text || '')) continue;
      const existing = result.find(row => Number(row.start) === start && Number(row.end) === end);
      if (existing) {
        existing.needsReview = true;
        continue;
      }
      result.push({
        id:'review-' + Number(chapter.number) + '-' + start + '-' + end,
        chapter_number:Number(chapter.number), chapter_title:String(chapter.title || ''),
        start, end, source_text:exact, text:exact, suggestions:[],
        suggested_speaker:'', confidence:0, skipped:false, assignmentSeries:'',
        source:'source-segmentation-review', speakers:[], assigned:false,
        assignmentPresent:false, assignmentSource:'', needsReview:true
      });
    }
    return result.sort((a,b) => Number(a.start) - Number(b.start) || Number(b.end) - Number(a.end));
  }
  async function refreshCharacterDialogueSuggestions() {
    const token = ++characterSuggestionsEpoch;
    try {
      const [loaded, status] = await Promise.all([
        call('character.dialogue.suggestions.list'),
        call('character.analysis.status')
      ]);
      if (token !== characterSuggestionsEpoch) return characterDialogueSuggestions;
      characterDialogueSuggestions = Array.isArray(loaded) ? loaded : [];
      if (status && typeof status === 'object') {
        characterAnalysisStatus = {
          analyzed: status.analyzed === true,
          updated_at: status.updated_at || null,
          dialogue_total: Math.max(0, Number(status.dialogue_total) || 0),
          unassigned_dialogue: Math.max(0, Number(status.unassigned_dialogue) || 0),
          suggestion_count: Math.max(0, Number(status.suggestion_count) || 0)
        };
      }
      window.ryuPremiumCharacterDialogueSuggestions = characterDialogueSuggestions;
      window.ryuPremiumCharacterAnalysisStatus = characterAnalysisStatus;
      return characterDialogueSuggestions;
    } catch (error) {
      console.warn('[Ryu character dialogue suggestions/status]', error);
      // A temporary bridge error should not erase the last confirmed local data.
      return characterDialogueSuggestions;
    }
  }
  async function refreshCharacterNarrationSegments() {
    try {
      const loaded = await call('character.narration.segments.list');
      characterNarrationSegments = Array.isArray(loaded) ? loaded : [];
      return characterNarrationSegments;
    } catch (error) {
      console.warn('[Ryu narrator segmentation]', error);
      return characterNarrationSegments;
    }
  }
  function characterNarrationSegmentsForChapter(chapter) {
    const number = Number(chapter?.number);
    if (!Number.isFinite(number)) return [];
    const source = String(chapter?.text || '');
    return characterNarrationSegments.filter(row => Number(row.chapter_number) === number &&
      row.kind === 'narration' && Number.isInteger(Number(row.start)) &&
      Number.isInteger(Number(row.end)) && Number(row.start) >= 0 &&
      Number(row.end) > Number(row.start) && Number(row.end) <= source.length &&
      source.slice(Number(row.start), Number(row.end)) === String(row.text || ''));
  }
  function installCharacterStudioStyles() {
    if ($('ryuLiveCharacterStudioStyles')) return;
    const style = document.createElement('style');
    style.id = 'ryuLiveCharacterStudioStyles';
    style.textContent =
      '.ryu-live-story{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8;min-height:220px;padding:14px;}' +
      '.ryu-live-passage{display:inline;white-space:pre-wrap;max-width:100%;cursor:pointer;border:0;border-radius:5px;padding:1px 2px;background:transparent;color:inherit;font:inherit;text-align:left;box-shadow:inset 3px 0 0 transparent;}' +
      '.ryu-live-passage:hover{background:rgba(255,255,255,.035);outline:1px solid rgba(255,255,255,.12);}' +
      '.ryu-live-passage.is-assigned{background:rgba(36,190,122,.07);box-shadow:inset 3px 0 0 #22c982;}' +
      '.ryu-live-passage.is-assigned-ai{background:rgba(236,160,45,.075);box-shadow:inset 3px 0 0 #efae35;}' +
      '.ryu-live-passage.is-assigned-manual{background:rgba(36,190,122,.07);box-shadow:inset 3px 0 0 #22c982;}' +
      '.ryu-live-passage.is-ai-review{background:rgba(236,160,45,.075);box-shadow:inset 3px 0 0 #efae35;}' +
      '.ryu-narrator-passage{display:inline;white-space:pre-wrap;overflow-wrap:anywhere;border-radius:5px;background:rgba(91,153,222,.055);box-shadow:inset 3px 0 0 rgba(91,153,222,.5);padding:1px 2px;}' +
      '.ryu-narrator-chip{display:inline-flex;vertical-align:middle;margin:0 5px 0 2px;padding:2px 6px;border-radius:8px;background:rgba(91,153,222,.14);color:#8fc0ff;font-size:10px;font-weight:800;letter-spacing:.02em;}' +
      '.ryu-needs-speaker-chip{background:rgba(236,160,45,.14);color:#efbd63;}' +
      '.ryu-live-passage .ryu-speaker-chip{display:inline-flex;vertical-align:middle;margin:0 5px 0 2px;padding:2px 6px;border-radius:8px;background:rgba(34,201,130,.12);color:#25d184;font-size:10px;font-weight:800;}' +
      '.ryu-character-empty{padding:22px 16px;text-align:center;color:#aeb6c5;line-height:1.6;}' +
      '.ryu-character-empty b{display:block;color:#f0f2f7;margin-bottom:7px;font-size:15px;}' +
      '.ryu-assigned-extra{display:flex;gap:10px;align-items:end;flex-wrap:wrap;padding:14px 0;}' +
      '.ryu-assigned-extra label,.ryu-manual-create label{display:flex;flex:1 1 210px;flex-direction:column;gap:6px;color:#aeb6c5;font-size:12px;font-weight:700;}' +
      '.ryu-assigned-extra select,.ryu-manual-create input,.ryu-manual-create select{width:100%;box-sizing:border-box;padding:10px;border:1px solid #343b49;border-radius:10px;background:#0d1119;color:#f4f5f8;font:inherit;}' +
      '.ryu-manual-create{padding:10px 2px;display:grid;grid-template-columns:1fr;gap:10px;}' +
      '.ryu-manual-create[hidden]{display:none!important;}' +
      '.ryu-character-subsection{margin:8px 0 5px;padding-top:9px;border-top:1px solid rgba(255,255,255,.09);color:#e3b65e;font-size:10px;letter-spacing:.12em;font-weight:800;text-transform:uppercase;}' +
      '.ryu-ai-option{display:flex!important;flex-direction:column;align-items:flex-start!important;gap:4px!important;text-align:left;}' +
      '.ryu-ai-option small{color:#aeb6c5;font-size:11px;font-weight:400;line-height:1.4;}' +
      '.ryu-assigned-series{border-left:3px solid #e3b65e;padding-left:12px;}' +
      '.ryu-assigned-dialogue{display:block;width:100%;box-sizing:border-box;margin:0 0 8px;padding:11px 13px;border:1px solid transparent;border-radius:9px;color:inherit;text-align:left;font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;cursor:pointer;}' +
      '.ryu-assigned-dialogue small{display:block;margin-bottom:6px;font-size:10px;letter-spacing:.06em;text-transform:uppercase;opacity:.8;}' +
      '.ryu-assigned-dialogue-ai{background:rgba(236,160,45,.075);border-color:rgba(236,160,45,.22);box-shadow:inset 3px 0 0 #efae35;}' +
      '.ryu-assigned-dialogue-manual{background:rgba(36,190,122,.07);border-color:rgba(36,190,122,.2);box-shadow:inset 3px 0 0 #22c982;}' +
      '.ryu-assigned-dialogue-unknown{background:rgba(140,145,155,.06);border-color:rgba(140,145,155,.2);box-shadow:inset 3px 0 0 #8d929b;}' +
      '.ryu-assigned-dialogue.is-selected{outline:2px solid rgba(255,255,255,.62);outline-offset:1px;}' +
      '.assigned-character.active{border-color:rgba(227,182,94,.8);background:rgba(227,182,94,.08);}' +
      '#characterAssignPopover{max-height:82vh;overflow-y:auto;box-sizing:border-box;}' +
      '#characterAssignPopover .popover-head>div{min-width:0;flex:1 1 auto;}' +
      '#characterAssignPopover .popover-head b{display:block;max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere;overflow:visible;text-overflow:clip;line-height:1.45;max-height:150px;overflow-y:auto;}' +
      '#characters .ai-sentence.unassigned{display:block;width:100%;max-width:100%;box-sizing:border-box;background:transparent!important;border:1px solid transparent!important;border-left:3px solid transparent!important;box-shadow:none!important;color:inherit!important;text-align:left;font:inherit;font-weight:400;white-space:pre-wrap;}' +
      '#characters .ai-sentence.review{display:block;width:100%;max-width:100%;box-sizing:border-box;background:rgba(236,160,45,.075)!important;border:1px solid rgba(236,160,45,.18)!important;border-left:3px solid #efae35!important;box-shadow:none!important;color:inherit!important;text-align:left;white-space:pre-wrap;}' +
      '#characters .ai-sentence.confirmed{display:block;width:100%;max-width:100%;box-sizing:border-box;background:rgba(36,190,122,.07)!important;border:1px solid rgba(36,190,122,.18)!important;border-left:3px solid #22c982!important;box-shadow:none!important;color:inherit!important;text-align:left;white-space:pre-wrap;}' +
      '#characters .ai-sentence.confirmed-manual{background:rgba(36,190,122,.07)!important;border-color:rgba(36,190,122,.18)!important;border-left-color:#22c982!important;}' +
      '#characters .ai-sentence.confirmed-ai{background:rgba(236,160,45,.075)!important;border-color:rgba(236,160,45,.22)!important;border-left-color:#efae35!important;}' +
      '#characters .ai-sentence.confirmed-ai.active,#characters .ai-sentence.confirmed-manual.active{outline:2px solid rgba(255,255,255,.65)!important;outline-offset:1px;}' +
      '#aiPredictionModal .ai-prediction-modal{width:min(640px,calc(100vw - 32px));height:min(680px,82vh);max-height:min(82vh,760px);overflow:auto;}' +
      '#aiPredictionModal .selected-dialogue-preview{margin-bottom:12px;min-height:64px;display:flex;align-items:center;line-height:1.6;}';
    document.head.appendChild(style);
  }
  function ensureAssignedAudioProfileControls() {
    const inspector = document.querySelector('#characters .assigned-inspector');
    const summary = inspector?.querySelector('.assigned-summary');
    if (!inspector || !summary) return;
    let box = $('assignedAudioProfileControls');
    if (!box) {
      box = document.createElement('div');
      box.id = 'assignedAudioProfileControls';
      box.className = 'ryu-assigned-extra';
      box.innerHTML = '<label>Audio profile: select a saved profile<select id="assignedAudioProfile"><option value="">No saved profiles available</option></select></label><button type="button" class="btn" id="saveAssignedAudioProfile" disabled>Save profile</button>';
      inspector.insertBefore(box, summary);
      const save = $('saveAssignedAudioProfile');
      if (save) save.addEventListener('click', act(async () => {
        const c = selectedCharacterRow();
        if (!c) throw new Error('Select a character from the active project cast first.');
        const profileName = String($('assignedAudioProfile')?.value || '').trim();
        if (profileName && !characterProfileByName(profileName)) throw new Error('Choose a saved audio profile.');
        await call('character.assign', {name:characterCanonical(c), series:characterSeries(c), profile_name:profileName});
        await refreshCharacters();
        await refreshCharacterLibrary();
        message(profileName ? 'Saved ' + profileName + ' for ' + characterCanonical(c) + '.' : 'Removed the assigned voice profile from ' + characterCanonical(c) + '.');
      }));
    }
    const select = $('assignedAudioProfile');
    if (!select) return;
    const saved = characterSavedProfiles();
    const currentCharacter = selectedCharacterRow();
    const current = String(currentCharacter?.voice_profile || '');
    const currentCharacterKey = currentCharacter
      ? characterAssignmentKey(characterCanonical(currentCharacter), characterSeries(currentCharacter))
      : '';
    const options = [['','Select a saved audio profile'], ...saved.map(item => [String(item.name), String(item.name) + ' · ' + String(item.provider || 'Voice')])];
    const signature = JSON.stringify(options);
    if (select.dataset.liveOptionsSignature !== signature) {
      const previous = select.value;
      select.innerHTML = options.map(([value,label]) => '<option value="' + esc(value) + '">' + esc(label) + '</option>').join('');
      select.dataset.liveOptionsSignature = signature;
      const previousStillAvailable = options.some(item => item[0] === previous);
      const characterChanged = select.dataset.characterKey !== currentCharacterKey;
      if (characterChanged || select.dataset.selectionInitialized !== '1' || !previousStillAvailable) {
        select.value = options.some(item => item[0] === current) ? current : '';
      }
    } else if (select.dataset.characterKey !== currentCharacterKey ||
               !options.some(item => item[0] === select.value)) {
      select.value = options.some(item => item[0] === current) ? current : '';
    }
    select.dataset.characterKey = currentCharacterKey;
    select.dataset.selectionInitialized = '1';
    select.disabled = !currentCharacter || saved.length === 0;
    const save = $('saveAssignedAudioProfile');
    if (save) save.disabled = !currentCharacter || saved.length === 0 || select.value === current;
    select.onchange = () => {
      if (save) save.disabled = !currentCharacter || saved.length === 0 || select.value === current;
      renderCharacterInspector();
    };
  }
  function characterVoiceAssignments(name, series) {
    const item = characterRowForName(name, series);
    const names = new Set([characterCanonical(item), ...characterAliases(item)]
      .filter(Boolean).map(value => value.toLowerCase()));
    const selectedSeries = String(series || characterSeries(item) || '').trim().toLowerCase();
    const projectDefaultSeries = String(activeCharacterProjectSeries() || '').trim().toLowerCase();
    const passages = [];
    const chapterSet = new Set();
    const seenPassageIds = new Set();
    let aiAssigned = 0;
    let manualAssigned = 0;
    let sourceUnavailable = 0;
    for (const chapter of chapters) {
      const source = String(chapter.text || '');
      for (const assignment of characterAssignmentsFor(chapter)) {
        const speakers = Array.isArray(assignment.speakers) ? assignment.speakers :
          (assignment.speaker ? [assignment.speaker] : []);
        const speakerKeys = speakers.map(speaker => String(speaker || '').trim().toLowerCase()).filter(Boolean);
        if (!speakerKeys.some(speaker => names.has(speaker))) continue;

        const storedSeries = String(assignment.series || '').trim().toLowerCase();
        const assignmentSeries = storedSeries || projectDefaultSeries;
        if (selectedSeries && assignmentSeries && assignmentSeries !== selectedSeries) continue;
        if (selectedSeries && !assignmentSeries) {
          // An unscoped legacy assignment is safe only when none of its speakers
          // also identify a saved character in another series.
          const ambiguousLegacyIdentity = characters.some(other => {
            if (!other || other === item) return false;
            const otherSeries = characterSeries(other).trim().toLowerCase();
            if (!otherSeries || otherSeries === selectedSeries) return false;
            const otherNames = [characterCanonical(other), ...characterAliases(other)]
              .map(value => String(value || '').trim().toLowerCase()).filter(Boolean);
            return otherNames.some(value => speakerKeys.includes(value));
          });
          if (ambiguousLegacyIdentity) continue;
        }

        const start = Number(assignment.start), end = Number(assignment.end);
        if (!Number.isInteger(start) || !Number.isInteger(end) ||
            start < 0 || end <= start || end > source.length) continue;
        const text = source.slice(start, end);
        if (!text || (assignment.text && String(assignment.text) !== text)) continue;
        const passageId = String(chapter.number) + ':' + start + ':' + end;
        if (seenPassageIds.has(passageId)) continue;
        seenPassageIds.add(passageId);

        chapterSet.add(Number(chapter.number));
        const rawSourceKind = String(assignment.source || '').trim().toLowerCase().replace(/_/g, '-');
        const sourceKind = ['ai', 'ai-analyzed'].includes(rawSourceKind)
          ? 'ai' : rawSourceKind === 'manual' ? 'manual' : 'unknown';
        if (sourceKind === 'ai') aiAssigned += 1;
        else if (sourceKind === 'manual') manualAssigned += 1;
        else sourceUnavailable += 1;
        passages.push({
          chapter_number:Number(chapter.number), start, end, text,
          source:sourceKind,
          series:storedSeries || assignmentSeries || selectedSeries,
          speakers
        });
      }
    }
    const dialogueLines = passages.length;
    const aiAssignedPercent = dialogueLines ? Math.round(aiAssigned / dialogueLines * 100) : 0;
    return {passages, chapters:[...chapterSet].sort((a,b) => a-b), dialogueLines,
      aiAssignedLines:aiAssigned, manualAssignedLines:manualAssigned,
      sourceUnavailableLines:sourceUnavailable, aiAssignedPercent};
  }
  function renderCharacterInspector() {
    const selected = selectedCharacterRow();
    const inspector = document.querySelector('#characters .assigned-inspector');
    if (!inspector) return;
    const summary = inspector.querySelector('.assigned-summary');
    if (summary && !$('assignedSeriesName')) {
      const seriesBox = document.createElement('div');
      seriesBox.className = 'ryu-assigned-series';
      seriesBox.innerHTML = '<b id="assignedSeriesName">—</b><span>Series</span>';
      const voiceCard = $('assignedVoiceName')?.closest('.assigned-summary > div');
      summary.insertBefore(seriesBox, voiceCard || summary.firstChild);
    }
    ensureAssignedAudioProfileControls();
    const nameNode = $('assignedInspectorName');
    const aliasesNode = $('assignedAliases');
    const voiceNode = $('assignedVoiceName');
    const lineNode = $('assignedLineCount');
    const chapterNode = $('assignedChapterCount');
    const aiAssignedNode = $('assignedConfidence');
    const quotesNode = $('assignedQuotes');
    const seriesBox = $('assignedSeriesName')?.closest('.assigned-summary > div');
    if (!selected) {
      if (nameNode) nameNode.textContent = 'No characters found';
      if (aliasesNode) aliasesNode.textContent = 'Choose a character from the saved Assigned Cast.';
      if (voiceNode) voiceNode.textContent = 'Unassigned';
      if (lineNode) lineNode.textContent = '0';
      if (chapterNode) chapterNode.textContent = '0';
      if (aiAssignedNode) aiAssignedNode.textContent = '0%';
      if (quotesNode) quotesNode.innerHTML = '<div class="ryu-character-empty"><b>No saved dialogue yet</b>Save a character dialogue assignment to display it here.</div>';
      if (seriesBox) seriesBox.hidden = true;
      if ($('assignedAudioProfile')) { $('assignedAudioProfile').value = ''; $('assignedAudioProfile').disabled = true; }
      if ($('saveAssignedAudioProfile')) $('saveAssignedAudioProfile').disabled = true;
      if ($('testAssignedVoice')) $('testAssignedVoice').disabled = true;
      if ($('editAssignedCharacter')) $('editAssignedCharacter').disabled = true;
      return;
    }
    if (nameNode) nameNode.textContent = characterCanonical(selected);
    if (aliasesNode) aliasesNode.textContent = 'Aliases: ' + (characterAliases(selected).join(', ') || 'None');
    const seriesValue = characterSeries(selected);
    const seriesName = $('assignedSeriesName');
    if (seriesName) seriesName.textContent = seriesValue;
    if (seriesBox) seriesBox.hidden = false;
    const profileName = String(selected.voice_profile || '').trim();
    if (voiceNode) voiceNode.textContent = profileName || 'Unassigned';
    const assignments = characterVoiceAssignments(selected.name, seriesValue);
    const selectedDialogueKey = String(window.ryuPremiumSelectedAssignedDialogueKey || '');
    const selectedDialogueRow = assignments.passages.find(row =>
      characterAssignmentKey(selected.name, seriesValue) + '::' +
        row.chapter_number + ':' + row.start + ':' + row.end === selectedDialogueKey
    );
    if (lineNode) lineNode.textContent = String(assignments.dialogueLines);
    if (chapterNode) chapterNode.textContent = String(assignments.chapters.length);
    if (aiAssignedNode) aiAssignedNode.textContent = String(assignments.aiAssignedPercent) + '%';
    if (quotesNode) {
      const rows = assignments.passages;
      quotesNode.innerHTML = rows.length ? rows.map(row => {
        const sourceKind = row.source === 'ai' ? 'ai' : row.source === 'manual' ? 'manual' : 'unknown';
        const sourceLabel = sourceKind === 'ai' ? 'AI-assigned' :
          sourceKind === 'manual' ? 'Manually assigned' : 'Source not recorded';
        const key = characterAssignmentKey(selected.name, seriesValue) + '::' +
          row.chapter_number + ':' + row.start + ':' + row.end;
        const active = key === selectedDialogueKey;
        return '<button type="button" class="ryu-assigned-dialogue ryu-assigned-dialogue-' + sourceKind +
          (active ? ' is-selected' : '') + '" data-assigned-dialogue-key="' + esc(key) + '">' +
          '<small>Chapter ' + Number(row.chapter_number) + ' · ' + sourceLabel + '</small>' +
          '<span>' + esc(row.text) + '</span></button>';
      }).join('') : '<div class="ryu-character-empty"><b>No assigned dialogue yet</b>Assign and save a source passage in Character assigning to see it here.</div>';
      if (selectedDialogueKey && !selectedDialogueRow) window.ryuPremiumSelectedAssignedDialogueKey = '';
    }
    const auditionProfileName = String($('assignedAudioProfile')?.value ?? profileName).trim();
    if ($('testAssignedVoice')) $('testAssignedVoice').disabled =
      !selectedDialogueRow || !auditionProfileName || !characterProfileByName(auditionProfileName);
    if ($('editAssignedCharacter')) $('editAssignedCharacter').disabled = false;
    ensureAssignedAudioProfileControls();
  }
  function renderCharacterStudioLive() {
    const root = $('characters');
    if (!root) return;
    installCharacterStudioStyles();
    ensureCharacterSeriesField();
    const liveChapters = Array.isArray(chapters) ? chapters : [];
    const selectedNumber = Number(characterStudioSelectedChapter || window.ryuPremiumSelectedChapter || liveChapters[0]?.number || 0);
    if (!liveChapters.some(chapter => Number(chapter.number) === selectedNumber)) {
      characterStudioSelectedChapter = liveChapters[0] ? Number(liveChapters[0].number) : null;
    } else characterStudioSelectedChapter = selectedNumber;
    const chapter = liveChapters.find(item => Number(item.number) === Number(characterStudioSelectedChapter)) || null;
    const allRows = liveChapters.flatMap(item => characterDialogueRowsForChapter(item));
    const unassignedRows = allRows.filter(item => !item.assigned && !item.skipped);
    const voicesAssigned = characters.filter(item => String(item.voice_profile || '').trim()).length;
    const readyPercent = characters.length ? Math.round(100 * voicesAssigned / characters.length) : null;
    if ($('charFoundMetric')) $('charFoundMetric').textContent = String(characters.length);
    if ($('charAssignedMetric')) $('charAssignedMetric').textContent = String(voicesAssigned);
    if ($('charReviewMetric')) $('charReviewMetric').textContent = String(unassignedRows.length);
    if ($('charReadyMetric')) $('charReadyMetric').textContent = readyPercent == null ? '—' : readyPercent + '%';
    const manualList = $('manualChapterList');
    if (manualList) {
      const query = String($('manualChapterSearch')?.value || '').trim().toLowerCase();
      const filter = root.querySelector('[data-ch-filter].active')?.dataset.chFilter || 'all';
      const chapterRows = liveChapters.map(item => {
        const rows = characterDialogueRowsForChapter(item);
        const empty = !String(item.text || '').trim();
        const pending = rows.filter(row => !row.assigned && !row.skipped).length;
        return {item, rows, empty, pending};
      }).filter(row => (!query || ('chapter ' + row.item.number + ' ' + row.item.title).toLowerCase().includes(query)) &&
        (filter === 'all' || (filter === 'empty' ? row.empty : (!row.empty && row.pending > 0))));
      const sig = JSON.stringify(chapterRows.map(row => [row.item.number,row.item.title,row.item.word_count,row.empty,row.pending,row.rows.length]));
      if (manualList.dataset.liveSignature !== sig) {
        const top = manualList.scrollTop;
        manualList.innerHTML = chapterRows.map(row => {
          const active = Number(row.item.number) === Number(characterStudioSelectedChapter);
          const status = row.empty ? 'No narration text' : (row.pending ? row.pending + ' dialogue passage(s) need review' : 'No unassigned dialogue');
          const state = row.empty ? 'empty' : (row.pending ? 'review' : 'done');
          return '<button type="button" class="chapter-pick ' + state + (active ? ' active' : '') + '" data-chapter-number="' + Number(row.item.number) + '">' +
            '<b>' + esc('Chapter ' + row.item.number + ' · ' + String(row.item.title || 'Untitled chapter')) + '</b><small>' +
            esc(status) + '</small></button>';
        }).join('') || '<div class="ryu-character-empty"><b>No chapters found</b>Open a local project from Library to load real chapter text.</div>';
        manualList.dataset.liveSignature = sig;
        manualList.scrollTop = top;
      } else {
        manualList.querySelectorAll('[data-chapter-number]').forEach(button => button.classList.toggle('active', Number(button.dataset.chapterNumber) === Number(characterStudioSelectedChapter)));
      }
      const countBadge = manualList.closest('.char-chapters')?.querySelector('.char-panel-title .badge');
      if (countBadge) countBadge.textContent = String(liveChapters.length);
      if (!manualList.dataset.liveBound) {
        manualList.dataset.liveBound = '1';
        manualList.addEventListener('click', event => {
          const button = event.target.closest('[data-chapter-number]');
          if (!button) return;
          characterStudioSelectedChapter = Number(button.dataset.chapterNumber);
          window.ryuPremiumSelectedChapter = characterStudioSelectedChapter;
          renderCharacterStudioLive();
          renderDialogueReview();
        });
      }
    }
    const manualTitle = $('manualChapterTitle'), story = $('manualStory');
    if (manualTitle) manualTitle.textContent = chapter ? 'Chapter ' + chapter.number + ' · ' + String(chapter.title || 'Untitled chapter') : 'No project selected';
    if (story) {
      const source = String(chapter?.text || '');
      const rows = characterDialogueRowsForChapter(chapter);
      const narratorRows = characterNarrationSegmentsForChapter(chapter);
      const visualRows = [
        ...rows.map(row => ({...row, visualKind:'dialogue'})),
        ...narratorRows.map(row => ({...row, visualKind:'narration', start:Number(row.start), end:Number(row.end)}))
      ].sort((a,b) => a.start - b.start || b.end - a.end);
      const renderSig = JSON.stringify([chapter?.number, chapter?.title, source,
        rows.map(row => [row.start,row.end,row.speakers,row.assignmentSource,row.skipped,row.suggestions]),
        narratorRows.map(row => [row.start,row.end,row.text,row.source])]);
      if (story.dataset.liveSignature !== renderSig) {
        let html = '', cursor = 0;
        for (const row of visualRows) {
          if (row.start < cursor) continue;
          html += esc(source.slice(cursor, row.start)).replace(/\n/g, '<br>');
          if (row.visualKind === 'narration') {
            html += '<span class="ryu-narrator-passage" title="Narrator · Automatically classified non-dialogue text">' +
              '<span class="ryu-narrator-chip">Narrator · Auto</span>' + esc(row.text) + '</span>';
            cursor = row.end;
            continue;
          }
          const assignedName = row.speakers.join(' + ');
          const sourceClass = row.assignmentSource === 'ai' ? ' is-assigned-ai' : ' is-assigned-manual';
          const classes = 'ryu-live-passage' + (row.assigned ? ' is-assigned' + sourceClass : '');
          const title = row.assigned ? 'Assigned to ' + assignedName : 'Needs speaker review · Click to assign';
          html += '<button type="button" class="' + classes + '" data-manual-dialogue="1" data-dialogue-id="' + esc(row.id) +
            '" data-chapter-number="' + Number(chapter.number) + '" data-start="' + row.start + '" data-end="' + row.end +
            '" title="' + esc(title) + '">' + (row.assigned ? '<span class="ryu-speaker-chip">' + esc(assignedName) + '</span>' :
              '<span class="ryu-speaker-chip ryu-needs-speaker-chip">Needs speaker</span>') +
            esc(row.text) + '</button>';
          cursor = row.end;
        }
        html += esc(source.slice(cursor)).replace(/\n/g, '<br>');
        story.innerHTML = source ? html : '<div class="ryu-character-empty"><b>No chapter text</b>Choose another chapter or save its narration text in Chapter Studio.</div>';
        story.classList.add('ryu-live-story');
        story.dataset.liveSignature = renderSig;
      }
      if (!story.dataset.liveBound) {
        story.dataset.liveBound = '1';
        story.addEventListener('click', event => {
          const passage = event.target.closest('[data-manual-dialogue]');
          if (!passage) return;
          event.preventDefault();
          const selectedChapter = chapters.find(item => Number(item.number) === Number(passage.dataset.chapterNumber));
          if (!selectedChapter) return;
          openCharacterAssignmentPopover({
            id:passage.dataset.dialogueId, chapter_number:Number(selectedChapter.number), chapter_title:selectedChapter.title,
            start:Number(passage.dataset.start), end:Number(passage.dataset.end),
            text:String(selectedChapter.text || '').slice(Number(passage.dataset.start),Number(passage.dataset.end))
          }, event.clientX, event.clientY);
        }, true);
        story.addEventListener('mouseup', event => {
          const currentStory = $('manualStory');
          const selection = window.getSelection();
          if (!selection || selection.isCollapsed || !currentStory?.contains(selection.anchorNode)) return;
          if (selection.anchorNode?.parentElement?.closest?.('[data-manual-dialogue]')) return;
          const selectedText = selection.toString().trim();
          if (!selectedText || !chapter) return;
          const at = String(chapter.text || '').indexOf(selectedText);
          if (at < 0 || String(chapter.text || '').indexOf(selectedText, at + 1) >= 0) return;
          openCharacterAssignmentPopover({
            id:'selection-' + chapter.number + '-' + at, chapter_number:Number(chapter.number),
            chapter_title:chapter.title, start:at, end:at + selectedText.length, text:String(chapter.text || '').slice(at, at + selectedText.length)
          }, event.clientX, event.clientY);
        }, true);
      }
    }
    const castList = $('assignedCharacterList');
    const assignedCastRows = characters.map(item => {
      const name = characterCanonical(item);
      const series = characterSeries(item);
      const assignments = characterVoiceAssignments(name, series);
      const profileName = String(item.voice_profile || '').trim();
      return {item, name, series, assignments, profileName,
        key:characterAssignmentKey(name, series)};
    }).filter(row => row.assignments.dialogueLines > 0 || Boolean(row.profileName));
    if (castList) {
      const assignedQuery = String($('assignedSearch')?.value || '').trim().toLowerCase();
      const visibleCharacters = assignedCastRows.filter(row =>
        [row.name,row.series,row.profileName,row.item.role,...characterAliases(row.item)]
          .join(' ').toLowerCase().includes(assignedQuery));
      const selectedKey = characterAssignmentKey(
        window.ryuPremiumSelectedCharacter, window.ryuPremiumSelectedCharacterSeries
      );
      const signature = JSON.stringify([assignedQuery,selectedKey,visibleCharacters.map(row => [
        row.key,row.profileName,row.item.aliases,row.assignments.dialogueLines,
        row.assignments.chapters,row.assignments.aiAssignedPercent
      ])]);
      if (castList.dataset.liveSignature !== signature) {
        const top = castList.scrollTop;
        castList.innerHTML = visibleCharacters.map(row =>
          '<button type="button" class="assigned-character' + (row.key === selectedKey ? ' active' : '') +
          '" data-character-name="' + esc(row.name) + '" data-character-series="' + esc(row.series) + '">' +
          '<span><b>' + esc(row.name) + '</b><small>' + esc(row.series) + ' · ' +
          row.assignments.dialogueLines + ' assigned line(s) · ' +
          esc(row.profileName || 'Unassigned voice') + '</small></span></button>'
        ).join('') || (assignedCastRows.length
          ? '<div class="ryu-character-empty">No assigned characters match this search.</div>'
          : '<div class="ryu-character-empty"><b>No Assigned Cast yet</b>Save a dialogue assignment or an explicit character voice profile to build this list.</div>');
        castList.dataset.liveSignature = signature;
        castList.scrollTop = top;
      }
      if (!castList.dataset.liveBound) {
        castList.dataset.liveBound = '1';
        castList.addEventListener('click', event => {
          const button = event.target.closest('[data-character-name][data-character-series]');
          if (!button) return;
          window.ryuPremiumSelectedCharacter = button.dataset.characterName;
          window.ryuPremiumSelectedCharacterSeries = button.dataset.characterSeries;
          window.ryuPremiumSelectedAssignedDialogueKey = '';
          const key = characterAssignmentKey(button.dataset.characterName, button.dataset.characterSeries);
          castList.querySelectorAll('[data-character-name][data-character-series]').forEach(row =>
            row.classList.toggle('active', characterAssignmentKey(row.dataset.characterName,row.dataset.characterSeries) === key));
          renderCharacterInspector();
        });
      }
    }
    const assignedBadge = $('assignedCountBadge');
    if (assignedBadge) assignedBadge.textContent = assignedCastRows.length +
      (assignedCastRows.length === 1 ? ' character' : ' characters');
    renderCharacterInspector();
    ensureManualAssignmentFields();
  }
  function ensureManualAssignmentFields() {
    const popover = $('characterAssignPopover');
    if (!popover || characterManualFormBound) return;
    const quick = $('quickCharacterList');
    if (!quick) return;
    const form = document.createElement('div');
    form.id = 'ryuManualCharacterCreate';
    form.className = 'ryu-manual-create';
    form.hidden = true;
    form.innerHTML =
      '<label>Series<select id="ryuManualSeries"><option value="">Choose a series</option><option value="__new_series__">＋ Create a new series…</option></select></label>' +
      '<label id="ryuManualNewSeriesLabel" hidden>New series name<input id="ryuManualNewSeries" maxlength="300" placeholder="Series or novel title"/></label>' +
      '<label>Character name<input id="ryuManualNewName" maxlength="160" placeholder="Canonical character name"/></label>' +
      '<label>Aliases<input id="ryuManualNewAliases" maxlength="1000" placeholder="Nickname, short name, other aliases"/></label>' +
      '<label>Audio profile<select id="ryuManualNewProfile"><option value="">Unassigned</option></select></label>' +
      '<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap"><button type="button" class="btn small secondary" id="cancelManualCharacterCreate">Cancel</button><button type="button" class="btn small" id="saveManualCharacterCreate">Save & Assign</button></div>';
    quick.insertAdjacentElement('afterend', form);
    const series = $('ryuManualSeries');
    series.addEventListener('change', () => {
      characterStudioSelectedSeries = series.value === '__new_series__' ? '' : series.value;
      const isNew = series.value === '__new_series__';
      if ($('ryuManualNewSeriesLabel')) $('ryuManualNewSeriesLabel').hidden = !isNew;
      if (isNew) $('ryuManualNewSeries')?.focus();
    });
    $('ryuManualNewSeries')?.addEventListener('input', () => {
      characterStudioSelectedSeries = String($('ryuManualNewSeries')?.value || '').trim();
    });
    $('cancelManualCharacterCreate')?.addEventListener('click', () => {
      form.hidden = true; quick.hidden = false;
    });
    $('saveManualCharacterCreate')?.addEventListener('click', act(saveManualCharacterAndAssign));
    characterManualFormBound = true;
  }
  function populateCharacterCreateFields() {
    ensureManualAssignmentFields();
    const seriesSelect = $('ryuManualSeries'), profileSelect = $('ryuManualNewProfile');
    if (seriesSelect) {
      const activeSeries = activeCharacterProjectSeries();
      const names = [...new Set([...libraryCharacters.map(librarySeriesName),activeSeries,characterStudioSelectedSeries].filter(Boolean))].sort((a,b) => a.localeCompare(b));
      const previous = characterStudioSelectedSeries || activeSeries;
      seriesSelect.innerHTML = '<option value="">Choose a series</option>' +
        names.map(name => '<option value="' + esc(name) + '">' + esc(name) + '</option>').join('') +
        '<option value="__new_series__">＋ Create a new series…</option>';
      seriesSelect.value = names.includes(previous) ? previous : (activeSeries && names.includes(activeSeries) ? activeSeries : '');
      characterStudioSelectedSeries = seriesSelect.value || '';
      if ($('ryuManualNewSeriesLabel')) $('ryuManualNewSeriesLabel').hidden = seriesSelect.value !== '__new_series__';
    }
    if (profileSelect) {
      const saved = characterSavedProfiles();
      const options = [['','Unassigned'], ...saved.map(item => [item.name, item.name + ' · ' + item.provider])];
      profileSelect.innerHTML = options.map(([value,label]) => '<option value="' + esc(value) + '">' + esc(label) + '</option>').join('');
    }
    const form = $('ryuManualCharacterCreate'), quick = $('quickCharacterList');
    if (form) form.hidden = false;
    if (quick) quick.hidden = true;
  }
  function renderManualCharacterChoices() {
    const list = $('quickCharacterList');
    if (!list) return;
    const query = String($('assignCharacterSearch')?.value || '').trim().toLowerCase();
    const merged = [];
    const seen = new Set();
    for (const item of characters) {
      const name = characterCanonical(item), series = characterSeries(item);
      const key = name.toLowerCase() + '::' + series.toLowerCase();
      if (!name || seen.has(key)) continue;
      seen.add(key);
      merged.push({name, series, aliases:characterAliases(item), voice_profile:String(item.voice_profile || ''), project:true, item});
    }
    for (const item of libraryCharacters) {
      const name = characterCanonical(item), series = characterSeries(item);
      const key = name.toLowerCase() + '::' + series.toLowerCase();
      if (!name || seen.has(key)) continue;
      seen.add(key);
      merged.push({name, series, aliases:characterAliases(item), voice_profile:String(item.voice_profile || item.voice || ''), project:false, item});
    }
    const visible = merged.filter(item => [item.name,item.series,item.voice_profile,...item.aliases].join(' ').toLowerCase().includes(query));
    list.innerHTML = visible.map(item => '<button type="button" class="quick-character" data-live-character="' + esc(item.name) + '" data-live-series="' + esc(item.series) + '" data-live-profile="' + esc(item.voice_profile) + '" data-live-project="' + (item.project ? 'true' : 'false') + '"><b>' + esc(item.name) + '</b><small>' + esc(item.series) + ' · ' + esc(item.voice_profile || 'Unassigned audio profile') + (item.project ? ' · This project' : ' · Character Library') + '</small></button>').join('') ||
      '<div class="ryu-character-empty"><b>No matching characters</b>Create a new character and assign a series.</div>';
  }
  function positionCharacterAssignmentPopover(popover, x, y) {
    if (!popover) return;
    const viewportWidth = Math.max(320, Number(window.innerWidth || 1024));
    const viewportHeight = Math.max(240, Number(window.innerHeight || 768));
    const maxHeight = Math.max(180, Math.min(680, viewportHeight - 24));
    const width = Math.max(280, Math.min(390, viewportWidth - 24));
    popover.style.position = 'fixed';
    popover.style.boxSizing = 'border-box';
    popover.style.width = width + 'px';
    popover.style.maxHeight = maxHeight + 'px';
    popover.style.overflowY = 'auto';
    const measuredHeight = Math.min(Math.max(160, popover.scrollHeight || popover.offsetHeight || 420), maxHeight);
    const left = Math.max(12, Math.min(viewportWidth - width - 12, Number(x || 0) + 10));
    const top = Math.max(12, Math.min(viewportHeight - measuredHeight - 12, Number(y || 0) + 10));
    popover.style.left = left + 'px';
    popover.style.top = top + 'px';
  }

  async function openCharacterAssignmentPopover(passage, x, y) {
    if (!passage || !passage.text || !Number.isInteger(Number(passage.chapter_number))) {
      throw new Error('Select a valid source passage from the active project first.');
    }
    window.ryuPremiumPendingDialogueText = String(passage.text);
    window.ryuPremiumPendingDialogueChapter = Number(passage.chapter_number);
    window.ryuPremiumPendingDialogueStart = Number(passage.start);
    window.ryuPremiumPendingDialogueEnd = Number(passage.end);
    window.ryuPremiumPendingDialogueId = String(passage.id || '');
    if ($('selectedTextPreview')) $('selectedTextPreview').textContent = String(passage.text);
    $('characterAssignPopover')?.classList.add('show');
    const popover = $('characterAssignPopover');
    positionCharacterAssignmentPopover(popover, x, y);
    $('selectionPlus')?.classList.remove('show');
    if ($('assignCharacterSearch')) $('assignCharacterSearch').value = '';
    $('ryuManualCharacterCreate') && ($('ryuManualCharacterCreate').hidden = true);
    $('quickCharacterList') && ($('quickCharacterList').hidden = false);
    await refreshCharacterLibrary().catch(error => console.warn('[Ryu assignment library]', error));
    renderManualCharacterChoices();
    populateCharacterCreateFields();
    const form = $('ryuManualCharacterCreate');
    if (form) form.hidden = true;
    if ($('quickCharacterList')) $('quickCharacterList').hidden = false;
    // The list grows asynchronously after the popup opens; recalculate using its
    // final live content so it remains on-screen at common display sizes.
    positionCharacterAssignmentPopover(popover, x, y);
  }
  function closeCharacterAssignmentPopover() {
    $('characterAssignPopover')?.classList.remove('show');
    $('ryuManualCharacterCreate') && ($('ryuManualCharacterCreate').hidden = true);
    $('quickCharacterList') && ($('quickCharacterList').hidden = false);
  }
  async function ensureCharacterInActiveProject(name, preferredSeries = '', preferredProfile = '') {
    const canonical = String(name || '').trim();
    if (!canonical) throw new Error('Choose a character before assigning dialogue.');
    const requestedSeries = String(preferredSeries || '').trim();
    const matchingProjectRows = characters.filter(item =>
      characterCanonical(item).toLowerCase() === canonical.toLowerCase() ||
      characterAliases(item).some(alias => alias.toLowerCase() === canonical.toLowerCase())
    );
    if (!requestedSeries && matchingProjectRows.length > 1) {
      throw new Error('This character name exists in multiple series. Choose the intended series before assigning dialogue.');
    }
    const current = characterRowForName(canonical, requestedSeries);
    if (current) return current;
    if (!libraryCharacters.length) await refreshCharacterLibrary();
    const matchesCharacter = item => characterCanonical(item).toLowerCase() === canonical.toLowerCase() ||
      characterAliases(item).some(alias => alias.toLowerCase() === canonical.toLowerCase());
    const libraryMatches = libraryCharacters.filter(matchesCharacter);
    let saved = null;
    if (requestedSeries) {
      const scoped = libraryMatches.filter(item =>
        librarySeriesName(item).toLowerCase() === requestedSeries.toLowerCase()
      );
      if (scoped.length > 1) throw new Error('More than one Character Library entry has this name in the selected series. Resolve the duplicate first.');
      saved = scoped[0] || null;
    } else {
      const activeSeries = activeCharacterProjectSeries().toLowerCase();
      const activeMatches = libraryMatches.filter(item => librarySeriesName(item).toLowerCase() === activeSeries);
      if (activeMatches.length === 1) saved = activeMatches[0];
      else if (libraryMatches.length === 1) saved = libraryMatches[0];
      else if (libraryMatches.length > 1) {
        throw new Error('This character name exists in multiple Character Library series. Choose a series before assigning dialogue.');
      }
    }
    const series = String(requestedSeries || librarySeriesName(saved || {}) || activeCharacterProjectSeries() || '').trim();
    if (!series) throw new Error('Choose a series before creating or assigning this character.');
    const profileName = String(preferredProfile || saved?.voice_profile || saved?.voice || '').trim();
    const usableProfile = profileName && characterProfileByName(profileName) ? profileName : '';
    const result = await call('character.create', {
      name:characterCanonical(saved || {name:canonical}),
      series,
      aliases:characterAliases(saved || {}),
      short:String(saved?.short || canonical.split(/\\s+/)[0]),
      notes:String(saved?.notes || ''),
      dialogue_sample:String(saved?.dialogue_sample || ''),
      voice_profile:usableProfile
    });
    await refreshCharacters();
    const createdSeries = String(result?.series || result?.character?.series || series).trim();
    const created = characterRowForName(result?.character?.name || canonical, createdSeries);
    if (!created) throw new Error('The character was created but could not be loaded into the active project cast for the selected series.');
    return created;
  }
  async function assignPassageToCharacter(name, preferredSeries = '', preferredProfile = '', assignmentSource = 'manual', assignmentConfidence = 1.0) {
    const dialogueText = String(window.ryuPremiumPendingDialogueText || '');
    const chapterNumber = Number(window.ryuPremiumPendingDialogueChapter);
    const start = Number(window.ryuPremiumPendingDialogueStart), end = Number(window.ryuPremiumPendingDialogueEnd);
    if (!dialogueText || !Number.isInteger(chapterNumber) || !Number.isInteger(start) || !Number.isInteger(end) || end <= start) {
      throw new Error('The selected passage is stale. Select the source text again.');
    }
    let character = await ensureCharacterInActiveProject(name, preferredSeries, preferredProfile);
    const selectedProfile = String(preferredProfile || '').trim();
    if (selectedProfile && selectedProfile !== String(character.voice_profile || '')) {
      if (!characterProfileByName(selectedProfile)) throw new Error('Choose a saved voice profile.');
      await call('character.assign', {name:characterCanonical(character),series:characterSeries(character),profile_name:selectedProfile});
      await refreshCharacters();
      character = characterRowForName(characterCanonical(character), characterSeries(character)) || character;
    }
    const result = await call('chapter.dialogue.assign', {
      dialogue_text:dialogueText, speakers:[characterCanonical(character)], series:characterSeries(character),
      chapter_number:chapterNumber, start, end, mode:'single', source:assignmentSource, confidence:assignmentConfidence
    });
    closeCharacterAssignmentPopover();
    await refreshChapters();
    await refreshCharacters();
    await refreshCharacterLibrary();
    message('Saved assignment: ' + characterCanonical(character) + ' · ' + characterSeries(character) + '.');
    return result;
  }
  async function saveManualCharacterAndAssign() {
    const name = String($('ryuManualNewName')?.value || '').trim();
    if (!name) throw new Error('Enter the character name before saving.');
    const seriesChoice = String($('ryuManualSeries')?.value || '');
    const series = seriesChoice === '__new_series__'
      ? String($('ryuManualNewSeries')?.value || '').trim()
      : seriesChoice.trim();
    if (!series) throw new Error('Choose an existing series or enter a new series name.');
    const aliases = String($('ryuManualNewAliases')?.value || '').split(/[,\\n]/).map(value => value.trim()).filter(Boolean);
    const profile = String($('ryuManualNewProfile')?.value || '').trim();
    if (profile && !characterProfileByName(profile)) throw new Error('Choose one of the saved audio profiles.');
    const result = await call('character.create', {
      name, series, aliases, short:name.split(/\\s+/)[0], voice_profile:profile,
      dialogue_sample:String(window.ryuPremiumPendingDialogueText || '')
    });
    await refreshCharacters();
    const current = characterRowForName(result?.character?.name || name, series);
    if (!current) throw new Error('Character was not returned by the active project cast.');
    await call('chapter.dialogue.assign', {
      dialogue_text:String(window.ryuPremiumPendingDialogueText || ''),
      speakers:[characterCanonical(current)], series:characterSeries(current),
      chapter_number:Number(window.ryuPremiumPendingDialogueChapter),
      start:Number(window.ryuPremiumPendingDialogueStart), end:Number(window.ryuPremiumPendingDialogueEnd), mode:'single'
    });
    closeCharacterAssignmentPopover();
    await refreshChapters(); await refreshCharacters(); await refreshCharacterLibrary();
    message('Created ' + name + ' in ' + series + ' and saved its selected passage assignment.');
  }
  async function runCharacterAnalysis() {
    const data = await call('character.analyze');
    await monitorJob(data.job_id, async () => {
      await refreshChapters();
      await refreshCharacters();
      await refreshCharacterLibrary();
      await refreshCharacterDialogueSuggestions();
      renderDialogueReview();
      renderCharacterStudioLive();
      setCharacterStudioMode('ai');
    });
  }
  function setCharacterStudioMode(mode) {
    const allowed = new Set(['manual','assigned','ai']);
    const chosen = allowed.has(mode) ? mode : 'manual';
    document.querySelectorAll('#characters .char-mode').forEach(button => {
      const active = button.dataset.charMode === chosen;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    document.querySelectorAll('#characters .char-view').forEach(view => view.classList.toggle('active', view.dataset.charView === chosen));
    if (chosen === 'ai') renderDialogueReview();
    if (chosen === 'assigned') renderCharacterInspector();
  }
  async function acceptHighConfidenceDialogues() {
    await refreshCharacterDialogueSuggestions();
    let applied = 0, skipped = 0;
    const pending = characterDialogueSuggestions.filter(row => !row.assigned && !row.skipped &&
      Number(row.suggestions?.[0]?.confidence ?? row.confidence ?? 0) >= 0.9);
    for (const row of pending) {
      try {
        const candidate = row.suggestions?.[0];
        if (!candidate?.name) { skipped++; continue; }
        const topConfidence = Number(candidate.confidence ?? row.confidence ?? 0);
        const topSeries = String(candidate.series || '').trim().toLowerCase();
        const ambiguousSeriesMatch = (row.suggestions || []).slice(1).some(other => {
          const otherConfidence = Number(other?.confidence || 0);
          const sameCharacterName = String(other?.name || '').trim().toLowerCase() === String(candidate.name).trim().toLowerCase();
          const otherSeries = String(other?.series || '').trim().toLowerCase();
          return sameCharacterName && topSeries && otherSeries && otherSeries !== topSeries &&
            Math.abs(otherConfidence - topConfidence) < 0.05;
        });
        // A high numeric score is not enough when an identical name exists in two
        // series. Leave that row for the person to select the intended series.
        if (ambiguousSeriesMatch) { skipped++; continue; }
        const source = chapters.find(chapter => Number(chapter.number) === Number(row.chapter_number));
        if (!source || String(source.text || '').slice(Number(row.start), Number(row.end)) !== String(row.source_text || row.text || '')) {
          skipped++; continue;
        }
        window.ryuPremiumPendingDialogueText = String(row.source_text || row.text);
        window.ryuPremiumPendingDialogueChapter = Number(row.chapter_number);
        window.ryuPremiumPendingDialogueStart = Number(row.start);
        window.ryuPremiumPendingDialogueEnd = Number(row.end);
        const candidateSeries = String(candidate.series || activeCharacterProjectSeries()).trim();
        const existingCast = characterRowForName(candidate.name, candidateSeries);
        if (existingCast && candidateSeries &&
            characterSeries(existingCast).toLowerCase() !== candidateSeries.toLowerCase()) {
          throw new Error('The AI suggestion "' + candidate.name + '" belongs to series "' + candidateSeries +
            '", but the project character is in "' + characterSeries(existingCast) + '". Review the series before accepting this suggestion.');
        }
        const preferredSeries = candidateSeries || (existingCast ? characterSeries(existingCast) :
          activeCharacterProjectSeries());
        const libraryCandidate = libraryCharacters.find(item =>
          (characterCanonical(item).toLowerCase() === String(candidate.name).toLowerCase() ||
            characterAliases(item).some(alias => alias.toLowerCase() === String(candidate.name).toLowerCase())) &&
          (!preferredSeries || librarySeriesName(item).toLowerCase() === preferredSeries.toLowerCase()));
        const castCandidate = await ensureCharacterInActiveProject(
          candidate.name, preferredSeries || librarySeriesName(libraryCandidate || {}));
        await call('chapter.dialogue.assign', {
          dialogue_text:String(row.source_text || row.text), speakers:[characterCanonical(castCandidate)],
          series:characterSeries(castCandidate),
          chapter_number:Number(row.chapter_number), start:Number(row.start), end:Number(row.end), mode:'single',
          source:'ai', confidence:topConfidence
        });
        applied++;
      } catch (error) {
        skipped++;
        console.warn('[Ryu high-confidence assignment]', error);
      }
    }
    await refreshChapters(); await refreshCharacters(); await refreshCharacterLibrary(); await refreshCharacterDialogueSuggestions();
    renderDialogueReview(); renderCharacterStudioLive();
    message('Applied ' + applied + ' high-confidence source-backed assignment(s).' + (skipped ? ' ' + skipped + ' item(s) were left for manual review.' : ''));
  }
  async function skipCurrentDialogueSuggestion() {
    const id = String(window.ryuPremiumSelectedDialogueId || '');
    if (!id) throw new Error('Select an AI review item before skipping it.');
    await call('character.dialogue.suggestion.skip', {id});
    await refreshCharacterDialogueSuggestions();
    renderDialogueReview();
    renderCharacterStudioLive();
    message('Skipped this analysis suggestion. The source text and character assignments were not changed.');
  }

  function getEditCharacterSeriesValue() {
    const selected = String($('editCharacterSeries')?.value || '').trim();
    if (selected === '__new_series__') return String($('editCharacterNewSeries')?.value || '').trim();
    return selected;
  }
  function populateEditCharacterSeriesOptions(preferred = '') {
    const select = $('editCharacterSeries');
    if (!select) return;
    const current = String(preferred || select.value || '').trim();
    const names = [...new Set([
      ...libraryCharacters.map(librarySeriesName),
      ...characters.map(characterSeries),
      activeCharacterProjectSeries(),
      characterStudioSelectedSeries,
      current
    ].map(value => String(value || '').trim()).filter(value =>
      value && !['All series','Unassigned series','Global character library','__new_series__'].includes(value)
    ))].sort((a,b) => a.localeCompare(b));
    select.innerHTML = '<option value="">Choose a series</option>' +
      names.map(value => '<option value="' + esc(value) + '">' + esc(value) + '</option>').join('') +
      '<option value="__new_series__">＋ Create a new series…</option>';
    select.value = current === '__new_series__' ? current : (names.includes(current) ? current : '');
    const newLabel = $('editCharacterNewSeriesLabel');
    if (newLabel) newLabel.hidden = select.value !== '__new_series__';
    const newInput = $('editCharacterNewSeries');
    if (newInput && select.value !== '__new_series__') newInput.value = '';
  }
  function ensureCharacterSeriesField() {
    const modal = $('characterEditorModal');
    if (!modal) return;
    const legacyScope = $('editCharacterScope');
    const legacyGroup = legacyScope?.closest('.form-group, .form-row, .field') || legacyScope?.parentElement;
    if (legacyGroup) legacyGroup.style.display = 'none';
    let select = $('editCharacterSeries');
    if (!select || select.tagName !== 'SELECT') {
      const wrap = document.createElement('div');
      wrap.className = 'form-group';
      wrap.id = 'editCharacterSeriesGroup';
      wrap.style.cssText = 'display:flex;flex-direction:column;gap:7px;margin-top:12px;';
      const label = document.createElement('label');
      label.htmlFor = 'editCharacterSeries';
      label.textContent = 'Series';
      label.style.cssText = 'font-size:13px;font-weight:700;color:#e6e9f0;';
      select = document.createElement('select');
      select.id = 'editCharacterSeries';
      select.style.cssText = 'width:100%;box-sizing:border-box;padding:10px 12px;border-radius:10px;border:1px solid #343b49;background:#0d1119;color:#f4f5f8;font:inherit;';
      const newLabel = document.createElement('label');
      newLabel.id = 'editCharacterNewSeriesLabel';
      newLabel.htmlFor = 'editCharacterNewSeries';
      newLabel.textContent = 'New series name';
      newLabel.style.cssText = label.style.cssText;
      const newInput = document.createElement('input');
      newInput.id = 'editCharacterNewSeries';
      newInput.type = 'text';
      newInput.maxLength = 300;
      newInput.placeholder = 'Series or novel title';
      newInput.autocomplete = 'off';
      newInput.style.cssText = 'width:100%;box-sizing:border-box;padding:10px 12px;border-radius:10px;border:1px solid #343b49;background:#0d1119;color:#f4f5f8;font:inherit;';
      newLabel.appendChild(newInput);
      newLabel.hidden = true;
      wrap.append(label, select, newLabel);
      const name = $('editCharacterName');
      const anchor = name?.closest('.form-group, .form-row, .field') || name?.parentElement;
      if (anchor?.parentElement) anchor.parentElement.insertBefore(wrap, anchor.nextSibling);
      else (modal.querySelector('.modal-body') || modal).appendChild(wrap);
    } else {
      const newLabel = $('editCharacterNewSeriesLabel');
      if (newLabel) newLabel.hidden = select.value !== '__new_series__';
    }
    if (!select.dataset.seriesBound) {
      select.dataset.seriesBound = 'true';
      select.addEventListener('change', () => {
        const createNew = select.value === '__new_series__';
        if ($('editCharacterNewSeriesLabel')) $('editCharacterNewSeriesLabel').hidden = !createNew;
        if (createNew) $('editCharacterNewSeries')?.focus();
      });
      $('editCharacterNewSeries')?.addEventListener('input', () => {
        if ($('editCharacterSeries')?.value === '__new_series__') characterStudioSelectedSeries = String($('editCharacterNewSeries')?.value || '').trim();
      });
    }
    populateEditCharacterSeriesOptions(select.value);
  }
  function ensureCharacterDialogueSampleField() {
    const modal = $('characterEditorModal');
    if (!modal) return;
    let sample = $('editCharacterDialogueSample');
    if (!sample) {
      const wrap = document.createElement('div');
      wrap.className = 'form-group';
      wrap.style.cssText = 'display:flex;flex-direction:column;gap:7px;margin-top:12px;';
      const label = document.createElement('label');
      label.htmlFor = 'editCharacterDialogueSample';
      label.textContent = 'Dialogue sample (editable)';
      label.style.cssText = 'font-size:13px;font-weight:700;color:#e6e9f0;';
      sample = document.createElement('textarea');
      sample.id = 'editCharacterDialogueSample';
      sample.rows = 4;
      sample.maxLength = 4000;
      sample.placeholder = 'Save a representative line so this character stays recognizable across volumes.';
      sample.style.cssText = 'width:100%;box-sizing:border-box;resize:vertical;min-height:92px;padding:10px 12px;border-radius:10px;border:1px solid #343b49;background:#0d1119;color:#f4f5f8;font:inherit;';
      wrap.append(label, sample);
      const notes = $('editCharacterNotes');
      const anchor = notes?.closest('.form-group, .form-row, .field') || notes?.parentElement;
      if (anchor?.parentElement) anchor.parentElement.insertBefore(wrap, anchor.nextSibling);
      else (modal.querySelector('.modal-body') || modal).appendChild(wrap);
    }
    const voice = $('editCharacterVoice');
    if (voice) {
      voice.title = 'Choose a saved Voice Studio profile for this character, or select Unassigned.';
      voice.disabled = voice.options.length <= 1;
    }
  }
  function ensureCharacterRecoveryButton() {
    if ($('openCharacterRecoveryBin')) return;
    const importButton = $('importCharacterLibrary');
    const addButton = $('addLibraryCharacter');
    const parent = importButton?.parentElement || addButton?.parentElement;
    if (!parent) return;
    const button = document.createElement('button');
    button.id = 'openCharacterRecoveryBin';
    button.type = 'button';
    button.className = 'btn small secondary';
    button.textContent = 'Recovery Bin';
    button.title = 'Restore characters previously removed from the reusable library';
    button.addEventListener('click', () => openCharacterRecoveryBin().catch(err => message(err?.message || String(err), true)));
    parent.appendChild(button);
  }
  function ensureCharacterRecoveryModal() {
    let modal = $('characterRecoveryModal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'characterRecoveryModal';
    modal.style.cssText = 'display:none;position:fixed;inset:0;z-index:100000;background:rgba(4,7,12,.82);backdrop-filter:blur(7px);align-items:center;justify-content:center;padding:22px;box-sizing:border-box;';
    modal.innerHTML = '<div role="dialog" aria-modal="true" aria-labelledby="characterRecoveryTitle" style="width:min(720px,96vw);max-height:84vh;overflow:auto;background:#10141d;border:1px solid #343b49;border-radius:16px;padding:22px;box-shadow:0 24px 80px rgba(0,0,0,.5);color:#f4f5f8"><div style="display:flex;justify-content:space-between;align-items:center;gap:12px"><div><h2 id="characterRecoveryTitle" style="margin:0">Character Recovery Bin</h2><p class="muted" style="margin:6px 0 0">Deleted reusable characters remain here until restored.</p></div><button type="button" class="btn small secondary" data-close-character-recovery>Close</button></div><div id="characterRecoveryItems" style="display:grid;gap:10px;margin-top:18px"></div></div>';
    modal.addEventListener('click', async event => {
      if (event.target === modal || event.target.closest('[data-close-character-recovery]')) {
        modal.style.display = 'none';
        return;
      }
      const restore = event.target.closest('[data-restore-character]');
      if (!restore) return;
      restore.disabled = true;
      try {
        const record = libraryDeletedCharacters.find(item => String(item.id) === restore.dataset.restoreCharacter);
        await call('character_library.restore', {id:restore.dataset.restoreCharacter});
        await refreshCharacterLibrary();
        message('Restored ' + (record?.name || 'character') + ' to the reusable Character Library.');
        await openCharacterRecoveryBin();
      } catch (error) {
        message(error?.message || String(error), true);
      } finally {
        restore.disabled = false;
      }
    });
    document.body.appendChild(modal);
    return modal;
  }
  let libraryDeletedCharacters = [];
  async function openCharacterRecoveryBin() {
    const modal = ensureCharacterRecoveryModal();
    libraryDeletedCharacters = await call('character_library.deleted.list');
    const list = $('characterRecoveryItems');
    if (list) list.innerHTML = libraryDeletedCharacters.map(c =>
      '<article class="card" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:14px"><div><b>' + esc(c.name) + '</b><div class="muted" style="margin-top:4px">' + esc(librarySeriesName(c) || 'Unassigned series') + ' · ' + esc(c.voice || 'Unassigned') + '</div><div class="muted" style="margin-top:4px">' + esc((c.aliases || []).join(', ') || 'No aliases') + '</div></div><button type="button" class="btn small secondary" data-restore-character="' + esc(c.id) + '">Restore</button></article>'
    ).join('') || '<div class="card" style="padding:18px"><b>The Recovery Bin is empty</b><p class="muted">Characters you delete from the reusable library will appear here.</p></div>';
    modal.style.display = 'flex';
  }
  function ensureCharacterLibraryViewControls() {
    const grid = $('characterLibraryGrid');
    if (!grid) return;
    let container = grid.parentElement;
    let cardsButton = null, compactButton = null;
    for (let depth = 0; container && depth < 7; depth++, container = container.parentElement) {
      const buttons = [...container.querySelectorAll('button')];
      cardsButton = buttons.find(button => button.textContent.trim().toLowerCase() === 'cards') || null;
      compactButton = buttons.find(button => button.textContent.trim().toLowerCase() === 'compact list') || null;
      if (cardsButton && compactButton) break;
    }
    if (!cardsButton || !compactButton) return;
    cardsButton.dataset.characterViewMode = 'cards';
    compactButton.dataset.characterViewMode = 'compact';
    for (const button of [cardsButton, compactButton]) {
      if (button.dataset.ryuViewBound === 'true') continue;
      button.dataset.ryuViewBound = 'true';
      button.addEventListener('click', () => {
        window.__ryuCharacterLibraryViewMode = button.dataset.characterViewMode || 'cards';
        refreshCharacterLibrary().catch(err => message(err?.message || String(err), true));
      });
    }
  }
  function applyCharacterLibraryViewMode(grid) {
    if (!grid) return;
    if (!document.getElementById('ryuCharacterLibraryViewStyles')) {
      const style = document.createElement('style');
      style.id = 'ryuCharacterLibraryViewStyles';
      style.textContent = '#characterLibraryGrid.character-library-compact{display:flex!important;flex-direction:column!important;gap:8px!important}#characterLibraryGrid.character-library-compact>.library-character-card{display:flex;flex-direction:row;align-items:center;justify-content:space-between;gap:16px;padding:14px 16px;flex-wrap:wrap}#characterLibraryGrid.character-library-compact .library-character-top{min-width:190px}#characterLibraryGrid.character-library-compact .alias-row{max-width:320px}#characterLibraryGrid.character-library-compact .library-character-meta{display:flex;gap:10px;flex-wrap:wrap}';
      document.head.appendChild(style);
    }
    const compact = window.__ryuCharacterLibraryViewMode === 'compact';
    grid.classList.toggle('character-library-compact', compact);
    grid.style.display = compact ? 'flex' : '';
    grid.style.flexDirection = compact ? 'column' : '';
    for (const button of document.querySelectorAll('button[data-character-view-mode]')) {
      const active = button.dataset.characterViewMode === (compact ? 'compact' : 'cards');
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    }
  }
  async function refreshCharacterLibrary() {
    libraryCharacters = await call('character_library.list');
    ensureCharacterDialogueSampleField();
    ensureCharacterRecoveryButton();
    ensureCharacterLibraryViewControls();
    const seriesFilter = $('characterSeriesFilter');
    const previousSeries = seriesFilter?.value || 'All series';
    const seriesNames = [...new Set(libraryCharacters.map(librarySeriesName).filter(Boolean))].sort((a,b) => a.localeCompare(b));
    if (seriesFilter) {
      seriesFilter.innerHTML = '';
      const all = document.createElement('option');
      all.value = 'All series'; all.textContent = 'All series'; seriesFilter.appendChild(all);
      for (const name of seriesNames) {
        const option = document.createElement('option');
        option.value = name; option.textContent = name; seriesFilter.appendChild(option);
      }
      seriesFilter.value = seriesNames.includes(previousSeries) ? previousSeries : 'All series';
    }
    const grid = $('characterLibraryGrid'), query = ($('characterLibrarySearch')?.value || '').trim().toLowerCase(), series = seriesFilter?.value || 'All series';
    const rows = libraryCharacters.filter(c => (!query || [c.name,c.short,c.voice,c.series,c.scope,...(c.aliases||[])].join(' ').toLowerCase().includes(query)) && (series === 'All series' || librarySeriesName(c) === series || c.scope === series));
    if (grid) grid.innerHTML = rows.map(c => {
      const sample = String(c.dialogue_sample || '').trim();
      const sampleText = sample ? '<p class="muted" style="margin:10px 0 0;line-height:1.5">“' + esc(sample.slice(0,220)) + (sample.length > 220 ? '…' : '') + '”</p>' : '';
      return '<article class="library-character-card" data-library-id="' + esc(c.id) + '"><div class="library-character-top"><span class="avatar">' + esc((c.short||c.name||'?').slice(0,1)) + '</span><div><h3>' + esc(c.name) + '</h3><p>' + esc(librarySeriesName(c)||'Unassigned series') + ' · ' + esc(c.voice||'Unassigned') + '</p></div></div><div class="alias-row">' + ((c.aliases||[]).map(x=>'<span class="alias-tag">' + esc(x) + '</span>').join('') || '<span class="alias-tag">No aliases</span>') + '</div>' + sampleText + '<div class="library-character-meta"><span>' + Number(c.lines||0) + ' assigned lines</span><span>' + Number(c.chapters||0) + ' chapters</span><span>' + Number(c.confidence??100) + '% confidence</span><span>' + esc(librarySeriesName(c)||'Unassigned series') + '</span></div><div class="library-character-actions" style="display:flex;gap:7px;flex-wrap:wrap"><button type="button" class="btn small secondary" data-test-library="' + esc(c.id) + '">▶ Test</button><button type="button" class="btn small secondary" data-edit-library="' + esc(c.id) + '">Edit</button><button type="button" class="btn small secondary" data-character-studio="' + esc(c.id) + '">Character Studio</button><button type="button" class="btn small ghost library-delete" data-delete-library="' + esc(c.id) + '">Delete</button></div></article>';
    }).join('') || '<div class="card"><b>No saved characters found</b><p class="muted">Import a cast or run Character Studio analysis on an imported book. Existing saved casts are indexed automatically; no sample characters are inserted.</p></div>';
    applyCharacterLibraryViewMode(grid);
    renderCharacterStudioLive();
    return libraryCharacters;
  }
  function openLibraryEditor(c) {
    libraryEditorActive = true; libraryEditorId = c?.id || null;
    if ($('characterEditorTitle')) $('characterEditorTitle').textContent = c ? 'Edit character' : 'Add new character';
    if ($('editCharacterName')) $('editCharacterName').value = c?.name || ''; if ($('editCharacterShort')) $('editCharacterShort').value = c?.short || '';
    if ($('editCharacterAliases')) $('editCharacterAliases').value = (c?.aliases||[]).join(', ');
    if ($('editCharacterVoice')) { $('editCharacterVoice').value = c?.voice || 'Unassigned'; $('editCharacterVoice').disabled = true; $('editCharacterVoice').title = 'Voice assignment is managed in Character Studio.'; }
    const activeSeries = $('characterSeriesFilter')?.value || 'All series';
    const defaultScope = activeSeries !== 'All series' ? 'Series · ' + activeSeries : 'Global character library';
    if ($('editCharacterScope')) $('editCharacterScope').value = c?.scope || defaultScope;
    if ($('editCharacterNotes')) $('editCharacterNotes').value = c?.notes || '';
    ensureCharacterSeriesField();
    const selectedSeries = c?.series || (activeSeries !== 'All series' ? activeSeries : activeCharacterProjectSeries());
    populateEditCharacterSeriesOptions(selectedSeries);
    if ($('editCharacterSeries')) $('editCharacterSeries').value = selectedSeries || '';
    if ($('editCharacterNewSeriesLabel')) $('editCharacterNewSeriesLabel').hidden = $('editCharacterSeries')?.value !== '__new_series__';
    ensureCharacterDialogueSampleField();
    if ($('editCharacterDialogueSample')) $('editCharacterDialogueSample').value = c?.dialogue_sample || '';
    if ($('deleteCharacter')) $('deleteCharacter').style.visibility = c ? 'visible' : 'hidden';
    $('characterEditorModal')?.classList.add('show');
    if ($('editCharacterVoice')) $('editCharacterVoice').disabled = true;
  }
  async function saveLibraryEditor() {
    const name = $('editCharacterName')?.value.trim() || ''; if (!name) throw new Error('Enter a character name before saving it to the Character Library.');
    const requestedSeries = getEditCharacterSeriesValue();
    if (!requestedSeries) throw new Error('Choose an existing series or create a new series before saving this character.');
    const scope = 'Series · ' + requestedSeries;
    const series = requestedSeries;
    const result = await call('character_library.save', {id:libraryEditorId||'',name,short:$('editCharacterShort')?.value||'',aliases:$('editCharacterAliases')?.value||'',scope,series,notes:$('editCharacterNotes')?.value||'',dialogue_sample:$('editCharacterDialogueSample')?.value||''});
    libraryEditorId = result.character.id; libraryEditorActive = false; $('characterEditorModal')?.classList.remove('show'); await refreshCharacterLibrary(); message('Character saved to the reusable local Character Library.');
  }
  function importCharacterLibraryFile() {
    const picker=document.createElement('input'); picker.type='file'; picker.accept='.json,application/json';
    picker.onchange=async()=>{const file=picker.files?.[0];if(!file)return;if(file.size>10*1024*1024){message('Character Library imports are limited to 10 MB.',true);return;}try{const data=JSON.parse(await file.text()), rows=Array.isArray(data)?data:data?.characters;if(!Array.isArray(rows))throw new Error('JSON must be an array or contain a characters array.');const result=await call('character_library.import',{characters:rows});await refreshCharacterLibrary();message('Imported '+result.imported+' character(s) into the local Character Library.');}catch(error){message(error?.message||String(error),true);}}; picker.click();
  }
  function pronunciationScopeKey(term) {
    return String(term.scope_type || 'current_book') + ':' + String(term.scope_id || '');
  }
  function pronunciationSelectionKey(term) {
    return pronunciationScopeKey(term) + '|' + String(term.written_form || term.word || '').normalize('NFC').toLocaleLowerCase();
  }
  function ensurePronunciationDictionaryTools(body) {
    if (!body || body.closest('.page')?.querySelector('[data-pron-dictionary-tools]')) return;
    const table = body.closest('table');
    if (!table?.parentNode) return;
    const tools = document.createElement('div');
    tools.dataset.pronDictionaryTools = '1';
    tools.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0 12px';
    tools.innerHTML =
      '<button type="button" class="btn small secondary" data-pron-import>Import dictionary JSON</button>' +
      '<button type="button" class="btn small ghost" data-pron-export>Export dictionary JSON</button>' +
      '<button type="button" class="btn small secondary" data-pron-test-matrix>Test selected entry across saved profiles</button>' +
      '<span class="muted" style="font-size:12px">Select exactly one enabled entry. Each saved profile is tested sequentially using the real pronunciation rule.</span>' +
      '<div data-pron-test-results style="width:100%;display:grid;gap:8px"></div>';
    table.parentNode.insertBefore(tools, table);
  }

  async function exportPronunciationDictionary() {
    const exported = await call('pronunciation.export');
    const blob = new Blob([JSON.stringify(exported, null, 2)], {type:'application/json;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    anchor.href = url;
    anchor.download = 'ryu-pronunciation-dictionary-' + stamp + '.json';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    message('Exported ' + (Array.isArray(exported.entries) ? exported.entries.length : 0) +
      ' pronunciation entry/entries with their original scopes.');
  }

  async function importPronunciationDictionary() {
    const picker = document.createElement('input');
    picker.type = 'file';
    picker.accept = '.json,application/json';
    picker.onchange = async () => {
      const file = picker.files?.[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) {
        message('Pronunciation dictionary imports are limited to 5 MB.', true);
        return;
      }
      try {
        const importedDocument = JSON.parse(await file.text());
        const preview = await call('pronunciation.import', {document:importedDocument, apply:false});
        const conflicts = Array.isArray(preview.conflicts) ? preview.conflicts : [];
        if (Number(preview.protected_manual_count || 0) > 0) {
          throw new Error('The file contains ' + preview.protected_manual_count +
            ' AI reading(s) that would overwrite a saved manual rule. Resolve those manually before importing.');
        }
        let replaceConflicts = false;
        if (conflicts.length) {
          const details = conflicts.slice(0, 8).map(row =>
            row.written_form + ' · ' + row.scope + ': ' + row.existing_spoken_form +
            ' → ' + row.imported_spoken_form
          ).join('\n');
          replaceConflicts = window.confirm(
            'The import contains ' + conflicts.length + ' conflicting pronunciation rule(s).\n\n' +
            details + (conflicts.length > 8 ? '\n… and ' + (conflicts.length - 8) + ' more.' : '') +
            '\n\nReplace these existing readings? Cancel keeps every saved rule unchanged.'
          );
          if (!replaceConflicts) {
            message('Import cancelled. Existing pronunciation rules were not changed.');
            return;
          }
        }
        const result = await call('pronunciation.import', {
          document:importedDocument, apply:true, replace_conflicts:replaceConflicts
        });
        await refreshTerms();
        message('Imported ' + Number(result.imported || 0) + ' new pronunciation rule(s), updated ' +
          Number(result.updated || 0) + ', skipped ' + Number(result.duplicate_count || 0) +
          ' duplicate(s).');
      } catch (error) {
        message(error?.message || String(error), true);
      }
    };
    picker.click();
  }

  function renderPronunciationRows() {
    const body = $('pronDictionaryBody');
    if (!body) return;
    ensurePronunciationDictionaryTools(body);
    const query = String($('pronSearchAdvanced')?.value || '').trim().toLocaleLowerCase();
    const scopeFilter = $('pronScopeFilter')?.value || 'all';
    const originFilter = $('pronOriginFilter')?.value || 'all';
    const savedProfiles = voices.filter(profile => profile && profile.saved === true && profile.name);
    const profileSelect = $('pronPreviewProfile');
    if (profileSelect) {
      const signature = JSON.stringify(savedProfiles.map(profile => [profile.name,profile.provider]));
      const previous = profileSelect.value;
      if (profileSelect.dataset.savedProfileSignature !== signature) {
        profileSelect.replaceChildren();
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = savedProfiles.length ? 'Select saved voice profile' : 'No saved voice profiles';
        profileSelect.appendChild(placeholder);
        for (const profile of savedProfiles) {
          const option = document.createElement('option');
          option.value = profile.name;
          option.textContent = profile.name + ' · ' + (profile.provider || 'Saved voice');
          profileSelect.appendChild(option);
        }
        profileSelect.dataset.savedProfileSignature = signature;
      }
      profileSelect.value = savedProfiles.some(profile => profile.name === previous)
        ? previous : (savedProfiles[0]?.name || '');
      profileSelect.disabled = savedProfiles.length === 0;
    }
    const scopeSelect = $('newPronScope');
    if (scopeSelect) {
      const previousScope = scopeSelect.value || 'current_book';
      const options = [
        ['current_book','Current book'],
        ['global_library','Global library']
      ];
      if (activePronunciationSeries) options.splice(1,0,['Series · ' + activePronunciationSeries,'Series · ' + activePronunciationSeries]);
      const signature = JSON.stringify(options);
      if (scopeSelect.dataset.scopeOptionsSignature !== signature) {
        scopeSelect.replaceChildren();
        for (const [value,label] of options) {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = label;
          scopeSelect.appendChild(option);
        }
        scopeSelect.dataset.scopeOptionsSignature = signature;
      }
      scopeSelect.value = options.some(([value]) => value === previousScope) ? previousScope : 'current_book';
    }
    const visible = terms.map((term,index) => ({term,index})).filter(({term}) => {
      const origin = String(term.origin || 'manual').toLowerCase();
      const searchable = [
        term.written_form, term.spoken_form, term.language,
        term.scope, term.scope_type, term.scope_id, origin,
        origin === 'ai' ? 'ai-generated ai generated' : 'manual manually entered'
      ].map(value => String(value || '')).join(' ').toLocaleLowerCase();
      const matchesQuery = !query || searchable.includes(query);
      const matchesScope = scopeFilter === 'all' ||
        (scopeFilter === 'series' ? term.scope_type === 'series' : term.scope_type === scopeFilter);
      const matchesOrigin = originFilter === 'all' || origin === originFilter;
      return matchesQuery && matchesScope && matchesOrigin;
    });
    if (!visible.length) {
      body.innerHTML = '<tr><td colspan="6" class="muted">No saved pronunciation entries match these filters.</td></tr>';
    } else {
      body.innerHTML = visible.map(({term,index}, rowIndex) => {
        const written = String(term.written_form || term.word || '');
        const spoken = String(term.spoken_form || term.pronunciation || '');
        const origin = String(term.origin || 'manual').toLowerCase() === 'ai' ? 'ai' : 'manual';
        const scope = String(term.scope || 'Current book');
        const scopeId = String(term.scope_id || '');
        const scopeKey = pronunciationScopeKey(term);
        const selectionKey = pronunciationSelectionKey(term);
        const selected = pronunciationSelectionKeys.has(selectionKey);
        const enabled = term.enabled !== false;
        const disabled = savedProfiles.length === 0;
        const safeLabel = esc(written);
        return '<tr class="pron-row-' + origin + (selected ? ' pron-row-selected' : '') + '" data-pron-row data-pron-index="' + index + '">' +
          '<td><label><input class="pron-row-select" type="checkbox" data-pron-select="' + index + '" aria-label="Select ' + safeLabel + '"' + (selected ? ' checked' : '') + '/>' +
          '<span>' + (rowIndex + 1) + '</span></label></td>' +
          '<td><b>' + safeLabel + '</b><span class="pron-origin-pill ' + origin + '">' + (origin === 'ai' ? 'AI' : 'Manual') + '</span></td>' +
          '<td>' + esc(spoken) + '</td>' +
          '<td><div class="pron-audio-actions">' +
            '<button type="button" class="btn small secondary" data-pron-audio-play="written" data-pron-index="' + index + '"' + (disabled ? ' disabled' : '') + '>▶ Written</button>' +
            '<button type="button" class="btn small secondary" data-pron-audio-play="spoken" data-pron-index="' + index + '"' + (disabled ? ' disabled' : '') + '>▶ Pronounce as</button>' +
            '<button type="button" class="btn small ghost" data-pron-audio-pause="' + index + '"' + (disabled ? ' disabled' : '') + '>Ⅱ</button>' +
            '<button type="button" class="btn small ghost" data-pron-audio-replay="' + index + '"' + (disabled ? ' disabled' : '') + '>↻</button>' +
          '</div></td>' +
          '<td><div class="pron-options">' +
            '<button type="button" class="btn small ghost" data-pron-edit="' + index + '">Edit</button>' +
            '<button type="button" class="btn small ghost" data-delete-pron="' + safeLabel + '" data-delete-scope="' + esc(scope) + '" data-delete-scope-id="' + esc(scopeId) + '">Delete</button>' +
          '</div></td>' +
          '<td><label class="pron-enable-switch" title="' + (enabled ? 'Disable rule' : 'Enable rule') + '">' +
            '<input type="checkbox" data-pron-enabled="' + index + '"' + (enabled ? ' checked' : '') + ' aria-label="Enable pronunciation rule for ' + safeLabel + '"/><span></span></label></td>' +
          '</tr>';
      }).join('');
    }
    const selectedCount = pronunciationSelectionKeys.size;
    const bulk = $('deleteSelectedPron');
    if (bulk) {
      bulk.disabled = selectedCount === 0;
      bulk.textContent = 'Delete selected (' + selectedCount + ')';
    }
  }
  function renderPronunciationSuggestions(suggestions) {
    const box = $('pronAiSuggestions');
    if (!box) return;
    const rows = Array.isArray(suggestions) ? suggestions : [];
    if (!rows.length) {
      box.hidden = true;
      box.replaceChildren();
      return;
    }
    const scopes = [['current_book','Current book']];
    if (activePronunciationSeries) scopes.push(['Series · ' + activePronunciationSeries,'Series · ' + activePronunciationSeries]);
    scopes.push(['global_library','Global library']);
    box.hidden = false;
    box.innerHTML = '<div class="toolbar"><div><b>Review AI pronunciation suggestions</b><p class="muted">These drafts are not saved or enabled until you accept them.</p></div><span class="badge warn">' + rows.length + ' to review</span></div>' +
      rows.map((row,index) => '<div class="pron-ai-suggestion" data-pron-ai-row="' + index + '">' +
        '<label><span>Written</span><input class="input" data-pron-ai-written="' + index + '" maxlength="500" value="' + esc(row.written_form || '') + '"/></label>' +
        '<label><span>Pronounce as · review this draft</span><input class="input" data-pron-ai-spoken="' + index + '" maxlength="1000" value="' + esc(row.spoken_form || '') + '"/></label>' +
        '<p class="pron-ai-evidence">' + esc([
          row.language || 'Language not identified',
          row.confidence == null ? '' : 'Confidence ' + Math.round(Number(row.confidence) * 100) + '%',
          row.ipa ? 'IPA ' + row.ipa : '',
          row.script || '',
          row.reason || '',
          Array.isArray(row.alternatives) && row.alternatives.length ? 'Alternatives: ' + row.alternatives.join(' / ') : ''
        ].filter(Boolean).join(' · ')) + '</p>' +
        '<label><span>Save scope</span><select class="select" data-pron-ai-scope="' + index + '">' + scopes.map(([value,label]) => '<option value="' + esc(value) + '">' + esc(label) + '</option>').join('') + '</select></label>' +
        '<button type="button" class="btn small" data-pron-ai-accept="' + index + '">Accept disabled</button>' +
        '<button type="button" class="btn small ghost" data-pron-ai-dismiss="' + index + '">Dismiss</button></div>'
      ).join('');
  }
  function renderPronunciationMatrixResults(panel, entry, results) {
    if (!panel) return;
    const rows = Array.isArray(results) ? results : [];
    if (!rows.length) {
      panel.innerHTML = '<p class="muted">No profile test results have been saved for this entry yet.</p>';
      return;
    }
    panel.innerHTML =
      '<h4 style="margin:6px 0">Saved-profile test results · ' + esc(entry.written_form || entry.word || '') + '</h4>' +
      rows.map((row, index) => {
        const passed = row.status === 'passed';
        const title = esc(row.profile_name || 'Unknown profile') + ' · ' + esc(row.provider || 'unknown provider');
        const detail = passed
          ? Number(row.actual_duration_seconds || 0).toFixed(1) + 's audio · ' +
            Number(row.synthesis_seconds || 0).toFixed(2) + 's synthesis · ' +
            Number(row.pronunciation_replacements || 0) + ' replacement(s)'
          : esc(row.error || 'Profile test failed');
        const audio = row.audio_url
          ? '<audio controls preload="none" src="' + esc(row.audio_url) +
            '" aria-label="Pronunciation test audio for ' + title + '" style="width:100%;max-width:420px"></audio>'
          : '';
        return '<div style="border:1px solid var(--border,#39404c);border-radius:8px;padding:9px;display:grid;gap:5px">' +
          '<b>' + title + '</b><span style="color:' + (passed ? 'var(--success,#258a56)' : 'var(--danger,#bd4141)') +
          '">' + (passed ? 'Passed · pronunciation rule applied' : 'Failed · pronunciation test not accepted') +
          '</span><small>' + detail + '</small>' + audio +
          '<small class="muted">' + esc(row.tested_at || '') + '</small></div>';
      }).join('');
  }

  async function loadPronunciationMatrixHistory(entry) {
    const panel = document.querySelector('[data-pron-test-results]');
    if (!panel || !entry) return [];
    const data = await call('pronunciation.test_results.get', {
      written_form:entry.written_form || entry.word || '',
      scope:entry.scope || entry.scope_type || 'current_book',
      scope_id:entry.scope_id || ''
    });
    const results = Array.isArray(data?.results) ? data.results : [];
    renderPronunciationMatrixResults(panel, entry, results);
    return results;
  }

  async function runPronunciationProfileMatrix() {
    const selected = terms.filter(term => pronunciationSelectionKeys.has(pronunciationSelectionKey(term)));
    if (selected.length !== 1) {
      throw new Error('Select exactly one pronunciation dictionary row before testing saved profiles.');
    }
    const entry = selected[0];
    if (entry.enabled === false) {
      throw new Error('Enable this pronunciation entry before running the saved-profile test matrix.');
    }
    if (!pronunciationEnabled) {
      throw new Error('Global pronunciation is OFF. Turn it on before testing this entry in production synthesis.');
    }
    const written = String(entry.written_form || entry.word || '').trim();
    if (!written) throw new Error('The selected dictionary entry has no written form.');
    await refreshVoices();
    const profiles = voices.filter(profile => profile && profile.saved === true && profile.name);
    if (!profiles.length) throw new Error('No saved Voice Studio profiles are available for pronunciation testing.');
    const panel = document.querySelector('[data-pron-test-results]');
    if (!panel) throw new Error('The saved-profile test results panel is not available. Refresh Pronunciation Studio.');
    panel.innerHTML = '<p class="muted">Testing ' + esc(written) + ' sequentially across ' +
      profiles.length + ' saved profile(s)… Do not close the project during the test.</p>';
    const outcomes = [];
    for (const profile of profiles) {
      const row = {
        profile_name:String(profile.name),
        provider:String(profile.provider || 'unknown'),
        status:'failed',
        error:'The preview did not complete.'
      };
      try {
        const started = await call('voice.preview', {
          profile_name:profile.name,
          text:written,
          duration_seconds:10,
          route_character_cast:false,
          apply_pronunciation_rules:true
        });
        if (!started?.job_id) throw new Error('The preview job was not created.');
        let completedJob = null;
        await monitorJob(started.job_id, async job => { completedJob = job; });
        const result = completedJob?.result || {};
        if (completedJob?.state !== 'completed' || !result.file_url) {
          throw new Error(completedJob?.error?.message || completedJob?.message ||
            'The preview completed without playable audio.');
        }
        const replacements = Number(result.pronunciation_replacements || 0);
        if (!Number.isFinite(replacements) || replacements < 1) {
          throw new Error('The pronunciation rule was not applied to this preview. Check its scope, global setting and written form.');
        }
        row.status = 'passed';
        row.actual_duration_seconds = Number(result.actual_duration_seconds || 0);
        row.synthesis_seconds = Number(result.synthesis_seconds || 0);
        row.total_seconds = Number(result.total_seconds || 0);
        row.real_time_factor = Number(result.real_time_factor || 0);
        row.pronunciation_replacements = replacements;
        row.audio_url = String(result.file_url);
        delete row.error;
      } catch (error) {
        row.status = 'failed';
        row.error = String(error?.message || error || 'Profile test failed').slice(0, 800);
      }
      outcomes.push(row);
      // Persist after each voice so a later provider failure cannot discard earlier evidence.
      const saved = await call('pronunciation.test_results.save', {
        written_form:written,
        scope:entry.scope || entry.scope_type || 'current_book',
        scope_id:entry.scope_id || '',
        results:[{
          profile_name:row.profile_name,
          provider:row.provider,
          status:row.status,
          actual_duration_seconds:row.actual_duration_seconds,
          synthesis_seconds:row.synthesis_seconds,
          total_seconds:row.total_seconds,
          real_time_factor:row.real_time_factor,
          pronunciation_replacements:row.pronunciation_replacements,
          error:row.error
        }]
      });
      if (!saved || Number(saved.saved || 0) !== 1) {
        throw new Error('Could not persist the test result for ' + profile.name + '.');
      }
      renderPronunciationMatrixResults(panel, entry, outcomes);
      panel.scrollIntoView?.({block:'nearest',behavior:'smooth'});
    }
    const passed = outcomes.filter(row => row.status === 'passed').length;
    const failed = outcomes.length - passed;
    message('Pronunciation profile matrix completed: ' + passed + ' passed, ' + failed +
      ' failed. Results are saved against ' + written + '.');
    return outcomes;
  }

  async function refreshTerms() {
    const requestToken = ++termsListEpoch;
    const [loaded, settings] = await Promise.all([
      call('pronunciation.list'),
      call('pronunciation.settings.get')
    ]);
    if (requestToken !== termsListEpoch) return terms;
    terms = Array.isArray(loaded) ? loaded : [];
    const validSelectionKeys = new Set(terms.map(pronunciationSelectionKey));
    pronunciationSelectionKeys = new Set([...pronunciationSelectionKeys].filter(key => validSelectionKeys.has(key)));
    pronunciationEnabled = settings?.enabled !== false;
    activePronunciationSeries = String(settings?.series_name || '').trim();
    for (const id of ['pronunciationGlobalToggle','productionPronunciationToggle']) {
      const toggle = $(id);
      if (toggle) toggle.checked = pronunciationEnabled;
    }
    renderPronunciationRows();
    return terms;
  }
  async function saveGlobalPronunciation(enabled) {
    const result = await call('pronunciation.settings.save',{enabled:Boolean(enabled)});
    pronunciationEnabled = result.enabled !== false;
    for (const id of ['pronunciationGlobalToggle','productionPronunciationToggle']) {
      const toggle = $(id);
      if (toggle) toggle.checked = pronunciationEnabled;
    }
    message(pronunciationEnabled
      ? 'Global pronunciation is ON. Individually enabled applicable rules will be used.'
      : 'Global pronunciation is OFF. All pronunciation substitutions are bypassed.');
    return result;
  }
  async function playPronunciationEntryPreview(profileName, textValue, label, rowIdentity = '', previewKind = 'written') {
    const profile = voices.find(item => item && item.saved === true &&
      String(item.name || '').toLowerCase() === String(profileName || '').toLowerCase());
    if (!profile) throw new Error('Choose an available saved Voice Studio profile before previewing a pronunciation entry.');
    if (!String(textValue || '').trim()) throw new Error('The selected pronunciation text is empty.');
    const request = {
      profile_name:profile.name,text:String(textValue),duration_seconds:10,
      route_character_cast:false,apply_pronunciation_rules:false
    };
    const data = await call('voice.preview',request);
    lastPronunciationPreview = {
      ...request,label:String(label || profile.name),
      rowIdentity:String(rowIdentity || ''),previewKind:String(previewKind || 'written')
    };
    if (rowIdentity) {
      pronunciationRowPreviewState.set(String(rowIdentity), {
        profile_name:profile.name,text:String(textValue),
        label:String(label || profile.name),previewKind:String(previewKind || 'written')
      });
    }
    await monitorJob(data.job_id, async job => {
      const url = job?.result?.file_url;
      if (!url) throw new Error('The pronunciation preview completed without a playable audio file.');
      if (previewAudio) { previewAudio.pause(); previewAudio = null; }
      previewAudio = new Audio(url);
      previewAudio.onerror = () => message('The pronunciation preview audio could not be played.',true);
      try {
        await previewAudio.play();
        message('Playing ' + lastPronunciationPreview.label + ' with ' + profile.name + ' · ' +
          Number(job.result.actual_duration_seconds || 0).toFixed(1) + ' seconds.');
      } catch (error) {
        throw new Error(error?.message || 'The pronunciation preview could not be played.');
      }
    });
  }
  async function waitForCatalogueScan(jobId, label) {
    if (!jobId) throw new Error('The ' + label + ' refresh did not create a background job.');
    return new Promise((resolve, reject) => {
      let checking = false;
      let settled = false;
      let timer = null;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        if (timer) clearInterval(timer);
        timer = null;
        callback(value);
      };
      const tick = async () => {
        if (settled || checking) return;
        checking = true;
        try {
          const jobs = await call('job.list', {include_hidden:true});
          const job = Array.isArray(jobs) ? jobs.find(row => row.job_id === jobId) : null;
          if (!job) throw new Error('The ' + label + ' refresh job disappeared before reporting a result.');
          if (job.state === 'completed') finish(resolve, job);
          else if (['failed','cancelled'].includes(job.state)) {
            finish(reject, new Error(job.error?.message || job.message ||
              ('The ' + label + ' refresh ' + job.state + '.')));
          }
        } catch (error) {
          finish(reject, error);
        } finally {
          checking = false;
        }
      };
      timer = setInterval(() => { void tick(); }, 750);
      void tick();
    });
  }

  async function loadModelInventory(forceRefresh = false) {
    if (modelInventoryLoadPromise) return modelInventoryLoadPromise;
    const task = (async () => {
      if (!forceRefresh && modelInventoryScanRequested &&
          Date.now() - modelInventoryLoadedAt < 5000) {
        return await call('models.list');
      }
      // Read the last-known-good snapshot immediately. A cold/expired request
      // starts a single-flight worker; this bridge call never enumerates files.
      await call('models.list');
      modelInventoryScanRequested = true;
      const scan = await call('models.refresh');
      await waitForCatalogueScan(scan?.job_id, 'model inventory');
      const rows = await call('models.list');
      modelInventoryLoadedAt = Date.now();
      return rows;
    })();
    modelInventoryLoadPromise = task;
    try {
      return await task;
    } catch (error) {
      modelInventoryScanRequested = false;
      modelInventoryLoadedAt = 0;
      throw error;
    } finally {
      if (modelInventoryLoadPromise === task) modelInventoryLoadPromise = null;
    }
  }

  async function loadSoundCatalogue(forceRefresh = false) {
    if (soundCatalogLoadPromise) return soundCatalogLoadPromise;
    const task = (async () => {
      if (!forceRefresh && soundCatalogScanRequested &&
          Date.now() - soundCatalogLoadedAt < 20000) {
        return await call('sound.catalog');
      }
      await call('sound.catalog');
      soundCatalogScanRequested = true;
      const scan = await call('sound.refresh');
      await waitForCatalogueScan(scan?.job_id, 'Sound Design catalogue');
      const rows = await call('sound.catalog');
      soundCatalogLoadedAt = Date.now();
      return rows;
    })();
    soundCatalogLoadPromise = task;
    try {
      return await task;
    } catch (error) {
      soundCatalogScanRequested = false;
      soundCatalogLoadedAt = 0;
      throw error;
    } finally {
      if (soundCatalogLoadPromise === task) soundCatalogLoadPromise = null;
    }
  }

  async function refreshSounds() {
    const requestToken = ++soundListEpoch;
    const forceRefresh = forceSoundCatalogRefreshPending;
    forceSoundCatalogRefreshPending = false;
    const loaded = await loadSoundCatalogue(forceRefresh);
    if (requestToken !== soundListEpoch) return sounds;
    sounds = Array.isArray(loaded) ? loaded : [];
    const selectedMusicTrack = selectedSoundPath
      ? sounds.find(track => String(track.path || '') === String(selectedSoundPath) && isMusicSoundAsset(track))
      : null;
    if (!selectedMusicTrack) {
      const stalePath = String(selectedSoundPath || '');
      if (stalePath && soundPreviewAudio && soundPreviewKind === 'music' && soundPreviewPath === stalePath) {
        stopSoundPreview();
      }
      selectedSoundPath = null;
      if ($('selectedSoundTitle')) $('selectedSoundTitle').textContent = 'No track selected';
      if ($('selectedSoundMeta')) $('selectedSoundMeta').textContent = stalePath
        ? 'The previously selected music track is no longer available. Select another track from the refreshed library.'
        : 'Select a track from the local catalogue.';
      if ($('previewSelectedTrack')) $('previewSelectedTrack').disabled = true;
    } else if ($('previewSelectedTrack')) {
      $('previewSelectedTrack').disabled = false;
    }
    const grid = $('soundTrackGrid');
    const query = ($('soundTrackSearch')?.value || '').trim().toLowerCase();
    const sourceFilter = document.querySelector('#soundSourceFilter [data-source].active')?.dataset.source || 'all';
    const selectedMusicCategory = document.querySelector('#sound .sound-categories-list [data-music-category].active')?.dataset.musicCategory || 'all';
    const categoryGroup = soundCategoryGroup;
    const visible = sounds.filter(t => {
      const metadata = t.metadata && typeof t.metadata === 'object' ? t.metadata : {};
      const role = soundAssetRole(t);
      const searchable = [
        t.title, t.source, t.format, t.category, t.category_label,
        metadata.category, metadata.tags, metadata.mood, metadata.original_filename
      ].map(value => Array.isArray(value) ? value.join(' ') : String(value ?? '')).join(' ').toLowerCase();
      const matchesMusicType = role !== 'cue';
      const matchesQuery = !query || searchable.includes(query);
      const sourceKind = soundSourceKind(t);
      const matchesSource = sourceFilter === 'all' ||
        (sourceFilter === 'built-in' && sourceKind === 'built-in') ||
        (sourceFilter === 'imported' && sourceKind === 'imported');
      const matchesCategory = selectedMusicCategory === 'all' || categoryGroup(t) === selectedMusicCategory;
      return matchesMusicType && matchesQuery && matchesSource && matchesCategory;
    });
    const signature = JSON.stringify({
      query, sourceFilter, selectedMusicCategory,
      rows: visible.map(t => [t.path,t.title,t.source,t.format,t.size_bytes,t.category])
    });
    const expectedTrackCount = visible.length;
    const renderedTrackCount = grid ? grid.querySelectorAll('[data-select-sound]').length : 0;
    const renderedSignature = grid?.dataset.soundListSignature || '';
    const gridNeedsRepair = Boolean(grid) && (
      renderedSignature !== signature ||
      renderedTrackCount !== expectedTrackCount ||
      (expectedTrackCount > 0 && renderedTrackCount === 0)
    );
    if (gridNeedsRepair) {
      grid.dataset.soundListSignature = signature;
      grid.innerHTML = visible.map(t => '<article class="sound-track card"><div class="sound-track-info"><b>' + esc(t.title) + '</b><small>' + esc(t.category_label || t.category || 'Others') + ' · ' + esc(t.source) + ' · ' + esc(t.format) + ' · ' + Math.round(Number(t.size_bytes || 0)/1024) + ' KB</small></div><button class="btn small secondary" data-select-sound="' + esc(t.path) + '">Select</button></article>').join('') || '<p class="muted">No tracks match these filters. Try All, another category, or import a licensed audio file.</p>';
    }
    renderSoundMixSummary();
    return sounds;
  }
  async function refreshSoundCues() {
    // The cue library shares the native sound catalogue with Music Library. Load
    // that catalogue here rather than relying on a prior Music-tab refresh; cue
    // imports can happen while the Music view is hidden, and another refresh may
    // supersede the shared array before this renderer runs.
    const requestToken = ++cueListEpoch;
    // Cue refreshes have their own request epoch. Do not advance soundListEpoch:
    // that epoch owns Music Library grid renders, and cue refreshes may overlap a
    // source/category refresh triggered immediately after a music import.
    const [loadedCatalog, loadedAssignments] = await Promise.all([
      loadSoundCatalogue(false),
      call('sound.cues.get')
    ]);
    if (requestToken !== cueListEpoch) return cueAssignments;
    sounds = Array.isArray(loadedCatalog) ? loadedCatalog : [];
    if (requestToken !== cueListEpoch) return cueAssignments;
    cueAssignments = loadedAssignments && typeof loadedAssignments === 'object' ? loadedAssignments : {};
    const names = {opening:'openingCueName',chapter:'chapterCueName',closing:'closingCueName'};
    for (const [slot,id] of Object.entries(names)) {
      const node = $(id);
      const cue = cueAssignments[slot] || {};
      const hasDraft = Object.prototype.hasOwnProperty.call(pendingCueAssignments, slot);
      const draftPath = hasDraft ? pendingCueAssignments[slot] : cue.path;
      const draftTrack = draftPath ? sounds.find(track => String(track.path || '') === String(draftPath)) : null;
      if (node) node.textContent = hasDraft
        ? (draftPath ? (draftTrack?.title || 'Selected cue (unsaved)') + ' · Unsaved' : 'Will be cleared · Unsaved')
        : (cue.available === true && cue.title ? cue.title : (cue.assigned || cue.missing ? 'Missing file' : 'Not assigned'));
    }
    const cueSaveState = $('cueSaveState');
    if (cueSaveState) {
      if (cueSaveError) {
        // A catalogue refresh must not replace a save failure with a generic
        // unsaved message. Keep it visible until a retry succeeds or the user
        // changes the staged assignment.
        cueSaveState.textContent = cueSaveError;
      } else if (!cueChangesDirty) {
        cueSaveState.textContent = 'All cue changes saved.';
      } else if (cueClearAllStaged) {
        cueSaveState.textContent = 'Clear All is staged. Press Save Cue Changes to remove the three saved assignments.';
      } else if (Object.keys(pendingCueAssignments).length) {
        cueSaveState.textContent = 'Unsaved cue changes — saving automatically shortly. Use Save Cue Changes to save now.';
      } else {
        cueSaveState.textContent = 'Unsaved cue changes — use Save Cue Changes to persist them.';
      }
    }
    const cueSaveButton = $('saveCueChanges');
    if (cueSaveButton) cueSaveButton.disabled = !cueChangesDirty;
    if (selectedCuePath && !sounds.some(track =>
      String(track.path || '') === String(selectedCuePath) && isCueSoundAsset(track))) {
      const stalePath = String(selectedCuePath);
      if (soundPreviewAudio && soundPreviewKind === 'cue' && soundPreviewPath === stalePath) {
        stopSoundPreview();
      }
      selectedCuePath = null;
      if ($('selectedCueTitle')) $('selectedCueTitle').textContent = 'No cue selected';
      if ($('selectedCueMeta')) $('selectedCueMeta').textContent = 'The previously selected cue is no longer available. Select another cue from the refreshed library.';
    }
    if (selectedCuePath) {
      const selectedCue = sounds.find(track => String(track.path || '') === String(selectedCuePath));
      if ($('selectedCueTitle')) $('selectedCueTitle').textContent = selectedCue?.title || 'Selected cue';
      if ($('selectedCueMeta')) $('selectedCueMeta').textContent = selectedCue
        ? String(selectedCue.source || 'Local catalogue') + ' · ' + String(selectedCue.format || '')
        : 'Selected cue is no longer available in the local catalogue.';
    }
    renderSoundMixSummary();
    const grid = $('cueGrid');
    if (!grid) return cueAssignments;
    const query = ($('cueSearch')?.value || '').trim().toLowerCase();
    const sourceFilter = document.querySelector('#cueSourceFilter [data-cue-source].active')?.dataset.cueSource || 'all';
    const visible = sounds.filter(t => {
      const text = (t.title + ' ' + t.source + ' ' + t.format).toLowerCase();
      const sourceKind = soundSourceKind(t);
      const isCue = isCueSoundAsset(t);
      return isCue && (!query || text.includes(query)) &&
        (sourceFilter === 'all' || (sourceFilter === 'built-in' && sourceKind === 'built-in') ||
         (sourceFilter === 'imported' && sourceKind === 'imported'));
    });
    const signature = JSON.stringify({query,sourceFilter,rows:visible.map(t => [t.path,t.title,t.source,t.format,t.size_bytes])});
    if (grid.dataset.cueListSignature !== signature) {
      grid.dataset.cueListSignature = signature;
      grid.innerHTML = visible.map(t => {
        const selected = String(t.path || '') === String(selectedCuePath || '');
        return '<button type="button" class="cue-card card' + (selected ? ' selected' : '') +
          '" data-cue-path="' + esc(t.path) + '" title="' + esc(t.title) + '" aria-pressed="' +
          (selected ? 'true' : 'false') + '"><h3>' + esc(t.title) + '</h3><p>' +
          esc(t.source || 'Local catalogue') + ' · ' + esc(t.format || '') + '</p></button>';
      }).join('') || '<p class="muted">No matching local cue clips. Import licensed audio clips to use them here.</p>';
    }
    return cueAssignments;
  }
  function chapterMusicCategoryGroup(track) { return soundCategoryGroup(track); }
  function ensureChapterBgmControls() {
    const picker = $('chapterTrackPicker');
    if (!picker) return;
    const editor = picker.closest('.chapter-bgm-editor');
    if (editor && !$('chapterBgmFilterControls')) {
      const filters = document.createElement('div');
      filters.id = 'chapterBgmFilterControls';
      filters.innerHTML =
        '<div class="chapter-bgm-filter-block"><label class="label" for="chapterTrackSearch">Search tracks</label><input class="input" id="chapterTrackSearch" type="search" placeholder="Search title, category or source"/></div>' +
        '<div class="chapter-bgm-filter-block"><span class="label">Source</span><div class="segmented" id="chapterBgmSourceFilter">' +
        '<button type="button" class="active" data-chapter-source="all">All</button><button type="button" data-chapter-source="built-in">Built-in</button><button type="button" data-chapter-source="imported">Imported</button></div></div>' +
        '<div class="chapter-bgm-filter-block"><span class="label">Category</span><div class="sound-categories-list" id="chapterBgmCategoryFilter">' +
        '<button type="button" class="active" data-chapter-category="all">All</button>' +
        '<button type="button" data-chapter-category="fantasy-adventure">Fantasy adventure</button>' +
        '<button type="button" data-chapter-category="battle-warfare">Battle &amp; warfare</button>' +
        '<button type="button" data-chapter-category="mystery">Mystery</button>' +
        '<button type="button" data-chapter-category="horror">Horror</button>' +
        '<button type="button" data-chapter-category="romance">Romance</button>' +
        '<button type="button" data-chapter-category="sci-fi">Sci-fi</button>' +
        '<button type="button" data-chapter-category="calm-narration">Calm narration</button>' +
        '<button type="button" data-chapter-category="others">Others</button></div></div>';
      editor.insertBefore(filters, picker);
    }
    if (editor && !$('chapterBgmSaveState')) {
      const status = document.createElement('p');
      status.id = 'chapterBgmSaveState';
      status.className = 'muted';
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
      status.textContent = 'Saved chapter assignments load from this book.';
      const saveButton = $('saveChapterBgm');
      if (saveButton && saveButton.parentElement === editor) saveButton.insertAdjacentElement('beforebegin', status);
      else editor.appendChild(status);
    }
    const layout = picker.closest('.chapter-bgm-layout');
    if (layout) {
      layout.classList.add('ryu-chapter-bgm-layout');
      if (!$('chapterBgmSelectedTrackPanel')) {
        const panel = document.createElement('aside');
        panel.id = 'chapterBgmSelectedTrackPanel';
        panel.className = 'card chapter-bgm-selected-track';
        panel.innerHTML =
          '<span class="eyebrow chapter-bgm-select-eyebrow">SELECT TRACK</span>' +
          '<h2 id="selectedChapterBgmTrackTitle">No track selected</h2>' +
          '<p class="muted" id="selectedChapterBgmTrackMeta">Select a track from the filtered library.</p>' +
          '<p class="muted" id="selectedChapterBgmTrackState">A library selection is only a candidate until you press Select.</p>' +
          '<button type="button" class="btn" id="confirmChapterBgmTrack">Select</button>';
        layout.appendChild(panel);
      }
    }
    if (!$('ryuChapterBgmControlStyles')) {
      const style = document.createElement('style');
      style.id = 'ryuChapterBgmControlStyles';
      style.textContent = [
        '#sound #chapterBgmFilterControls{display:grid;gap:12px;margin:14px 0}',
        '#sound .chapter-bgm-filter-block{display:grid;gap:6px;min-width:0}',
        '#sound #chapterBgmCategoryFilter{display:flex;flex-wrap:wrap;gap:6px}',
        '#sound #chapterBgmCategoryFilter button{max-width:100%;white-space:normal}',
        '#sound #chapterBgmSourceFilter{display:flex;flex-wrap:wrap;gap:6px}',
        '#sound #chapterBgmFilterControls button.active{outline:1px solid var(--accent,#b58b45);border-color:var(--accent,#b58b45)}',
        '#sound .chapter-bgm-layout.ryu-chapter-bgm-layout{grid-template-columns:minmax(180px,.72fr) minmax(300px,1.28fr) minmax(215px,.82fr);align-items:start}',
        '#sound #chapterBgmSelectedTrackPanel{position:sticky;top:12px;min-width:0;overflow-wrap:anywhere}',
        '#sound #chapterBgmSelectedTrackPanel .chapter-bgm-select-eyebrow{color:#e6c85f}',
        '#sound #chapterBgmSelectedTrackPanel h2{font-size:1.15rem;line-height:1.35;margin:10px 0}',
        '#sound #chapterBgmSelectedTrackPanel #confirmChapterBgmTrack{width:100%;margin-top:8px}',
        '#sound .chapter-track-option.active{outline:1px solid var(--accent,#b58b45);border-color:var(--accent,#b58b45)}',
        '@media(max-width:1200px){#sound .chapter-bgm-layout.ryu-chapter-bgm-layout{grid-template-columns:minmax(155px,.72fr) minmax(270px,1.28fr)}#sound #chapterBgmSelectedTrackPanel{grid-column:2;position:static}}',
        '@media(max-width:800px){#sound .chapter-bgm-layout.ryu-chapter-bgm-layout{grid-template-columns:minmax(0,1fr)}#sound #chapterBgmSelectedTrackPanel{grid-column:auto;position:static}}'
      ].join('\n');
      (document.head || document.documentElement).appendChild(style);
    }
  }
  function renderSelectedChapterBgmTrack() {
    const title = $('selectedChapterBgmTrackTitle');
    const meta = $('selectedChapterBgmTrackMeta');
    const state = $('selectedChapterBgmTrackState');
    const button = $('confirmChapterBgmTrack');
    const candidate = sounds.find(track => String(track.path || '') === String(chapterBgmCandidateTrackPath || '') &&
      isMusicSoundAsset(track));
    const chapterBased = ['custom', 'chapter-based', 'chapter_based', 'chapter'].includes(String(chapterBgmState.strategy || 'same').toLowerCase());
    if (title) title.textContent = candidate?.title || 'No track selected';
    if (meta) meta.textContent = candidate
      ? [candidate.category_label || candidate.category || 'Others', candidate.source || 'Local catalogue', candidate.format || ''].filter(Boolean).join(' · ')
      : 'Select a track from the filtered library.';
    if (state) {
      const current = (chapterBgmState.overrides || {})[String(selectedBgmChapter)] || {};
      const alreadyAssigned = current.rule === 'custom' && String(current.path || '') === String(candidate?.path || '');
      state.textContent = !chapterBased
        ? 'Switch to Chapter-Based BGM before assigning a chapter track.'
        : !candidate
          ? 'A library selection is only a candidate until you press Select.'
          : alreadyAssigned && !chapterBgmDraftDirty
            ? 'This track is already saved for Chapter ' + selectedBgmChapter + '.'
            : 'Candidate only — press Select to save it for Chapter ' + selectedBgmChapter + '.';
    }
    if (button) button.disabled = !chapterBased || !candidate;
  }
  function ensureSoundMixPresentation() {
    const defaultNode = $('mixDefaultTrack');
    const statusGrid = $('mixBgmStatus')?.closest('.mix-status-grid');
    if (defaultNode && statusGrid) {
      const defaultRow = defaultNode.closest('div');
      if (defaultRow?.parentElement === statusGrid) defaultRow.remove();
    }
    const statusRow = $('mixBgmStatus')?.closest('div');
    const statusLabel = statusRow?.querySelector('span');
    if (statusLabel) statusLabel.textContent = 'BGM status';
    if (statusGrid && !$('mixEffectiveTracks')) {
      const row = document.createElement('div');
      row.innerHTML = '<span>Effective track(s)</span><b id="mixEffectiveTracks">Loading saved tracks…</b>';
      statusGrid.appendChild(row);
    }
    const mixView = document.querySelector('#sound [data-sound-view="mix"]');
    const bgmLabel = Array.from(mixView?.querySelectorAll('.mix-signal > span') || [])
      .find(node => /BGM volume|BGM level/i.test(node.textContent || ''));
    if (bgmLabel && !$('mixBgmVolumeValue')) {
      bgmLabel.textContent = 'BGM level (0–50%) ';
      const value = document.createElement('b');
      value.id = 'mixBgmVolumeValue';
      value.className = 'mix-level-value';
      value.textContent = '—';
      value.style.marginLeft = '6px';
      bgmLabel.appendChild(value);
    }
  }
  function renderSoundMixSummary() {
    ensureSoundMixPresentation();
    const setText = (id, value) => {
      const node = $(id);
      if (node) node.textContent = String(value ?? '');
    };
    const overrides = chapterBgmState.overrides && typeof chapterBgmState.overrides === 'object'
      ? chapterBgmState.overrides : {};
    // The backend keeps stable-ID keys and numeric compatibility aliases in
    // the same persisted map. Build one row per real project chapter so summary
    // counts/levels never double-count the same assignment.
    const chapterOverrideRows = Array.isArray(chapterBgmState.chapters)
      ? chapterBgmState.chapters.map(chapter => {
          const identity = String(chapter?.chapter_id || '').trim();
          const stable = identity ? overrides[identity] : null;
          const legacy = overrides[String(chapter?.number)];
          const row = stable && typeof stable === 'object' ? stable : legacy;
          return row && typeof row === 'object' ? row : null;
        }).filter(Boolean)
      : Object.values(overrides).filter(item => item && typeof item === 'object');
    const chapterBased = ['custom', 'chapter-based', 'chapter_based', 'chapter'].includes(String(chapterBgmState.strategy || 'same').toLowerCase());
    const masterEnabled = chapterBgmState.bgm_enabled === true;
    const bgmLevelInput = $('advancedMusicVolume');
    const narrationInput = $('narrationVolume');
    const cueLevelInput = $('cueVolume');
    const storedBgm = Math.max(0, Math.min(0.50, Number(chapterBgmState.default_volume ?? 0.18)));
    const storedNarration = Math.max(0, Math.min(1, Number(chapterBgmState.narration_volume ?? 1)));
    const storedCue = Math.max(0, Math.min(0.50, Number(chapterBgmState.cue_volume ?? 0.25)));
    // Preserve every pending slider draft until the shared manifest save completes.
    // Rehydrating an inactive control from stale persisted state can erase a
    // different slider value when several levels are edited in quick succession.
    if (!mixLevelsDirty && bgmLevelInput && document.activeElement !== bgmLevelInput && Number.isFinite(storedBgm)) {
      bgmLevelInput.value = String(Math.round(storedBgm * 100));
    }
    if (!mixLevelsDirty && narrationInput && document.activeElement !== narrationInput && Number.isFinite(storedNarration)) narrationInput.value = String(Math.round(storedNarration * 100));
    if (!mixLevelsDirty && cueLevelInput && document.activeElement !== cueLevelInput && Number.isFinite(storedCue)) cueLevelInput.value = String(Math.round(storedCue * 100));
    const bgmLevel = Math.max(0, Math.min(0.50, Number(bgmLevelInput?.value ?? storedBgm * 100) / 100));
    setText('advancedMusicVolumeValue', Math.round(bgmLevel * 100) + '%');
    const narrationLevel = Math.max(0, Math.min(1, Number(narrationInput?.value ?? storedNarration * 100) / 100));
    const cueLevel = Math.max(0, Math.min(0.50, Number(cueLevelInput?.value ?? storedCue * 100) / 100));
    setText('narrationVolumeValue', Math.round(narrationLevel * 100) + '%');
    setText('cueVolumeValue', Math.round(cueLevel * 100) + '%');
    setText('mixLevelsSaveState', mixLevelsDirty
      ? 'Unsaved mix level changes — release the slider to save them.'
      : 'Narration, BGM and cue levels are saved with the mix.');
    const defaultPath = String(chapterBgmState.default_path || '').trim();
    const defaultTrack = defaultPath
      ? sounds.find(track => String(track.path || '') === defaultPath && isMusicSoundAsset(track))
      : null;
    const defaultAvailable = Boolean(defaultPath && chapterBgmState.default_available === true && defaultTrack);
    const activeChapterRows = chapterOverrideRows.filter(item =>
      item && item.rule === 'custom' && item.path && item.available !== false &&
      sounds.some(track => String(track.path || '') === String(item.path) && isMusicSoundAsset(track))
    );
    const hasActiveBgm = chapterBased ? activeChapterRows.length > 0 : Boolean(defaultAvailable && defaultTrack);
    const activeCueSlots = ['opening','chapter','closing'].filter(slot => {
      const cue = cueAssignments[slot] || {};
      return masterEnabled && cue.available === true && Boolean(cue.path);
    });
    const missingDefault = !chapterBased && defaultPath && !defaultAvailable ? 1 : 0;
    const missingChapterTracks = chapterOverrideRows.filter(item =>
      item && item.rule === 'custom' && (item.available === false || !item.path)
    ).length;
    const missingCues = ['opening','chapter','closing'].filter(slot => {
      const cue = cueAssignments[slot] || {};
      return cue.missing === true || (cue.assigned === true && cue.available !== true);
    }).length;
    const missingCount = missingDefault + missingChapterTracks + missingCues;
    const assignedOverrideCount = chapterOverrideRows.filter(item => ['custom','none'].includes(item.rule)).length;
    const explicitChapterTrackCount = Number(chapterBgmState.explicit_chapter_track_count ??
      new Set(Object.values(overrides)
        .filter(item => item && item.rule === 'custom' && item.path)
        .map(item => String(item.path))).size);

    setText('mixBgmStatus', !masterEnabled ? 'Voice only' : (hasActiveBgm ? 'Enabled' : 'Enabled · no BGM track assigned'));
    const effectiveTrackPaths = chapterBased
      ? Array.from(new Set(activeChapterRows.map(item => String(item.path || '')).filter(Boolean)))
      : (defaultAvailable && defaultTrack ? [String(defaultTrack.path || defaultPath)] : []);
    const effectiveTrackNames = effectiveTrackPaths.map(trackPath => {
      const catalogTrack = sounds.find(track => String(track.path || '') === trackPath);
      const overrideTrack = activeChapterRows.find(item => String(item.path || '') === trackPath);
      return String(catalogTrack?.title || overrideTrack?.title || trackPath.split(/[\\/]/).pop() || 'Unknown track');
    });
    const effectiveLabel = !masterEnabled
      ? 'Disabled · Voice Only'
      : (!effectiveTrackNames.length ? 'No BGM track assigned' : effectiveTrackNames.join(', '));
    setText('mixEffectiveTracks', effectiveLabel);
    const effectiveNode = $('mixEffectiveTracks');
    if (effectiveNode) effectiveNode.title = effectiveTrackNames.join('\n');
    setText('mixStrategy', chapterBased ? 'Chapter-Based BGM' : 'Same BGM');
    setText('mixOverrides', assignedOverrideCount + ' chapters');
    const cueLabel = slot => {
      const cue = cueAssignments[slot] || {};
      if (cue.available === true && cue.title) return cue.title;
      if (cue.missing === true || cue.assigned === true) return 'Missing file';
      return 'Not assigned';
    };
    setText('mixOpening', cueLabel('opening'));
    setText('mixChapterCue', cueLabel('chapter'));
    setText('mixClosing', cueLabel('closing'));

    const selectedVolumes = chapterBased
      ? activeChapterRows.map(item => Number(item.volume ?? chapterBgmState.default_volume ?? 0.18))
      : (hasActiveBgm ? [bgmLevel] : []);
    const averageVolume = selectedVolumes.length
      ? selectedVolumes.reduce((sum, volume) => sum + (Number.isFinite(volume) ? volume : 0), 0) / selectedVolumes.length
      : 0;
    const musicWidth = masterEnabled && hasActiveBgm ? Math.max(0, Math.min(100, averageVolume / 0.5 * 100)) : 0;
    setText('mixBgmVolumeValue', !masterEnabled ? 'Off' : (!hasActiveBgm ? '0%' : Math.round(averageVolume * 100) + '%' + (chapterBased ? ' avg' : '')));
    const narrationSignal = $('mixNarrationSignal');
    const cueWidth = masterEnabled ? Math.max(0, Math.min(100, cueLevel / 0.50 * 100)) : 0;
    const musicSignal = $('mixBgmSignal');
    const cueSignal = $('mixCueSignal');
    if (narrationSignal?.style) narrationSignal.style.width = Math.max(0, Math.min(100, narrationLevel * 100)) + '%';
    if (musicSignal?.style) musicSignal.style.width = musicWidth + '%';
    if (cueSignal?.style) cueSignal.style.width = cueWidth + '%';

    const outputDescription = !masterEnabled
      ? 'Narration only · BGM and cues disabled'
      : (hasActiveBgm
        ? (activeCueSlots.length ? 'Narration + BGM + configured cues' : 'Narration + BGM')
        : (activeCueSlots.length ? 'Narration + cues · no BGM track assigned' : 'Narration only · no BGM track assigned'));
    setText('soundPreviewPath', outputDescription);
    setText('soundFinalRenderPath', 'Uses the same saved sound settings');
    const activeMissingCount = masterEnabled ? missingCount : 0;
    setText('soundMissingFiles', String(activeMissingCount));
    const savedAt = chapterBgmState.last_saved_at;
    let savedLabel = 'Not saved yet';
    if (savedAt) {
      const date = new Date(savedAt);
      savedLabel = Number.isNaN(date.getTime()) ? String(savedAt) : date.toLocaleString();
    }
    setText('soundLastSaved', savedLabel);
    const soundSaveInFlight = Boolean(
      chapterBgmSavePromise || cueSavePromise || mixLevelsSavePromise ||
      soundManifestSavePromise || chapterStrategySavePromise
    );
    const hasUnsavedSoundChanges = chapterBgmDraftDirty || cueChangesDirty || mixLevelsDirty ||
      cueClearAllStaged || Object.keys(pendingCueAssignments).length > 0 ||
      Object.keys(soundManifestPendingOverrides).length > 0;
    const overallSaveState = soundSaveInFlight
      ? 'Saving sound configuration…'
      : hasUnsavedSoundChanges
        ? 'Unsaved sound changes — save before opening Production Studio.'
        : activeMissingCount > 0
          ? 'Saved configuration has ' + activeMissingCount + ' missing active audio asset' + (activeMissingCount === 1 ? '' : 's') + '.'
          : (savedAt ? 'All sound settings saved.' : 'Sound configuration has not been saved yet.');
    setText('mixOverallSaveState', overallSaveState);
    document.querySelectorAll('#sound [data-bgm-enabled], #generate [data-bgm-enabled]').forEach(button => {
      const selected = (button.dataset.bgmEnabled === 'true') === masterEnabled;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
    const productionMusicLabel = !masterEnabled
      ? 'Voice Only · BGM disabled'
      : chapterBased
        ? 'Chapter-Based BGM · ' + explicitChapterTrackCount + ' unique assigned track' + (explicitChapterTrackCount === 1 ? '' : 's')
        : (defaultAvailable && defaultTrack
          ? defaultTrack.title
          : (defaultPath ? 'Saved book-default track missing' : 'No BGM track assigned'));
    setText('productionMusicSummary', productionMusicLabel);
    setText('productionPreviewMix', outputDescription);
    setText('productionFinalMix', !masterEnabled ? 'Voice Only' : (chapterBased ? 'Chapter-Based BGM' : 'Same BGM'));
    const productionSoundReady = $('productionSoundReady');
    if (productionSoundReady) {
      if (soundSaveInFlight) {
        productionSoundReady.textContent = 'Saving sound settings…';
        productionSoundReady.style.color = 'var(--muted)';
      } else if (hasUnsavedSoundChanges) {
        productionSoundReady.textContent = 'Unsaved sound changes';
        productionSoundReady.style.color = 'var(--amber)';
      } else if (activeMissingCount > 0) {
        productionSoundReady.textContent = activeMissingCount + ' missing audio asset' + (activeMissingCount === 1 ? '' : 's');
        productionSoundReady.style.color = 'var(--danger)';
      } else if (masterEnabled && !hasActiveBgm && activeCueSlots.length === 0) {
        productionSoundReady.textContent = 'No BGM or cues assigned';
        productionSoundReady.style.color = 'var(--amber)';
      } else if (savedAt) {
        productionSoundReady.textContent = masterEnabled ? '✓ Synced' : '✓ Voice Only synced';
        productionSoundReady.style.color = 'var(--green)';
      } else {
        productionSoundReady.textContent = 'Not saved yet';
        productionSoundReady.style.color = 'var(--muted)';
      }
    }
  }
  function renderChapterBgm() {
    ensureChapterBgmControls();
    const list = $('chapterBgmList'), picker = $('chapterTrackPicker');
    const rows = chapterBgmState.chapters || chapters.map(ch => ({number:ch.number,title:ch.title}));
    if (!rows.length) {
      if (list) list.innerHTML = '<p class="muted">Import a book to assign chapter music.</p>';
      if (picker) picker.innerHTML = '<p class="muted">No chapters are available.</p>';
      return;
    }
    if (!rows.some(ch => Number(ch.number) === Number(selectedBgmChapter))) selectedBgmChapter = Number(rows[0].number);
    const overrides = chapterBgmState.overrides || {};
    const overrideFor = chapter => {
      const identity = String(chapter?.chapter_id || '').trim();
      return (identity && overrides[identity]) || overrides[String(chapter?.number)] || {};
    };
    const strategy = chapterBgmState.strategy || 'same';
    const chapterBased = ['custom', 'chapter-based', 'chapter_based'].includes(strategy);
    const ruleFor = row => {
      let value = row.rule || (chapterBased ? 'none' : 'default');
      // Legacy default overrides are not permitted to fall back to book music
      // after the user selects the Chapter-Based strategy.
      if (chapterBased && value === 'default') value = 'none';
      return value;
    };
    if (list) list.innerHTML = rows.map(ch => {
      const o = overrideFor(ch);
      const rule = ruleFor(o);
      const label = rule === 'custom' ? (o.title || (o.available === false ? 'Missing custom track' : 'Custom track')) : rule === 'none' ? 'No BGM' : 'Book default';
      return '<button type="button" class="chapter-bgm-item ' + (Number(ch.number) === Number(selectedBgmChapter) ? 'active' : '') + (rule === 'custom' ? ' override' : '') + '" data-chapter-bgm="' + Number(ch.number) + '"><b>' + esc('Chapter ' + ch.number + ' · ' + ch.title) + '</b><small>' + esc(label) + '</small></button>';
    }).join('');
    const chapter = rows.find(ch => Number(ch.number) === Number(selectedBgmChapter)) || rows[0];
    const current = overrideFor(chapter);
    const rule = ruleFor(current);
    selectedBgmTrackPath = rule === 'custom' ? (current.path || null) : null;
    if (chapterBgmCandidateChapter !== Number(chapter.number)) {
      chapterBgmCandidateChapter = Number(chapter.number);
      chapterBgmCandidateTrackPath = selectedBgmTrackPath;
    }
    if ($('chapterBgmTitle')) $('chapterBgmTitle').textContent = 'Chapter ' + chapter.number + ' · ' + chapter.title;
    const help = $('chapterBgmHelp');
    if (help) help.textContent = chapterBased
      ? 'Assign one track or choose No BGM. Unassigned chapters remain silent; the book-default track is ignored.'
      : 'Same BGM uses the selected book-default track for every chapter. Switch to Chapter-Based BGM to assign chapter tracks.';
    document.querySelectorAll('#sound [data-bgm-strategy]').forEach(b => b.classList.toggle('active', b.dataset.bgmStrategy === strategy));
    document.querySelectorAll('#sound .chapter-rule [data-chapter-rule]').forEach(b => b.classList.toggle('active', b.dataset.chapterRule === rule));
    const defaultRuleButton = document.querySelector('#sound .chapter-rule [data-chapter-rule="default"]');
    if (defaultRuleButton) defaultRuleButton.hidden = chapterBased;
    document.querySelectorAll('#sound .chapter-bgm-editor .chapter-rule button, #sound #chapterVolume, #sound .chapter-mix-row select, #sound #saveChapterBgm').forEach(control => {
      control.disabled = !chapterBased;
    });
    if ($('chapterVolume')) $('chapterVolume').value = Math.round(Number(current.volume ?? chapterBgmState.default_volume ?? 0.18) * 100);
    const selects = document.querySelectorAll('#sound [data-sound-view="chapters"] .chapter-mix-row select');
    if (selects[0]) selects[0].selectedIndex = ({immediate:0,after_first_paragraph:1,after_10_seconds:2})[current.start_offset || 'immediate'] ?? 0;
    if (selects[1]) selects[1].selectedIndex = ({fade_before_end:0,continue_to_transition:1,stop_immediately:2})[current.end_behavior || 'fade_before_end'] ?? 0;
    if (picker) {
      const query = String($('chapterTrackSearch')?.value || '').trim().toLowerCase();
      const sourceFilter = document.querySelector('#chapterBgmSourceFilter [data-chapter-source].active')?.dataset.chapterSource || 'all';
      const categoryFilter = document.querySelector('#chapterBgmCategoryFilter [data-chapter-category].active')?.dataset.chapterCategory || 'all';
      const allMusicTracks = sounds.filter(track => isMusicSoundAsset(track));
      const visible = allMusicTracks.filter(track => {
        const metadata = track.metadata && typeof track.metadata === 'object' ? track.metadata : {};
        const searchable = [track.title, track.source, track.format, track.category, track.category_label,
          metadata.category, metadata.tags, metadata.mood, metadata.original_filename]
          .map(value => Array.isArray(value) ? value.join(' ') : String(value ?? '')).join(' ').toLowerCase();
        const sourceKind = soundSourceKind(track);
        const matchesSource = sourceFilter === 'all' ||
          (sourceFilter === 'built-in' && sourceKind === 'built-in') ||
          (sourceFilter === 'imported' && sourceKind === 'imported');
        const matchesCategory = categoryFilter === 'all' || chapterMusicCategoryGroup(track) === categoryFilter;
        return matchesSource && matchesCategory && (!query || searchable.includes(query));
      });
      const signature = JSON.stringify({query, sourceFilter, categoryFilter,
        rows:visible.map(track => [track.path, track.title, track.source, track.format, track.category])});
      if (picker.dataset.chapterTrackListSignature !== signature) {
        picker.dataset.chapterTrackListSignature = signature;
        picker.innerHTML = visible.map(track =>
          '<button type="button" class="chapter-track-option ' +
          (String(track.path || '') === String(chapterBgmCandidateTrackPath || '') ? 'active' : '') +
          '" data-chapter-track="' + esc(track.path) + '"><b>' + esc(track.title) + '</b><small>' +
          esc(track.category_label || track.category || 'Others') + ' · ' + esc(track.source || 'Local catalogue') +
          ' · ' + esc(track.format || '') + '</small></button>').join('') ||
          '<p class="muted">No music tracks match these filters. Try All or import a licensed audio file.</p>';
      }
      picker.querySelectorAll('button[data-chapter-track]').forEach(control => { control.disabled = !chapterBased; });
    }
    renderSelectedChapterBgmTrack();
    const mixStrategy = $('mixStrategy');
    if (mixStrategy) mixStrategy.textContent = chapterBased ? 'Chapter-Based BGM' : 'Same BGM';
    const mixOverrides = $('mixOverrides');
    if (mixOverrides) mixOverrides.textContent = Object.values(overrides).filter(o => o.rule === 'custom' || o.rule === 'none').length + ' chapters';
  }
  function setProductionStatus(id, value, kind = 'info') {
    const node = $(id);
    if (!node) return;
    const next = String(value ?? '');
    if (node.textContent !== next) node.textContent = next;
    if (node.style) node.style.color = kind === 'ready' ? 'var(--green)' :
      (kind === 'warn' ? 'var(--amber)' : 'var(--muted)');
  }

  function setMetadataDialogStatus(value, kind = 'info') {
    const node = $('projectMetadataStatus');
    if (!node) return;
    node.textContent = String(value || '');
    node.style.color = kind === 'ready' ? 'var(--green)' :
      (kind === 'warn' ? 'var(--amber)' : (kind === 'error' ? 'var(--danger)' : 'var(--muted)'));
  }

  function productionGenerationBlockReason(active) {
    if (!active?.folder) return 'Open a saved project before starting full generation.';
    const configuredCharacterVoiceCount = Math.max(0, Number(
      active.configured_character_voice_profile_count ?? active.character_voice_count ?? 0
    ));
    const narratorOnly = active.narrator_only_generation === true;
    if (narratorOnly && configuredCharacterVoiceCount > 0) {
      return 'Narrator-Only Generation is no longer available because '
        + configuredCharacterVoiceCount
        + ' valid character voice profile(s) are configured. Turn it off to use multi-character speaker review.';
    }
    if (!narratorOnly && active.dialogue_index_ready !== true) {
      return 'The canonical dialogue index could not be verified. Refresh Character Studio and retry before generating.';
    }
    const assignmentIssues = Math.max(0, Number(active.character_assignment_issue_count || 0));
    if (!narratorOnly && assignmentIssues > 0) {
      return assignmentIssues + ' saved character voice assignment(s) need attention before generation.';
    }
    const pendingDialogue = Math.max(0, Number(active.pending_dialogue_count || 0));
    const conflictingDialogue = Math.max(0, Number(active.conflicting_dialogue_count || 0));
    const indexIssues = Math.max(0, Number(active.dialogue_index_issue_count || 0));
    if (!narratorOnly && active.dialogue_review_complete !== true) {
      return 'Generation is blocked until dialogue review is complete: '
        + pendingDialogue + ' passage(s) need speaker review, '
        + conflictingDialogue + ' conflict(s), and '
        + indexIssues + ' source/index issue(s).';
    }
    const unsaved = metadataDialogDirty && metadataDialogProjectFolder === String(active.folder);
    if (unsaved) return 'Save or discard Input Project Details changes before generation.';
    if (active.metadata_complete !== true) {
      const missing = Array.isArray(active.metadata_missing_fields) ? active.metadata_missing_fields : [];
      return 'Complete required Input Project Details' +
        (missing.length ? ': ' + missing.join(', ') : '') + '.';
    }
    if (active.narrator_voice_configured !== true || active.narrator_profile_available !== true) {
      return 'Choose and save an available narrator voice profile before full generation.';
    }
    const eligibleChapters = Math.max(0, Number(
      active.eligible_chapter_count ?? active.prepared_chapter_count ?? 0
    ));
    if (eligibleChapters < 1) {
      return 'Add narration text or re-include at least one chapter for generation.';
    }
    if (active.output_format_supported !== true) {
      return 'Select a supported .m4b output destination before generation.';
    }
    if (active.output_folder_ready !== true) {
      return 'Choose an output folder that exists or whose parent is writable.';
    }
    if (active.output_configured !== true) {
      return 'Configure a writable .m4b output destination before generation.';
    }
    return '';
  }

function renderProductionMetadataGate(active) {
    const status = $('productionMetadataStatus');
    const start = $('startGenerate');
    if (!active?.folder) {
      if (status) {
        status.textContent = 'Open a saved project to validate its details.';
        status.style.color = 'var(--amber)';
      }
      if (start) {
        start.disabled = true;
        start.title = 'Open a project and complete Input Project Details first.';
      }
      return;
    }
    const unsaved = metadataDialogDirty && metadataDialogProjectFolder === String(active.folder);
    const missing = Array.isArray(active.metadata_missing_fields) ? active.metadata_missing_fields : [];
    const complete = active.metadata_complete === true;
    const generationBlockReason = productionGenerationBlockReason(active);
    if (status) {
      status.textContent = unsaved
        ? 'Unsaved changes — save Input Project Details before full generation.'
        : (complete
          ? 'Project details saved and validated.'
          : 'Incomplete metadata — complete: ' + (missing.join(', ') || 'required project details') + '.');
      status.style.color = complete && !unsaved ? 'var(--green)' : 'var(--amber)';
    }
    const audioActive = productionJobIsActive(productionJobSnapshots.full) ||
      productionJobIsActive(productionJobSnapshots.preview);
    if (start) {
      start.disabled = Boolean(generationBlockReason) || audioActive;
      start.title = audioActive
        ? 'Finish or cancel the active Production audio operation first.'
        : (generationBlockReason || 'Generate the full audiobook using saved project configuration.');
    }
  }

  function populateMetadataHistory(field, values) {
    const list = $('metadataHistory' + field[0].toUpperCase() + field.slice(1));
    if (!list) return;
    const rows = Array.isArray(values) ? values : [];
    list.replaceChildren(...rows.map(value => {
      const option = document.createElement('option');
      option.value = String(value ?? '');
      return option;
    }));
  }

  async function openProjectMetadataDialog() {
    const dialog = $('inputProjectDetailsDialog');
    if (!dialog) throw new Error('Input Project Details dialog is unavailable in this build.');
    const requestEpoch = ++metadataDialogEpoch;
    const active = await call('project.get_active');
    if (!active?.folder) throw new Error('Open a saved project from the Library before editing its details.');
    const history = await call('project.metadata.history', {
      expected_project_folder: active.folder
    });
    if (requestEpoch !== metadataDialogEpoch) return;
    if (String(history?.project_folder || '') !== String(active.folder)) {
      throw new Error('The active project changed while its metadata was loading. Reopen Input Project Details.');
    }
    metadataDialogProjectFolder = String(active.folder);
    metadataDialogDirty = false;
    $('metadataTitle').value = String(active.title || '');
    $('metadataAuthor').value = String(active.author || '');
    $('metadataNarrator').value = String(active.voice_profile || active.narrator || '');
    $('metadataPublisher').value = String(active.publisher || '');
    $('metadataSeries').value = String(active.series || active.series_name || '');
    $('metadataSeriesVolume').value = String(active.series_volume || '');
    $('metadataLanguage').value = String(active.language || '');
    $('metadataYear').value = String(active.year || '');
    $('metadataGenre').value = String(active.genre || '');
    $('metadataCoverPath').value = String(active.cover_path || '');
    const coverName = $('metadataCoverName');
    if (coverName) coverName.textContent = active.cover_path ? String(active.cover_path).split(/[\\/]/).pop() : 'No cover selected';
    const coverPreview = $('metadataCoverPreview');
    if (coverPreview) {
      coverPreview.dataset.coverPath = String(active.cover_path || '');
      applyProjectCover(coverPreview, active.cover_path || '');
    }
    const values = history?.values || {};
    for (const field of ['author','publisher','series','series_volume','language','year','genre']) {
      populateMetadataHistory(field, values[field]);
    }
    setMetadataDialogStatus(
      active.metadata_complete === true
        ? 'Saved project details loaded.'
        : 'Missing required details: ' + (active.metadata_missing_fields || []).join(', '),
      active.metadata_complete === true ? 'ready' : 'warn'
    );
    renderProductionMetadataGate(active);
    if (!dialog.open) dialog.showModal();
  }

  function wireProjectMetadataDialog() {
    const dialog = $('inputProjectDetailsDialog');
    if (!dialog || dialog.dataset.ryuMetadataBound === '1') return;
    dialog.dataset.ryuMetadataBound = '1';
    const form = $('projectMetadataForm');
    const markDirty = () => {
      metadataDialogDirty = true;
      setMetadataDialogStatus('Unsaved changes. Save to persist these details to the active project.', 'warn');
      renderProductionMetadataGate(window.ryuPremiumActiveProject || null);
    };
    form?.addEventListener('input', event => {
      if (event.target?.id !== 'metadataNarrator') markDirty();
    });
    const coverButton = $('metadataChooseCover');
    if (coverButton) coverButton.onclick = async () => {
      try {
        if (!metadataDialogProjectFolder) throw new Error('Reload the active project details and try again.');
        const result = await call('project.metadata.cover.choose', {
          expected_project_folder: metadataDialogProjectFolder
        });
        if (result?.cancelled) return;
        if (String(result?.project_folder || '') !== metadataDialogProjectFolder) {
          throw new Error('The active project changed while selecting the cover. Reopen the dialog.');
        }
        $('metadataCoverPath').value = String(result.cover_path || '');
        const name = $('metadataCoverName');
        if (name) name.textContent = String(result.filename || 'Cover selected');
        const preview = $('metadataCoverPreview');
        if (preview) {
          preview.dataset.coverPath = String(result.cover_path || '');
          applyProjectCover(preview, result.cover_path || '');
        }
        markDirty();
      } catch (error) {
        setMetadataDialogStatus(error?.message || String(error), 'error');
        message(error?.message || String(error), true);
      }
    };
    const close = () => {
      if (metadataDialogDirty && !window.confirm('Discard unsaved Input Project Details changes?')) return;
      metadataDialogDirty = false;
      dialog.close();
      renderProductionMetadataGate(window.ryuPremiumActiveProject || null);
    };
    if ($('projectMetadataClose')) $('projectMetadataClose').onclick = close;
    dialog.addEventListener('cancel', event => {
      if (metadataDialogDirty) {
        event.preventDefault();
        close();
      }
    });
    if ($('projectMetadataSave')) $('projectMetadataSave').onclick = async () => {
      const button = $('projectMetadataSave');
      if (!metadataDialogProjectFolder) {
        setMetadataDialogStatus('Reload the active project before saving.', 'error');
        return;
      }
      button.disabled = true;
      setMetadataDialogStatus('Saving project details…', 'info');
      let persisted = false;
      try {
        const result = await call('project.metadata.save', {
          expected_project_folder: metadataDialogProjectFolder,
          title: $('metadataTitle').value,
          author: $('metadataAuthor').value,
          publisher: $('metadataPublisher').value,
          series: $('metadataSeries').value,
          series_volume: $('metadataSeriesVolume').value,
          language: $('metadataLanguage').value,
          year: $('metadataYear').value,
          genre: $('metadataGenre').value,
          cover_path: $('metadataCoverPath').value
        });
        if (result?.saved !== true || String(result.project_folder || '') !== metadataDialogProjectFolder) {
          throw new Error('The backend did not confirm that these project details were saved.');
        }
        persisted = true;
        metadataDialogDirty = false;
        // Update the in-memory Production gate from the same authoritative
        // save response before the asynchronous project refresh can run.
        window.ryuPremiumActiveProject = {
          ...(window.ryuPremiumActiveProject || {}),
          folder: String(result.project_folder || metadataDialogProjectFolder),
          title: String(result.title || ''),
          author: String(result.author || ''),
          publisher: String(result.publisher || ''),
          series: String(result.series || ''),
          series_name: String(result.series_name || result.series || ''),
          series_volume: String(result.series_volume || ''),
          language: String(result.language || ''),
          year: String(result.year || ''),
          genre: String(result.genre || ''),
          narrator: String(result.narrator || ''),
          voice_profile: String(result.narrator || ''),
          cover_path: String(result.cover_path || ''),
          metadata_complete: result.metadata_complete === true,
          metadata_missing_fields: Array.isArray(result.metadata_missing_fields)
            ? result.metadata_missing_fields.slice() : []
        };
        setMetadataDialogStatus('Project details saved successfully.', 'ready');
        dialog.close();
        renderProductionMetadataGate(window.ryuPremiumActiveProject);
      } catch (error) {
        metadataDialogDirty = true;
        setMetadataDialogStatus('Save failed: ' + (error?.message || String(error)), 'error');
        renderProductionMetadataGate(window.ryuPremiumActiveProject || null);
        message(error?.message || String(error), true);
      } finally {
        button.disabled = false;
      }
      if (persisted) {
        try {
          await refreshProjects();
          await refreshProductionSummary();
          message('Input Project Details saved to the active project.');
        } catch (refreshError) {
          message('Project details were saved, but the production summary could not refresh: ' +
            (refreshError?.message || String(refreshError)), true);
        }
      }
    };
    const open = $('openProjectDetails');
    if (open) open.onclick = async () => {
      try { await openProjectMetadataDialog(); }
      catch (error) { message(error?.message || String(error), true); }
    };
  }

  async function refreshProductionSummary() {
    const active = await call('project.get_active');
    if (!active || !active.folder) {
      window.ryuPremiumActiveProject = null;
      setProductionStatus('productionBookTitle', 'No project selected');
      setProductionStatus('productionBookMetadata', 'Open or import a saved project to view its details.');
      setProductionStatus('productionNarrator', 'Not set');
      setProductionStatus('productionVoiceCastCount', 'No saved character assignments');
      setProductionStatus('productionOutputSummary', 'No output target configured');
      renderProductionMetadataGate(null);
      setProductionStatus('productionBookImported', 'No active project', 'warn');
      setProductionStatus('productionChaptersReady', 'No active project', 'warn');
      setProductionStatus('productionNarratorReady', 'No active project', 'warn');
      setProductionStatus('productionCharacterVoices', 'No active project', 'warn');
      setProductionStatus('productionPronunciationReady', 'No active project');
      setProductionStatus('productionOutputReady', 'No active project', 'warn');
      const cover = $('productionBookCover');
      if (cover) applyProjectCover(cover, '');
      return null;
    }
    window.ryuPremiumActiveProject = active;
    const author = String(active.author || '').trim() || 'Author not set';
    const language = String(active.language || '').trim() || 'Language not set';
    const publisher = String(active.publisher || '').trim();
    const series = String(active.series_name || active.series || '').trim();
    const seriesVolume = String(active.series_volume || '').trim();
    const genre = String(active.genre || '').trim();
    setProductionStatus('productionBookTitle', String(active.title || 'Untitled audiobook'));
    setProductionStatus('productionBookMetadata', [author, language,
      genre ? 'Genre ' + genre : 'Genre not set',
      publisher ? 'Publisher ' + publisher : 'Publisher not set',
      series ? 'Series ' + series + (seriesVolume ? ' · Volume ' + seriesVolume : '') : ''].filter(Boolean).join(' · '));
    setProductionStatus('productionNarrator',
      String(active.narrator || active.voice_profile || '').trim() || 'Not set');

    const totalCharacters = Math.max(0, Number(active.character_count || 0));
    const assignedCharacters = Math.max(0, Math.min(totalCharacters, Number(active.character_voice_count || 0)));
    const analysisDone = active.character_analysis_done === true;
    setProductionStatus('productionVoiceCastCount', totalCharacters
      ? assignedCharacters + ' / ' + totalCharacters + ' assigned'
      : (analysisDone ? 'No character speakers detected' : 'Character analysis not run'));

    const outputTarget = String(active.output_target_path || active.output_path || '').trim();
    const outputFormat = String(active.output_format || 'M4B').toUpperCase();
    const bitrate = Math.max(128, Math.min(320, Number(active.audio_bitrate || 256)));
    setProductionStatus('productionOutputSummary', outputTarget
      ? outputFormat + ' · ' + bitrate + ' kbps · ' + outputTarget
      : 'No output target configured');

    const cover = $('productionBookCover');
    if (cover) {
      cover.dataset.coverPath = String(active.cover_path || '');
      applyProjectCover(cover, active.cover_path || '');
    }
    const sourceReady = active.source_exists === true;
    setProductionStatus('productionBookImported',
      sourceReady ? 'Source file available' : 'Source file missing or unavailable',
      sourceReady ? 'ready' : 'warn');

    const chapterCount = Math.max(0, Number(active.chapter_count || 0));
    const preparedCount = Math.max(0, Math.min(chapterCount, Number(active.prepared_chapter_count || 0)));
    const eligibleCount = Math.max(0, Math.min(chapterCount, Number(active.eligible_chapter_count ?? preparedCount)));
    const emptyCount = Math.max(0, Number(active.empty_chapter_count || 0));
    const excludedCount = Math.max(0, Number(active.excluded_chapter_count || 0));
    const chaptersReady = eligibleCount > 0;
    const chapterStatus = eligibleCount
      ? eligibleCount + ' eligible for generation' +
        (emptyCount || excludedCount ? ' · skip ' + emptyCount + ' empty / ' + excludedCount + ' excluded' : '')
      : (chapterCount ? 'No eligible chapters · add text or re-include a chapter' : 'No chapters available');
    setProductionStatus('productionChaptersReady', chapterStatus, chaptersReady ? 'ready' : 'warn');

    const narratorReady = active.narrator_voice_configured === true &&
      active.narrator_profile_available === true;
    const narratorProfile = String(active.voice_profile || '').trim();
    setProductionStatus('productionNarratorReady',
      narratorReady ? 'Saved voice profile · ' + narratorProfile : 'No saved narrator voice profile',
      narratorReady ? 'ready' : 'warn');

    const configuredCharacterVoiceCount = Math.max(0, Number(
      active.configured_character_voice_profile_count ?? active.character_voice_count ?? 0
    ));
    const narratorOnlyRequested = active.narrator_only_generation === true;
    const narratorOnly = narratorOnlyRequested && configuredCharacterVoiceCount === 0;
    const assignmentIssues = Math.max(0, Number(active.character_assignment_issue_count || 0));
    const pendingDialogue = Math.max(0, Number(active.pending_dialogue_count || 0));
    const conflictingDialogue = Math.max(0, Number(active.conflicting_dialogue_count || 0));
    const dialogueIndexIssues = Math.max(0, Number(active.dialogue_index_issue_count || 0));
    let characterStatus = narratorOnly
      ? '0 configured character voice profiles · character voice assignment not required; saved narrator reads all passages'
      : 'Character analysis not run';
    let characterKind = narratorOnly ? 'ready' : 'warn';
    if (narratorOnlyRequested && configuredCharacterVoiceCount > 0) {
      characterStatus = configuredCharacterVoiceCount
        + ' valid character voice profile(s) · narrator-only is no longer eligible; switch to multi-character speaker review';
      characterKind = 'warn';
    } else if (!narratorOnly && active.dialogue_index_ready !== true) {
      characterStatus = 'Canonical dialogue index unavailable · refresh Character Studio before generation';
      characterKind = 'warn';
    } else if (!narratorOnly && assignmentIssues > 0) {
      characterStatus = assignmentIssues + ' saved character voice assignment(s) need attention';
      characterKind = 'warn';
    } else if (!narratorOnly && active.dialogue_review_complete !== true) {
      characterStatus = pendingDialogue + ' passage(s) need speaker review · '
        + conflictingDialogue + ' conflict(s) · ' + dialogueIndexIssues + ' index issue(s)';
      characterKind = 'warn';
    } else if (!narratorOnly && analysisDone && totalCharacters === 0) {
      characterStatus = 'No character dialogue needs speaker review';
      characterKind = 'ready';
    } else if (!narratorOnly) {
      characterStatus = configuredCharacterVoiceCount + ' valid character voice profile(s) · dialogue index reviewed';
      characterKind = 'ready';
    }
    setProductionStatus('productionCharacterVoices', characterStatus, characterKind);

    const pronunciationCount = Math.max(0, Number(active.pronunciation_rule_count || 0));
    setProductionStatus('productionPronunciationReady', pronunciationCount
      ? pronunciationCount + ' saved pronunciation rules'
      : 'No custom pronunciation rules saved · optional',
      pronunciationCount ? 'ready' : 'info');

    const outputReady = active.output_configured === true &&
      active.output_folder_ready === true && active.output_format_supported === true;
    const outputStatus = active.output_format_supported === false
      ? 'Unsupported output type · choose M4B'
      : (outputReady ? 'Writable · ' + String(active.output_folder || '')
        : 'Output destination is missing or its folder is not writable');
    setProductionStatus('productionOutputReady', outputStatus, outputReady ? 'ready' : 'warn');
    renderProductionMetadataGate(active);
    return active;
  }

  function formatProductionDuration(value) {
    const seconds = Math.max(0, Math.floor(Number(value) || 0));
    const hours = Math.floor(seconds / 3600), minutes = Math.floor((seconds % 3600) / 60);
    const remainder = seconds % 60;
    return hours ? hours + ':' + String(minutes).padStart(2, '0') + ':' + String(remainder).padStart(2, '0')
      : minutes + ':' + String(remainder).padStart(2, '0');
  }

  const PRODUCTION_ACTIVE_JOB_STATES = new Set(['queued','running','pause_requested','paused','cancel_requested','retrying']);
  const PRODUCTION_TERMINAL_JOB_STATES = new Set(['completed','failed','cancelled']);
  function productionJobIsActive(job) {
    return Boolean(job && PRODUCTION_ACTIVE_JOB_STATES.has(String(job.state || '').toLowerCase()));
  }
  function productionJobDate(job) {
    return Date.parse(job?.updated_at || job?.started_at || job?.queued_at || '') || 0;
  }
  function newestProductionJob(rows) {
    return rows.slice().sort((a,b) => productionJobDate(b) - productionJobDate(a))[0] || null;
  }
  function productionElapsedSeconds(job) {
    if (!job) return NaN;
    const raw = job.elapsed_seconds;
    const stored = raw !== null && raw !== undefined && raw !== '' ? Number(raw) : NaN;
    if (String(job.state || '').toLowerCase() === 'running') {
      const startedAt = Date.parse(job.started_at || '');
      if (Number.isFinite(startedAt)) {
        const liveElapsed = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
        return Number.isFinite(stored) ? Math.max(stored, liveElapsed) : liveElapsed;
      }
    }
    return stored;
  }
  function productionJobEtaSeconds(job) {
    if (!job || String(job.state || '').toLowerCase() !== 'running') return NaN;
    const raw = job.eta_seconds;
    if (raw === null || raw === undefined || raw === '') return NaN;
    const value = Number(raw);
    return Number.isFinite(value) && value >= 0 ? value : NaN;
  }
  function syncProductionPreviewChapterSelector() {
    const select = $('productionPreviewChapterSelect');
    if (!select) return;
    const projectFolder = String(window.ryuPremiumActiveProject?.folder || '');
    if (projectFolder !== productionPreviewSelectionProjectFolder) {
      const previousFolder = productionPreviewSelectionProjectFolder;
      productionPreviewSelectionProjectFolder = projectFolder;
      productionPreviewSelectedChapter = null;
      productionPreviewSelectedChapterId = '';
      productionPreviewSelectedChapterSignature = '';
      if (previousFolder && previousFolder !== projectFolder) {
        // A completed preview belongs to its original project. Clear only the
        // playable UI reference; keep the durable job ID so an active original
        // job can still be cancelled and its status remains visible in History.
        invalidateVoicePreview();
        if ($('productionPreviewStatus')) {
          $('productionPreviewStatus').textContent = 'Project changed. Generate a fresh preview for the selected project before playback or saving.';
        }
      }
    }
    const rows = (Array.isArray(chapters) ? chapters : []).filter(chapter =>
      Number.isInteger(Number(chapter?.number)) && Number(chapter.number) > 0
    );
    const currentNumber = Number(productionPreviewSelectedChapter || 0);
    const currentRow = rows.find(chapter => Number(chapter.number) === currentNumber);
    const currentId = String(currentRow?.chapter_id || currentRow?.id || '');
    const currentSignature = currentRow ? JSON.stringify([
      Number(currentRow.number), currentId, String(currentRow.title || ''), String(currentRow.text || '')
    ]) : '';
    if (productionPreviewSelectedChapter && !currentRow) {
      // Deleting/re-numbering the selected chapter invalidates its old preview,
      // even when the replacement chapter has no stable ID.
      invalidateVoicePreview();
      productionPreviewSelectedChapter = null;
      productionPreviewSelectedChapterId = '';
      productionPreviewSelectedChapterSignature = '';
    } else if (currentRow && (
      (productionPreviewSelectedChapterId && currentId && productionPreviewSelectedChapterId !== currentId) ||
      (productionPreviewSelectedChapterSignature && currentSignature !== productionPreviewSelectedChapterSignature)
    )) {
      // Chapter data can change during a refresh while the user's selected
      // chapter number remains valid. Invalidate stale audio, but preserve
      // that explicit Production selection instead of falling back to the
      // independent Chapter Studio selection.
      invalidateVoicePreview();
      productionPreviewSelectedChapterId = currentId;
      productionPreviewSelectedChapterSignature = currentSignature;
    }
    if (!rows.length) {
      productionPreviewSelectedChapter = null;
      productionPreviewSelectedChapterId = '';
      productionPreviewSelectedChapterSignature = '';
    } else if (!currentRow || !productionPreviewSelectedChapter) {
      const studioNumber = Number(window.ryuPremiumSelectedChapter || 0);
      const fallback = rows.find(chapter => Number(chapter.number) === studioNumber) || rows[0];
      productionPreviewSelectedChapter = Number(fallback.number);
      productionPreviewSelectedChapterId = String(fallback.chapter_id || fallback.id || '');
      productionPreviewSelectedChapterSignature = JSON.stringify([
        Number(fallback.number), productionPreviewSelectedChapterId,
        String(fallback.title || ''), String(fallback.text || '')
      ]);
    } else {
      if (!productionPreviewSelectedChapterId) productionPreviewSelectedChapterId = currentId;
      if (!productionPreviewSelectedChapterSignature) productionPreviewSelectedChapterSignature = currentSignature;
    }

    const signature = JSON.stringify(rows.map(chapter => [
      Number(chapter.number), String(chapter.chapter_id || chapter.id || ''),
      String(chapter.title || '')
    ]));
    if (select.dataset.chapterSignature !== signature) {
      const options = rows.map(chapter => {
        const option = document.createElement('option');
        option.value = String(Number(chapter.number));
        option.textContent = 'Chapter ' + Number(chapter.number) + ' · ' +
          String(chapter.title || 'Untitled chapter');
        return option;
      });
      if (!options.length) {
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = 'No saved chapters available';
        empty.disabled = true;
        options.push(empty);
      }
      select.replaceChildren(...options);
      select.dataset.chapterSignature = signature;
    }
    const selectedValue = productionPreviewSelectedChapter ? String(productionPreviewSelectedChapter) : '';
    if (select.value !== selectedValue) select.value = selectedValue;
    select.disabled = !rows.length ||
      productionJobIsActive(productionJobSnapshots.full) ||
      productionJobIsActive(productionJobSnapshots.preview);
  }

  function ensureProductionPreviewMonitorUi() {
    const controls = $('productionPreviewControls');
    if (!controls) return;
    if (!$('productionPreviewChapterSelectWrap')) {
      const picker = document.createElement('label');
      picker.id = 'productionPreviewChapterSelectWrap';
      picker.className = 'production-preview-chapter-picker';
      picker.style.cssText = 'display:flex;align-items:center;gap:8px;flex-wrap:wrap;width:100%;min-width:0;margin:0 0 8px;box-sizing:border-box';
      const caption = document.createElement('span');
      caption.className = 'muted';
      caption.textContent = 'Preview chapter';
      const select = document.createElement('select');
      select.id = 'productionPreviewChapterSelect';
      select.setAttribute('aria-label', 'Select a saved chapter for Production preview');
      select.style.cssText = 'flex:1 1 220px;min-width:0;max-width:100%;padding:8px 10px;border:1px solid var(--border,rgba(128,128,128,.35));border-radius:8px;background:var(--input-bg,transparent);color:inherit';
      select.addEventListener('change', () => {
        const chapterNumber = Number(select.value);
        const chapter = chapters.find(item => Number(item.number) === chapterNumber);
        if (!chapter) {
          syncProductionPreviewChapterSelector();
          return;
        }
        const chapterId = String(chapter.chapter_id || chapter.id || '');
        const chapterSignature = JSON.stringify([
          chapterNumber, chapterId, String(chapter.title || ''), String(chapter.text || '')
        ]);
        const selectionChanged =
          chapterNumber !== Number(productionPreviewSelectedChapter) ||
          chapterId !== productionPreviewSelectedChapterId ||
          chapterSignature !== productionPreviewSelectedChapterSignature;
        // Reconcile the selected identity even when the number is unchanged.
        // The selector can be restored from a project refresh while its internal
        // chapter identity is stale; returning early here leaves the visible
        // selection and Production status out of sync.
        productionPreviewSelectedChapter = chapterNumber;
        productionPreviewSelectedChapterId = chapterId;
        productionPreviewSelectedChapterSignature = chapterSignature;
        if (selectionChanged) {
          invalidateVoicePreview();
          if ($('productionPreviewTiming')) $('productionPreviewTiming').textContent = 'No preview generated for this chapter yet.';
        }
        if (!voicePreviewValid && $('productionPreviewStatus')) {
          $('productionPreviewStatus').textContent =
            'Chapter ' + chapterNumber + ' selected. Generate a new preview for this chapter.';
        }
        syncProductionPreviewControls();
      });
      picker.append(caption, select);
      controls.insertAdjacentElement('afterbegin', picker);
    }
    const addButton = (id, label, className, anchor, insertAfter = true) => {
      if ($(id)) return $(id);
      const button = document.createElement('button');
      button.id = id;
      button.type = 'button';
      button.className = className;
      button.textContent = label;
      button.disabled = true;
      button.setAttribute('aria-label', label);
      if (anchor) {
        if (insertAfter) anchor.insertAdjacentElement('afterend', button);
        else anchor.insertAdjacentElement('beforebegin', button);
      } else {
        controls.appendChild(button);
      }
      return button;
    };
    addButton('productionPreviewReplay', '↻ Replay', 'btn small secondary', $('productionPreviewPlay'));
    addButton('productionPreviewCancel', 'Cancel preview', 'btn small danger', $('productionPreviewDownload'));
    if (!$('productionPreviewMonitor')) {
      const monitor = document.createElement('div');
      monitor.id = 'productionPreviewMonitor';
      monitor.className = 'production-preview-monitor';
      monitor.setAttribute('aria-live', 'polite');
      monitor.style.cssText = 'width:100%;max-width:100%;margin:8px auto 0;box-sizing:border-box';
      const progress = document.createElement('div');
      progress.className = 'progress';
      progress.id = 'productionPreviewProgressTrack';
      progress.setAttribute('role', 'progressbar');
      progress.setAttribute('aria-label', 'Production preview generation progress');
      progress.setAttribute('aria-valuemin', '0');
      progress.setAttribute('aria-valuemax', '100');
      progress.setAttribute('aria-valuenow', '0');
      progress.style.cssText = 'width:100%;margin:6px 0 4px';
      const fill = document.createElement('i');
      fill.id = 'productionPreviewProgressBar';
      fill.style.width = '0%';
      progress.appendChild(fill);
      const chapter = document.createElement('small');
      chapter.id = 'productionPreviewChapter';
      chapter.className = 'muted';
      chapter.textContent = 'Select a saved chapter for preview.';
      const timing = document.createElement('small');
      timing.id = 'productionPreviewTiming';
      timing.className = 'muted';
      timing.textContent = 'Preview timing will appear after a job starts.';
      monitor.append(chapter, progress, timing);
      controls.insertAdjacentElement('afterend', monitor);
    }
    let previewStatus = $('productionPreviewStatus');
    if (!previewStatus) {
      previewStatus = document.createElement('small');
      previewStatus.id = 'productionPreviewStatus';
      previewStatus.className = 'muted';
      previewStatus.setAttribute('role', 'status');
      previewStatus.setAttribute('aria-live', 'polite');
      previewStatus.style.cssText = 'display:block;width:100%;margin:4px 0 8px;box-sizing:border-box';
      previewStatus.textContent = 'Select a saved chapter before generating a preview.';
      const monitor = $('productionPreviewMonitor');
      if (monitor) monitor.insertAdjacentElement('afterbegin', previewStatus);
      else controls.appendChild(previewStatus);
    }
    syncProductionPreviewChapterSelector();
    syncProductionPreviewControls();
  }
  function monitorProductionJob(jobId, operation, done) {
    if (!['full','preview'].includes(operation)) return Promise.reject(new Error('Unknown Production Studio job operation.'));
    const previous = productionJobMonitors[operation];
    if (previous?.timer) clearInterval(previous.timer);
    if (previous?.resolve) previous.resolve(null);
    const token = ++productionMonitorEpochs[operation];
    return new Promise(resolve => {
      const record = {token, timer:null, checking:false, settled:false, resolve, errorShown:false};
      productionJobMonitors[operation] = record;
      const finish = job => {
        if (record.settled) return;
        record.settled = true;
        if (record.timer) clearInterval(record.timer);
        if (productionJobMonitors[operation] === record) productionJobMonitors[operation] = null;
        resolve(job || null);
      };
      const tick = async () => {
        if (record.settled || productionMonitorEpochs[operation] !== token || record.checking) return;
        record.checking = true;
        try {
          const rows = await call('job.list', {include_hidden:true});
          if (record.settled || productionMonitorEpochs[operation] !== token) return;
          const job = rows.find(row => String(row.job_id || '') === String(jobId));
          await refreshJobs();
          if (!job || !PRODUCTION_TERMINAL_JOB_STATES.has(String(job.state || '').toLowerCase())) return;
          let previewReady = true;
          if (operation === 'preview' && job.state === 'completed' && typeof done === 'function') {
            try { previewReady = await done(job); }
            catch (error) {
              previewReady = false;
              console.error('[Ryu Production preview validation]', error);
              message('The preview job completed, but its audio could not be prepared: ' + (error?.message || String(error)), true);
            }
            if (!previewReady) {
              const status = $('productionPreviewStatus');
              if (status) status.textContent = 'Preview completed, but the audio did not pass playback validation. Retry the preview.';
              message('The preview job ended, but its output did not pass playback validation. Check the preview status and retry.', true);
            }
          }
          if (job.state !== 'completed') {
            const detail = job.error?.message || job.message || ((job.title || 'Production job') + ' ' + job.state);
            if (operation === 'preview' && $('productionPreviewStatus')) {
              $('productionPreviewStatus').textContent = (job.state === 'failed' ? 'Preview failed · ' : 'Preview cancelled · ') + detail;
            }
            message(detail, true);
          } else if (operation === 'full') {
            message(job.message || 'Audiobook generation completed.', false);
            await refreshProjects().catch(() => {});
          } else if (previewReady) {
            message(job.message || 'Production preview is ready.', false);
          }
          await refreshHistory().catch(() => {});
          await refreshJobs().catch(() => {});
          finish(job);
        } catch (error) {
          if (!record.errorShown && !record.settled) {
            record.errorShown = true;
            message('Production job status could not be refreshed: ' + (error?.message || String(error)), true);
          }
          console.error('[Ryu Production job monitor]', error);
        } finally {
          record.checking = false;
        }
      };
      record.timer = setInterval(tick, 1000);
      tick();
    });
  }
  function renderProductionGeneration(jobs = []) {
    const page = $('generate');
    if (!page || !isVisiblePage('generate')) return;
    ensureProductionPreviewMonitorUi();
    const project = window.ryuPremiumActiveProject || null;
    const projectFolder = String(project?.folder || '').replace(/\\/g, '/').toLowerCase();
    const projectRows = jobs.filter(row => {
      if (!projectFolder) return true;
      return String(row.project_folder || '').replace(/\\/g, '/').toLowerCase() === projectFolder;
    });
    const fullRows = projectRows.filter(row => String(row.type || '').toLowerCase() === 'audiobook-generation');
    const pinnedFull = productionFullJobId
      ? fullRows.find(row => String(row.job_id || '') === String(productionFullJobId))
      : null;
    const fullJob = pinnedFull || newestProductionJob(fullRows);
    if (fullJob?.job_id) productionFullJobId = String(fullJob.job_id);
    productionJobSnapshots.full = fullJob || null;

    const previewRows = projectRows.filter(row =>
      String(row.type || '').toLowerCase() === 'production-preview' ||
      (productionPreviewJobId && String(row.job_id || '') === String(productionPreviewJobId))
    );
    const pinnedPreview = productionPreviewJobId
      ? previewRows.find(row => String(row.job_id || '') === String(productionPreviewJobId))
      : null;
    const previewJob = pinnedPreview || newestProductionJob(previewRows);
    productionPreviewJobId = previewJob?.job_id ? String(previewJob.job_id) : null;
    productionJobSnapshots.preview = previewJob || null;

    const fullState = String(fullJob?.state || '').toLowerCase();
    const fullActive = productionJobIsActive(fullJob);
    const completedOutput = !fullJob && Boolean(project?.completed && project?.output_path);
    const fullError = String(fullJob?.error?.message || fullJob?.message || '').trim();
    const fullStageLabel = fullState === 'failed'
      ? 'Failed · ' + (fullError || 'Generation failed. Retry from Production Studio or inspect Background Jobs.')
      : fullState === 'cancelled'
        ? 'Cancelled'
        : String(fullJob?.stage || fullJob?.message || fullState || 'Generation running');
    const fullPercent = fullJob
      ? Math.max(0, Math.min(100, Math.round(Number(fullJob.progress || 0))))
      : (completedOutput ? 100 : 0);
    const ring = $('genRing');
    if (ring?.style) {
      ring.style.setProperty('--progress', fullPercent + '%');
      ring.setAttribute('role', 'progressbar');
      ring.setAttribute('aria-valuemin', '0');
      ring.setAttribute('aria-valuemax', '100');
      ring.setAttribute('aria-valuenow', String(fullPercent));
      ring.setAttribute('aria-valuetext', fullJob
        ? fullStageLabel + ' · ' + fullPercent + '%'
        : (completedOutput ? 'Audiobook ready' : 'Idle'));
    }
    setProductionStatus('genPercent', fullJob ? fullPercent + '%' : (completedOutput ? '100%' : 'Idle'));
    setProductionStatus('genStage', fullJob
      ? fullStageLabel
      : (completedOutput ? 'Audiobook ready' : 'Ready to generate'));
    const chapter = Math.max(0, Number(fullJob?.current_chapter || 0));
    const total = Math.max(0, Number(fullJob?.chapters_total || project?.chapter_count || 0));
    setProductionStatus('genChapter', fullJob
      ? (chapter ? 'Chapter ' + chapter + (total ? ' of ' + total : '') : String(fullJob.stage || '').toLowerCase().includes('packag') ? 'Assembling final audiobook' : 'Waiting for first chapter')
      : (completedOutput ? (total ? total + ' chapters completed' : 'Completed output verified') : 'No chapter currently rendering'));
    const elapsed = productionElapsedSeconds(fullJob);
    const eta = productionJobEtaSeconds(fullJob);
    setProductionStatus('elapsed', Number.isFinite(elapsed) && elapsed >= 0 ? formatProductionDuration(elapsed) : '—');
    setProductionStatus('remaining', Number.isFinite(eta) ? formatProductionDuration(eta) : '—');

    const pause = $('pauseGenerate');
    if (pause) {
      const canPause = Boolean(fullJob && ['running','paused'].includes(fullState));
      pause.disabled = !canPause;
      pause.textContent = fullState === 'paused' ? 'Resume' : fullState === 'pause_requested' ? 'Pausing…' : 'Pause';
    }
    const cancelFull = $('cancelJob');
    if (cancelFull) {
      cancelFull.disabled = !fullActive || fullState === 'cancel_requested';
      cancelFull.textContent = fullState === 'cancel_requested' ? 'Cancelling…' : 'Cancel job';
    }

    const previewState = String(previewJob?.state || '').toLowerCase();
    const previewActive = productionJobIsActive(previewJob);
    const previewChapterNumber = Math.max(0, Number(previewJob?.current_chapter || previewJob?.result?.chapter_number || window.ryuPremiumSelectedChapter || 0));
    const previewChapterRow = chapters.find(item => Number(item.number) === previewChapterNumber);
    const previewChapterTitle = String(previewJob?.current_chapter_title || previewJob?.result?.chapter_title || previewChapterRow?.title || '').trim();
    const previewChapterLabel = previewChapterNumber
      ? 'Chapter ' + previewChapterNumber + (previewChapterTitle ? ' · ' + previewChapterTitle : '')
      : 'Select a saved chapter for preview.';
    const previewChapterElement = $('productionPreviewChapter');
    if (previewChapterElement) previewChapterElement.textContent = previewChapterLabel;
    const previewPercent = previewJob
      ? Math.max(0, Math.min(100, Math.round(Number(previewJob.progress || 0))))
      : 0;
    const previewProgress = $('productionPreviewProgressBar');
    const previewTrack = $('productionPreviewProgressTrack');
    if (previewProgress?.style) previewProgress.style.width = previewPercent + '%';
    if (previewTrack) {
      previewTrack.setAttribute('aria-valuenow', String(previewPercent));
      previewTrack.hidden = !previewJob;
    }
    const previewStatus = $('productionPreviewStatus');
    if (previewStatus) {
      const chapterPrefix = previewChapterNumber > 0 ? previewChapterLabel + ' · ' : '';
      let label = 'Generate a chapter preview to enable playback and download.';
      if (previewActive) label = chapterPrefix + String(previewJob.stage || previewJob.message || previewState) + ' · ' + previewPercent + '%';
      else if (previewState === 'completed') {
        const actual = Number(previewJob.result?.actual_duration_seconds);
        const sound = previewJob.result?.sound_configuration || {};
        const mixMode = String(sound.background_audio_mode || '').toLowerCase();
        const mixLabel = mixMode === 'off' ? ' · Voice Only'
          : sound.bgm_enabled ? ' · BGM mixed'
          : sound.cues_mixed ? ' · chapter cues'
          : ' · no mix assigned';
        label = chapterPrefix + (voicePreviewValid && Number.isFinite(actual) && actual > 0
          ? 'Preview ready · ' + actual.toFixed(1) + ' seconds' + mixLabel
          : 'Preview completed, but playback validation is not ready yet.');
      } else if (previewState === 'failed') {
        label = chapterPrefix + 'Preview failed · ' + String(previewJob.error?.message || previewJob.message || 'Check the job and retry.');
      } else if (previewState === 'cancelled') {
        label = chapterPrefix + 'Preview cancelled · Partial preview audio was discarded.';
      } else if (voicePreviewValid && previewAudio) {
        label = chapterPrefix + 'Preview ready · ' + (Number(previewAudio.duration) > 0 ? Number(previewAudio.duration).toFixed(1) + ' seconds' : 'loading duration');
      }
      previewStatus.textContent = label;
    }
    const previewTiming = $('productionPreviewTiming');
    if (previewTiming) {
      if (!previewJob) {
        previewTiming.textContent = voicePreviewValid
          ? 'Validated audio is available for playback and download.'
          : 'Requested duration: select 10, 30, 60 or 90 seconds · default 30 seconds.';
      } else {
        const previewElapsed = productionElapsedSeconds(previewJob);
        const previewEta = productionJobEtaSeconds(previewJob);
        const requested = Number(previewJob.result?.requested_duration_seconds || 0);
        const actual = Number(previewJob.result?.actual_duration_seconds || 0);
        const totalSeconds = Number(previewJob.result?.total_seconds);
        const synthesisSeconds = Number(previewJob.result?.synthesis_seconds);
        if (previewState === 'completed' && Number.isFinite(actual) && actual > 0) {
          previewTiming.textContent = 'Generated audio: ' + actual.toFixed(1) + 's' +
            (requested > 0 ? ' · requested ' + requested + 's' : '') +
            (Number.isFinite(totalSeconds) ? ' · total ' + totalSeconds.toFixed(1) + 's' : '') +
            (Number.isFinite(synthesisSeconds) ? ' · synthesis ' + synthesisSeconds.toFixed(1) + 's' : '');
        } else {
          previewTiming.textContent = (Number.isFinite(previewElapsed) ? 'Elapsed ' + formatProductionDuration(previewElapsed) : 'Elapsed —') +
            (Number.isFinite(previewEta) ? ' · remaining ' + formatProductionDuration(previewEta) : '');
        }
      }
    }
    const cancelPreview = $('productionPreviewCancel');
    if (cancelPreview) {
      cancelPreview.disabled = !previewActive || previewState === 'cancel_requested';
      cancelPreview.textContent = previewState === 'cancel_requested' ? 'Cancelling preview…' : 'Cancel preview';
    }
    const fullStart = $('startGenerate');
    const previewStart = $('previewGenerate');
    const anyAudioActive = fullActive || previewActive;
    const generationBlockReason = productionGenerationBlockReason(project);
    syncProductionPreviewChapterSelector();
    let narratorOnlyControl = $('narratorOnlyGeneration');
    if (!narratorOnlyControl) {
      const generateButton = $('startGenerate');
      const generateCard = generateButton?.closest('.card') || generateButton?.parentElement;
      if (generateCard) {
        const row = document.createElement('label');
        row.id = 'narratorOnlyGenerationControl';
        row.style.cssText = 'display:flex;align-items:flex-start;gap:10px;margin:12px 0;padding:12px;border:1px solid var(--border,rgba(128,128,128,.28));border-radius:10px;cursor:pointer';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.id = 'narratorOnlyGeneration';
        input.checked = project?.narrator_only_generation === true;
        input.disabled = project?.narrator_only_eligible !== true;
        input.style.cssText = 'margin-top:3px;flex:0 0 auto';
        input.addEventListener('change', () => {
          const requested = input.checked === true;
          input.disabled = true;
          narratorOnlySavePromise = (async () => {
            try {
              // The control is created once and reused when the user switches
              // books. Resolve the displayed and persisted identities at click
              // time; never retain the project from the first render closure.
              const displayedProject = window.ryuPremiumActiveProject || null;
              if (!displayedProject?.folder) {
                throw new Error('Open a saved project before changing Narrator-Only Generation.');
              }
              const active = await call('project.get_active', {});
              const normalizeFolder = value => String(value || '')
                .replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
              if (!active?.folder ||
                  normalizeFolder(active.folder) !== normalizeFolder(displayedProject.folder)) {
                throw new Error('The active project changed while saving Narrator-Only Generation. Reopen Production and retry.');
              }
              const saved = await call('production.narrator_only.save', {
                enabled:requested,
                expected_project_folder:String(active.folder || '')
              });
              if (normalizeFolder(saved?.project_folder) !== normalizeFolder(active.folder)) {
                throw new Error('The active project changed while saving Narrator-Only Generation. Reopen Production and retry.');
              }
              input.checked = saved.enabled === true;
              input.disabled = saved.automatic !== true && saved.user_opt_out !== true &&
                active.narrator_only_eligible !== true;
              window.ryuPremiumActiveProject = {...active,
                narrator_only_generation:input.checked,
                narrator_only_generation_user_opt_out:saved.user_opt_out === true,
                narrator_only_generation_auto:saved.automatic === true};
              const status = $('narratorOnlyGenerationStatus');
              if (status) status.textContent = input.checked
                ? (saved.automatic === true
                  ? 'Automatically enabled because this book has no configured character voice profiles. The saved narrator reads all narration and dialogue.'
                  : 'Saved for this book. The narrator reads all narration and dialogue.')
                : 'Off by your choice. Character assignments and speaker review will be used.';
            } catch (error) {
              const currentProject = window.ryuPremiumActiveProject || null;
              input.checked = currentProject?.narrator_only_generation === true;
              message(error?.message || String(error), true);
              throw error;
            } finally {
              input.disabled = (window.ryuPremiumActiveProject || {}).narrator_only_eligible !== true;
            }
          })();
          narratorOnlySavePromise.catch(() => {});
        });
        const copy = document.createElement('span');
        copy.style.cssText = 'display:grid;gap:3px;min-width:0';
        const title = document.createElement('strong');
        title.textContent = 'Narrator-Only Generation';
        const description = document.createElement('small');
        description.className = 'muted';
        description.textContent = 'Automatically use the saved narrator for every passage, including dialogue, when this book has zero configured character voice profiles and an available narrator. Uncheck to review dialogue before generation; adding a character voice profile returns production to multi-character routing.';
        const status = document.createElement('small');
        status.id = 'narratorOnlyGenerationStatus';
        status.className = 'muted';
        status.textContent = input.checked
          ? (project?.narrator_only_generation_auto === true
            ? 'Automatically enabled because this book has no configured character voice profiles. The saved narrator reads all narration and dialogue.'
            : 'Saved for this book. The narrator reads all narration and dialogue.')
          : (project?.narrator_only_generation_user_opt_out === true
            ? 'Off by your choice. Character assignments and speaker review will be used.'
            : (project?.narrator_only_eligible === true
              ? 'Available. This book has no configured character voice profiles.'
              : 'Unavailable until this book has an available narrator and no configured character voice profiles.'));
        copy.append(title,description,status);
        row.append(input,copy);
        generateButton?.parentElement?.insertBefore(row,generateButton);
        narratorOnlyControl = input;
      }
    } else {
      const savedValue = project?.narrator_only_generation === true;
      if (document.activeElement !== narratorOnlyControl && narratorOnlyControl.checked !== savedValue) {
        narratorOnlyControl.checked = savedValue;
      }
      narratorOnlyControl.disabled = project?.narrator_only_eligible !== true;
      const status = $('narratorOnlyGenerationStatus');
      if (status) status.textContent = savedValue
        ? (project?.narrator_only_generation_auto === true
          ? 'Automatically enabled because this book has no configured character voice profiles. The saved narrator reads all narration and dialogue.'
          : 'Saved for this book. The narrator reads all narration and dialogue.')
        : (project?.narrator_only_generation_user_opt_out === true
          ? 'Off by your choice. Character assignments and speaker review will be used.'
          : (project?.narrator_only_eligible === true
            ? 'Available. This book has no configured character voice profiles.'
            : 'Unavailable until this book has an available narrator and no configured character voice profiles.'));
    }
    // Job-state refreshes must reuse the exact Production prerequisite
    // gate; polling must never re-enable generation after a blocker is found.
    if (fullStart) {
      fullStart.disabled = anyAudioActive || Boolean(generationBlockReason);
      fullStart.title = anyAudioActive
        ? 'Finish or cancel the active Production audio operation first.'
        : (generationBlockReason || 'Generate the full audiobook using saved project configuration.');
    }
    // Preview remains available when metadata is incomplete; only active audio
    // work prevents a second full/preview operation.
    if (previewStart) previewStart.disabled = anyAudioActive;
    syncProductionPreviewControls();
  }

  async function refreshChapterBgm() {
    await loadSoundCatalogue(false);
    chapterBgmState = await call('sound.chapter_bgm.get');
    const fadeIn = Number(chapterBgmState.fade_in_seconds ?? 2);
    const fadeOut = Number(chapterBgmState.fade_out_seconds ?? 3);
    if ($('bgmFadeIn')) $('bgmFadeIn').selectedIndex = ({0:0,2:1,3:2,5:3})[fadeIn] ?? 0;
    if ($('bgmFadeOut')) $('bgmFadeOut').selectedIndex = ({0:0,3:1,5:2,8:3})[fadeOut] ?? 0;
    renderChapterBgm();
    renderSoundMixSummary();
    return chapterBgmState;
  }
  function soundFileUrl(rawPath) {
    const normalized = String(rawPath || '').replace(/\\/g, '/');
    return 'file:///' + normalized.split('/').map((part, index) =>
      index === 0 && /^[A-Za-z]:$/.test(part) ? part : encodeURIComponent(part)
    ).join('/');
  }
  function stopSoundPreview() {
    if (soundPreviewAudio) {
      soundPreviewAudio.pause();
      soundPreviewAudio = null;
    }
    soundPreviewKind = null;
    soundPreviewPath = null;
    $('soundWave')?.classList.remove('playing');
    if ($('previewSelectedTrack')) $('previewSelectedTrack').textContent = '▶ Preview selected track';
  }
  function createSoundPreview(rawPath, kind, volume = 1) {
    const audio = new Audio(soundFileUrl(rawPath));
    audio.volume = Math.max(0, Math.min(1, Number(volume)));
    soundPreviewAudio = audio;
    soundPreviewKind = kind;
    soundPreviewPath = String(rawPath || '');
    audio.onended = () => {
      if (soundPreviewAudio === audio) {
        soundPreviewAudio = null;
        soundPreviewKind = null;
        soundPreviewPath = null;
        $('soundWave')?.classList.remove('playing');
        if (kind === 'music' && $('previewSelectedTrack')) $('previewSelectedTrack').textContent = '▶ Preview selected track';
      }
    };
    audio.onerror = () => {
      if (soundPreviewAudio === audio) {
        soundPreviewAudio = null;
        soundPreviewKind = null;
        soundPreviewPath = null;
        $('soundWave')?.classList.remove('playing');
        if (kind === 'music' && $('previewSelectedTrack')) $('previewSelectedTrack').textContent = '▶ Preview selected track';
      }
      message('The selected local audio file could not be played in the embedded preview.', true);
    };
    return audio;
  }
  async function saveCurrentChapterBgmDraft(force = false) {
    if (chapterBgmAutoSaveTimer) clearTimeout(chapterBgmAutoSaveTimer);
    chapterBgmAutoSaveTimer = null;
    if (chapterBgmSavePromise) return chapterBgmSavePromise;
    if (!chapterBgmDraftDirty && !force) return false;
    const strategy = String(chapterBgmState.strategy || 'same').toLowerCase();
    const chapterBased = ['custom','chapter-based','chapter_based','chapter'].includes(strategy);
    if (!chapterBased) {
      if (!force) return false;
      throw new Error('Switch to Chapter-Based BGM before saving a chapter assignment.');
    }
    if (!selectedBgmChapter) throw new Error('Choose a chapter before saving its BGM assignment.');
    const controls = Array.from(document.querySelectorAll(
      '#sound [data-bgm-strategy], #chapterBgmList button, #chapterTrackPicker button, ' +
      '#chapterBgmFilterControls input, #chapterBgmFilterControls button, ' +
      '#sound .chapter-rule button, #chapterVolume, #chapterStartOffset, #chapterEndBehavior, ' +
      '#saveChapterBgm, #confirmChapterBgmTrack'
    ));
    const priorDisabled = controls.map(control => control.disabled);
    const runSave = (async () => {
      controls.forEach(control => { control.disabled = true; });
      setChapterBgmSaveStatus('Saving chapter BGM assignment…');
      try {
        while (true) {
          const revision = chapterBgmDraftRevision;
          let rule = document.querySelector('#sound .chapter-rule [data-chapter-rule].active')?.dataset.chapterRule || 'none';
          if (rule === 'default') rule = 'none';
          if (rule === 'custom' && !selectedBgmTrackPath) {
            throw new Error('Choose a track and press Select before saving a custom chapter assignment.');
          }
          const chapterNumber = Number(selectedBgmChapter);
          const chapterRow = (chapterBgmState.chapters || []).find(ch => Number(ch.number) === chapterNumber);
          const chapterId = String(chapterRow?.chapter_id || '').trim();
          if (!chapterId) throw new Error('The selected chapter identity is unavailable. Refresh Chapter BGM before saving.');
          const selects = document.querySelectorAll('#sound [data-sound-view="chapters"] .chapter-mix-row select');
          const payload = {
            number:chapterNumber, chapter_id:chapterId, rule, path:rule === 'custom' ? selectedBgmTrackPath : null,
            volume:Math.max(0, Math.min(0.50, Number($('chapterVolume')?.value ?? 18)/100)),
            start_offset:['immediate','after_first_paragraph','after_10_seconds'][selects[0]?.selectedIndex || 0],
            end_behavior:['fade_before_end','continue_to_transition','stop_immediately'][selects[1]?.selectedIndex || 0]
          };
          await call('sound.chapter_bgm.save', payload);
          if (revision !== chapterBgmDraftRevision) continue;
          chapterBgmDraftDirty = false;
          await refreshChapterBgm();
          if (revision !== chapterBgmDraftRevision) {
            chapterBgmDraftDirty = true;
            continue;
          }
          setChapterBgmSaveStatus('Chapter assignment saved.');
          return true;
        }
      } catch (error) {
        chapterBgmDraftDirty = true;
        setChapterBgmSaveStatus('Save failed. Unsaved chapter changes have been retained.');
        throw error;
      } finally {
        controls.forEach((control, index) => { control.disabled = priorDisabled[index]; });
      }
    })();
    chapterBgmSavePromise = runSave;
    try {
      return await runSave;
    } finally {
      if (chapterBgmSavePromise === runSave) chapterBgmSavePromise = null;
    }
  }
  function scheduleCueAutoSave() {
    if (cueAutoSaveTimer) clearTimeout(cueAutoSaveTimer);
    cueAutoSaveTimer = null;
    const status = $('cueSaveState');
    // A failed automatic save is a user-visible pending state, not a reason
    // to silently launch another retry. Keep the error until the user edits
    // the draft or explicitly presses Save Cue Changes.
    if (cueSaveError) {
      if (status) status.textContent = cueSaveError;
      const retryButton = $('saveCueChanges');
      if (retryButton) retryButton.disabled = !cueChangesDirty;
      return;
    }
    if (cueClearAllStaged || !Object.keys(pendingCueAssignments).length) return;
    if (status) status.textContent = 'Unsaved cue changes — saving automatically shortly. Use Save Cue Changes to save now.';
    cueAutoSaveTimer = setTimeout(async () => {
      cueAutoSaveTimer = null;
      try {
        const saved = await savePendingCueChanges();
        if (saved) {
          await refreshChapterBgm();
          message('Cue changes saved automatically.');
        }
      } catch (error) {
        // Mirror the failure state here as well as in savePendingCueChanges().
        // This is the outer handler that owns the timer-driven automatic save.
        cueChangesDirty = Object.keys(pendingCueAssignments).length > 0;
        cueSaveError = 'Save failed. Unsaved cue changes have been retained.';
        const failureStatus = $('cueSaveState');
        if (failureStatus) failureStatus.textContent = cueSaveError;
        const retryButton = $('saveCueChanges');
        if (retryButton) retryButton.disabled = !cueChangesDirty;
        message(error?.message || String(error), true);
      }
    }, 700);
  }
  async function savePendingCueChanges() {
    if (cueAutoSaveTimer) clearTimeout(cueAutoSaveTimer);
    cueAutoSaveTimer = null;
    if (cueSavePromise) return cueSavePromise;
    if (!Object.keys(pendingCueAssignments).length) return false;
    const runSave = (async () => {
      const status = $('cueSaveState');
      const button = $('saveCueChanges');
      cueSaveError = '';
      if (status) status.textContent = 'Saving cue changes…';
      if (button) button.disabled = true;
      try {
        // Drain changes until empty. A newer value selected during an in-flight
        // request remains queued and is written on the next pass.
        while (Object.keys(pendingCueAssignments).length) {
          const entries = Object.entries(pendingCueAssignments);
          for (const [slot, path] of entries) {
            await call('sound.cues.save', {slot, path:path || null});
            if (Object.prototype.hasOwnProperty.call(pendingCueAssignments, slot) &&
                pendingCueAssignments[slot] === path) {
              delete pendingCueAssignments[slot];
            }
            cueChangesDirty = Object.keys(pendingCueAssignments).length > 0;
          }
          await refreshSoundCues();
        }
        cueChangesDirty = false;
        cueClearAllStaged = false;
        cueSaveError = '';
        if (status) status.textContent = 'All cue changes saved.';
        return true;
      } catch (error) {
        cueChangesDirty = Object.keys(pendingCueAssignments).length > 0;
        cueSaveError = 'Save failed. Unsaved cue changes have been retained.';
        if (status) status.textContent = cueSaveError;
        throw error;
      } finally {
        if (button) button.disabled = !cueChangesDirty;
      }
    })();
    cueSavePromise = runSave;
    try {
      return await runSave;
    } finally {
      if (cueSavePromise === runSave) cueSavePromise = null;
    }
  }
  function currentSoundManifestPayload() {
    const chapterBased = ['custom','chapter-based','chapter_based','chapter'].includes(String(chapterBgmState.strategy || 'same').toLowerCase());
    const currentVolume = $('advancedMusicVolume')?.value;
    const volume = currentVolume == null
      ? Math.max(0, Math.min(0.50, Number(chapterBgmState.default_volume ?? 0.18)))
      : Math.max(0, Math.min(0.50, Number(currentVolume) / 100));
    const narration = Math.max(0, Math.min(1, Number($('narrationVolume')?.value ?? Math.round(Number(chapterBgmState.narration_volume ?? 1) * 100)) / 100));
    const cue = Math.max(0, Math.min(0.50, Number($('cueVolume')?.value ?? Math.round(Number(chapterBgmState.cue_volume ?? 0.25) * 100)) / 100));
    return {
      path:chapterBased ? '' : (chapterBgmState.default_path || ''),
      volume, narration_volume:narration, cue_volume:cue,
      fade_in_seconds:fadeSeconds('bgmFadeIn'), fade_out_seconds:fadeSeconds('bgmFadeOut')
    };
  }
  async function saveSoundManifest(overrides = {}) {
    Object.assign(soundManifestPendingOverrides, overrides || {});
    soundManifestSaveRevision += 1;
    if (soundManifestSavePromise) return soundManifestSavePromise;
    const runSave = (async () => {
      let result = null;
      let savedRevision = -1;
      while (savedRevision !== soundManifestSaveRevision) {
        const revision = soundManifestSaveRevision;
        result = await call('sound.save_manifest', {
          ...currentSoundManifestPayload(),
          ...soundManifestPendingOverrides
        });
        savedRevision = revision;
      }
      soundManifestPendingOverrides = Object.create(null);
      return result;
    })();
    soundManifestSavePromise = runSave;
    try {
      return await runSave;
    } finally {
      if (soundManifestSavePromise === runSave) soundManifestSavePromise = null;
    }
  }
  async function saveSoundMixLevels(force = false) {
    if (!mixLevelsDirty && !force) return false;
    if (mixLevelsSavePromise) return mixLevelsSavePromise;
    const runSave = (async () => {
      let result = null;
      while (true) {
        const revision = mixLevelsRevision;
        result = await saveSoundManifest();
        if (revision === mixLevelsRevision) {
          if (result && typeof result === 'object') {
            chapterBgmState.default_volume = Number(result.bgm_volume ?? chapterBgmState.default_volume ?? 0.18);
            chapterBgmState.narration_volume = Number(result.narration_volume ?? chapterBgmState.narration_volume ?? 1);
            chapterBgmState.cue_volume = Number(result.cue_volume ?? chapterBgmState.cue_volume ?? 0.25);
            chapterBgmState.last_saved_at = result.updated_at || chapterBgmState.last_saved_at;
          }
          mixLevelsDirty = false;
          renderSoundMixSummary();
          return result;
        }
      }
    })();
    mixLevelsSavePromise = runSave;
    try {
      return await runSave;
    } finally {
      if (mixLevelsSavePromise === runSave) mixLevelsSavePromise = null;
    }
  }
  async function flushSoundDesignState({requireExplicitCueClear = false} = {}) {
    // A single transaction is shared by preview, Production handoff and final
    // generation. Never let one of these paths start against a stale draft.
    if (requireExplicitCueClear && cueClearAllStaged) {
      throw new Error('Clear All is staged. Press Save Cue Changes before generating a Sound Design preview.');
    }
    if (chapterStrategySavePromise) await chapterStrategySavePromise;
    await saveCurrentChapterBgmDraft();
    await savePendingCueChanges();
    await saveSoundMixLevels(true);
    await refreshChapterBgm();
    await refreshSoundCues();
    const unresolved = chapterBgmDraftDirty || cueChangesDirty || mixLevelsDirty ||
      cueClearAllStaged || Object.keys(pendingCueAssignments).length > 0 ||
      Object.keys(soundManifestPendingOverrides).length > 0 ||
      Boolean(chapterBgmSavePromise || cueSavePromise || mixLevelsSavePromise ||
        soundManifestSavePromise || chapterStrategySavePromise);
    if (unresolved) {
      throw new Error('Sound Design changes are still saving or unsaved. Preview or production was not started.');
    }
    renderSoundMixSummary();
    return true;
  }
  function scheduleLibrarySearchRefresh() {
    if (librarySearchTimer) clearTimeout(librarySearchTimer);
    librarySearchTimer = setTimeout(() => {
      librarySearchTimer = null;
      refreshProjects().catch(error => message(error?.message || String(error), true));
    }, 160);
  }
  function scheduleSoundSearchRefresh() {
    if (soundSearchTimer) clearTimeout(soundSearchTimer);
    soundSearchTimer = setTimeout(() => {
      soundSearchTimer = null;
      refreshSounds().catch(error => message(error?.message || String(error), true));
    }, 160);
  }
  function scheduleCueSearchRefresh() {
    if (cueSearchTimer) clearTimeout(cueSearchTimer);
    cueSearchTimer = setTimeout(() => {
      cueSearchTimer = null;
      refreshSoundCues().catch(error => message(error?.message || String(error), true));
    }, 160);
  }
  function backgroundGenerationJobActions(job, id, action, canControlGeneration, canCancelImport, canCancelPreview) {
    const state = String(job.state || 'unknown').toLowerCase();
    const isGeneration = Boolean(canControlGeneration);
    const canCancelAnalysis = String(job.type || '').toLowerCase() === 'character-analysis';
    const actions = [];
    if (isGeneration && state === 'running') {
      actions.push(action('pause','Pause','secondary'));
    } else if (isGeneration && state === 'pause_requested') {
      actions.push('<small class="muted" role="status" aria-live="polite">Pausing at the next saved chunk/batch boundary…</small>');
    } else if (isGeneration && state === 'paused') {
      actions.push(action('resume','Resume',''));
    }
    if (state === 'cancel_requested') {
      actions.push('<small class="muted" role="status" aria-live="polite">Cancelling…</small>');
    } else if (state === 'queued' ||
        (isGeneration && ['running','paused','pause_requested'].includes(state)) ||
        (canCancelImport && state === 'running') ||
        (canCancelPreview && ['queued','running'].includes(state)) ||
        (canCancelAnalysis && ['queued','running'].includes(state))) {
      actions.push(action('cancel','Cancel','ghost'));
    }
    if (state === 'failed' && job.recoverable && isGeneration) {
      const interrupted = String(job.error?.code || '').toLowerCase() === 'interrupted';
      actions.push(action(interrupted ? 'recover' : 'retry', interrupted ? 'Recover' : 'Retry','secondary'));
    } else if (state === 'cancelled' && isGeneration) {
      actions.push(action('retry','Retry','secondary'));
    }
    if (['running','pause_requested'].includes(state) && !isGeneration && !canCancelImport && !canCancelPreview && !canCancelAnalysis) {
      actions.push('<small>Cancellation and pause are not supported for this operation.</small>');
    }
    return actions.join('');
  }

  let backendJobFilter = 'active';
  function ensureFailedJobsFilter() {
    // Failed and cancelled audiobook jobs can be retried or recovered from
    // Background Jobs. Expose a dedicated filter instead of making users
    // hunt through every active/completed row in the All view.
    const modal = $('backgroundJobsModal');
    const activeFilter = modal?.querySelector('[data-job-filter="active"]');
    const group = activeFilter?.parentElement || modal?.querySelector('.jobs-tabs');
    if (!group || group.querySelector('[data-job-filter="failed"]')) return;
    const templateButton = activeFilter || group.querySelector('button[data-job-filter]');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = String(templateButton?.className || '').replace(/\bactive\b/g, '').trim();
    button.dataset.jobFilter = 'failed';
    button.textContent = 'Failed / Cancelled';
    button.setAttribute('aria-label', 'Show failed and cancelled background jobs');
    group.appendChild(button);
  }

  // Intercept Task Manager filters before the reference HTML's demo onclick
  // handlers can repaint the live job list with prototype rows.
  if (!window.__ryuBackendJobFilterCaptureBound) {
    window.__ryuBackendJobFilterCaptureBound = true;
    document.addEventListener('click', event => {
      const filter = event.target?.closest?.('#backgroundJobsModal [data-job-filter]');
      if (!filter) return;
      const requested = String(filter.dataset.jobFilter || 'active');
      if (!['active','completed','all','failed'].includes(requested)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      backendJobFilter = requested;
      filter.parentElement?.querySelectorAll('[data-job-filter]').forEach(button => {
        button.classList.toggle('active', button === filter);
      });
      const list = $('backgroundJobsList');
      if (list) list.dataset.backendJobsSignature = '';
      refreshJobs().catch(error => message(error?.message || String(error), true));
    }, true);
  }

  async function refreshJobs() {
    // Coalesce overlapping calls without dropping state changes. A Task Manager
    // filter can change while job.list is in flight; that request must receive
    // a follow-up render using the latest filter before callers resolve.
    jobsRefreshRequested = true;
    if (jobsRefreshPromise) return jobsRefreshPromise;
    const refreshPromise = (async () => {
      let latestJobs = [];
      while (jobsRefreshRequested) {
        jobsRefreshRequested = false;
        latestJobs = await refreshJobsImpl();
      }
      return latestJobs;
    })();
    jobsRefreshPromise = refreshPromise;
    try { return await refreshPromise; }
    finally { if (jobsRefreshPromise === refreshPromise) jobsRefreshPromise = null; }
  }
  async function refreshJobsImpl() {
    ensureFailedJobsFilter();
    const allJobs = await call('job.list', {include_hidden:false});
    if (allJobs.some(job => String(job.type || '').toLowerCase() === 'import' && job.state === 'completed')) {
      await refreshLatestImport();
    }
    // A poll can start before the modal is parsed and finish after it is mounted.
    // Re-run the idempotent filter ensure after the asynchronous bridge call.
    ensureFailedJobsFilter();
    if (isVisiblePage('dashboard')) refreshDashboardGeneration(allJobs);
    if (isVisiblePage('generate')) renderProductionGeneration(allJobs);
    const jobs = allJobs.filter(j => backendJobFilter === 'all' ||
      (backendJobFilter === 'completed' ? j.state === 'completed' :
      (backendJobFilter === 'failed' ? ['failed','cancelled'].includes(j.state) :
      !['completed','failed','cancelled'].includes(j.state))));
    const box = $('backgroundJobsList');
    // The jobs modal is normally hidden. Avoid rebuilding its DOM on every poll;
    // when open, preserve row nodes and update only changing fields/progress.
    const panelVisible = Boolean($('backgroundJobsModal')?.classList.contains('show'));
    if (box && panelVisible) {
      // Keep the structural signature independent of progress text. Message
      // and error contents are updated in place below; rebuilding every row
      // when a worker first emits a message flashes the entire job panel.
      const signature = jobs.map(j => [
        j.job_id, j.state, j.type, j.title, Boolean(j.recoverable), j.project_title, String(j.error?.code || '')
      ].join('\u001f')).join('\u001e');
      const renderedRows = Array.from(box.querySelectorAll('[data-backend-job]'));
      const renderedIds = renderedRows.map(row => String(row.dataset.backendJob || '')).sort();
      const expectedIds = jobs.map(job => String(job.job_id || '')).sort();
      const rowStructureValid = renderedRows.length === jobs.length &&
        renderedRows.every(row =>
          row.children.length === 3 &&
          row.children[0].classList.contains('job-type-icon') &&
          row.children[1].classList.contains('job-main') &&
          row.children[2].classList.contains('job-actions')
        ) &&
        !box.querySelector('.job-row:not([data-backend-job])');
      // Every backend-owned operation must keep one identity-matched View action,
      // including imports/previews which intentionally expose no generation controls.
      // Repair a missing/mismatched action in-place before any whole-list rebuild.
      renderedRows.forEach(row => {
        const id = String(row.dataset.backendJob || '');
        const actions = row.querySelector('.job-actions');
        const view = actions?.querySelector('[data-job-view]');
        if (id && actions && (!view || String(view.dataset.jobView || '') !== id)) {
          if (view) view.remove();
          const button = document.createElement('button');
          button.className = 'btn small secondary';
          button.type = 'button';
          button.dataset.jobView = id;
          button.textContent = 'View';
          actions.prepend(button);
        }
      });
      const rowsHaveViewActions = renderedRows.every(row => {
        const id = String(row.dataset.backendJob || '');
        const view = row.querySelector('[data-job-view]');
        return Boolean(id && view && String(view.dataset.jobView || '') === id);
      });
      const backendDomMatches = JSON.stringify(renderedIds) === JSON.stringify(expectedIds) &&
        rowStructureValid && rowsHaveViewActions;
      if (box.dataset.backendJobsSignature !== signature || !backendDomMatches) {
        box.innerHTML = jobs.map(j => {
          const id = esc(j.job_id || ''), state = String(j.state || 'unknown');
          const action = (name,label,cls) => '<button class="btn small ' + cls + '" data-job-action="' + name + '" data-job-id="' + id + '">' + label + '</button>';
          const canControlGeneration = j.type === 'audiobook-generation';
          const canCancelImport = j.type === 'import';
          const canCancelPreview = ['voice-preview','production-preview','sound-design-preview'].includes(j.type);
          const actions = backgroundGenerationJobActions(j, id, action, canControlGeneration, canCancelImport, canCancelPreview);
          const icon = j.type === 'audiobook-generation' ? '♪' :
            (j.type === 'import' ? '⇧' : (String(j.type || '').includes('preview') ? '▶' : '⚙'));
          const view = '<button class="btn small secondary" type="button" data-job-view="' + id + '">View</button>';
          const pct = Math.max(0,Math.min(100,Number(j.progress || 0)));
          const stateClass = state.toLowerCase().replace(/[^a-z0-9_-]/g,'-');
          return '<article class="job-row" data-backend-job="' + id + '">' +
            '<div class="job-type-icon" aria-hidden="true">' + icon + '</div>' +
            '<div class="job-main">' +
              '<h3 data-job-title>' + esc(j.title || j.type || id) + '</h3>' +
              '<p data-job-stage>' + esc(j.stage || j.message || state) + '</p>' +
              '<div class="job-meta" data-job-meta>' + esc(jobMetaSummary(j)) + '</div>' +
              '<div class="job-progress-line"><div class="progress"><i data-job-progress style="width:' + pct + '%"></i></div>' +
                '<small class="job-state-' + stateClass + '" data-job-state>' + esc(state) + ' · ' + Math.round(Number(j.progress || 0)) + '%</small></div>' +
              '<p data-job-message' + (j.message ? '' : ' hidden') + '>' + esc(j.message || '') + '</p>' +
              '<p class="muted" data-job-error' + (j.error?.message ? '' : ' hidden') + '>' + esc(j.error?.message || '') + '</p>' +
            '</div><div class="job-actions">' + view + actions + '</div></article>';
        }).join('') || '<p class="muted" data-backend-empty="1">No backend jobs in this view.</p>';
        box.dataset.backendJobsSignature = signature;
      } else {
        jobs.forEach(j => {
          const row = [...box.querySelectorAll('[data-backend-job]')].find(el => el.dataset.backendJob === String(j.job_id || ''));
          if (!row) return;
          const pct = Math.max(0, Math.min(100, Number(j.progress || 0)));
          const stage = row.querySelector('[data-job-stage]');
          const progress = row.querySelector('[data-job-progress]');
          const state = row.querySelector('[data-job-state]');
          const meta = row.querySelector('[data-job-meta]');
          const messageNode = row.querySelector('[data-job-message]');
          const errorNode = row.querySelector('[data-job-error]');
          writeTextIfChanged(stage, j.stage || j.message || j.state || 'unknown');
          writeStyleIfChanged(progress, 'width', pct + '%');
          writeTextIfChanged(state, String(j.state || 'unknown') + ' · ' + Math.round(pct) + '%');
          writeTextIfChanged(meta, jobMetaSummary(j));
          writeTextIfChanged(messageNode, j.message || '');
          writeBooleanIfChanged(messageNode, 'hidden', !j.message);
          writeTextIfChanged(errorNode, j.error?.message || '');
          writeBooleanIfChanged(errorNode, 'hidden', !j.error?.message);
        });
      }
      box.dataset.backendJobsRendered = '1';
    }
    writeTextIfChanged($('jobsRunningCount'), allJobs.filter(j => ['running','pause_requested','cancel_requested','retrying'].includes(j.state)).length);
    writeTextIfChanged($('jobsQueuedCount'), allJobs.filter(j => j.state === 'queued').length);
    writeTextIfChanged($('jobsCompletedCount'), allJobs.filter(j => j.state === 'completed').length);
    writeTextIfChanged($('backgroundJobCount'), allJobs.filter(j => !['completed','failed','cancelled'].includes(j.state)).length + ' background jobs');
    return allJobs;
  }
  async function monitorJob(jobId, done, terminal) {
    const originPage = document.querySelector('.page.active')?.id || '';
    const monitorToken = ++monitorEpoch;
    activeJob = jobId;
    activeJobType = null;
    if (poll) clearInterval(poll);
    poll = null;
    let finished = false;
    let checking = false;
    const tick = async () => {
      // setInterval does not wait for async callbacks. Ignore overlapping ticks
      // and late responses from an older job monitor to avoid duplicate terminal
      // callbacks, stale progress and UI updates after navigating to another task.
      if (finished || monitorToken !== monitorEpoch || checking) return;
      checking = true;
      try {
        const jobs = await call('job.list', {include_hidden:true});
        if (finished || monitorToken !== monitorEpoch) return;
        const job = jobs.find(j => j.job_id === jobId);
        if (!job) return;
        if (activeJob === jobId) activeJobType = job.type || null;
        const pct = Math.max(0, Math.min(100, Number(job.progress || 0)));
        const originVisible = isVisiblePage(originPage);
        // A background job must never write progress into an unrelated screen.
        // Dedicated progress widgets are only updated while their owning screen
        // is visible; the shared Background Jobs and History views remain global.
        if (originVisible && originPage === 'generate') {
          writeTextIfChanged($('genPercent'), Math.round(pct) + '%');
          writeCssVariableIfChanged($('genRing'), '--progress', pct + '%');
          writeTextIfChanged($('genStage'), job.stage || job.message || job.state);
        }
        if (originVisible && originPage === 'import' && job.type === 'import') {
          writeStyleIfChanged($('importBar'), 'width', pct + '%');
          writeTextIfChanged($('importStatus'), job.message || job.stage || job.state);
        }
        if (originVisible && originPage === 'characters' && job.type === 'character-analysis') {
          writeTextIfChanged($('aiProgressText'), job.stage || job.message || job.state);
          writeStyleIfChanged($('aiProgressBar'), 'width', pct + '%');
        }
        if (originVisible && originPage === 'pronunciation' && job.type === 'pronunciation-analysis') {
          const status = $('pronAnalysisStatus');
          if (status) {
            status.hidden = false;
            writeTextIfChanged(status, (job.stage || job.state) + ' · ' + Math.round(pct) + '%' +
              (job.message ? ' · ' + job.message : ''));
          }
        }
        if (originVisible && originPage === 'voices' && job.type === 'voice-preview') {
          writeStyleIfChanged($('previewProgress'), 'width', pct + '%');
        }
        if (originVisible && originPage === 'voices' && job.type === 'voice-preview') {
          const previewDetail = String(job.message || '').trim();
          const elapsedMatch = previewDetail.match(/elapsed \d+:\d{2}/i);
          const previewDetailIsUseful = Boolean(elapsedMatch) ||
            /loading qwen model|qwen model loaded|switching to cpu/i.test(previewDetail);
          const shortDetail = elapsedMatch?.[0] ||
            (/switching to cpu/i.test(previewDetail) ? 'Selecting compatible backend' :
             /loading qwen model/i.test(previewDetail) ? 'Loading Qwen model' :
             /qwen model loaded/i.test(previewDetail) ? 'Model loaded' : '');
          // Keep the compact badge stable-width. Putting the full backend heartbeat
          // here makes the toolbar wrap between refresh ticks and moves the preview.
          writeTextIfChanged($('previewState'), (job.stage || job.state) + ' · ' + Math.round(pct) + '%');
          writeTextIfChanged($('sumPreview'), ['completed','failed','cancelled'].includes(job.state)
            ? (job.state==='completed'?'Finalizing':job.state==='failed'?'Failed':'Cancelled')
            : 'Synthesizing · '+Math.round(pct)+'%');
          if($('validation')&&!['completed','failed','cancelled'].includes(job.state)) {
            writeTextIfChanged($('validation'), 'Synthesizing preview · '+Math.round(pct)+'% · '+
              (job.stage||job.state)+(previewDetailIsUseful ? ' · '+shortDetail : ''));
          }
        }
        await refreshJobs();
        if (finished || monitorToken !== monitorEpoch) return;
        if (['completed','failed','cancelled'].includes(job.state)) {
          finished = true;
          if (poll) clearInterval(poll);
          poll = null;
          if (activeJob === jobId) { activeJob = null; activeJobType = null; }
          if (typeof terminal === 'function') {
            try { await terminal(job); }
            catch (terminalError) {
              console.warn('[Ryu job terminal callback]', terminalError);
              if (monitorToken === monitorEpoch) message('The task finished, but its follow-up refresh did not complete: ' + (terminalError?.message || String(terminalError)), true);
            }
          }
          if (monitorToken !== monitorEpoch) return;
          let completionResult;
          try { completionResult = job.state === 'completed' && done ? await done(job) : undefined; }
          catch (completionError) {
            console.error('[Ryu job completion callback]', completionError);
            if (monitorToken === monitorEpoch) message('The task finished, but its output could not be finalized: ' + (completionError?.message || String(completionError)), true);
            return;
          }
          if (monitorToken !== monitorEpoch) return;
          if (completionResult === false) {
            message('The preview job ended, but its output did not pass playback validation. Check the preview status and retry.', true);
          } else {
            // Import results carry review warnings separately from the concise job status.
            // Surface those warnings to the user instead of silently dropping them.
            const importWarnings = job.type === 'import' && job.state === 'completed' &&
              Array.isArray(job.result?.warnings) ? job.result.warnings.filter(Boolean) : [];
            const completionMessage = importWarnings.length
              ? importWarnings.join(' ')
              : (job.state === 'failed' && job.error?.message
                  ? (job.message || ((job.title || 'Job') + ' failed')) + ' ' + String(job.error.message)
                  : (job.message || ((job.title || 'Job') + ' ' + job.state)));
            message(completionMessage, job.state !== 'completed');
          }
          await refreshHistory().catch(() => {});
          if (job.state === 'completed' && monitorToken === monitorEpoch && job.type === 'audiobook-generation') {
            await refreshProjects().catch(() => {});
          }
          if (job.state === 'completed' && monitorToken === monitorEpoch &&
              ['import','character-analysis'].includes(job.type)) {
            await refreshChapters().catch(()=>{});
            await refreshCharacters().catch(()=>{});
          }
        }
      } catch (e) {
        if (monitorToken === monitorEpoch) console.error('[Ryu job monitor]', e);
      } finally {
        checking = false;
      }
    };
    await tick();
    if (!finished && monitorToken === monitorEpoch) poll = setInterval(tick, 1000);
  }
  function waitForNarratorPreviewJob(jobId, durationSeconds, profileName) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        callback(value);
      };
      monitorJob(jobId, job => {
        const ready = preparePreviewPlayback(job, durationSeconds, {
          profileName,
          preserveSummary:true
        });
        if (ready) {
          finish(resolve, {
            job,
            profileName,
            outputPath:lastVoicePreviewPath,
            durationSeconds
          });
        } else {
          finish(reject, new Error('The narrator preview did not pass audio validation.'));
        }
        return ready;
      }, job => {
        if (job.state !== 'completed') {
          finish(reject, new Error(job.error?.message || job.message || 'Narrator preview did not complete.'));
        }
      });
    });
  }

  function requestElevenLabsApiKey() {
    return new Promise(resolve => {
      $('ryuElevenLabsKeyDialog')?.remove();
      const overlay = document.createElement('div');
      overlay.id = 'ryuElevenLabsKeyDialog';
      overlay.style.cssText = 'position:fixed;inset:0;z-index:100000;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(3,5,10,.8);backdrop-filter:blur(7px)';
      const panel = document.createElement('section');
      panel.setAttribute('role','dialog'); panel.setAttribute('aria-modal','true'); panel.setAttribute('aria-labelledby','ryuElevenLabsKeyTitle');
      panel.style.cssText = 'box-sizing:border-box;width:min(460px,100%);background:#151a25;border:1px solid rgba(255,255,255,.13);border-radius:18px;box-shadow:0 24px 80px rgba(0,0,0,.5);padding:22px;color:#f4f5f8';
      const heading = document.createElement('h2'); heading.id='ryuElevenLabsKeyTitle'; heading.textContent='Connect ElevenLabs';
      heading.style.cssText='margin:0 0 8px;font-size:22px';
      const description = document.createElement('p');
      description.textContent='Paste your ElevenLabs API key. It is saved in the app’s local settings and is sent only to the ElevenLabs provider when you use its service. Do not paste passwords or other account credentials.';
      description.style.cssText='margin:0 0 16px;color:#aeb6c5;font-size:13px;line-height:1.5';
      const label = document.createElement('label'); label.textContent='API key'; label.htmlFor='ryuElevenLabsKeyInput';
      label.style.cssText='display:block;margin-bottom:6px;font-size:12px;color:#aeb6c5';
      const input = document.createElement('input'); input.id='ryuElevenLabsKeyInput'; input.type='password';
      input.autocomplete='new-password'; input.spellcheck=false; input.placeholder='Paste ElevenLabs API key';
      input.style.cssText='box-sizing:border-box;width:100%;padding:12px;border-radius:10px;border:1px solid #42495a;background:#0c1018;color:#f6f7fa;font:inherit';
      const actions=document.createElement('div'); actions.style.cssText='display:flex;justify-content:flex-end;gap:10px;margin-top:20px';
      const cancel=document.createElement('button'); cancel.type='button'; cancel.textContent='Cancel';
      cancel.style.cssText='padding:10px 14px;border-radius:10px;background:#1c2230;border:1px solid #343b4a;color:#f2f4f8;font-weight:700;cursor:pointer';
      const save=document.createElement('button'); save.type='button'; save.textContent='Save Key & Connect';
      save.style.cssText='padding:10px 16px;border-radius:10px;background:#c92050;border:1px solid #e7426a;color:white;font-weight:800;cursor:pointer';
      actions.append(cancel,save); panel.append(heading,description,label,input,actions); overlay.append(panel);
      let finished=false;
      const finish=value=>{if(finished)return;finished=true;overlay.remove();resolve(value)};
      cancel.addEventListener('click',()=>finish(false));
      overlay.addEventListener('click',event=>{if(event.target===overlay)finish(false)});
      input.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();finish(false)}if(event.key==='Enter'){event.preventDefault();save.click()}});
      save.addEventListener('click',async()=>{
        const key=String(input.value||'').trim();
        if(!key){input.focus();message('Paste an ElevenLabs API key first.',true);return}
        save.disabled=true; save.textContent='Saving…';
        try {
          await call('voice.credentials.set',{api_key:key});
          input.value='';
          await refreshProviderCatalog('eleven',true);
          message('ElevenLabs API key saved to local app settings. The catalogue has been checked.');
          finish(true);
        } catch(error) {
          message(error?.message||String(error),true);
          save.disabled=false; save.textContent='Save Key & Connect';
        }
      });
      document.body.append(overlay); input.focus();
    });
  }

  function getElevenLabsDesignOptions() {
    const panel = document.querySelector('#voices .provider[data-provider="eleven"] [data-epanel="create"]');
    const selects = [...(panel?.querySelectorAll('.form5 select') || [])];
    const styleText = String(selects[0]?.value || 'Anime').trim();
    const archetypeText = String(selects[1]?.value || 'Anime Heroine').trim();
    const gender = String(selects[2]?.value || 'Female').trim().toLowerCase();
    const age = String(selects[3]?.value || 'Young adult').trim();
    const temperament = String(selects[4]?.value || 'Bright / cheerful').trim();
    let archetype = archetypeText.toLowerCase();
    if (/villain/.test(archetype)) archetype='villain';
    else if (/heroine/.test(archetype)) archetype='heroine';
    else if (/\bhero\b/.test(archetype)) archetype='hero';
    else if (/rival/.test(archetype)) archetype='rival';
    else if (/healer/.test(archetype)) archetype='healer';
    else if (/mentor/.test(archetype)) archetype='mentor';
    else if (/tsundere/.test(archetype)) archetype='tsundere';
    else if (/sidekick/.test(archetype)) archetype='sidekick';
    else if (/chibi/.test(archetype)) archetype='chibi';
    else if (/mysterious/.test(archetype)) archetype='mysterious';
    else archetype='heroine';
    return {panel,style:/cartoon/i.test(styleText)?'cartoon':'anime',archetype,gender,age,temperament};
  }

  function renderElevenLabsCandidates() {
    const container = $('candidates');
    if (!container) return;
    container.replaceChildren();
    if (!elevenCandidates.length) {
      const empty=document.createElement('div'); empty.className='candidate';
      const title=document.createElement('b'); title.textContent='No candidates yet';
      const description=document.createElement('p'); description.className='muted';
      description.textContent='Generate temporary voice previews first. Choose one before creating it in My Voices.';
      empty.append(title,description); container.appendChild(empty);
      if ($('addPremium')) $('addPremium').disabled=true;
      return;
    }
    elevenCandidates.forEach((candidate,index)=>{
      const card=document.createElement('div'); card.className='candidate';
      card.style.cssText='border:1px solid '+(selectedElevenCandidate?.generated_voice_id===candidate.generated_voice_id?'#e63361':'rgba(148,163,184,.2)')+';border-radius:12px;padding:12px;margin:8px 0;background:rgba(9,12,18,.45)';
      const title=document.createElement('b'); title.textContent='Voice Design candidate '+(index+1);
      const info=document.createElement('p'); info.className='muted'; info.textContent=[candidate.gender,candidate.age,candidate.style,candidate.archetype].filter(Boolean).join(' · ');
      const audio=document.createElement('audio'); audio.controls=true; audio.preload='none';
      audio.style.cssText='display:block;width:100%;margin:8px 0';
      audio.src='data:audio/mpeg;base64,'+String(candidate.audio_base_64||'');
      const select=document.createElement('button'); select.type='button'; select.className='btn choose';
      select.textContent=selectedElevenCandidate?.generated_voice_id===candidate.generated_voice_id?'Selected':'Select this voice';
      select.addEventListener('click',()=>{
        selectedElevenCandidate=candidate;
        elevenCandidates.forEach((item,idx)=>{
          const other=container.children[idx];
          if(other)other.style.borderColor=item.generated_voice_id===candidate.generated_voice_id?'#e63361':'rgba(148,163,184,.2)';
          const button=other?.querySelector('button.choose');
          if(button)button.textContent=item.generated_voice_id===candidate.generated_voice_id?'Selected':'Select this voice';
        });
        if($('addPremium'))$('addPremium').disabled=false;
        if($('premiumName')&&!$('premiumName').value.trim())$('premiumName').value=(candidate.archetype||'Character')+' Voice '+(index+1);
      });
      card.append(title,info,audio,select); container.appendChild(card);
    });
    if ($('addPremium')) $('addPremium').disabled=!selectedElevenCandidate;
  }

  async function generateElevenLabsCandidates(appendMore = false) {
    const options=getElevenLabsDesignOptions();
    if (!options.panel) throw new Error('ElevenLabs Voice Design panel is unavailable.');
    const button = $(appendMore?'generateMore':'generateCandidates');
    if (button) {button.disabled=true;button.textContent='Generating…'}
    try {
      const result=await call('voice.elevenlabs.design',{
        style:options.style,archetype:options.archetype,gender:options.gender,
        age:options.age,temperament:options.temperament,seed:elevenDesignSeed++
      });
      const generated=Array.isArray(result.candidates)?result.candidates:[];
      if(!appendMore)elevenCandidates=[];
      elevenCandidates.push(...generated);
      selectedElevenCandidate=null;
      renderElevenLabsCandidates();
      message('Generated '+generated.length+' real ElevenLabs preview(s). Select one to create it in My Voices.');
    } finally {
      if(button){button.disabled=false;button.textContent=appendMore?'Generate 3 More':'Generate 3 Premium Character Voices'}
    }
  }

  async function createSelectedElevenLabsVoice() {
    if(!selectedElevenCandidate)throw new Error('Select one generated voice preview first.');
    const options=getElevenLabsDesignOptions();
    const input=$('premiumName');
    const initialName=String(input?.value||'').trim();
    if(!initialName)throw new Error('Enter a name for the selected premium voice.');
    const name=await requestVoiceProfileSaveName(initialName,'eleven','ElevenLabs Voice Design preview','eleven-create');
    if(!name){message('Premium voice creation cancelled.');return;}
    if(input)input.value=name;
    const created=await call('voice.elevenlabs.create',{
      generated_voice_id:selectedElevenCandidate.generated_voice_id,name,
      voice_description:selectedElevenCandidate.description||'',
      style:options.style,gender:options.gender,age:options.age
    });
    selectedVoice=created.name;selectedVoiceId=created.voice_id;
    if($('profileName'))$('profileName').value=created.name;
    if($('profileLibrary'))$('profileLibrary').textContent='elevenlabs';
    if($('profileVoice'))$('profileVoice').textContent=created.voice_id;
    if($('previewProfile'))$('previewProfile').textContent=created.name;
    if($('addPremium'))$('addPremium').disabled=true;
    await refreshVoices();
    await refreshProviderCatalog('eleven',true);
    message('Created the voice in ElevenLabs and saved its local Ryu profile. Narrator assignment is still explicit.');
  }

  function applyVoiceDesignPreset(button) {
    const panel=document.querySelector('.provider[data-provider="voicedesign"]'),textarea=panel?.querySelector('textarea');
    if(!panel||!textarea)return;
    const preset=String(button.textContent||'').trim().toLowerCase();
    const prompts={
      'anime heroine':'Young adult female voice, bright and warm, slightly playful anime heroine timbre, clear natural English diction, expressive emotional reactions and cinematic storytelling.',
      'anime hero':'Young adult male voice, confident and warm anime hero timbre, clear natural English diction, determined energy with sincere emotional range and cinematic storytelling.',
      'anime rival':'Young adult voice with cool controlled intensity, precise diction, restrained emotion, competitive edge and a confident, slightly mysterious anime rival presence.',
      'anime villain':'Mature, controlled voice with elegant menace, precise diction, quiet intensity and theatrical restraint for a fictional anime villain.',
      'anime healer':'Gentle, reassuring voice with soft warmth, sincere emotion, clear diction and a calm, supportive anime healer presence.',
      'custom description':''
    };
    if(!(preset in prompts))return;
    invalidateVoicePreview();selectedVoice=null;selectedVoiceId=null;selectedVoiceProvider='qwen-character';profileEditOriginalName='';
    clearSavedProfileSelection();
    panel.querySelectorAll('.preset').forEach(item=>item.classList.toggle('active',item===button));
    textarea.value=prompts[preset];
    const label=String(button.textContent||'Custom Description').trim(),name='Qwen VoiceDesign · '+label;
    if($('profileName'))$('profileName').value=name;if($('premiumName'))$('premiumName').value=name;
    if($('profileLibrary'))$('profileLibrary').textContent='Qwen VoiceDesign';
    if($('profileVoice'))$('profileVoice').textContent=label;
    if($('previewProfile'))$('previewProfile').textContent=name;
    if($('sumProfile'))$('sumProfile').textContent='Unsaved';
    const assigned=$('assignedSide');if(assigned)assigned.textContent='';const p=assigned?.closest('p');if(p)p.hidden=true;
    updateVoiceSummary({name,provider:'qwen-character',qwen_mode:'design'},{saved:false,previewReady:false,assignment:''});
    textarea.dispatchEvent(new Event('input',{bubbles:true}));updateVoiceActionButtons();
    message('VoiceDesign preset selected: '+label+'. The previous saved profile is no longer selected; save and preview this voice separately.');
  }

  function requestVoiceProfileSaveName(initialName, providerKey, voiceLabel, purpose = 'profile') {
    return new Promise(resolve => {
      $('ryuVoiceProfileSaveConfirm')?.remove();
      const providerNames = {offline:'Offline Neural Voices',sapi:'Windows SAPI',customvoice:'Qwen CustomVoice',voicedesign:'Qwen VoiceDesign',qwenclone:'Qwen Voice Clone',customref:'Reference Voice',edge:'Edge TTS',eleven:'ElevenLabs'};
      const overlay = document.createElement('div');
      overlay.id = 'ryuVoiceProfileSaveConfirm';
      overlay.style.cssText = 'position:fixed;inset:0;z-index:100000;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(3,5,10,.78);backdrop-filter:blur(7px)';
      const panel = document.createElement('section');
      panel.setAttribute('role','dialog'); panel.setAttribute('aria-modal','true');
      panel.setAttribute('aria-labelledby','ryuVoiceSaveTitle');
      panel.style.cssText = 'box-sizing:border-box;width:min(460px,100%);background:#151a25;border:1px solid rgba(255,255,255,.13);border-radius:18px;box-shadow:0 24px 80px rgba(0,0,0,.5);padding:22px;color:#f4f5f8';
      const eyebrow = document.createElement('div');
      const creatingProviderVoice = purpose === 'eleven-create';
      eyebrow.textContent = creatingProviderVoice ? 'CREATE PROVIDER VOICE' : 'CONFIRM VOICE PROFILE';
      eyebrow.style.cssText = 'color:#e8b957;font-size:11px;font-weight:800;letter-spacing:.13em;margin-bottom:8px';
      const title = document.createElement('h2');
      title.id = 'ryuVoiceSaveTitle'; title.textContent = creatingProviderVoice ? 'Create this premium voice?' : 'Save this voice profile?';
      title.style.cssText = 'margin:0 0 8px;font-size:22px';
      const description = document.createElement('p');
      description.textContent = creatingProviderVoice
        ? 'This sends the selected temporary preview to your ElevenLabs account to create a persistent provider voice, then saves a local Ryu profile. It may use your provider plan quota. It will not change your narrator until you explicitly assign it.'
        : 'This saves profile settings locally. It does not generate audio or change your narrator until you choose “Save and Use as Narrator”.';
      description.style.cssText = 'margin:0 0 16px;color:#aeb6c5;font-size:13px;line-height:1.5';
      const providerLabel = document.createElement('div');
      providerLabel.textContent = 'Voice library · ' + (providerNames[providerKey] || providerKey);
      providerLabel.style.cssText = 'font-size:13px;font-weight:700;margin:8px 0';
      const voiceLine = document.createElement('div');
      voiceLine.textContent = 'Selected voice / model · ' + (voiceLabel || 'Provider default');
      voiceLine.style.cssText = 'font-size:13px;font-weight:700;margin:8px 0 16px;overflow-wrap:anywhere';
      const label = document.createElement('label');
      label.htmlFor = 'ryuVoiceProfileNameConfirm'; label.textContent = 'Profile name (editable)';
      label.style.cssText = 'display:block;font-size:12px;color:#aeb6c5;margin:12px 0 6px';
      const input = document.createElement('input');
      input.id = 'ryuVoiceProfileNameConfirm'; input.maxLength = 160; input.value = initialName || '';
      input.style.cssText = 'box-sizing:border-box;width:100%;padding:12px;border-radius:10px;border:1px solid #42495a;background:#0c1018;color:#f6f7fa;font:inherit;outline-color:#e63361';
      const actions = document.createElement('div');
      actions.style.cssText = 'display:flex;justify-content:flex-end;gap:10px;margin-top:20px;flex-wrap:wrap';
      const cancel = document.createElement('button');
      cancel.type = 'button'; cancel.textContent = 'Cancel';
      cancel.style.cssText = 'padding:10px 14px;border-radius:10px;background:#1c2230;border:1px solid #343b4a;color:#f2f4f8;font-weight:700;cursor:pointer';
      const save = document.createElement('button');
      save.type = 'button'; save.textContent = creatingProviderVoice ? 'Confirm & Create Voice' : 'Confirm & Save Profile';
      save.style.cssText = 'padding:10px 16px;border-radius:10px;background:#c92050;border:1px solid #e7426a;color:white;font-weight:800;cursor:pointer';
      actions.append(cancel,save);
      panel.append(eyebrow,title,description,providerLabel,voiceLine,label,input,actions);
      overlay.append(panel);
      let finished = false;
      const finish = value => { if (finished) return; finished = true; overlay.remove(); resolve(value); };
      cancel.addEventListener('click', () => finish(null));
      save.addEventListener('click', () => {
        const value = String(input.value || '').trim();
        if (!value) { input.focus(); message('Enter a profile name before saving.', true); return; }
        finish(value);
      });
      overlay.addEventListener('click', event => { if (event.target === overlay) finish(null); });
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); save.click(); }
        if (event.key === 'Escape') { event.preventDefault(); finish(null); }
      });
      document.body.appendChild(overlay);
      input.focus(); input.select();
    });
  }

  async function importSelectedReferenceFile(file, profileName) {
    if (!file) throw new Error('Choose a reference audio file before saving this clone profile.');
    const maxBytes = 25 * 1024 * 1024;
    if (file.size > maxBytes) throw new Error('Reference audio must be smaller than 25 MB.');
    const suffix = String(file.name || '').split('.').pop().toLowerCase();
    const allowed = new Set(['wav','mp3','flac','ogg','m4a','aac','aiff','opus']);
    if (!allowed.has(suffix)) throw new Error('Choose a WAV, MP3, FLAC, OGG, M4A, AAC, AIFF or OPUS reference audio file.');
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    const chunk = 0x8000;
    for (let offset = 0; offset < bytes.length; offset += chunk) {
      binary += String.fromCharCode(...bytes.subarray(offset, Math.min(offset + chunk, bytes.length)));
    }
    const result = await call('voice.import_reference', {
      profile_name:profileName,
      filename:String(file.name || 'reference.' + suffix),
      content_base64:btoa(binary)
    });
    if (result.cancelled || !result.sample_path) throw new Error('Reference audio was not imported.');
    return result.sample_path;
  }

  async function saveVoice(options = {}) {
    const name = String(options.nameOverride ?? ($('profileName')?.value || $('premiumName')?.value || '')).trim();
    const originalName = String(options.originalNameOverride ?? selectedVoice ?? profileEditOriginalName ?? '').trim();
    const existingSavedProfile = voices.find(profile =>
      profile.saved === true && profile.name.toLowerCase() === originalName.toLowerCase()
    ) || null;
    const choice = document.querySelector('.provider.active')?.dataset.provider || 'offline';
    const providerMap = {offline:'piper',sapi:'windows-sapi',customvoice:'qwen-character',voicedesign:'qwen-character',qwenclone:'qwen-character',customref:'chatterbox',edge:'edge-tts',eleven:'elevenlabs'};
    const provider = choice === 'offline'
      ? (existingSavedProfile?.provider || selectedVoiceProvider || 'piper')
      : (providerMap[choice] || (choice.includes('clone') ? 'qwen-character' : 'piper'));
    const voiceLabel = $('profileVoice')?.textContent?.trim() || selectedVoiceId || 'Amy';
    if (!options.confirmed) {
      const confirmedName = await requestVoiceProfileSaveName(name, choice, voiceLabel);
      if (!confirmedName) { message('Voice profile save cancelled.'); return null; }
      return saveVoice({
        confirmed:true, nameOverride:confirmedName,
        originalNameOverride:options.originalNameOverride ?? existingSavedProfile?.name ?? ''
      });
    }
    if (!name) throw new Error('Enter a profile name before saving.');
    if (name.length > 160) throw new Error('Profile names must be 160 characters or fewer.');

    const providerPanel = document.querySelector('#voices .provider[data-provider="' + choice + '"]');
    const referenceFile = providerPanel?.querySelector('input[type="file"]')?.files?.[0];
    const authorized = Boolean($('clonePermission')?.checked || $('customPermission')?.checked || existingSavedProfile?.authorized);
    let sample_path = String(existingSavedProfile?.sample_path || '');
    if (provider === 'chatterbox' || (provider === 'qwen-character' && /clone/i.test(choice))) {
      if (!authorized) throw new Error('Confirm you have permission to use this reference recording.');
      if (referenceFile) sample_path = await importSelectedReferenceFile(referenceFile, name);
      if (!sample_path) throw new Error('Choose a reference audio file before saving this clone profile.');
    }

    const matchedPiper = voices.find(v => v.provider === 'piper' && String(v.voice_id || '').toLowerCase().includes(voiceLabel.toLowerCase()));
    const designPanel = document.querySelector('.provider[data-provider="voicedesign"]');
    const designPrompt = designPanel?.querySelector('textarea')?.value?.trim() || '';
    const designLanguage = designPanel?.querySelector('select')?.value || existingSavedProfile?.language || 'English';
    const rawSeed = Number(designPanel?.querySelector('input[type="number"]')?.value || 0);
    const designSeed = Number.isFinite(rawSeed) && rawSeed > 0 ? Math.trunc(rawSeed) : null;
    if (choice === 'voicedesign' && !designPrompt) throw new Error('Enter a voice description before saving a VoiceDesign profile.');
    const qwenMode = choice === 'voicedesign' ? 'design' : choice === 'qwenclone' ? 'clone' : (existingSavedProfile?.qwen_mode || 'custom');
    const qwenDefaultSpeaker = ({English:'Ryan',Chinese:'Serena',Japanese:'Ono_Anna',Korean:'Sohee'}[designLanguage] || 'Ryan');
    const qwenSelectedSpeaker = selectedVoiceId && !/custom description|reference voice|custom voice description/i.test(selectedVoiceId)
      ? selectedVoiceId : (/custom description|reference voice|custom voice description/i.test(voiceLabel) || choice === 'voicedesign' || choice === 'qwenclone' ? qwenDefaultSpeaker : (voiceLabel || qwenDefaultSpeaker));
    const voice_id = provider === 'piper'
      ? (selectedVoiceId || matchedPiper?.voice_id || voices.find(v => v.name === name)?.voice_id || 'en_US-amy-medium')
      : provider === 'qwen-character'
        ? qwenSelectedSpeaker
        : (selectedVoiceId || voiceLabel || name);
    const currentCatalogEntry = providerCatalogs[choice]?.voices?.find(row => String(row.voice_id || '') === String(selectedVoiceId || ''));
    const result = await call('voice.save', {
      name, original_name:options.originalNameOverride ?? existingSavedProfile?.name ?? '',
      provider, voice_id, sample_path, authorized,
      model_id:existingSavedProfile?.model_id || (provider === 'chatterbox' ? 'chatterbox' : provider === 'qwen-character' ? 'auto' : provider),
      backend:existingSavedProfile?.backend || (['piper','kokoro','qwen-character'].includes(provider) ? 'automatic' : provider),
      language:choice === 'voicedesign' ? designLanguage : (existingSavedProfile?.language || currentCatalogEntry?.language || 'English'),
      qwen_mode:provider === 'qwen-character' ? qwenMode : (existingSavedProfile?.qwen_mode || 'custom'),
      qwen_prompt:choice === 'voicedesign' ? designPrompt : (existingSavedProfile?.qwen_prompt || ''),
      qwen_seed:choice === 'voicedesign' ? designSeed : (existingSavedProfile?.qwen_seed ?? null),
      qwen_profile_id:existingSavedProfile?.qwen_profile_id || '',
      qwen_anchor_path:existingSavedProfile?.qwen_anchor_path || '',
      qwen_anchor_text:existingSavedProfile?.qwen_anchor_text || '',
      notes:choice === 'voicedesign' ? designPrompt : (existingSavedProfile?.notes || ''),
      exaggeration:existingSavedProfile?.exaggeration ?? 0.5,
      cfg_weight:existingSavedProfile?.cfg_weight ?? 0.35,
      style_preset:existingSavedProfile?.style_preset || 'Natural',
      reference_text:$('cloneTranscript')?.value || existingSavedProfile?.reference_text || ''
    });
    selectedVoice=result.name;profileEditOriginalName=result.name;selectedVoiceId=result.voice_id;selectedVoiceProvider=result.provider;
    await refreshVoices();
    if(voicePreviewValid)lastVoicePreviewProfileName=result.name;
    if ($('profileName')) $('profileName').value = result.name;
    if ($('premiumName')) $('premiumName').value = result.name;
    const savedSelect = document.querySelector('#voices .panel[data-panel="3"] .toolbar select');
    if (savedSelect) savedSelect.value = result.name;
    document.querySelectorAll('#voices *').forEach(node => {
      if (node.children.length === 0 && node.textContent.trim() === 'Unsaved') node.textContent = 'Saved';
    });
    if ($('profileLibrary')) $('profileLibrary').textContent=({'piper':'Offline Neural Voices','kokoro':'Offline Neural Voices','qwen-character':result.qwen_mode==='design'?'Qwen VoiceDesign':/clone/i.test(result.qwen_mode||'')?'Qwen Voice Clone':'Qwen CustomVoice','windows-sapi':'Windows SAPI','edge-tts':'Edge TTS','elevenlabs':'ElevenLabs','chatterbox':'Reference Voice'})[result.provider]||result.provider;
    if ($('profileVoice')) $('profileVoice').textContent=result.voice_id||result.name;
    if ($('previewProfile')) $('previewProfile').textContent=result.name;
    updateVoiceSummary({...result,saved:true},{saved:true,previewReady:voicePreviewValid,assignment: $('sumAssign')?.textContent || ''});
    void refreshAssignedCharacterForProfile({...result,saved:true});updateVoiceActionButtons();
    message('Saved voice profile locally: '+result.name);
    return result;
  }

  async function startImportPayload(payload, displayName) {
    if ($('importStatus')) $('importStatus').textContent = 'Importing ' + displayName + '…';
    if ($('importBar')) $('importBar').style.width = '5%';
    const result = await call('import.start', payload);
    if (result.job_id) await monitorJob(result.job_id, async () => {
      await refreshProjects(); await refreshChapters();
      if (typeof window.go === 'function') window.go('chapters');
    });
    else { await refreshProjects(); await refreshChapters(); message('Book imported into the local library.'); }
  }
  async function importBook() {
    const chosen = await call('import.choose_file');
    if (chosen.cancelled || !chosen.path) return;
    const name = chosen.path.split(/[\\/]/).pop();
    await startImportPayload({file_path:chosen.path,title:name.replace(/\.[^.]+$/,'')}, name);
  }
  async function importDroppedFile(file) {
    if (!file) return;
    const suffix = (file.name.match(/\.[^.]+$/) || [''])[0].toLowerCase();
    if (!['.epub','.pdf','.txt','.docx'].includes(suffix)) {
      throw new Error('Unsupported file type. Use EPUB, PDF, TXT, or DOCX.');
    }
    if (!file.size) throw new Error('The selected file is empty.');
    if (file.size > 25 * 1024 * 1024) {
      throw new Error('Dropped files are limited to 25 MB. Use Browse files for larger books.');
    }
    if ($('importStatus')) $('importStatus').textContent = 'Reading ' + file.name + '…';
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = '';
    const chunkSize = 0x8000;
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(offset, Math.min(offset + chunkSize, bytes.length)));
    }
    await startImportPayload({file_name:file.name,title:file.name.replace(/\.[^.]+$/,''),content_base64:btoa(binary)}, file.name);
  }
  function formatPlaybackTime(value){const seconds=Math.max(0,Math.floor(Number(value)||0));return String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');}
  function syncPreviewPlaybackTime(){
    const time=formatPlaybackTime(previewAudio?.currentTime||0)+' / '+formatPlaybackTime(previewAudio?.duration||0);
    const voiceTime=$('previewPlaybackTime'),productionTime=$('productionPreviewTime');
    if(voiceTime)voiceTime.textContent=time;
    if(productionTime)productionTime.textContent=time;
    syncProductionPreviewControls();
  }
  function preparePreviewPlayback(job, requestedSeconds, options = {}) {
    const url=job?.result?.file_url,actual=Number(job?.result?.actual_duration_seconds),requested=Number(requestedSeconds||job?.result?.requested_duration_seconds||0),play=$('playPreview');
    const totalElapsed = Number(job?.result?.total_seconds);
    const synthesisElapsed = Number(job?.result?.synthesis_seconds);
    const realTimeFactor = Number(job?.result?.real_time_factor);
    const performanceTargetMet = job?.result?.performance_target_met;
    if(!url||!Number.isFinite(actual)||actual<=0){
      voicePreviewValid=false;lastVoicePreviewPath=null;lastVoicePreviewChapterNumber=null;lastVoicePreviewChapterTitle='';if(play)play.disabled=true;if($('downloadPreview'))$('downloadPreview').disabled=true;
      if($('previewState'))$('previewState').textContent='Failed';
      if($('validation'))$('validation').textContent=!url?'Preview job completed without a playable local audio file. Check the job details and retry.':'Preview job completed without a valid measured audio duration. The result cannot be marked ready.';
      updateVoiceActionButtons();return false;
    }
    if(previewAudio){previewAudio.pause();previewAudio=null;}
    previewAudio=new Audio(url);previewAudio.preload='auto';previewAudio.volume=previewVolume;
    lastVoicePreviewPath=String(job?.result?.output_path||'');lastVoicePreviewProfileName=String(options.profileName||currentVoiceName());lastVoicePreviewChapterNumber=Number(job?.result?.chapter_number)||null;lastVoicePreviewChapterTitle=String(job?.result?.chapter_title||'');voicePreviewValid=Boolean(lastVoicePreviewPath);
    previewAudio.ontimeupdate=syncPreviewPlaybackTime;previewAudio.onloadedmetadata=syncPreviewPlaybackTime;
    previewAudio.onplay=()=>{if(play)play.textContent='Ⅱ Pause';if($('wave'))$('wave').classList.add('playing');syncPreviewPlaybackTime();};
    previewAudio.onpause=()=>{if(play)play.textContent='▶ Play';if($('wave'))$('wave').classList.remove('playing');syncPreviewPlaybackTime();};
    previewAudio.onended=()=>{if(play)play.textContent='▶ Play';if($('wave'))$('wave').classList.remove('playing');syncPreviewPlaybackTime();};
    previewAudio.onerror=()=>{voicePreviewValid=false;if(play)play.disabled=true;if($('downloadPreview'))$('downloadPreview').disabled=true;if($('previewState'))$('previewState').textContent='Playback error';if($('validation'))$('validation').textContent='The preview file exists but the embedded player could not open it. Generate another preview and check the local audio runtime.';updateVoiceActionButtons();};
    if(play)play.disabled=false;if($('downloadPreview'))$('downloadPreview').disabled=false;
    if($('previewState'))$('previewState').textContent='Ready · 100%';if($('previewProgress'))$('previewProgress').style.width='100%';
    const timingNote = Number.isFinite(totalElapsed) && totalElapsed >= 0
      ? ' · generated in ' + totalElapsed.toFixed(1) + 's' +
        (Number.isFinite(synthesisElapsed) ? ' synthesis ' + synthesisElapsed.toFixed(1) + 's' : '') +
        (Number.isFinite(realTimeFactor) ? ' (' + realTimeFactor.toFixed(2) + '× real time)' : '') +
        (requested === 30 && performanceTargetMet === false ? ' · exceeds 30s preview target (<60s generation)' : '')
      : '';
    if($('validation'))$('validation').textContent=requested>0&&actual+1.5<requested
      ?'Preview shorter than requested · '+actual.toFixed(1)+'s of '+requested.toFixed(0)+'s. The source text or voice provider produced less audio than requested; try a longer passage and check the selected voice.'+timingNote
      :'Preview ready · '+actual.toFixed(1)+' seconds'+(requested>0?' (requested '+requested.toFixed(0)+'s)':'')+timingNote;
    syncPreviewPlaybackTime();
    if(!options.preserveSummary) updateVoiceSummary({name:currentVoiceName(),provider:selectedVoiceProvider||({offline:'piper',sapi:'windows-sapi',customvoice:'qwen-character',voicedesign:'qwen-character',qwenclone:'qwen-character',customref:'chatterbox',edge:'edge-tts',eleven:'elevenlabs'}[document.querySelector('#voices .provider.active')?.dataset.provider]||'piper'),qwen_mode:document.querySelector('#voices .provider.active')?.dataset.provider==='voicedesign'?'design':'custom'},
      {saved:Boolean(selectedVoice),previewReady:true,assignment: $('sumAssign')?.textContent || ''});
    updateVoiceActionButtons();return voicePreviewValid;
  }



  function characterPassageFromButton(button) {
    const id = String(button?.dataset?.dialogueId || '');
    const existing = (window.ryuPremiumDialogueReviewItems || []).find(item => String(item.id) === id);
    if (existing) return existing;
    const number = Number(button?.dataset?.chapterNumber);
    const start = Number(button?.dataset?.start), end = Number(button?.dataset?.end);
    const chapter = chapters.find(item => Number(item.number) === number);
    if (!chapter || !Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start) return null;
    const text = String(chapter.text || '').slice(start, end);
    if (!text) return null;
    return {id:id || ('dialogue-' + number + '-' + start + '-' + end), chapter_number:number,
      chapter_title:chapter.title, start, end, text, source_text:text, speakers:[],
      assigned:false, assignmentPresent:false, skipped:false, suggestions:[]};
  }
  async function openAiCharacterReview(item) {
    if (!item || !item.text) throw new Error('This source passage is no longer available. Refresh the chapter and select it again.');
    await refreshCharacterLibrary().catch(error => console.warn('[Ryu AI review library]', error));
    window.ryuPremiumSelectedDialogueId = String(item.id || '');
    window.ryuPremiumAiChapterNumber = Number(item.chapter_number);
    window.ryuPremiumPendingDialogueText = String(item.text);
    window.ryuPremiumPendingDialogueChapter = Number(item.chapter_number);
    window.ryuPremiumPendingDialogueStart = Number(item.start);
    window.ryuPremiumPendingDialogueEnd = Number(item.end);
    window.ryuPremiumPendingDialogueId = String(item.id || '');
    if ($('aiSelectedSentence')) $('aiSelectedSentence').textContent = String(item.text);
    const projectOptions = characters.map(c => ({
      name:characterCanonical(c), series:characterSeries(c), profile:String(c.voice_profile || ''),
      aliases:characterAliases(c), source:'project'
    }));
    const libraryOptions = libraryCharacters.map(c => ({
      name:characterCanonical(c), series:characterSeries(c), profile:String(c.voice_profile || c.voice || ''),
      aliases:characterAliases(c), source:'library'
    }));
    const projectSeriesKey = activeCharacterProjectSeries().toLowerCase();
    const suggestions = Array.isArray(item.suggestions) ? item.suggestions.filter(c => c && c.name).slice().sort((left,right) => {
      const lc = Number(left.confidence || 0), rc = Number(right.confidence || 0);
      if (Math.abs(lc - rc) > 0.025) return rc - lc;
      const leftActive = String(left.series || '').toLowerCase() === projectSeriesKey ? 1 : 0;
      const rightActive = String(right.series || '').toLowerCase() === projectSeriesKey ? 1 : 0;
      return rightActive - leftActive || String(left.name).localeCompare(String(right.name));
    }) : [];
    const candidateHtml = suggestions.length ? suggestions.map((candidate,index) => {
      const name = String(candidate.name || '').trim();
      const matchesName = row => row.name.toLowerCase() === name.toLowerCase()
        || row.aliases.some(alias => alias.toLowerCase() === name.toLowerCase());
      const hintedSeries = String(candidate.series || '').trim();
      const linked = (hintedSeries
        ? [...projectOptions,...libraryOptions].find(row => matchesName(row) && row.series.toLowerCase() === hintedSeries.toLowerCase())
        : null) || projectOptions.find(matchesName) ||
        libraryOptions.find(row => matchesName(row) && row.series.toLowerCase() === activeCharacterProjectSeries().toLowerCase()) ||
        libraryOptions.find(matchesName);
      const candidateSeries = String(linked?.series || hintedSeries || activeCharacterProjectSeries());
      const probability = Number(candidate.confidence || 0);
      const isActive = item.speakers?.some(s => String(s).toLowerCase() === name.toLowerCase()) &&
        (!item.assignmentSeries || candidateSeries.toLowerCase() === String(item.assignmentSeries).toLowerCase()) ||
        (!item.assigned && index === 0);
      const evidence = String(candidate.evidence || 'Local dialogue-context suggestion');
      return '<button type="button" class="prediction-option ryu-ai-option' + (isActive ? ' active' : '') +
        '" data-prediction="' + esc(name) + '" data-series="' + esc(candidateSeries) +
        '" data-profile="' + esc(linked?.profile || '') + '" data-source="ai" data-confidence="' + esc(probability) + '"><b>' + esc(name) + '</b><small>' +
        esc(candidateSeries) + ' · ' + Math.round(probability * 100) + '% · ' + esc(evidence) + '</small></button>';
    }).join('') : '<p class="muted">No ranked AI suggestion is available for this passage. Choose a saved character below or create a new one.</p>';
    const seen = new Set();
    const savedOptions = [...projectOptions,...libraryOptions].filter(row => {
      const key = row.name.toLowerCase() + '::' + row.series.toLowerCase();
      if (!row.name || seen.has(key)) return false;
      seen.add(key); return true;
    });
    const savedHtml = savedOptions.map((row,index) => {
      const active = item.speakers?.some(s => String(s).toLowerCase() === row.name.toLowerCase()) &&
        (!item.assignmentSeries || row.series.toLowerCase() === String(item.assignmentSeries).toLowerCase());
      return '<button type="button" class="prediction-option ryu-ai-option' + (active ? ' active' : '') +
        '" data-prediction="' + esc(row.name) + '" data-series="' + esc(row.series) + '" data-profile="' +
        esc(row.profile) + '" data-source="' + esc(row.source) + '"><b>' + esc(row.name) +
        '</b><small>' + esc(row.series) + ' · ' + esc(row.profile || 'No audio profile assigned') +
        (row.source === 'library' ? ' · Character Library' : ' · This project') + '</small></button>';
    }).join('') || '<p class="muted">No saved characters exist yet. Use New character to create one in a series.</p>';
    const savedVoiceProfiles = characterSavedProfiles();
    const profileOptions = ['<option value="">No character voice profile yet</option>',
      ...savedVoiceProfiles.map(profile => '<option value="' + esc(profile.name) + '">' +
        esc(profile.name) + ' · ' + esc(profile.provider || 'Voice') + '</option>')
    ].join('');
    const profileSelector = '<div class="ryu-character-subsection" style="margin-top:12px">Character audio profile</div>' +
      '<label class="ryu-ai-profile-selector" style="display:grid;gap:6px;margin:0 0 12px">' +
      '<span>Assign a saved Voice Studio profile now (or assign one later)</span>' +
      '<select id="aiCharacterVoiceProfile" style="width:100%;min-width:0">' + profileOptions + '</select></label>';
    if ($('predictionList')) $('predictionList').innerHTML =
      '<div class="ryu-character-subsection">AI suggestions</div>' + candidateHtml +
      '<div class="ryu-character-subsection">Saved / manually created characters</div>' + savedHtml +
      profileSelector;
    const initialChoice = $('predictionList')?.querySelector('.prediction-option.active');
    const initialProfile = String(initialChoice?.dataset.profile || '');
    if ($('aiCharacterVoiceProfile') && savedVoiceProfiles.some(profile => profile.name === initialProfile)) {
      $('aiCharacterVoiceProfile').value = initialProfile;
    }
    if ($('confirmAiCharacter')) $('confirmAiCharacter').disabled = !(suggestions.length || savedOptions.length);
    const removeButton = ensureDialogueUnassignButton();
    if (removeButton) removeButton.hidden = !(item.assignmentPresent || item.assigned);
    $('aiPredictionModal')?.classList.add('show');
    renderAiChapterDocument();
    renderCharacterStudioLive();
  }
  function openCharacterEditorForSelected() {
    const selected = selectedCharacterRow();
    if (!selected) throw new Error('Select a real character from this project before editing.');
    libraryEditorActive = false;
    ensureCharacterSeriesField();
    if ($('characterEditorTitle')) $('characterEditorTitle').textContent = 'Edit character';
    if ($('editCharacterName')) $('editCharacterName').value = selected.name || '';
    if ($('editCharacterShort')) $('editCharacterShort').value = selected.short_description || selected.short || '';
    if ($('editCharacterAliases')) $('editCharacterAliases').value = characterAliases(selected).join(', ');
    if ($('editCharacterVoice')) {
      const saved = characterSavedProfiles();
      $('editCharacterVoice').innerHTML = '<option value="">Unassigned</option>' + saved.map(profile =>
        '<option value="' + esc(profile.name) + '">' + esc(profile.name) + ' · ' + esc(profile.provider || 'Voice') + '</option>'
      ).join('');
      $('editCharacterVoice').value = selected.voice_profile || '';
      $('editCharacterVoice').disabled = saved.length === 0;
    }
    if ($('editCharacterScope')) $('editCharacterScope').value = selected.scope || 'Current book only';
    populateEditCharacterSeriesOptions(characterSeries(selected));
    if ($('editCharacterSeries')) $('editCharacterSeries').value = characterSeries(selected);
    if ($('editCharacterNotes')) $('editCharacterNotes').value = selected.notes || '';
    if ($('deleteCharacter')) $('deleteCharacter').style.visibility = 'visible';
    $('characterEditorModal')?.classList.add('show');
  }
  async function saveCharacterEditorForProject() {
    const current = selectedCharacterRow();
    const name = String($('editCharacterName')?.value || '').trim();
    const series = getEditCharacterSeriesValue();
    if (!current || !name) throw new Error('Select a saved project character and enter its canonical name.');
    if (!series) throw new Error('Choose an existing series or create a new series before saving this character.');
    const result = await call('character.update', {
      original_name:characterCanonical(current),
      original_series:characterSeries(current),
      name,
      short_description:$('editCharacterShort')?.value || '',
      aliases:$('editCharacterAliases')?.value || '',
      voice_profile:String($('editCharacterVoice')?.value ?? current.voice_profile ?? ''),
      series, scope:series ? 'Series · ' + series : 'Current book only',
      notes:$('editCharacterNotes')?.value || ''
    });
    window.ryuPremiumSelectedCharacter = name;
    window.ryuPremiumSelectedCharacterSeries = series;
    window.ryuPremiumSelectedAssignedDialogueKey = '';
    $('characterEditorModal')?.classList.remove('show');
    await refreshCharacters();
    await refreshCharacterLibrary();
    message('Character details and series saved to the project and Character Library.');
    return result;
  }
  async function deleteSelectedProjectCharacter() {
    const current = selectedCharacterRow();
    if (!current) throw new Error('Select a real project character before deleting.');
    const name = characterCanonical(current);
    if (!window.confirm('Dismiss "' + name + '" from this project cast and prevent Character Analysis from automatically adding it again in "' + characterSeries(current) + '"? Saved dialogue assignments must be cleared first. The reusable Character Library entry is retained; explicitly adding it again from the Library restores detection for this series.')) return;
    await call('character.delete', {name, series:characterSeries(current)});
    window.ryuPremiumSelectedCharacter = '';
    window.ryuPremiumSelectedCharacterSeries = '';
    window.ryuPremiumSelectedAssignedDialogueKey = '';
    $('characterEditorModal')?.classList.remove('show');
    await refreshCharacters(); await refreshCharacterLibrary();
    message('Removed ' + name + ' from this project cast.');
  }
  async function testSelectedCharacterVoice() {
    const current = selectedCharacterRow();
    if (!current) throw new Error('Select a character from the active project cast first.');
    const selectedProfileName = String($('assignedAudioProfile')?.value ?? current.voice_profile ?? '').trim();
    const profile = characterProfileByName(selectedProfileName);
    if (!profile) throw new Error('Choose a saved audio profile first.');
    const assignments = characterVoiceAssignments(current.name, characterSeries(current));
    const selectedKey = String(window.ryuPremiumSelectedAssignedDialogueKey || '');
    const selected = assignments.passages.find(row =>
      characterAssignmentKey(current.name, characterSeries(current)) + '::' +
        row.chapter_number + ':' + row.start + ':' + row.end === selectedKey
    );
    if (!selected) throw new Error('Select a saved dialogue row in the Assigned Cast inspector before testing voice.');
    const previewSavedVoice = window.__ryuPreviewSavedProfile;
    if (typeof previewSavedVoice !== 'function') {
      throw new Error('The shared Voice Studio preview service is not ready. Re-enter Voice Studio and retry.');
    }
    await previewSavedVoice(profile, String(selected.text || ''), current.name, {routeCharacterCast:false});
  }
  function installCharacterStudioHandlers() {
    if (characterStudioCaptureBound) return;
    characterStudioCaptureBound = true;
    document.addEventListener('input', event => {
      const target = event.target;
      if (!target || !['manualChapterSearch','assignedSearch','assignCharacterSearch'].includes(target.id)) return;
      event.stopImmediatePropagation();
      if (target.id === 'manualChapterSearch' || target.id === 'assignedSearch') renderCharacterStudioLive();
      if (target.id === 'assignCharacterSearch') renderManualCharacterChoices();
    }, true);
    document.addEventListener('click', event => {
      const button = event.target?.closest?.('button');
      if (!button) return;
      const handle = fn => { event.preventDefault(); event.stopImmediatePropagation(); void Promise.resolve().then(fn).catch(error => message(error?.message || String(error), true)); };
      const mode = button.closest('#characters [data-char-mode]');
      if (mode) { handle(() => setCharacterStudioMode(mode.dataset.charMode)); return; }
      const filter = button.closest('#characters [data-ch-filter]');
      if (filter) {
        handle(() => {
          document.querySelectorAll('#characters [data-ch-filter]').forEach(item => item.classList.toggle('active', item === filter));
          renderCharacterStudioLive();
        });
        return;
      }
      if (button.id === 'openCharacterLibrary' || button.id === 'chooseFromLibrary') {
        handle(async () => {
          closeCharacterAssignmentPopover();
          document.querySelector('[data-page="library"]')?.click();
          setTimeout(() => $('characterLibraryZone')?.scrollIntoView({behavior:'smooth',block:'start'}), 180);
        });
        return;
      }
      if (button.id === 'analyzeCharacters' || button.id === 'runAiAnalysis') {
        handle(async () => { setCharacterStudioMode('ai'); await runCharacterAnalysis(); });
        return;
      }
      if (button.id === 'manualPreviousIssue' || button.id === 'manualNextIssue') {
        handle(() => {
          const chapter = chapters.find(item => Number(item.number) === Number(characterStudioSelectedChapter));
          const rows = characterDialogueRowsForChapter(chapter).filter(row => !row.assigned && !row.skipped);
          if (!rows.length) { message('This chapter has no unassigned dialogue passages.'); return; }
          const currentId = String(window.ryuPremiumSelectedDialogueId || '');
          let index = rows.findIndex(row => row.id === currentId);
          if (button.id === 'manualPreviousIssue') index = index <= 0 ? rows.length - 1 : index - 1;
          else index = index < 0 || index >= rows.length - 1 ? 0 : index + 1;
          const row = rows[index];
          openCharacterAssignmentPopover(row, window.innerWidth * 0.55, window.innerHeight * 0.5);
        });
        return;
      }
      if (button.id === 'selectionPlus') {
        handle(() => openCharacterAssignmentPopover({
          id:window.ryuPremiumPendingDialogueId,
          chapter_number:window.ryuPremiumPendingDialogueChapter,
          start:window.ryuPremiumPendingDialogueStart,end:window.ryuPremiumPendingDialogueEnd,
          text:window.ryuPremiumPendingDialogueText
        }, event.clientX, event.clientY));
        return;
      }
      if (button.hasAttribute('data-manual-dialogue')) {
        const item = characterPassageFromButton(button);
        if (!item) { handle(() => { throw new Error('This passage is no longer in the selected chapter. Refresh and try again.'); }); return; }
        handle(() => openCharacterAssignmentPopover(item, event.clientX, event.clientY));
        return;
      }
      if (button.matches('#quickCharacterList [data-live-character]')) {
        handle(async () => {
          const name = button.dataset.liveCharacter;
          const selectedSeries = String(button.dataset.liveSeries || '').trim().toLowerCase();
          const candidate = [...characters,...libraryCharacters].find(item =>
            characterCanonical(item).toLowerCase() === String(name).toLowerCase() &&
            characterSeries(item).toLowerCase() === selectedSeries);
          if (!candidate) throw new Error('That character is no longer in the live project or Character Library.');
          await assignPassageToCharacter(name, button.dataset.liveSeries || characterSeries(candidate),
            String(button.dataset.liveProfile || $('ryuManualNewProfile')?.value || ''));
        });
        return;
      }
      if (button.id === 'createCharacterQuick') {
        handle(() => {
          populateCharacterCreateFields();
          if ($('ryuManualNewName')) $('ryuManualNewName').value = '';
          if ($('ryuManualNewAliases')) $('ryuManualNewAliases').value = '';
          if ($('ryuManualNewProfile')) $('ryuManualNewProfile').value = '';
          $('ryuManualNewName')?.focus();
        });
        return;
      }
      if (button.id === 'saveManualCharacterCreate') { handle(() => saveManualCharacterAndAssign()); return; }
      if (button.id === 'cancelManualCharacterCreate' || button.hasAttribute('data-close-popover')) {
        handle(() => closeCharacterAssignmentPopover());
        return;
      }
      if (button.id === 'assignCharactersEmpty') {
        handle(async () => {
          setCharacterStudioMode('manual');
          const chapter = chapters.find(item => String(item.text || '').trim()) || chapters[0];
          if (!chapter) throw new Error('Open a local project and load chapters first.');
          characterStudioSelectedChapter = Number(chapter.number);
          const row = characterDialogueRowsForChapter(chapter)[0];
          if (!row) throw new Error('This project has no quoted dialogue yet. Select a sentence directly from the chapter text to assign it.');
          await openCharacterAssignmentPopover(row, window.innerWidth * 0.55, window.innerHeight * 0.5);
        });
        return;
      }
      if (button.matches('#characters #assignedQuotes [data-assigned-dialogue-key]')) {
        handle(() => {
          window.ryuPremiumSelectedAssignedDialogueKey = button.dataset.assignedDialogueKey || '';
          renderCharacterInspector();
        });
        return;
      }
      if (button.matches('#characters #assignedCharacterList [data-character-name][data-character-series]')) {
        handle(() => {
          window.ryuPremiumSelectedCharacter = button.dataset.characterName;
          window.ryuPremiumSelectedCharacterSeries = button.dataset.characterSeries;
          window.ryuPremiumSelectedAssignedDialogueKey = '';
          const key = characterAssignmentKey(button.dataset.characterName, button.dataset.characterSeries);
          document.querySelectorAll('#assignedCharacterList [data-character-name][data-character-series]').forEach(item =>
            item.classList.toggle('active',
              characterAssignmentKey(item.dataset.characterName, item.dataset.characterSeries) === key));
          renderCharacterInspector();
        });
        return;
      }
      if (button.id === 'testAssignedVoice') { handle(() => testSelectedCharacterVoice()); return; }
      if (button.id === 'editAssignedCharacter') { handle(() => openCharacterEditorForSelected()); return; }
      if (button.id === 'saveCharacterProfile' && !libraryEditorActive) { handle(() => saveCharacterEditorForProject()); return; }
      if (button.id === 'deleteCharacter' && !libraryEditorActive) { handle(() => deleteSelectedProjectCharacter()); return; }
      if (button.id === 'closeCharacterEditor' || button.hasAttribute('data-close-character-editor')) {
        handle(() => $('characterEditorModal')?.classList.remove('show'));
        return;
      }
      if (button.matches('#aiQueue [data-dialogue-id]')) {
        const row = characterPassageFromButton(button);
        if (!row) { handle(() => { throw new Error('That queue item no longer matches saved source text. Refresh or re-run analysis.'); }); return; }
        handle(() => {
          window.ryuPremiumSelectedDialogueId = row.id;
          window.ryuPremiumAiChapterNumber = Number(row.chapter_number);
          characterStudioSelectedChapter = Number(row.chapter_number);
          renderCharacterStudioLive(); renderDialogueReview();
          const target = [...document.querySelectorAll('#characters .ai-document [data-dialogue-id]')].find(item => item.dataset.dialogueId === row.id);
          target?.scrollIntoView({block:'nearest',behavior:'smooth'});
        });
        return;
      }
      if (button.matches('#characters .ai-document [data-ai-sentence][data-dialogue-id]')) {
        const row = characterPassageFromButton(button);
        if (!row) { handle(() => { throw new Error('The selected dialogue no longer matches the source chapter. Re-run analysis.'); }); return; }
        handle(() => openAiCharacterReview(row));
        return;
      }
      if (button.matches('#predictionList .prediction-option')) {
        handle(() => {
          document.querySelectorAll('#predictionList .prediction-option').forEach(item => item.classList.toggle('active', item === button));
          if ($('aiCharacterVoiceProfile')) {
            const preferred = String(button.dataset.profile || '');
            $('aiCharacterVoiceProfile').value = characterSavedProfiles().some(profile => profile.name === preferred)
              ? preferred : '';
          }
          if ($('confirmAiCharacter')) $('confirmAiCharacter').disabled = false;
        });
        return;
      }
      if (button.id === 'confirmAiCharacter') {
        handle(async () => {
          const selected = $('predictionList')?.querySelector('.prediction-option.active');
          const name = String(selected?.dataset.prediction || '').trim();
          if (!name) throw new Error('Select an AI suggestion or a saved character first.');
          const assignmentSource = selected.dataset.source === 'ai' ? 'ai' : 'manual';
          const assignmentConfidence = assignmentSource === 'ai' ? Number(selected.dataset.confidence || 0) : 1.0;
          const selectedProfile = String($('aiCharacterVoiceProfile')?.value ?? selected.dataset.profile ?? '').trim();
          await assignPassageToCharacter(name, String(selected.dataset.series || activeCharacterProjectSeries()),
            selectedProfile, assignmentSource, assignmentConfidence);
          $('aiPredictionModal')?.classList.remove('show');
          window.ryuPremiumSelectedDialogueId = '';
        });
        return;
      }
      if (button.id === 'removeAiCharacterAssignment') {
        handle(async () => {
          const text = String(window.ryuPremiumPendingDialogueText || '');
          const chapterNumber = Number(window.ryuPremiumPendingDialogueChapter);
          const start = Number(window.ryuPremiumPendingDialogueStart), end = Number(window.ryuPremiumPendingDialogueEnd);
          if (!text || !Number.isInteger(chapterNumber) || !Number.isInteger(start) || !Number.isInteger(end)) throw new Error('Select a saved source dialogue assignment first.');
          await call('chapter.dialogue.unassign',{chapter_number:chapterNumber,start,end,dialogue_text:text});
          $('aiPredictionModal')?.classList.remove('show');
          await refreshChapters(); await refreshCharacters();
          message('Removed the speaker assignment from the selected source passage.');
        });
        return;
      }
      if (button.id === 'aiUseLibrary') {
        handle(async () => {
          await refreshCharacterLibrary();
          const firstSaved = [...document.querySelectorAll('#predictionList .prediction-option')].find(item => item.dataset.source === 'library');
          if (firstSaved) {
            document.querySelectorAll('#predictionList .prediction-option').forEach(item => item.classList.toggle('active', item === firstSaved));
            firstSaved.scrollIntoView({block:'nearest',behavior:'smooth'});
            if ($('confirmAiCharacter')) $('confirmAiCharacter').disabled = false;
          } else message('No saved Character Library entries exist yet. Use New character to create one.');
        });
        return;
      }
      if (button.id === 'aiCreateNew') {
        handle(async () => {
          const item = (window.ryuPremiumDialogueReviewItems || []).find(row => row.id === window.ryuPremiumSelectedDialogueId);
          if (!item) throw new Error('Select the dialogue passage again before creating a character.');
          $('aiPredictionModal')?.classList.remove('show');
          await openCharacterAssignmentPopover(item, window.innerWidth * 0.55, window.innerHeight * 0.45);
          populateCharacterCreateFields();
          if ($('ryuManualNewName')) $('ryuManualNewName').value = String(item.suggestions?.[0]?.name || '');
        });
        return;
      }
      if (button.id === 'acceptHighConfidence') { handle(() => acceptHighConfidenceDialogues()); return; }
      if (button.id === 'skipAiSuggestion') { handle(() => skipCurrentDialogueSuggestion()); return; }
      if (button.hasAttribute('data-close-ai-modal')) {
        handle(() => $('aiPredictionModal')?.classList.remove('show'));
        return;
      }
    }, true);
  }

  function suppressLegacyVoicePreviewHandlers() {
    // The approved HTML is a visual prototype and attaches simulated actions
    // to several Voice Studio controls. A bubbling guard added after those
    // handlers is too late: same-element handlers have already run. Replace
    // each control before binding the backend actions so cloned nodes retain
    // the approved markup but not prototype listeners or inline click handlers.
    // Install the propagation guard first; the real backend handlers are bound
    // later in wire(), while the prototype's delegated bubble listener is blocked.
    const ids = [
      'generatePreview','playPreview','stopPreview',
      'saveProfile','saveOnly','useNarrator','assignCharacter'
    ];
    for (const id of ids) {
      const original = $(id);
      if (!original || original.dataset.ryuPrototypeActionShield === '1') continue;
      const replacement = original.cloneNode(true);
      replacement.removeAttribute('onclick');
      replacement.removeAttribute('onmousedown');
      replacement.dataset.ryuPrototypeActionShield = '1';
      replacement.addEventListener('click', event => {
        event.stopPropagation();
      });
      original.replaceWith(replacement);
    }
  }

  function ensureStableStudioLayout() {
    if (document.getElementById('ryuStableStudioLayoutStyle')) return;
    const style = document.createElement('style');
    style.id = 'ryuStableStudioLayoutStyle';
    // Live status/progress updates should not make Chromium choose a different
    // scroll anchor and jump the visible part of the Voice Studio workspace.
    // Manual scrolling remains enabled; this only disables automatic anchoring.
    style.textContent = [
      // The main app uses .workspace as its scroll container. Disabling anchoring
      // there prevents background status/card updates from jumping the viewport
      // in any menu, not just Voice Studio.
      '.workspace{overflow-anchor:none!important}',
      '#voices{overflow-anchor:none!important}',
      '#voices .content,#voices .layout,#voiceWorkspace,#voiceWorkspace .panel{overflow-anchor:none!important}',
      '#voices #previewState{min-height:1.25em;white-space:nowrap;max-width:170px;overflow:hidden;text-overflow:ellipsis;flex:0 0 auto}',
      '#voices #validation{min-height:3em;box-sizing:border-box;overflow-wrap:anywhere}'
    ].join('');
    document.head.appendChild(style);
  }

  function ensurePreviewDurationOptions() {
    if (!document.getElementById('ryuPreviewDurationStyle')) {
      const style = document.createElement('style');
      style.id = 'ryuPreviewDurationStyle';
      style.textContent = '.ryuPreviewDurationOption{transition:background-color .16s ease,color .16s ease,border-color .16s ease,box-shadow .16s ease,transform .16s ease}.ryuPreviewDurationOption:active{transform:scale(.98)}';
      document.head.appendChild(style);
    }
    const groups = [];
    const voiceToolbar = [...document.querySelectorAll('#voices .toolbar')].find(el => /Length/i.test(el.textContent));
    const voiceGroup = voiceToolbar?.querySelector('.seg');
    if (voiceGroup) groups.push({group:voiceGroup,scope:'voices',compact:false});
    const generateGroup = [...document.querySelectorAll('#generate .segmented')].find(el =>
      [...el.querySelectorAll('button')].some(button => /10s|30s|60s/i.test(button.textContent))
    );
    if (generateGroup) groups.push({group:generateGroup,scope:'generate',compact:true});
    for (const {group,scope,compact} of groups) {
      let buttons = [...group.querySelectorAll('button')];
      const has90 = buttons.some(button => /^\s*90\s*(?:s|seconds?)\b/i.test(button.textContent.trim()));
      if (!has90) {
        const template = buttons.find(button => /^\s*60\s*(?:s|seconds?)\b/i.test(button.textContent.trim())) || buttons[buttons.length-1];
        if (template) {
          const option = template.cloneNode(false);
          option.removeAttribute('id');
          option.classList.remove('active');
          option.classList.add('ryuPreviewDurationOption');
          option.textContent = compact ? '90s' : '90 seconds';
          option.setAttribute('aria-pressed','false');
          option.dataset.ryuDurationOption = '90';
          group.appendChild(option);
          buttons = [...group.querySelectorAll('button')];
        }
      }
      if (!buttons.some(button => button.classList.contains('active'))) {
        const preferred = buttons.find(button => /^\s*30\s*(?:s|seconds?)\b/i.test(button.textContent.trim()));
        if (preferred) preferred.classList.add('active');
      }
      for (const button of buttons) {
        button.classList.add('ryuPreviewDurationOption');
        if (button.dataset.ryuDurationWired === '1') continue;
        button.dataset.ryuDurationWired = '1';
        button.addEventListener('click', () => {
          for (const item of group.querySelectorAll('button')) {
            const active = item === button;
            item.classList.toggle('active', active);
            item.setAttribute('aria-pressed', active ? 'true' : 'false');
          }
          if (scope === 'voices' && typeof invalidateVoicePreview === 'function') invalidateVoicePreview();
        });
      }
    }
  }

  async function previewVoice() {
    const name=String(selectedVoice||$('profileName')?.value||'').trim();
    const activeProviderKey=document.querySelector('#voices .provider.active')?.dataset.provider||'';
    const providerMap={offline:'piper',sapi:'windows-sapi',customvoice:'qwen-character',voicedesign:'qwen-character',qwenclone:'qwen-character',customref:'chatterbox',edge:'edge-tts',eleven:'elevenlabs'};
    const savedProfile=selectedVoice?voices.find(item=>item.saved===true&&item.name.toLowerCase()===selectedVoice.toLowerCase()):null;
    const providerKey=savedProfile?providerPanelForProfile(savedProfile):activeProviderKey;
    const resolvedProvider=savedProfile?savedProfile.provider:(providerKey==='offline'?(selectedVoiceProvider||'piper'):providerMap[providerKey]);
    if (!savedProfile && !resolvedProvider) throw new Error('Select a provider and voice from Voice Library first.');
    const c = selectedChapter();
    const lengthGroup = [...document.querySelectorAll('#voices .toolbar')].find(el => /Length/.test(el.textContent));
    const duration = lengthGroup?.querySelector('.seg button.active')?.textContent.match(/\d+/)?.[0] || '30';
    const modeGroup = [...document.querySelectorAll('#voices .seg')].find(el => [...el.querySelectorAll('button')].some(b => /Current Chapter|Selected Passage|Custom Text/.test(b.textContent)));
    const mode = modeGroup?.querySelector('button.active')?.textContent.trim() || 'Current Chapter';
    const previewBox = [...document.querySelectorAll('#voices textarea')].find(el => /Preview text/.test(el.closest('label')?.textContent || ''));
    // The editable preview box is the source of truth for what the user is auditioning.
    // It is hydrated from the selected chapter, but deliberate edits must not be ignored.
    let previewText = previewBox?.value || c?.text || '';
    if (/Custom Text/i.test(mode)) previewText = previewBox?.value || '';
    if (/Selected Passage/i.test(mode)) {
      const editor = $('chapterEditor');
      previewText = editor && editor.selectionEnd > editor.selectionStart ? editor.value.slice(editor.selectionStart, editor.selectionEnd) : window.getSelection()?.toString() || '';
      if (!previewText.trim()) throw new Error('Select a passage in Chapter Studio before generating a passage preview.');
    }
    if (!previewText.trim()) throw new Error('The selected preview text is empty.');
    const payload = {
      profile_name:name,
      text:previewText,
      duration_seconds:Number(duration),
      chapter_number:c?.number,
      // Voice Studio auditions the selected profile itself. Character cast
      // routing belongs to Production/Character Studio, not this voice test.
      route_character_cast:false
    };
    if (!savedProfile) {
      const panel = document.querySelector('#voices .provider.active');
      const design = document.querySelector('#voices .provider[data-provider="voicedesign"]');
      const designLanguage = design?.querySelector('.form2 select')?.value || 'English';
      let voiceId = String(selectedVoiceId || '').trim();
      if (!voiceId && providerKey === 'voicedesign') voiceId = ({English:'Ryan',Japanese:'Ono_Anna',Chinese:'Serena',Korean:'Sohee'}[designLanguage] || 'Ryan');
      if (!voiceId) throw new Error('Select a voice from the active library before previewing. VoiceDesign can preview the current description without a fixed speaker selection.');
      if (providerKey === 'qwenclone' || providerKey === 'customref') {
        throw new Error('Save the reference-voice profile first so the imported recording can be used for preview.');
      }
      const qwenMode = providerKey === 'voicedesign' ? 'design' : providerKey === 'qwenclone' ? 'clone' : 'custom';
      const languageSelect = providerKey === 'voicedesign'
        ? design?.querySelector('.form2 select')
        : panel?.querySelector('.form3 select');
      payload.provider = resolvedProvider;
      payload.voice_id = voiceId;
      payload.model_id = resolvedProvider === 'qwen-character' ? 'auto' : resolvedProvider;
      payload.backend = ['piper','kokoro','qwen-character'].includes(resolvedProvider) ? 'automatic' : resolvedProvider;
      payload.language = String(languageSelect?.value || 'English');
      payload.qwen_mode = qwenMode;
      payload.qwen_prompt = providerKey === 'voicedesign' ? (design?.querySelector('textarea')?.value || '') : '';
      payload.qwen_seed = providerKey === 'voicedesign' ? (design?.querySelector('input[type="number"]')?.value || '') : '';
      payload.reference_text = $('cloneTranscript')?.value || '';
      payload.authorized = Boolean($('clonePermission')?.checked || $('customPermission')?.checked);
      payload.exaggeration = Number(panel?.querySelector('input[type="range"]')?.value || 0.5);
      payload.cfg_weight = 0.35;
      payload.style_preset = panel?.querySelector('select')?.value || 'Natural';
    }
    const previewToken=++voicePreviewEpoch;voicePreviewValid=false;lastVoicePreviewPath=null;lastVoicePreviewProfileName='';
    if(previewAudio){previewAudio.pause();previewAudio=null;}
    if($('playPreview')){$('playPreview').disabled=true;$('playPreview').textContent='▶ Play';}
    if($('downloadPreview'))$('downloadPreview').disabled=true;
    if($('previewProgress'))$('previewProgress').style.width='0%';
    if($('previewState'))$('previewState').textContent='Preparing · 2%';
    if($('validation'))$('validation').textContent='Preparing synthesis · 2%';
    updateVoiceActionButtons();
    const data=await call('voice.preview',payload);
    if(previewToken!==voicePreviewEpoch)return;
    await monitorJob(data.job_id,async job=>{
      if(previewToken!==voicePreviewEpoch)return true;
      const playable=preparePreviewPlayback(job,Number(duration));
      if($('previewState')&&playable)$('previewState').textContent='Ready · 100%';
      return playable;
    });
  }
  function setPlaybackButtonState() {
    const paused = !playerAudio || playerAudio.paused;
    const main = $('mainPlay'), mini = $('miniPlay');
    if (main) main.textContent = paused ? '▶' : 'Ⅱ';
    if (mini) mini.textContent = paused ? '▶' : 'Ⅱ';
    if (main) main.disabled = !(playerAudio && playerAudio.src);
    if (mini) mini.disabled = !(playerAudio && playerAudio.src);
  }
  function clearAudiobookPlayerDisplay() {
    if (playerAudio && playerAudio.src) return;
    const page = $('player');
    if (!page) return;
    const grid = page.querySelector('.player-grid');
    const bookCard = grid?.querySelector(':scope > .card:first-child');
    const playbackCard = grid?.querySelector(':scope > .card:nth-child(2)');
    const title = bookCard?.querySelector('h2');
    const metadata = bookCard?.querySelector('p.muted');
    const nowPlaying = playbackCard?.querySelector('h2');
    if (title) title.textContent = 'No audiobook selected';
    if (metadata) metadata.textContent = 'Choose a finished audiobook from your library to begin playback.';
    if (nowPlaying) nowPlaying.textContent = 'Select a finished audiobook';
    applyProjectCover(bookCard?.querySelector('.player-cover,.book-cover,[data-project-cover]'), '');
    const timeline = $('playerTimeline');
    if (timeline) { timeline.value = 0; timeline.disabled = true; }
    if ($('currentTime')) $('currentTime').textContent = '0:00';
    if ($('miniProgress')) $('miniProgress').style.width = '0%';
    const durationNode = $('currentTime')?.parentElement?.querySelectorAll('span')?.[1];
    if (durationNode) durationNode.textContent = '0:00';
    const chapterList = grid?.querySelector('aside.card .list');
    if (chapterList) chapterList.innerHTML = '<div class="list-item">No audiobook selected.</div>';
    activePlayerChapters = [];
    const mini = $('miniPlayer');
    if (mini) {
      const miniTitle = mini.querySelector('b');
      const miniSubtitle = mini.querySelector('small.muted');
      const time = mini.querySelector('span.muted');
      if (miniTitle) miniTitle.textContent = 'No audiobook selected';
      if (miniSubtitle) miniSubtitle.textContent = 'Choose Play audiobook from the Audiobooks page';
      if (time) time.textContent = '0:00';
      applyProjectCover(mini.querySelector('.mini-cover,.book-cover,.project-cover,[data-project-cover],img[alt*="cover" i]'), '');
      mini.classList.add('hidden');
    }
    setPlaybackButtonState();
  }
  function renderSelectedAudiobook(data) {
    const page = $('player');
    const grid = page?.querySelector('.player-grid');
    const bookCard = grid?.querySelector(':scope > .card:first-child');
    const playbackCard = grid?.querySelector(':scope > .card:nth-child(2)');
    const title = bookCard?.querySelector('h2');
    const metadata = bookCard?.querySelector('p.muted');
    const nowPlaying = playbackCard?.querySelector('h2');
    if (title) title.textContent = data.title || 'Untitled audiobook';
    const author = String(data.author || '').trim();
    const narrator = String(data.narrator || data.voice_profile || '').trim();
    if (metadata) metadata.textContent = (author ? author + ' · ' : '') + (narrator ? 'Narrated by ' + narrator : 'Narrator not set');
    if (nowPlaying) nowPlaying.textContent = 'Full audiobook';
    applyProjectCover(bookCard?.querySelector('.player-cover,.book-cover,[data-project-cover]'), data.cover_path || '');
    const chapters = Array.isArray(data.chapters) ? data.chapters : [];
    activePlayerChapters = chapters;
    const chapterList = grid?.querySelector('aside.card .list');
    if (chapterList) {
      chapterList.innerHTML = chapters.map((chapter, index) => {
        const start = Number(chapter.start_seconds), end = Number(chapter.end_seconds);
        const hasTiming = Number.isFinite(start) && start >= 0 && Number.isFinite(end) && end > start;
        return '<div class="list-item" role="button" tabindex="' + (hasTiming ? '0' : '-1') +
          '" data-audiobook-chapter-index="' + String(index) + '"' +
          ' data-audiobook-chapter-start="' + (hasTiming ? String(start) : '') + '"' +
          ' data-audiobook-chapter-end="' + (hasTiming ? String(end) : '') + '"' +
          ' aria-pressed="false"' + (hasTiming ? '' : ' aria-disabled="true"') + '>' +
          esc('Chapter ' + Number(chapter.number || 0) + ' · ' + String(chapter.title || 'Untitled chapter')) +
          '<small class="muted" data-audiobook-chapter-time="' + (hasTiming ? 'true' : 'false') +
          '" style="display:block;margin-top:4px;font-size:11px">' +
          esc(hasTiming ? formatTime(start) + ' – ' + formatTime(end) : 'Timing unavailable') +
          '</small>' +
          '</div>';
      }).join('') || '<div class="list-item">No chapter metadata available.</div>';
    }
    const speedButtons = [...(page?.querySelectorAll('.player-grid .toolbar .segmented button') || [])];
    speedButtons.forEach(button => {
      const rate = Number(String(button.textContent || '').replace('×','').trim());
      button.classList.toggle('active', Number.isFinite(rate) && Math.abs(rate - playerRate) < 0.01);
    });
    const volumeControl = page?.querySelector('.player-grid .toolbar input.range');
    if (volumeControl) volumeControl.value = String(Math.round(playerVolume * 100));
    const playerButtons = [...(page?.querySelectorAll('.player-controls button') || [])];
    const hasTimedChapters = chapters.some(chapter => {
      const start = Number(chapter.start_seconds), end = Number(chapter.end_seconds);
      return Number.isFinite(start) && start >= 0 &&
        Number.isFinite(end) && end > start;
    });
    if (playerButtons[1]) {
      playerButtons[1].disabled = !hasTimedChapters;
      playerButtons[1].title = hasTimedChapters ? 'Previous chapter' : 'Chapter navigation is unavailable for this audiobook file';
    }
    if (playerButtons[3]) {
      playerButtons[3].disabled = !hasTimedChapters;
      playerButtons[3].title = hasTimedChapters ? 'Next chapter' : 'Chapter navigation is unavailable for this audiobook file';
    }
    const duration = Number(playerAudio?.duration) || 0;
    if ($('playerTimeline')) {
      $('playerTimeline').value = duration > 0 ? (playerAudio.currentTime / duration) * 100 : 0;
      $('playerTimeline').disabled = !(playerAudio && playerAudio.src && Number.isFinite(duration) && duration > 0);
    }
    if ($('currentTime')) $('currentTime').textContent = formatTime(playerAudio?.currentTime || 0);
    if ($('miniProgress')) $('miniProgress').style.width =
      (playerAudio?.duration ? playerAudio.currentTime / playerAudio.duration * 100 : 0) + '%';
    const durationNode = $('currentTime')?.parentElement?.querySelectorAll('span')?.[1];
    if (durationNode) durationNode.textContent = formatTime(duration);
    const mini = $('miniPlayer');
    if (mini) {
      const miniTitle = mini.querySelector('b');
      const miniSubtitle = mini.querySelector('small.muted');
      const time = mini.querySelector('span.muted');
      if (miniTitle) miniTitle.textContent = data.title || 'Untitled audiobook';
      if (miniSubtitle) miniSubtitle.textContent = 'Full audiobook · ' + chapters.length + ' chapters';
      if (time) time.textContent = formatTime(playerAudio?.currentTime || 0);
      applyProjectCover(mini.querySelector('.mini-cover,.book-cover,.project-cover,[data-project-cover],img[alt*="cover" i]'), data.cover_path || '');
    }
    syncActivePlayerChapter(playerAudio);
    setPlaybackButtonState();
  }
  function syncActivePlayerChapter(audio = playerAudio) {
    if (!audio || audio !== playerAudio) return null;
    const current = Number(audio.currentTime), chapters = Array.isArray(activePlayerChapters) ? activePlayerChapters : [];
    const activeIndex = Number.isFinite(current) && current >= 0
      ? chapters.findIndex(chapter => {
          const start = Number(chapter.start_seconds), end = Number(chapter.end_seconds);
          return Number.isFinite(start) && Number.isFinite(end) && end > start &&
            current >= start && current < end;
        }) : -1;
    const rows = [...($('player')?.querySelectorAll('[data-audiobook-chapter-start]') || [])];
    rows.forEach((row,index) => {
      const selected = index === activeIndex;
      row.classList.toggle('active',selected);
      row.setAttribute('aria-pressed',selected ? 'true' : 'false');
      if (selected) row.setAttribute('aria-current','true');
      else row.removeAttribute('aria-current');
    });
    const heading = $('player')?.querySelector('.player-grid > .card:nth-child(2) h2');
    if (heading) {
      const chapter = activeIndex >= 0 ? chapters[activeIndex] : null;
      heading.textContent = chapter
        ? 'Chapter ' + Number(chapter.number || activeIndex + 1) + ' · ' + String(chapter.title || 'Untitled chapter')
        : 'Full audiobook';
    }
    return activeIndex >= 0 ? chapters[activeIndex] : null;
  }
  function persistPlayerPosition(force = false, reset = false, folder = selectedAudiobookFolder, audio = playerAudio) {
    if (!folder || !audio || !audio.src) return;
    const now = Date.now();
    if (!force && now - playerPositionSaveAt < 10000) return;
    playerPositionSaveAt = now;
    const seconds = reset ? 0 : Math.max(0, Number(audio.currentTime) || 0);
    void call('player.position.save', {folder, position_seconds:seconds})
      .catch(error => console.warn('[Ryu player position]', error?.message || error));
  }
  let playerPreferenceSave = Promise.resolve();
  function savePlayerPreferences(patch) {
    // Serialize preference updates so rapid rate/volume changes cannot let an
    // older response overwrite a newer setting. Return the real backend save.
    playerPreferenceSave = playerPreferenceSave.catch(() => {}).then(async () => {
      const saved = await call('settings.save', patch);
      if (saved?.saved === false) throw new Error('Player preferences were not saved.');
      if (Object.prototype.hasOwnProperty.call(patch, 'player_rate')) {
        const acknowledgedRate = Number(saved?.player_rate);
        if (!Number.isFinite(acknowledgedRate) ||
            Math.abs(acknowledgedRate - Number(patch.player_rate)) > 0.01) {
          throw new Error('The saved playback speed was not confirmed by Settings read-back.');
        }
      }
      if (Object.prototype.hasOwnProperty.call(patch, 'player_volume')) {
        const acknowledgedVolume = Number(saved?.player_volume);
        if (!Number.isFinite(acknowledgedVolume) ||
            Math.abs(acknowledgedVolume - Number(patch.player_volume)) > 0.01) {
          throw new Error('The saved player volume was not confirmed by Settings read-back.');
        }
      }
      return saved;
    });
    return playerPreferenceSave;
  }
  function applyPlayerRate(value, persist = true) {
    const rate = Number(value);
    if (!Number.isFinite(rate) || rate < 0.5 || rate > 2) {
      message('Playback speed must be between 0.5× and 2.0×.', true);
      return Promise.reject(new Error('Playback speed must be between 0.5× and 2.0×.'));
    }
    playerRate = rate;
    if (playerAudio) playerAudio.playbackRate = rate;
    const page = $('player');
    [...(page?.querySelectorAll('.player-grid .toolbar .segmented button') || [])].forEach(button => {
      const candidate = Number(String(button.textContent || '').replace('×','').trim());
      button.classList.toggle('active', Number.isFinite(candidate) && Math.abs(candidate-rate) < 0.01);
    });
    if (!persist) return Promise.resolve({playback_rate:rate});
    return savePlayerPreferences({player_rate:rate})
      .catch(error => { message(error?.message || String(error), true); throw error; });
  }
  function applyPlayerVolume(value, persist = false) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return Promise.resolve(null);
    playerVolume = Math.max(0, Math.min(1, amount / 100));
    if (playerAudio) playerAudio.volume = playerVolume;
    const control = $('player')?.querySelector('.player-grid .toolbar input.range');
    if (control) control.value = String(Math.round(playerVolume * 100));
    if (!persist) return Promise.resolve({playback_volume:playerVolume});
    return savePlayerPreferences({player_volume:playerVolume})
      .catch(error => { message(error?.message || String(error), true); throw error; });
  }
  function seekPlayerBy(seconds) {
    if (!playerAudio || !playerAudio.src || !Number.isFinite(playerAudio.duration)) {
      message('Choose Play audiobook on a finished title before using playback controls.', true);
      return;
    }
    playerAudio.currentTime = Math.max(0, Math.min(playerAudio.duration, playerAudio.currentTime + Number(seconds || 0)));
  }
  function jumpPlayerChapter(direction) {
    if (!playerAudio || !playerAudio.src) return;
    const chapters = activePlayerChapters
      .filter(chapter => {
        const start = Number(chapter.start_seconds), end = Number(chapter.end_seconds);
        return Number.isFinite(start) && start >= 0 &&
          Number.isFinite(end) && end > start;
      })
      .slice().sort((a,b) => Number(a.start_seconds) - Number(b.start_seconds));
    if (!chapters.length) {
      message('Chapter navigation is unavailable for this audiobook file.', true);
      return;
    }
    const current = Math.max(0, Number(playerAudio.currentTime) || 0);
    let index = 0;
    for (let i = 0; i < chapters.length; i++) {
      if (Number(chapters[i].start_seconds) <= current + 0.05) index = i;
      else break;
    }
    let targetIndex;
    if (direction === 'previous') {
      targetIndex = current - Number(chapters[index].start_seconds) > 3 ? index : index - 1;
      if (targetIndex < 0) targetIndex = 0;
    } else {
      targetIndex = index + 1;
      if (targetIndex >= chapters.length) {
        message('You are already at the final chapter of this audiobook.');
        return;
      }
    }
    playerAudio.currentTime = Math.max(0, Number(chapters[targetIndex].start_seconds) || 0);
  }
  function bindAudiobookPlayerControls() {
    const page = $('player');
    if (!page || page.dataset.backendPlayerControlsBound === 'true') return;
    page.dataset.backendPlayerControlsBound = 'true';
    const buttons = [...(page.querySelector('.player-controls')?.querySelectorAll('button') || [])];
    if (buttons[0]) { buttons[0].title = 'Rewind 15 seconds'; buttons[0].onclick = () => seekPlayerBy(-15); }
    if (buttons[1]) { buttons[1].title = 'Previous chapter'; buttons[1].onclick = () => jumpPlayerChapter('previous'); }
    if (buttons[3]) { buttons[3].title = 'Next chapter'; buttons[3].onclick = () => jumpPlayerChapter('next'); }
    if (buttons[4]) { buttons[4].title = 'Forward 15 seconds'; buttons[4].onclick = () => seekPlayerBy(15); }
    const speedButtons = [...page.querySelectorAll('.player-grid .toolbar .segmented button')];
    speedButtons.forEach(button => {
      button.onclick = () => {
        const rate = Number(String(button.textContent || '').replace('×','').trim());
        void applyPlayerRate(rate, true);
      };
    });
    const volumeControl = page.querySelector('.player-grid .toolbar input.range');
    if (volumeControl) {
      volumeControl.oninput = () => { void applyPlayerVolume(volumeControl.value, false); };
      volumeControl.onchange = () => { void applyPlayerVolume(volumeControl.value, true); };
    }
    const playSelectedChapter = async chapter => {
      if (!chapter || chapter.getAttribute('aria-disabled') === 'true') return;
      const audio = playerAudio, start = Number(chapter.dataset.audiobookChapterStart),
        end = Number(chapter.dataset.audiobookChapterEnd);
      if (!audio || !audio.src || !Number.isFinite(audio.duration) ||
          !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) {
        message('This audiobook chapter has no usable embedded playback timing.', true);
        return;
      }
      audio.currentTime = Math.max(0,Math.min(audio.duration,start));
      syncActivePlayerChapter(audio);
      try { await audio.play(); }
      catch (error) { message(error?.message || 'The selected chapter could not be started.',true); }
    };
    page.addEventListener('click', event => {
      const chapter = event.target && typeof event.target.closest === 'function'
        ? event.target.closest('[data-audiobook-chapter-start]') : null;
      if (!chapter || chapter.getAttribute('aria-disabled') === 'true') return;
      void playSelectedChapter(chapter);
    });
    page.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const chapter = event.target && typeof event.target.closest === 'function'
        ? event.target.closest('[data-audiobook-chapter-start]') : null;
      if (!chapter || chapter.getAttribute('aria-disabled') === 'true') return;
      event.preventDefault();
      void playSelectedChapter(chapter);
    });
    applyPlayerRate(playerRate, false);
    applyPlayerVolume(playerVolume * 100, false);
  }
  async function openPlayer(projectFolder = selectedAudiobookFolder) {
    const autoplay = arguments[1]?.autoplay !== false;
    const folder = String(projectFolder || '').trim();
    if (!folder) throw new Error('Select a finished audiobook from the Audiobooks library before playing.');
    const data = await call('player.get_active', {folder});
    if (playerAudio && playerAudio.src === data.file_url &&
        String(playerAudio.dataset?.projectFolder || '') === folder) {
      selectedAudiobookFolder = folder;
      miniPlayerDismissed = false;
      playerAudio.dataset.projectFolder = folder;
      playerRate = Number.isFinite(Number(data.playback_rate)) ? Number(data.playback_rate) : playerRate;
      playerVolume = Number.isFinite(Number(data.playback_volume)) ? Math.max(0,Math.min(1,Number(data.playback_volume))) : playerVolume;
      playerAudio.playbackRate = playerRate;
      playerAudio.volume = playerVolume;
      renderSelectedAudiobook(data);
      if (autoplay) {
        if (playerAudio.paused) await playerAudio.play(); else playerAudio.pause();
      } else if (!playerAudio.paused) {
        // Open is load-only: reopening the already-selected book must not leave it playing.
        playerAudio.pause();
      }
      syncMiniPlayer();
      setPlaybackButtonState();
      return;
    }
    if (playerAudio) {
      persistPlayerPosition(true, false, selectedAudiobookFolder, playerAudio);
      playerAudio.pause();
    }
    selectedAudiobookFolder = folder;
    playerPositionSaveAt = 0;
    playerRate = Number.isFinite(Number(data.playback_rate)) && Number(data.playback_rate) >= 0.5 && Number(data.playback_rate) <= 2
      ? Number(data.playback_rate) : 1;
    playerVolume = Number.isFinite(Number(data.playback_volume)) && Number(data.playback_volume) >= 0 && Number(data.playback_volume) <= 1
      ? Number(data.playback_volume) : 0.8;
    playerAudio = new Audio(data.file_url);
    const audio = playerAudio;
    audio.dataset.projectFolder = folder;
    const audioFolder = folder;
    audio.preload = 'metadata';
    audio.playbackRate = playerRate;
    audio.volume = playerVolume;
    const updateAudioPositionUi = () => {
      if (audio !== playerAudio || audioFolder !== selectedAudiobookFolder) return;
      const duration = Number(audio.duration) || 0, current = Number(audio.currentTime) || 0;
      if ($('playerTimeline')) {
        $('playerTimeline').value = duration > 0 ? current / duration * 100 : 0;
        $('playerTimeline').disabled = !(audio.src && Number.isFinite(duration) && duration > 0);
      }
      if ($('miniProgress') && duration > 0) $('miniProgress').style.width = current / duration * 100 + '%';
      if ($('currentTime')) $('currentTime').textContent = formatTime(current);
      const time = $('miniPlayer')?.querySelector('span.muted');
      if (time) time.textContent = formatTime(current);
      syncActivePlayerChapter(audio);
      setPlaybackButtonState();
      persistPlayerPosition(false, false, audioFolder, audio);
    };
    audio.ontimeupdate = updateAudioPositionUi;
    audio.onseeked = updateAudioPositionUi;
    audio.onplay = () => {
      if (audio !== playerAudio || audioFolder !== selectedAudiobookFolder) return;
      // Reassert the selected project's current preference on the media element.
      // Qt WebEngine may return a newly loaded element to 1× before playback starts.
      audio.playbackRate = playerRate;
      audio.volume = playerVolume;
      setPlaybackButtonState(); syncMiniPlayer();
    };
    audio.onpause = () => {
      if (audio !== playerAudio || audioFolder !== selectedAudiobookFolder) return;
      persistPlayerPosition(true,false,audioFolder,audio);
      setPlaybackButtonState(); syncMiniPlayer();
    };
    audio.onended = () => {
      if (audio !== playerAudio || audioFolder !== selectedAudiobookFolder) return;
      persistPlayerPosition(true,true,audioFolder,audio);
      setPlaybackButtonState(); syncMiniPlayer();
    };
    audio.onloadedmetadata = () => {
      if (audio !== playerAudio || audioFolder !== selectedAudiobookFolder) return;
      // Apply persisted preferences after the browser has finished loading the
      // media resource; setting playbackRate before load/metadata is not enough
      // in every Qt WebEngine build.
      audio.playbackRate = playerRate;
      audio.volume = playerVolume;
      const duration = Number(audio.duration) || 0;
      const savedPosition = Math.max(0, Number(data.playback_position_seconds) || 0);
      if (duration > 0 && savedPosition > 0 && savedPosition < duration - 1) {
        audio.currentTime = savedPosition;
      } else if (duration > 0 && savedPosition >= duration - 1) {
        audio.currentTime = 0;
      }
      renderSelectedAudiobook(data);
    };
    audio.onerror = () => {
      if (audio !== playerAudio || audioFolder !== selectedAudiobookFolder) return;
      miniPlayerDismissed = true;
      syncMiniPlayer();
      message('The local audiobook file could not be opened in the embedded player.', true);
    };
    if (autoplay) await audio.play();
    else audio.load();
    miniPlayerDismissed = false;
    renderSelectedAudiobook(data);
    syncMiniPlayer();
    setPlaybackButtonState();
  }
  const formatTime = seconds => {
    const n = Math.max(0, Math.floor(Number(seconds) || 0)), h = Math.floor(n / 3600), m = Math.floor((n % 3600) / 60), sec = n % 60;
    return h ? h + ':' + String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0') : m + ':' + String(sec).padStart(2,'0');
  };
  function ensureHistoryRangeControls(section) {
    const filters = $('historyFilters');
    if (!section || !filters || !filters.parentElement) return null;
    let controls = $('historyRangeControls');
    if (!controls) {
      controls = document.createElement('div');
      controls.id = 'historyRangeControls';
      controls.className = 'toolbar';
      controls.style.display = 'flex';
      controls.style.flexWrap = 'wrap';
      controls.style.alignItems = 'end';
      controls.style.gap = '10px';
      controls.style.margin = '12px 0 14px';
      controls.innerHTML =
        '<label style="display:grid;gap:4px;min-width:180px;flex:1;font-size:12px;color:var(--muted)">Search' +
          '<input id="historySearchFilter" type="search" placeholder="Job, project, chapter or error" ' +
          'style="min-width:0;width:100%;padding:9px 11px;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:9px"></label>' +
        '<label style="display:grid;gap:4px;min-width:140px;font-size:12px;color:var(--muted)">From Date' +
          '<input id="historyFromDate" type="date" aria-label="History from date" ' +
          'style="padding:9px 11px;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:9px"></label>' +
        '<label style="display:grid;gap:4px;min-width:140px;font-size:12px;color:var(--muted)">To Date' +
          '<input id="historyToDate" type="date" aria-label="History to date" ' +
          'style="padding:9px 11px;background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:9px"></label>' +
        '<button class="btn small secondary" id="clearHistoryFilters" type="button">Clear filters</button>' +
        '<small id="historyFilterHint" class="muted" role="status" aria-live="polite"></small>';
      filters.insertAdjacentElement('afterend', controls);
      const refresh = () => {
        section.dataset.historyRenderSignature = '';
        refreshHistory().catch(error => message(error?.message || String(error), true));
      };
      controls.querySelectorAll('input').forEach(input => {
        input.addEventListener('input', refresh);
        input.addEventListener('change', refresh);
      });
      $('clearHistoryFilters')?.addEventListener('click', () => {
        const search = $('historySearchFilter'), from = $('historyFromDate'), to = $('historyToDate');
        if (search) search.value = '';
        if (from) from.value = '';
        if (to) to.value = '';
        refresh();
      });
    }
    // Remove prototype sample records after the page is connected to real data.
    section.querySelectorAll('.history-row:not([data-backend-history])').forEach(row => row.remove());
    return controls;
  }

  function jobDateValue(job) {
    return job?.completed_at || job?.updated_at || job?.started_at || job?.queued_at || job?.created_at || '';
  }

  function generationModeLabel(job) {
    if (String(job?.type || '') !== 'audiobook-generation') return '';
    const result = job?.result && typeof job.result === 'object' ? job.result : {};
    if (result.narrator_only === true || result.generation_mode === 'narrator_only') return 'Narrator-only';
    if (result.generation_mode === 'character_cast') return 'Character cast';
    // Legacy jobs created before mode tracking must not be silently re-labelled.
    return 'Generation mode not recorded';
  }

  function jobMetaSummary(job) {
    const project = String(job?.project_title || job?.project_name || '').trim() || 'Project unavailable';
    const mode = generationModeLabel(job);
    const phase = String(job?.chapter_title || job?.stage || job?.phase || '').trim();
    const elapsed = Number(job?.elapsed_seconds);
    const elapsedText = Number.isFinite(elapsed) && elapsed >= 0 ? formatTime(elapsed) : 'Elapsed time unavailable';
    const dateValue = jobDateValue(job);
    const dateText = dateValue && Number.isFinite(Date.parse(dateValue))
      ? new Date(dateValue).toLocaleString() : 'Timestamp unavailable';
    return [project, mode, phase, elapsedText, dateText].filter(Boolean).join(' · ');
  }

  function ensureJobDetailsModal() {
    let root = $('jobDetailsModal');
    if (root) return root;
    root = document.createElement('div');
    root.id = 'jobDetailsModal';
    root.className = 'modal-back';
    root.innerHTML =
      '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="jobDetailsTitle" ' +
      'style="width:min(760px,calc(100vw - 28px));max-height:calc(100vh - 36px);overflow:auto">' +
        '<div class="modal-title"><div><span class="eyebrow">OPERATION DETAILS</span>' +
          '<h2 id="jobDetailsTitle">Background job</h2><p class="muted" id="jobDetailsSubtitle"></p></div>' +
          '<button class="icon-btn" type="button" data-job-detail-close aria-label="Close job details">×</button></div>' +
        '<div id="jobDetailsFields" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px"></div>' +
        '<div id="jobDetailsError" class="muted" style="margin-top:12px;white-space:pre-wrap"></div>' +
        '<div id="jobDetailsActions" class="toolbar" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:16px"></div>' +
        '<div class="toolbar" style="display:flex;justify-content:flex-end;margin-top:14px">' +
          '<button class="btn small secondary" type="button" id="jobDetailsOpenTaskManager">Open Task Manager</button>' +
          '<button class="btn small ghost" type="button" data-job-detail-close>Close</button>' +
        '</div></div>';
    document.body.appendChild(root);
    root.addEventListener('click', event => {
      if (event.target === root || event.target.closest('[data-job-detail-close]')) root.classList.remove('show');
      if (event.target.closest('#jobDetailsOpenTaskManager')) {
        root.classList.remove('show');
        $('backgroundJobsButton')?.click();
      }
    });
    if (!window.__ryuJobDetailsEscapeBound) {
      window.__ryuJobDetailsEscapeBound = true;
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape') $('jobDetailsModal')?.classList.remove('show');
      });
    }
    return root;
  }

  function renderJobDetails(job) {
    const root = ensureJobDetailsModal();
    const id = String(job?.job_id || job?.id || '');
    const state = String(job?.state || 'unknown');
    const error = job?.error && typeof job.error === 'object'
      ? String(job.error.message || '') : String(job?.error || '');
    const generationResult = job?.result && typeof job.result === 'object' ? job.result : {};
    const generationMode = generationModeLabel(job) || 'Not applicable';
    const configuredProfiles = Number(generationResult.character_voice_profile_count);
    const generationIdentityFields = String(job?.type || '') === 'audiobook-generation'
      ? [
          ['Generation mode', generationMode],
          ['Saved narrator profile', generationResult.voice_profile || 'Not recorded'],
          ['Character profiles configured',
            Number.isFinite(configuredProfiles) && configuredProfiles >= 0
              ? String(Math.floor(configuredProfiles)) : 'Not recorded']
        ]
      : [];
    const result = job?.result && typeof job.result === 'object'
      ? String(job.result.summary || job.result.message || '')
      : String(job?.result || '');
    const fields = [
      ['Job ID', id],
      ['Type', job?.type || job?.operation || 'Unknown'],
      ['Project', job?.project_title || job?.project_name || 'Project unavailable'],
      ['Status', state],
      ['Progress', Number.isFinite(Number(job?.progress)) ? Math.round(Number(job.progress)) + '%' : 'Unavailable'],
      ['Chapter', job?.chapter_title || job?.chapter_number || job?.chapter || 'Not applicable'],
      ['Phase', job?.stage || job?.phase || 'Not reported'],
      ['Elapsed time', Number.isFinite(Number(job?.elapsed_seconds)) ? formatTime(job.elapsed_seconds) : 'Unavailable'],
      ['Queued', job?.queued_at || 'Unavailable'],
      ['Started', job?.started_at || 'Unavailable'],
      ['Finished', job?.completed_at || 'Not finished'],
      ['Output', job?.output_path || job?.result?.output_path || 'No output registered'],
      ...generationIdentityFields,
      ['Result', result || 'No result summary reported'],
      ['Recovery', job?.recoverable ? 'Recoverable' : 'Not marked recoverable']
    ];
    $('jobDetailsTitle').textContent = String(job?.title || job?.type || 'Background job');
    $('jobDetailsSubtitle').textContent = (job?.project_title || 'Local task') + ' · ' + state;
    $('jobDetailsFields').innerHTML = fields.map(([label,value]) =>
      '<div style="padding:10px;border:1px solid var(--border);border-radius:10px;background:var(--surface);min-width:0">' +
        '<small class="muted">' + esc(label) + '</small><div data-job-detail-field="' +
        esc(label.toLowerCase().replace(/[^a-z0-9]+/g,'-')) +
        '" style="margin-top:4px;overflow-wrap:anywhere">' + esc(value) + '</div></div>'
    ).join('');
    $('jobDetailsError').textContent = error ? 'Failure details: ' + error : '';
    const action = (name,label,cls) =>
      '<button class="btn small ' + cls + '" data-job-action="' + name + '" data-job-id="' + esc(id) + '">' + label + '</button>';
    const isGeneration = String(job?.type || '') === 'audiobook-generation';
    const isImport = String(job?.type || '') === 'import';
    const isPreview = ['voice-preview','production-preview','sound-design-preview'].includes(String(job?.type || ''));
    const stateActions = backgroundGenerationJobActions(job || {}, esc(id), action, isGeneration, isImport, isPreview);
    $('jobDetailsActions').innerHTML = stateActions || '<small class="muted">No additional operation is available for this job state.</small>';
    root.classList.add('show');
  }

  async function openJobDetails(jobId) {
    const id = String(jobId || '').trim();
    if (!id) throw new Error('Select a job before opening its details.');
    const [jobs, history] = await Promise.all([
      call('job.list', {include_hidden:true}),
      call('history.list')
    ]);
    const jobRows = Array.isArray(jobs) ? jobs : [];
    const historyRows = Array.isArray(history) ? history : [];
    const historyMatch = historyRows.find(row => String(row.job_id || row.id || '') === id);
    const queueMatch = jobRows.find(row => String(row.job_id || row.id || '') === id);
    const job = historyMatch || queueMatch;
    if (!job) throw new Error('This job is no longer available in History or the task queue.');
    renderJobDetails(job);
    return job;
  }

  async function refreshHistory() {
    const requestToken = ++historyListEpoch;
    const section = $('history');
    ensureHistoryRangeControls(section);
    const filters = $('historyFilters');
    const host = filters?.parentElement;
    const filter = filters?.querySelector('button.active')?.textContent?.trim().toLowerCase() || 'all';
    const query = String($('historySearchFilter')?.value || '').trim().toLowerCase();
    const fromDate = String($('historyFromDate')?.value || '').trim();
    const toDate = String($('historyToDate')?.value || '').trim();
    const hint = $('historyFilterHint');
    if (fromDate && toDate && fromDate > toDate) {
      if (hint) hint.textContent = 'From Date must be on or before To Date.';
      if (section) section.querySelectorAll('[data-backend-history]').forEach(el => el.remove());
      if (host) {
        let empty = host.querySelector('[data-history-empty]');
        if (!empty) { empty = document.createElement('p'); empty.dataset.historyEmpty='1'; empty.className='muted'; host.appendChild(empty); }
        empty.textContent = 'Choose a valid date range to view History.';
      }
      return [];
    }
    if (hint) hint.textContent = '';
    const loaded = await call('history.list');
    if (requestToken !== historyListEpoch) return [];
    const rows = Array.isArray(loaded) ? loaded : [];
    const fromTime = fromDate ? new Date(fromDate + 'T00:00:00').getTime() : null;
    const toTime = toDate ? new Date(toDate + 'T23:59:59.999').getTime() : null;
    const activeStates = ['queued','running','pause_requested','paused','cancel_requested','retrying'];
    const visible = rows.filter(job => {
      const state = String(job.state || '').toLowerCase();
      if (filter === 'completed' && state !== 'completed') return false;
      if (filter === 'running' && !activeStates.includes(state)) return false;
      if (filter === 'failed' && !['failed','cancelled'].includes(state)) return false;
      const timestamp = Date.parse(jobDateValue(job));
      if (fromTime !== null && (!Number.isFinite(timestamp) || timestamp < fromTime)) return false;
      if (toTime !== null && (!Number.isFinite(timestamp) || timestamp > toTime)) return false;
      if (query) {
        const searchable = [
          job.job_id,job.title,job.type,job.operation,job.project_title,job.project_name,
          job.project_folder,job.chapter_title,job.chapter_number,job.stage,job.phase,
          job.message,job.error?.code,job.error?.message,job.output_path
        ].map(value => String(value ?? '')).join(' ').toLowerCase();
        if (!searchable.includes(query)) return false;
      }
      return true;
    });
    const signature = JSON.stringify({
      filter,query,fromDate,toDate,
      rows:visible.map(job => [job.job_id,job.title,job.type,job.project_title,job.stage,job.message,
        job.state,job.elapsed_seconds,job.progress,job.error?.message,jobDateValue(job)])
    });
    if (section && host && section.dataset.historyRenderSignature === signature) return rows;
    if (section) section.querySelectorAll('[data-backend-history]').forEach(el => el.remove());
    if (host) {
      let empty = host.querySelector('[data-history-empty]');
      if (!visible.length) {
        if (!empty) { empty = document.createElement('p'); empty.dataset.historyEmpty='1'; empty.className='muted'; host.appendChild(empty); }
        empty.textContent = 'No matching backend jobs yet.';
      } else if (empty) empty.remove();
      visible.forEach(job => {
        const row = document.createElement('div');
        const id = String(job.job_id || job.id || '');
        const state = String(job.state || 'unknown').toLowerCase();
        const label = state.replace(/_/g,' ');
        const elapsed = Number(job.elapsed_seconds);
        const duration = Number.isFinite(elapsed) && elapsed >= 0 ? formatTime(elapsed) : 'Elapsed time unavailable';
        const progress = Number(job.progress);
        const progressText = Number.isFinite(progress) ? Math.round(progress) + '%' : '—';
        const timestamp = jobDateValue(job);
        const timestampText = timestamp && Number.isFinite(Date.parse(timestamp))
          ? new Date(timestamp).toLocaleString() : 'Timestamp unavailable';
        const phase = [job.chapter_title || (job.chapter_number ? 'Chapter ' + job.chapter_number : ''),
          job.stage || job.phase || ''].filter(Boolean).join(' · ');
        const project = job.project_title || job.project_name || 'Project unavailable';
        const errorText = job.error?.message
          ? '<small class="muted" style="color:var(--danger)">Error: ' + esc(job.error.message) + '</small>' : '';
        row.className = 'history-row';
        row.dataset.backendHistory='1';
        row.dataset.historyJob = id;
        row.innerHTML =
          '<div><b>' + esc(job.title || job.type || 'Background task') + '</b><br>' +
            '<span class="muted">' + esc(project) + ' · ' + esc(phase || job.message || 'No phase reported') + ' · ' + esc(duration) + '</span><br>' +
            '<small class="muted">' + esc(timestampText) + '</small><br>' + errorText +
          '</div><span class="badge ' + (state === 'failed' || state === 'cancelled' ? 'red' : ['running','queued','pause_requested','paused','retrying'].includes(state) ? 'info' : '') + '">' +
            esc(label) + '</span><span>' + esc(progressText) + '</span>' +
          '<button class="btn small secondary" type="button" data-history-job="' + esc(id) + '">View</button>';
        host.appendChild(row);
      });
      if (section) section.dataset.historyRenderSignature = signature;
    }
    return rows;
  }
  async function renderHardwareOptimizationSettings(result = {}) {
    const section = $('performance');
    if (!section) return;
    let panel = $('performanceHardwareOptimization');
    if (!panel) {
      panel = document.createElement('section');
      panel.id = 'performanceHardwareOptimization';
      panel.className = 'card';
      panel.style.marginTop = '18px';
      section.appendChild(panel);
    }
    let settings = {};
    try { settings = await call('settings.get', {}); } catch (error) {
      panel.innerHTML = '<h3>Hardware Optimization</h3><p class="muted">Settings are unavailable: ' + esc(error?.message || error) + '</p>';
      return;
    }
    const accelerators = Array.isArray(result.accelerators) ? result.accelerators : [];
    const available = [...new Set(accelerators
      .filter(item => item && item.supported === true && ['cuda', 'rocm', 'xpu'].includes(String(item.backend)))
      .map(item => String(item.backend)))];
    const options = [
      {value:'automatic', label:'Automatic — choose the best validated backend'},
      {value:'cpu', label:'CPU only'}
    ];
    if (available.includes('cuda')) options.push({value:'cuda',label:'NVIDIA CUDA'});
    if (available.includes('rocm')) options.push({value:'rocm',label:'AMD ROCm'});
    if (available.includes('xpu')) options.push({value:'xpu',label:'Intel XPU'});
    const selected = String(settings.qwen_backend || 'automatic').toLowerCase();
    if (!options.some(option => option.value === selected)) {
      options.push({value:selected,label:selected.toUpperCase() + ' — saved choice, currently unavailable'});
    }
    const lowMemory = settings.qwen_low_memory === true;
    const concurrency = lowMemory ? 1 : Math.max(1, Math.min(3, Number(settings.concurrency || 1)));
    const qwenModels = Array.isArray(result.qwen_models_installed) ? result.qwen_models_installed : [];
    const last = result.last_inference && typeof result.last_inference === 'object' ? result.last_inference : {};
    const actual = last.verified_inference
      ? String(last.backend || 'unknown').toUpperCase() + ' · ' + String(last.device || 'device unavailable')
      : 'No verified Qwen inference recorded yet';
    panel.innerHTML =
      '<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap">' +
        '<div><h3 style="margin:0">Hardware Optimization</h3>' +
        '<p class="muted" style="margin:4px 0 0">Hardware detection, validated runtime and actual model inference are reported separately.</p></div>' +
        '<span class="muted" style="font-size:12px">Last Qwen inference: ' + esc(actual) + '</span></div>' +
      '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:14px">' +
        '<label>Preferred Qwen backend<select id="performanceQwenBackend" class="input" style="display:block;width:100%;margin-top:6px">' +
          options.map(option => '<option value="' + esc(option.value) + '"' + (option.value === selected ? ' selected' : '') + '>' + esc(option.label) + '</option>').join('') +
        '</select></label>' +
        '<label style="display:flex;gap:8px;align-items:center"><input id="performanceQwenLowMemory" type="checkbox"' + (lowMemory ? ' checked' : '') + '> Low-memory mode</label>' +
        '<label>Maximum concurrent audiobook jobs<select id="performanceHeavyConcurrency" class="input" style="display:block;width:100%;margin-top:6px"' + (lowMemory ? ' disabled' : '') + '>' +
          [1,2,3].map(value => '<option value="' + value + '"' + (value === concurrency ? ' selected' : '') + '>' + value + '</option>').join('') +
        '</select></label>' +
      '</div>' +
      '<p class="muted" style="margin:10px 0 0;font-size:12px">Low-memory mode enforces one heavy generation job, requests low-memory model loading when supported and checks actual free accelerator memory before loading. If a GPU runtime cannot be validated, Auto reports the reason and falls back to CPU without changing the selected model or voice identity. Settings apply to new jobs; active inference is never switched mid-job.</p>' +
      '<div style="display:grid;grid-template-columns:minmax(180px,1fr) auto;gap:10px;align-items:end;margin-top:14px">' +
        '<label>Qwen CustomVoice benchmark model<select id="performanceQwenBenchmarkModel" class="input" style="display:block;width:100%;margin-top:6px">' +
          qwenModels.map(kind => '<option value="' + esc(kind) + '">' + esc(kind) + '</option>').join('') +
        '</select></label>' +
        '<button type="button" class="' + esc($('runTtsBenchmark')?.className || $('runBenchmark')?.className || 'btn') + '" data-run-qwen-benchmark ' + (qwenModels.length ? '' : 'disabled') + '>Run Qwen 30s warm preview benchmark</button>' +
      '</div>' +
      (!qwenModels.length ? '<p class="muted" style="margin:6px 0 0;font-size:12px">Install and verify a Qwen CustomVoice 0.6B or 1.7B model in Models Center to run this benchmark.</p>' : '') +
      '<div style="display:flex;justify-content:flex-end;margin-top:12px"><button type="button" class="' + esc($('runTtsBenchmark')?.className || $('runBenchmark')?.className || 'btn') + '" data-save-hardware-optimization>Save optimization settings</button></div>';
    const low = panel.querySelector('#performanceQwenLowMemory');
    const concurrencySelect = panel.querySelector('#performanceHeavyConcurrency');
    low?.addEventListener('change', () => {
      if (concurrencySelect) {
        concurrencySelect.disabled = low.checked;
        if (low.checked) concurrencySelect.value = '1';
      }
    });
    panel.querySelector('[data-run-qwen-benchmark]')?.addEventListener('click', act(async () => {
      const modelKind = panel.querySelector('#performanceQwenBenchmarkModel')?.value;
      if (!modelKind) { message('Install a Qwen CustomVoice model before benchmarking.', true); return; }
      const button = panel.querySelector('[data-run-qwen-benchmark]');
      if (button) button.disabled = true;
      try {
        const queued = await call('performance.qwen_benchmark', {model_kind: modelKind, voice: 'Ryan'});
        await refreshJobs();
        message('Qwen 30-second warm preview benchmark queued for ' + modelKind + '.');
        await monitorJob(queued.job_id, null, async job => {
          await refreshPerformance();
          await refreshJobs();
          const result = job?.result || {};
          if (job?.state === 'completed' && result.success) {
            message('Qwen benchmark: ' + Number(result.seconds).toFixed(2) + 's for ' +
              Number(result.audio_seconds).toFixed(2) + 's audio · RTF ' +
              Number(result.realtime_factor).toFixed(3) + ' · ' +
              (result.target_performance_met ? '30s / under-60s target met' : 'target not met'));
          } else {
            message(job?.error?.message || job?.message || 'Qwen benchmark failed.', true);
          }
        });
      } finally {
        if (button) button.disabled = false;
      }
    }));
    panel.querySelector('[data-save-hardware-optimization]')?.addEventListener('click', act(async () => {
      const backend = panel.querySelector('#performanceQwenBackend')?.value || 'automatic';
      const lowMemoryEnabled = Boolean(low?.checked);
      const maxConcurrent = lowMemoryEnabled ? 1 : Number(concurrencySelect?.value || 1);
      await call('settings.save', {
        qwen_backend: backend,
        qwen_low_memory: lowMemoryEnabled,
        concurrency: maxConcurrent
      });
      message('Hardware optimization settings saved. They apply to newly started Qwen and audiobook generation jobs.');
      await refreshPerformance();
    }));
  }

  function renderPerformanceHistory(result = {}) {
    const section = $('performance');
    if (!section) return;
    let panel = $('performanceBenchmarkHistory');
    if (!panel) {
      panel = document.createElement('section');
      panel.id = 'performanceBenchmarkHistory';
      panel.className = 'card';
      panel.style.marginTop = '18px';
      section.appendChild(panel);
    }
    const records = Array.isArray(result.benchmark_history) ? result.benchmark_history : [];
    const buttonClass = $('runTtsBenchmark')?.className || $('runBenchmark')?.className || 'btn';
    const rows = records.map((record, index) => {
      const data = record?.result && typeof record.result === 'object' ? record.result : {};
      const hardware = data.hardware && typeof data.hardware === 'object' ? data.hardware : {};
      const resources = data.resources && typeof data.resources === 'object' ? data.resources : {};
      const success = data.success === true;
      const status = success ? 'Successful' : 'Failed';
      const measuredAt = record.measured_at ? new Date(record.measured_at).toLocaleString() : 'Date unavailable';
      const duration = Number.isFinite(Number(data.seconds)) ? Number(data.seconds).toFixed(2) + ' s' : 'Not measured';
      const audio = Number.isFinite(Number(data.audio_seconds)) ? Number(data.audio_seconds).toFixed(2) + ' s' : 'Not measured';
      const rtf = Number.isFinite(Number(data.realtime_factor)) ? Number(data.realtime_factor).toFixed(3) : 'Not measured';
      const cpu = Number.isFinite(Number(resources.cpu_percent)) ? Number(resources.cpu_percent).toFixed(1) + '%' : 'Unavailable';
      const ram = Number.isFinite(Number(resources.memory_available_bytes)) ? (Number(resources.memory_available_bytes) / 1024 ** 3).toFixed(1) + ' GB free' : 'Unavailable';
      const gpu = hardware.gpu_name || 'No GPU reported';
      const backend = data.backend_verified === true
        ? String(data.backend || 'unknown').toUpperCase() + ' · verified'
        : 'Unverified · requested ' + String(data.requested_backend || 'automatic');
      const gpuUse = resources.gpu_percent !== null && resources.gpu_percent !== undefined && Number.isFinite(Number(resources.gpu_percent))
        ? Number(resources.gpu_percent).toFixed(1) + '%' : 'Unavailable';
      const vram = resources.vram_used_mb !== null && resources.vram_used_mb !== undefined &&
        resources.vram_total_mb !== null && resources.vram_total_mb !== undefined
        ? Number(resources.vram_used_mb).toFixed(0) + ' / ' + Number(resources.vram_total_mb).toFixed(0) + ' MB'
        : 'Unavailable';
      const target = data.target_audio_seconds === 30
        ? (data.target_performance_met ? '30s preview / under 60s: met' : '30s preview / under 60s: not met')
        : '';
      return '<article class="performance-history-row" style="padding:12px 0;border-top:1px solid var(--border-subtle,rgba(255,255,255,.10))">' +
        '<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">' +
          '<label style="display:flex;gap:7px;align-items:center"><input type="checkbox" data-performance-select="' + esc(String(record.benchmark_id || '')) + '"> Compare</label>' +
          '<strong>' + esc(String(data.model_kind || data.voice || 'Piper')) + '</strong>' +
          (data.provider ? '<span class="muted" style="margin-left:8px">' + esc(String(data.provider)) + '</span>' : '') +
          '<span class="muted">' + esc(status) + ' · ' + esc(measuredAt) +
          (record.source_origin === 'imported' ? ' · Imported from ' + esc(String(record.source_file_name || 'another PC')) : ' · This PC') + '</span>' +
        '</div>' +
        '<div class="muted" style="margin-top:5px;font-size:12px">' +
          'Actual inference backend: ' + esc(String(backend)) + ' · GPU: ' + esc(String(gpu)) +
        '</div>' +
        (hardware.recommended_backend ? '<div class="muted" style="margin-top:4px;font-size:11px">Host recommendation: ' + esc(String(hardware.recommended_backend)) + '</div>' : '') +
        '<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:6px;font-size:12px">' +
          '<span>Synthesis: ' + esc(duration) + '</span><span>Audio: ' + esc(audio) +
          '</span><span>RTF: ' + esc(rtf) + '</span><span>CPU: ' + esc(cpu) +
          '</span><span>RAM: ' + esc(ram) + '</span><span>GPU: ' + esc(gpuUse) +
          '</span><span>VRAM: ' + esc(vram) + '</span>' +
        '</div>' +
        (target ? '<div style="margin-top:6px;font-size:12px"><strong>' + esc(target) + '</strong></div>' : '') +
        '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">' +
          '<button type="button" class="' + esc(buttonClass) + '" data-performance-repeat="' + index + '">Repeat</button>' +
          '<details><summary class="muted" style="cursor:pointer;padding:7px">View details</summary>' +
          '<pre class="muted" style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px;max-height:240px;overflow:auto">' +
          esc(JSON.stringify(record, null, 2)) + '</pre></details>' +
        '</div></article>';
    }).join('');
    panel.innerHTML =
      '<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap">' +
        '<div><h3 style="margin:0">Benchmark History</h3>' +
        '<p class="muted" style="margin:4px 0 0">Persisted local synthesis measurements; clearing this list does not clear Background Jobs or model files.</p></div>' +
        '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
          '<button type="button" class="' + esc(buttonClass) + '" data-performance-import>Import PC report</button>' +
          '<button type="button" class="' + esc(buttonClass) + '" data-performance-compare ' + (records.length >= 2 ? '' : 'disabled') + '>Compare selected (2)</button>' +
          '<button type="button" class="' + esc(buttonClass) + '" data-performance-export ' + (records.length ? '' : 'disabled') + '>Export report</button>' +
          '<button type="button" class="' + esc(buttonClass) + '" data-performance-clear ' + (records.length ? '' : 'disabled') + '>Clear history</button>' +
        '</div></div>' +
      (rows || '<p class="muted" style="margin:12px 0 0">No benchmark runs have been recorded yet. Run a real local TTS benchmark to create the first record.</p>');
    const comparisonButton = panel.querySelector('[data-performance-compare]');
    const comparisonChecks = [...panel.querySelectorAll('[data-performance-select]')];
    const updateComparisonButton = () => {
      const selectedCount = comparisonChecks.filter(input => input.checked).length;
      if (comparisonButton) {
        comparisonButton.disabled = selectedCount !== 2;
        comparisonButton.textContent = 'Compare selected (' + selectedCount + '/2)';
      }
    };
    comparisonChecks.forEach(input => input.addEventListener('change', () => {
      const checked = comparisonChecks.filter(item => item.checked);
      if (checked.length > 2) input.checked = false;
      updateComparisonButton();
    }));
    updateComparisonButton();
    panel.querySelector('[data-performance-import]')?.addEventListener('click', act(async () => {
      const imported = await call('performance.history.import', {});
      if (imported?.cancelled) return;
      message('Imported ' + Number(imported?.imported || 0) + ' benchmark record(s). Original PC hardware information was preserved.');
      await refreshPerformance();
    }));
    comparisonButton?.addEventListener('click', act(async () => {
      const selected = comparisonChecks.filter(input => input.checked).map(input => input.dataset.performanceSelect);
      if (selected.length !== 2) return;
      const comparison = await call('performance.history.compare', {benchmark_ids:selected});
      let resultPanel = panel.querySelector('#performanceComparisonResult');
      if (!resultPanel) {
        resultPanel = document.createElement('section');
        resultPanel.id = 'performanceComparisonResult';
        resultPanel.className = 'card';
        resultPanel.style.marginTop = '12px';
        panel.appendChild(resultPanel);
      }
      const first = comparison.records?.[0] || {}, second = comparison.records?.[1] || {};
      const fmt = value => Number.isFinite(Number(value)) ? Number(value).toFixed(2) : 'Unavailable';
      resultPanel.innerHTML =
        '<h4 style="margin:0 0 8px">PC performance comparison</h4>' +
        '<p class="muted" style="margin:0 0 8px">Same provider, model, voice and workload. Imported results retain their source-PC details.</p>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px">' +
          '<div><strong>' + esc(String(first.label || 'PC A')) + '</strong><div class="muted">Backend: ' + esc(String(first.backend || 'Unavailable')) + '</div><div>Synthesis: ' + fmt(first.synthesis_seconds) + ' s</div><div>RTF: ' + fmt(first.realtime_factor) + '</div></div>' +
          '<div><strong>' + esc(String(second.label || 'PC B')) + '</strong><div class="muted">Backend: ' + esc(String(second.backend || 'Unavailable')) + '</div><div>Synthesis: ' + fmt(second.synthesis_seconds) + ' s</div><div>RTF: ' + fmt(second.realtime_factor) + '</div></div>' +
        '</div><p style="margin:10px 0 0"><strong>Faster: ' + esc(String(comparison.faster || 'Equal')) + '</strong> · ' + fmt(comparison.speedup_ratio) + '× relative speed difference</p>';
    }));
    panel.querySelector('[data-performance-export]')?.addEventListener('click', act(async () => {
      const exported = await call('performance.history.export', {});
      if (exported?.cancelled) return;
      if (!exported?.exported) { message('There are no benchmark records to export.', true); return; }
      message('Benchmark report exported: ' + (exported.path || 'saved'));
    }));
    panel.querySelector('[data-performance-clear]')?.addEventListener('click', act(async () => {
      const accepted = await requestModelActionDialog({
        title: 'Clear benchmark history',
        description: 'Only saved Performance Center benchmark records will be cleared. Background Jobs history, projects, model files and voice profiles will remain untouched.',
        confirmLabel: 'Clear benchmark records',
        danger: true
      });
      if (!accepted) return;
      const cleared = await call('performance.history.clear', {});
      message('Cleared ' + Number(cleared?.cleared || 0) + ' benchmark record(s). Background Job history was preserved.');
      await refreshPerformance();
    }));
    panel.querySelectorAll('[data-performance-repeat]').forEach(button => {
      button.addEventListener('click', act(async () => {
        const index = Number(button.dataset.performanceRepeat);
        const record = records[index];
        const voice = String(record?.result?.voice || '').trim();
        if (!voice) { message('The saved benchmark does not contain a repeatable voice selection.', true); return; }
        button.disabled = true;
        try {
          const isQwen = data.provider === 'QwenCharacterProvider';
          const command = isQwen ? 'performance.qwen_benchmark' : 'performance.benchmark';
          const payload = isQwen ? {voice, model_kind: data.model_kind} : {voice};
          const queued = await call(command, payload);
          await refreshJobs();
          message('Repeat benchmark queued for ' + voice + '.');
          await monitorJob(queued.job_id, null, async job => {
            await refreshPerformance();
            await refreshJobs();
            if (job?.state === 'completed' && job?.result?.success) {
              message('Repeat benchmark complete: ' + Number(job.result.seconds).toFixed(2) +
                's synthesis · RTF ' + Number(job.result.realtime_factor).toFixed(3));
            } else {
              message(job?.error?.message || job?.message || 'Repeat benchmark failed.', true);
            }
          });
        } finally {
          button.disabled = false;
        }
      }));
    });
  }

  async function refreshPerformance() {
    let result;
    try {
      result = await call('performance.info', {refresh:false});
    } catch (error) {
      result = {available:false, reason:error?.message || 'Live hardware telemetry is unavailable.'};
    }
    const section = $('performance');
    if (!result?.available) {
      const metrics = section?.querySelectorAll('.grid.metrics .metric');
      const labels = [
        ['Unavailable', 'CPU telemetry unavailable'],
        ['Unavailable', 'GPU / VRAM telemetry unavailable'],
        ['Not tested', 'Generation performance'],
        ['Unavailable', 'Backend recommendation']
      ];
      metrics?.forEach((metric,index)=>{
        const strong=metric.querySelector('strong'),detail=metric.querySelector('span');
        if(strong&&labels[index])strong.textContent=labels[index][0];
        if(detail&&labels[index])detail.textContent=labels[index][1];
      });
      if($('benchmarkResult'))$('benchmarkResult').textContent='Not tested';
      const note=$('benchmarkResult')?.parentElement?.querySelector('p.muted');
      if(note)note.textContent=result?.reason||'Host telemetry is unavailable on this device.';
      await renderHardwareOptimizationSettings(result || {});
      renderPerformanceHistory(result || {});
      return {...(result||{}),available:false};
    }
    const metrics=section?.querySelectorAll('.grid.metrics .metric');
    const fmt=value=>value!==null&&value!==undefined&&Number.isFinite(Number(value))?Number(value):null;
    const cpu=fmt(result.cpu_percent),gpu=fmt(result.gpu_percent),vram=fmt(result.vram_used_mb),
      totalVram=fmt(result.vram_total_mb),duration=fmt(result.generation_seconds);
    const ram=fmt(result.memory_total_bytes),free=fmt(result.memory_available_bytes);
    const values=[
      [cpu===null?'Unavailable':cpu.toFixed(1)+'%','CPU usage'],
      [gpu===null?'Detected':gpu.toFixed(1)+'%',result.gpu_name?
        result.gpu_name+' · '+(vram===null?'VRAM telemetry unavailable':Math.round(vram)+' / '+Math.round(totalVram||0)+' MB VRAM'):'GPU telemetry'],
      [duration===null?'Not tested':duration.toFixed(2)+' s',
        duration===null?'No real synthesis benchmark yet':
          (result.benchmark_voice||'Piper')+' · '+(fmt(result.benchmark_audio_seconds)===null?'audio duration unavailable':fmt(result.benchmark_audio_seconds).toFixed(2)+' s audio')+
          (fmt(result.benchmark_realtime_factor)===null?'':' · RTF '+fmt(result.benchmark_realtime_factor).toFixed(2))],
      [String(result.recommended_backend||'Unavailable'),result.backend_active?'Runtime active':'Detected / runtime status']
    ];
    metrics?.forEach((metric,index)=>{
      const strong=metric.querySelector('strong'),detail=metric.querySelector('span');
      if(strong&&values[index])strong.textContent=values[index][0];
      if(detail&&values[index])detail.textContent=values[index][1];
    });
    const ready=section?.querySelectorAll('.ready-list .ready b');
    if(ready?.length){
      ready[0].textContent=ram===null?'Unavailable':(ram/1024**3).toFixed(1)+' GB total RAM';
      if(ready[1])ready[1].textContent=free===null?'Unavailable':(free/1024**3).toFixed(1)+' GB available RAM';
      if(ready[2])ready[2].textContent=result.backend_active?'GPU runtime active':'No active GPU runtime';
    }
    const note=$('benchmarkResult')?.parentElement?.querySelector('p.muted');
    if(note)note.textContent=(result.reason||'Live host telemetry connected.')+' · '+(result.platform||'')+' · '+(result.processor||'');
    if($('benchmarkResult'))$('benchmarkResult').textContent=duration===null?'Not tested':duration.toFixed(1)+' s';
    await renderHardwareOptimizationSettings(result);
    renderPerformanceHistory(result);
    return result;
  }
  function requestModelActionDialog(options = {}) {
    return new Promise(resolve => {
      $('ryuModelActionDialog')?.remove();
      const overlay = document.createElement('div');
      overlay.id = 'ryuModelActionDialog';
      overlay.style.cssText = 'position:fixed;inset:0;z-index:100000;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(3,5,10,.80);backdrop-filter:blur(7px)';
      const input = options.input ? '<label for="ryuModelActionInput" style="display:block;font-size:12px;color:#aeb6c5;margin:14px 0 6px">' + esc(options.input.label || 'Value') + '</label><input id="ryuModelActionInput" maxlength="140" value="' + esc(options.input.value || '') + '" placeholder="' + esc(options.input.placeholder || '') + '" style="box-sizing:border-box;width:100%;padding:12px;border-radius:10px;border:1px solid #42495a;background:#0c1018;color:#f6f7fa;font:inherit;outline-color:#e63361" />' : '';
      overlay.innerHTML =
        '<section role="dialog" aria-modal="true" aria-labelledby="ryuModelActionTitle" style="width:min(500px,100%);max-height:85vh;overflow:auto;background:#151a25;border:1px solid rgba(255,255,255,.13);border-radius:18px;box-shadow:0 24px 80px rgba(0,0,0,.5);padding:22px;color:#f4f5f8">' +
          '<div style="color:#e8b957;font-size:11px;font-weight:800;letter-spacing:.13em;text-transform:uppercase;margin-bottom:8px">Model management</div>' +
          '<h2 id="ryuModelActionTitle" style="margin:0 0 9px;font-size:22px">' + esc(options.title || 'Confirm action') + '</h2>' +
          '<p style="margin:0;color:#aeb6c5;font-size:13px;line-height:1.6;white-space:pre-line">' + esc(options.description || '') + '</p>' +
          input +
          '<div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px;flex-wrap:wrap">' +
            '<button type="button" data-model-dialog-cancel style="padding:10px 14px;border-radius:10px;background:#1c2230;border:1px solid #343b4a;color:#f2f4f8;font-weight:700;cursor:pointer">Cancel</button>' +
            '<button type="button" data-model-dialog-confirm style="padding:10px 16px;border-radius:10px;background:' + (options.danger ? '#7e1f36' : '#c92050') + ';border:1px solid ' + (options.danger ? '#b63350' : '#e7426a') + ';color:white;font-weight:800;cursor:pointer">' + esc(options.confirmLabel || 'Continue') + '</button>' +
          '</div></section>';
      const field = overlay.querySelector('#ryuModelActionInput');
      const finish = value => { overlay.remove(); resolve(value); };
      overlay.querySelector('[data-model-dialog-cancel]').addEventListener('click', () => finish(null));
      overlay.querySelector('[data-model-dialog-confirm]').addEventListener('click', () => {
        if (options.input) {
          const value = String(field?.value || '').trim();
          if (!value) { field?.focus(); message('Enter a value before continuing.', true); return; }
          if (!/^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$/.test(value)) {
            field?.focus(); message('Use letters, numbers, dots, underscores or hyphens only.', true); return;
          }
          finish(value);
        } else finish(true);
      });
      overlay.addEventListener('click', event => { if (event.target === overlay) finish(null); });
      overlay.addEventListener('keydown', event => {
        if (event.key === 'Escape') { event.preventDefault(); finish(null); }
        if (event.key === 'Enter' && options.input) { event.preventDefault(); overlay.querySelector('[data-model-dialog-confirm]').click(); }
      });
      document.body.appendChild(overlay);
      (field || overlay.querySelector('[data-model-dialog-confirm]'))?.focus();
      field?.select();
    });
  }

  function formatModelBytes(raw) {
    const value = Number(raw || 0);
    if (!Number.isFinite(value) || value <= 0) return '—';
    const units = ['B','KB','MB','GB','TB'];
    let amount = value, unit = 0;
    while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit++; }
    return amount.toFixed(unit >= 3 ? 1 : 0) + ' ' + units[unit];
  }
  function modelNeedsAttention(model) {
    const status = String(model?.status || '').trim().toLowerCase();
    if (['missing','not configured','partially installed','unhealthy','unsupported','location unavailable'].includes(status)) return true;
    return /incomplete|needs installation|needs setup|setup required|api key required|runtime required|dependency missing|not ready|no .* detected|no .* installed/i
      .test(status);
  }
  function modelLifecycleActionButtons(model) {
    const actions = [];
    const installId = model.install_id || model.model_id;
    const repairId = model.repair_id || model.model_id;
    const uninstallId = model.uninstall_id || model.model_id;
    const isPiper = model.model_id === 'piper';
    if (model.installable && (!model.installed || isPiper)) {
      const label = isPiper ? 'Add voice model' : 'Install';
      actions.push('<button type="button" class="btn primary small" data-model-install="' + esc(installId) + '" title="Install this component using the local backend">' + label + '</button>');
    }
    // Piper can contain several independently installed voices. Its dedicated
    // selector below targets the exact voice, so generic duplicate repair/delete
    // buttons would be ambiguous and are intentionally omitted.
    if (model.repairable && !isPiper) {
      actions.push('<button type="button" class="btn secondary small" data-model-repair="' + esc(repairId) + '" title="Recheck or repair this component using its real installer">Repair</button>');
    }
    if (model.uninstallable && !isPiper) {
      const kind = model.model_id && /^(custom-|design-|base-)/.test(model.model_id) ? model.model_id : '';
      actions.push('<button type="button" class="btn danger small" data-model-uninstall="' + esc(uninstallId) + '"' +
        (kind ? ' data-model-kind="' + esc(kind) + '"' : '') +
        ' title="Remove only this app-managed component">Uninstall</button>');
    }
    const verifyId = model.verify_id || model.model_id;
    actions.push('<button type="button" class="btn secondary small" data-model-verify="' + esc(verifyId) + '" title="Check actual installed files and required dependencies; this does not claim functional inference readiness">Verify files</button>');
    const providerTarget = ({
      piper:'offline', kokoro:'offline', 'custom-0.6b':'customvoice', 'custom-1.7b':'customvoice',
      'design-1.7b':'voicedesign', 'base-0.6b':'qwenclone', 'base-1.7b':'qwenclone',
      'qwen-runtime':'customvoice', 'chatterbox-runtime':'customref',
      'windows-sapi':'sapi', 'edge-tts':'edge', 'elevenlabs':'eleven'
    }[model.model_id] || ({
      'qwen-customvoice':'customvoice','qwen-voicedesign':'voicedesign','qwen-clone':'qwenclone'
    }[model.feature]));
    if (providerTarget) {
      actions.push('<button type="button" class="btn secondary small" data-model-open-provider="' + esc(providerTarget) + '">Open Voice Studio</button>');
    } else if (model.model_id === 'audiobook-ai') {
      actions.push('<button type="button" class="btn secondary small" data-model-open-page="characters">Open Character Studio</button>');
    }
    return actions.join('');
  }
  function renderModelInventory() {
    if (!document.getElementById('modelInstallDetailsStyle')) {
      const style = document.createElement('style');
      style.id = 'modelInstallDetailsStyle';
      style.textContent = '.model-install-details[open]>.model-install-content{display:grid;gap:10px;padding-top:10px}#backgroundJobsModal .jobs-modal,.modal-back .jobs-modal{box-sizing:border-box;width:min(780px,calc(100vw - 40px));min-width:0;max-width:calc(100vw - 40px)}';
      document.head.appendChild(style);
    }
    const rows = Array.isArray(window.ryuModelInventoryRows) ? window.ryuModelInventoryRows : [];
    const grid = $('modelGrid');
    const query = String($('modelInventorySearch')?.value || '').trim().toLowerCase();
    const filter = $('modelInventoryFilter')?.value || 'all';
    const filtered = rows.filter(model => {
      const searchText = [model.name,model.provider,model.model_id,model.status,model.status_detail,
        model.capability,model.version,model.notes,model.requirements,
        ...(Array.isArray(model.dependencies) ? model.dependencies : [])].join(' ').toLowerCase();
      if (query && !searchText.includes(query)) return false;
      if (filter === 'attention' && !modelNeedsAttention(model)) return false;
      if (filter === 'ready' && String(model.status || '') !== 'Ready') return false;
      if (filter === 'local' && model.component_type === 'provider') return false;
      return true;
    });
    if (!grid) return;
    grid.style.display = 'grid';
    grid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))';
    grid.style.gap = '12px';
    grid.style.alignItems = 'stretch';
    grid.style.minWidth = '0';
    grid.style.paddingBottom = '48px';
    const signature = JSON.stringify(rows);
    if (grid.dataset.modelSignature !== signature || grid.dataset.modelFilter !== query + '|' + filter) {
      grid.dataset.modelSignature = signature;
      grid.dataset.modelFilter = query + '|' + filter;
      grid.innerHTML = filtered.map(model => {
        const local = model.component_type !== 'provider';
        const status = String(model.status || (model.installed ? 'Installed' : 'Missing'));
        const problem = modelNeedsAttention({...model,status});
        const badge = status === 'Ready' ? '' : status === 'Installed' ? 'info' : problem ? 'warn' : 'info';
        const storage = Number(model.storage_bytes || 0) > 0
          ? '<span class="model-meta-item">Local files · ' + esc(formatModelBytes(model.storage_bytes)) + '</span>' : '';
        const requirement = model.requirements ? '<p class="model-requirements">' + esc(model.requirements) + '</p>' : '';
        const statusDetail = model.status_detail && model.status_detail !== status
          ? '<p class="muted" style="font-size:12px;margin:0">' + esc(model.status_detail) + '</p>' : '';
        const piperVoices = model.model_id === 'piper' && Array.isArray(model.installed_voice_names) && model.installed_voice_names.length
          ? '<div class="model-voice-manager"><label>Installed local voices<select data-piper-voice-select>' +
            model.installed_voice_names.map(name => '<option value="' + esc(name) + '">' + esc(name) + '</option>').join('') +
            '</select></label><div class="model-actions model-voice-actions">' +
            '<button type="button" class="btn secondary small" data-model-repair="piper">Repair selected voice</button>' +
            '<button type="button" class="btn danger small" data-model-uninstall="piper">Remove selected voice</button></div></div>'
          : '';
        const pathRows = [];
        const addPathRow = (label, location, path) => {
          if (!path) return;
          pathRows.push('<div class="model-path-row" style="display:grid;gap:6px;margin:8px 0">' +
            '<strong>' + esc(label) + '</strong><code style="overflow-wrap:anywhere;white-space:normal">' + esc(path) + '</code>' +
            '<div class="model-actions"><button type="button" class="btn secondary small" data-model-open-folder="' + esc(model.model_id) + '" data-model-location="' + esc(location) + '">Open folder</button>' +
            '<button type="button" class="btn secondary small" data-model-copy-path="' + esc(model.model_id) + '" data-model-location="' + esc(location) + '">Copy path</button></div></div>');
        };
        addPathRow('Model location', 'model', model.model_path);
        addPathRow('Runtime location', 'runtime', model.runtime_path);
        addPathRow('Python environment', 'python', model.python_path);
        addPathRow('Runtime executable', 'runtime_executable', model.runtime_executable);
        const verifiedAt = model.last_verified ? new Date(model.last_verified) : null;
        const verifiedLabel = verifiedAt && !Number.isNaN(verifiedAt.getTime()) ? verifiedAt.toLocaleString() : 'Not verified';
        const dependencyList = Array.isArray(model.dependencies) ? model.dependencies.join(', ') : String(model.dependencies || '');
        const deviceList = Array.isArray(model.supported_devices) && model.supported_devices.length
          ? model.supported_devices.join(', ') : 'Not yet assessed';
        const infoRows = [
          ['Capability', model.capability],
          ['Detected version', model.version || 'Not reported'],
          ['Runtime version', model.runtime_version || 'Not reported'],
          ['Runtime status', model.runtime_status || 'Not assessed'],
          ['Health', model.health || 'Not verified'],
          ['Last verified', verifiedLabel],
          ['Dependencies', dependencyList || 'Not reported'],
          ['Hardware compatibility', model.hardware_compatibility || 'Not assessed'],
          ['Supported compute devices', deviceList]
        ];
        const infoMarkup = '<div class="model-install-info" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:8px">' +
          infoRows.map(([label,value]) => '<div style="min-width:0;padding:8px;border:1px solid var(--border,rgba(255,255,255,.1));border-radius:8px">' +
            '<span class="muted" style="display:block;font-size:11px">' + esc(label) + '</span>' +
            '<strong style="display:block;overflow-wrap:anywhere;font-size:12px">' + esc(value) + '</strong></div>').join('') +
          '</div>';
        const details = local && (model.file_inventory_available || pathRows.length)
          ? '<details class="model-install-details" data-model-details="' + esc(model.model_id) + '" style="border-top:1px solid var(--border,rgba(255,255,255,.12));padding-top:8px">' +
            '<summary style="cursor:pointer;font-weight:600">Installation details · actual paths, runtime and files</summary>' +
            '<div class="model-install-content">' + infoMarkup + pathRows.join('') +
            '<div data-model-file-list style="display:grid;gap:6px"><span class="muted">Expand to enumerate the actual installed files and their sizes.</span></div></div></details>'
          : '';
        return '<article class="card model-card" data-model-id="' + esc(model.model_id) + '" style="display:flex;flex-direction:column;gap:12px;min-width:0">' +
          '<div class="model-card-head" style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">' +
            '<div style="min-width:0"><div class="model-eyebrow">' + esc(String(model.provider || 'Local component').replace(/-/g,' ')) + '</div>' +
            '<h3 style="margin:6px 0 0;overflow-wrap:anywhere">' + esc(model.name) + '</h3></div>' +
            '<span class="badge ' + badge + '" title="' + esc(status) + '">' + esc(status) + '</span></div>' +
          '<p class="muted model-description">' + esc(model.notes || 'No additional details were returned by the local backend.') + '</p>' +
          (storage ? '<div class="model-meta">' + storage + '</div>' : '') + requirement + statusDetail +
          piperVoices + details +
          '<div class="model-actions">' + modelLifecycleActionButtons(model) + '</div>' +
        '</article>';
      }).join('') || '<p class="muted model-empty">No components match this filter. Refresh the model status or change the filter.</p>';
    }

    const summary = $('modelInventorySummary');
    if (summary) {
      const managed = rows.filter(model => model.component_type !== 'provider');
      const ready = rows.filter(model => model.status === 'Ready').length;
      const installed = rows.filter(model => model.status === 'Installed').length;
      const needsAttention = rows.filter(model => modelNeedsAttention(model)).length;
      const providers = rows.filter(model => model.component_type === 'provider');
      const providersAvailable = providers.filter(model => model.installed).length;
      const free = rows.find(model => model.disk_free_bytes != null)?.disk_free_bytes;
      const storageRoot = rows.find(model => model.storage_root)?.storage_root || 'Local application model folder';
      const managedStorageBytes = rows.reduce((sum, model) => sum + Math.max(0, Number(model.storage_bytes || 0)), 0);
      summary.innerHTML =
        '<div class="model-summary-metrics">' +
          '<div><span>Total components</span><strong>' + rows.length + '</strong></div>' +
          '<div><span>Ready</span><strong>' + ready + '</strong></div>' +
          '<div><span>Installed · not yet verified</span><strong>' + installed + '</strong></div>' +
          '<div><span>Needs attention</span><strong>' + needsAttention + '</strong></div>' +
          '<div><span>System / online providers available</span><strong>' + providersAvailable + ' / ' + providers.length + '</strong></div>' +
        '</div><p class="model-storage-path">Storage root: <code>' + esc(storageRoot) + '</code> · Managed files: ' +
          esc(formatModelBytes(managedStorageBytes)) + ' · Drive free: ' + esc(formatModelBytes(free)) + '</p>';
    }
  }
  async function refreshModels() {
    const requestToken = ++modelListEpoch;
    const forceRefresh = forceModelInventoryRefreshPending;
    forceModelInventoryRefreshPending = false;
    const loadedRows = await loadModelInventory(forceRefresh);
    if (requestToken !== modelListEpoch) return window.ryuModelInventoryRows || [];
    const rows = Array.isArray(loadedRows) ? loadedRows : [];
    window.ryuModelInventoryRows = rows;
    const root = $('models');
    const grid = $('modelGrid');
    if (!root || !grid) return rows;

    // The old static screen said "Check updates" but had no update endpoint.
    // Make its replacement truthful and useful: refresh the live inventory,
    // provider-backed saved profile list, and the installed/readiness statuses.
    let refreshButton = $('modelStatusRefresh');
    if (!refreshButton) {
      refreshButton = [...root.querySelectorAll('button')].find(button =>
        /^check updates$/i.test(String(button.textContent || '').trim())
      ) || null;
    }
    if (refreshButton) {
      refreshButton.id = 'modelStatusRefresh';
      refreshButton.textContent = 'Refresh status';
      refreshButton.title = 'Re-read local model files, runtime markers, provider prerequisites and drive space.';
      if (refreshButton.dataset.ryuRefreshBound !== 'true') {
        refreshButton.dataset.ryuRefreshBound = 'true';
        refreshButton.addEventListener('click', async event => {
          event.preventDefault();
          event.stopPropagation();
          const previousText = refreshButton.textContent;
          refreshButton.disabled = true;
          refreshButton.textContent = 'Refreshing…';
          try {
            forceModelInventoryRefreshPending = true;
            await refreshModels();
            await refreshVoices();
            message('Model status refreshed from the local installation and saved voice catalogue.');
          } catch (error) {
            message(error?.message || String(error), true);
          } finally {
            refreshButton.disabled = false;
            refreshButton.textContent = 'Refresh status';
          }
        });
      }
    }
    let toolbar = $('modelInventoryToolbar');
    if (!toolbar) {
      toolbar = document.createElement('div');
      toolbar.id = 'modelInventoryToolbar';
      toolbar.className = 'model-inventory-toolbar';
      toolbar.style.cssText = 'display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 12px';
      toolbar.innerHTML =
        '<input id="modelInventorySearch" type="search" aria-label="Search models and providers" placeholder="Search models, provider or status" style="flex:1;min-width:220px" />' +
        '<select id="modelInventoryFilter" aria-label="Filter model components" style="min-width:170px"><option value="all">All components</option><option value="attention">Needs setup / attention</option><option value="ready">Installed / ready</option><option value="local">Local models and runtimes</option></select>';
      grid.parentNode.insertBefore(toolbar, grid);
      $('modelInventorySearch').addEventListener('input', renderModelInventory);
      $('modelInventoryFilter').addEventListener('change', renderModelInventory);
    }
    let summary = $('modelInventorySummary');
    if (!summary) {
      summary = document.createElement('section');
      summary.id = 'modelInventorySummary';
      summary.className = 'model-inventory-summary card';
      summary.style.cssText = 'margin:0 0 14px;padding:14px 16px';
      toolbar.insertAdjacentElement('beforebegin', summary);
    }
    const heading = root.querySelector('.model-runtime h2');
    const managed = rows.filter(model => model.component_type !== 'provider');
    const ready = managed.filter(model => model.status === 'Ready').length;
    const missing = managed.length - ready;
    if (heading) heading.textContent = ready + ' managed component(s) functionally ready · ' + missing + ' need setup or further verification';
    // Replace the HTML prototype's fixed storage number with a total derived
    // from live per-component file sizes. Its old capacity bar had no measured
    // denominator, so hide it instead of presenting a fake percentage.
    const managedStorageBytes = rows.reduce((sum, model) =>
      sum + Math.max(0, Number(model.storage_bytes || 0)), 0);
    const liveFreeBytes = rows.find(model => model.disk_free_bytes != null)?.disk_free_bytes;
    const storageLabel = [...root.querySelectorAll('*')].find(node =>
      node.children.length === 0 && node.textContent.trim() === 'Models storage');
    const oldFreeLabel = [...root.querySelectorAll('*')].find(node =>
      node.children.length === 0 && /free in model folder/i.test(node.textContent));
    if (storageLabel) storageLabel.textContent = 'Managed model files';
    if (storageLabel && oldFreeLabel) {
      // Find the smallest storage widget containing both the old metric and its
      // footer so unrelated dashboard metrics are never changed.
      let storageWidget = storageLabel;
      while (storageWidget && storageWidget !== root && !storageWidget.contains(oldFreeLabel)) {
        storageWidget = storageWidget.parentElement;
      }
      if (storageWidget && storageWidget !== root) {
        const oldSize = [...storageWidget.querySelectorAll('*')].find(node =>
          node.children.length === 0 && /^\\d+(?:\\.\\d+)?\\s*(?:B|KB|MB|GB|TB)$/i.test(node.textContent.trim()));
        if (oldSize) oldSize.textContent = formatModelBytes(managedStorageBytes);
        oldFreeLabel.textContent = liveFreeBytes == null
          ? 'Drive free space unavailable'
          : formatModelBytes(liveFreeBytes) + ' free on drive at model location';
        const capacityBars = [...storageWidget.querySelectorAll('*')].filter(node =>
          node.style && node.style.width && /%/.test(node.style.width));
        for (const fill of capacityBars) {
          const track = fill.closest('.progress,.progress-bar,.meter,.storage-progress') || fill.parentElement;
          if (track && track !== storageWidget) track.hidden = true;
          else fill.hidden = true;
        }
      }
    }
    renderModelInventory();
    return rows;
  }
  async function refreshStorageRoots() {
    const result = await call('storage.get');
    const rows = Array.isArray(result?.roots) ? result.roots : [];
    for (const row of rows) {
      const path = $('storagePath_' + row.kind);
      const capacity = $('storageCapacity_' + row.kind);
      if (path) path.textContent = row.path || 'Path unavailable';
      if (capacity) {
        const format = value => formatModelBytes(Math.max(0, Number(value || 0)));
        capacity.textContent = row.available
          ? Number(row.file_count || 0).toLocaleString() + ' files · ' + format(row.component_bytes) +
            ' component data · ' + format(row.used_bytes) + ' used · ' + format(row.free_bytes) +
            ' free · ' + format(row.total_bytes) + ' total'
          : 'Location unavailable · configured path preserved; reconnect the drive to restore access.';
      }
    }
    const status = $('storageStatus');
    if (status) status.textContent = result?.restart_required
      ? 'Storage status refreshed from the local filesystem. Root changes require an application restart.'
      : 'Storage status refreshed.';
    const cleanupHost = $('storageMigrationCleanup');
    if (cleanupHost) {
      const pending = Array.isArray(result?.pending_cleanup) ? result.pending_cleanup : [];
      cleanupHost.innerHTML = pending.length
        ? '<h3>Verified migrations · retained source copies</h3>' + pending.map(item =>
            '<div class="setting-row" style="align-items:flex-start;flex-wrap:wrap"><div style="min-width:210px;flex:1"><b>Retained source copy</b><p class="muted">' +
            esc(item.file_count || 0) + ' files · ' + esc(formatModelBytes(item.total_bytes || 0)) +
            '</p><code style="display:block;overflow-wrap:anywhere">' + esc(item.source || '') +
            '</code><p class="muted">Verified destination: ' + esc(item.destination || '') +
            '</p></div><button class="btn secondary" data-storage-cleanup-source="' + esc(item.journal_name || '') +
            '">Verify &amp; remove old copy</button></div>'
          ).join('')
        : '<p class="muted">No verified migration source copies are awaiting cleanup.</p>';
      cleanupHost.querySelectorAll('[data-storage-cleanup-source]').forEach(button => {
        if (button.dataset.ryuCleanupBound === 'true') return;
        button.dataset.ryuCleanupBound = 'true';
        button.addEventListener('click', async event => {
          event.preventDefault(); event.stopPropagation();
          button.disabled = true;
          const prior = button.textContent;
          button.textContent = 'Verifying…';
          try {
            const cleanup = await call('storage.cleanup_source', {journal_name:button.dataset.storageCleanupSource});
            if (cleanup?.cancelled) return;
            await refreshStorageRoots();
            message('Retained source copy removed only after file-by-file verification against the active destination.');
          } catch (error) {
            message(error?.message || String(error), true);
          } finally {
            button.disabled = false; button.textContent = prior;
          }
        });
      });
    }
    return result;
  }
  function renderHelpGuide() {
    const root = document.getElementById('help');
    if (!root || root.dataset.ryuHelpGuideRendered === 'true') return;
    root.dataset.ryuHelpGuideRendered = 'true';

    const topics = [
      {
        title: 'Getting started',
        summary: 'A safe path from an imported book to a finished audiobook.',
        items: [
          'Open Library to continue an existing project, or use Import Book to create a project from a supported source file.',
          'Review the extracted text and chapter boundaries before configuring voices. Save edits before moving to another screen.',
          'Choose a narrator voice, review detected characters, set pronunciation and sound preferences, then complete Input Project Details.',
          'Use the chapter preview to check the selected chapter and settings before starting full-book generation.',
          'After generation, open Audiobooks to listen to the M4B output and use History or Background Jobs if a task needs attention.'
        ]
      },
      {
        title: 'Dashboard and Library',
        summary: 'Find projects, check their status and recover work safely.',
        items: [
          'Dashboard counts and recent-project cards reflect local project data. Select a card to reopen that exact project.',
          'In Library, search by project metadata and filter by status. Open a project to restore its saved book and metadata.',
          'Use the project delete and recovery controls carefully. Review Trash before permanent purge; deleting a project must not erase its completed History records.',
          'If a project is missing or interrupted, use the available recovery guidance rather than creating a duplicate project immediately.'
        ]
      },
      {
        title: 'Import Studio',
        summary: 'Bring in book text without silently losing content.',
        items: [
          'Supported source formats are TXT, EPUB, searchable PDF and DOCX. Unsupported or corrupt files should show a clear error.',
          'Use Browse or drag and drop to select a file. Wait for extraction to finish and inspect the text preview, title, author and cover metadata.',
          'Check the extracted chapter and word coverage before continuing. Cancel a long import if the wrong file was selected.',
          'Scanned/image-only PDF OCR is not supported. Use a searchable PDF or convert the source to DOCX or TXT first.'
        ]
      },
      {
        title: 'Chapter Studio',
        summary: 'Review, edit and organize the book before narration.',
        items: [
          'Run chapter detection, then review every heading and boundary. Detection should not silently replace your manual edits.',
          'Rename, reorder, split, edit or delete chapters using the available controls. Save changes and wait for the Saved status before leaving.',
          'Use search and Find & Replace to locate text. Review punctuation, paragraph breaks, dialogue and multilingual names after cleanup.',
          'Empty or whitespace-only chapters are identified separately. Valid chapters can continue; an all-empty book must be repaired before generation.',
          'If a save is still in progress, wait for it to finish before splitting or changing chapters again.'
        ]
      },
      {
        title: 'Voice Studio',
        summary: 'Choose a provider, configure a voice, save a profile and preview it.',
        items: [
          'Follow Voice Library → Configure → Voice Profile → Preview & Assign. Guided mode and Show All Steps should preserve the current selection.',
          'Provider readiness is based on the actual runtime, model, network or API configuration. A catalogue entry alone does not mean the provider is ready.',
          'Save Profile Only stores the profile without changing the narrator. Save and Use as Narrator changes the active project narrator; Assign to Character opens the character selector.',
          'Preview targets include 10, 30, 60 or 90 seconds. Check the requested and actual duration, listen in the in-app player, and wait for successful preview completion before assigning.',
          'Changing provider, voice, profile, model, prompt or preview text invalidates an older preview. Generate a fresh preview before assignment.',
          'For voice cloning or custom reference audio, use only voices and recordings you are authorized to use. Online providers require network access; local providers depend on installed models and supported hardware.'
        ]
      },
      {
        title: 'Character Studio',
        summary: 'Review the cast and make sure each dialogue line uses the intended voice.',
        items: [
          'Run Analyze after importing or substantially editing the book. Review character candidates, confidence and dialogue examples before accepting suggestions.',
          'Use the left chapter list in both Manual and AI review to open the full text of a specific chapter. The AI pending queue is filtered to the selected chapter; selecting a passage opens the source-backed review panel.',
          'Use Assigned Cast to review the character, series, dialogue-line count and chapter count. Assigned Voice and AI-assignment percentages reflect saved project assignments, not suggested matches.',
          'Manual assignments are shown separately from AI suggestions. Review low-confidence matches and correct aliases or speaker names when needed. Accepting an AI suggestion saves an assignment; a suggestion alone does not change the cast.',
          'When reviewing an AI or manual passage, you can choose a saved Voice Studio profile in the review panel. Edit Character also lets you change the saved profile for an existing project character.',
          'Use the selected dialogue and selected saved profile to Test Voice. Stop, resume or replay the test from the in-app controls.',
          'Unquoted narration is automatically routed to the project Narrator. Quoted or dash-led dialogue remains in Needs Speaker Review during normal cast-aware generation until it has a character assignment.'
        ]
      },
      {
        title: 'Narrator-only audiobook generation (GEN-07)',
        summary: 'Generate a complete audiobook with the narrator voice when no character voice profiles are configured.',
        items: [
          'Narrator-only mode is available when the active project has zero saved character voice-profile assignments. A list of detected or manually created character candidates without voice profiles does not prevent this mode.',
          'Choose a valid, available saved narrator profile using the project narrator or its series default. The narrator must still be configured; missing narrator profiles continue to block generation.',
          'In narrator-only mode, the narrator intentionally reads every passage, including quoted and dash-led dialogue. You do not need to create character profiles or assign speakers just to generate this version.',
          'The Production job identifies Narrator-only mode and records the effective narrator and zero configured character profiles. Preview and final generation use the same narrator-only route.',
          'As soon as any character voice profile is configured in the project, normal cast-aware rules apply. Unassigned dialogue must then be reviewed or assigned before full generation; the app does not silently route a partial cast to the narrator.',
          'Required project metadata, valid chapters, output-folder permissions and the selected narrator remain mandatory in both modes.'
        ]
      },
      {
        title: 'Character Library',
        summary: 'Reuse characters and series information across projects.',
        items: [
          'Create or select a series, then add a character with a canonical name, aliases and a representative dialogue sample.',
          'Choose a saved voice profile when one is appropriate. A library entry is reusable reference data; confirm the assignment in the current project.',
          'Review series volume and project metadata before generation. Do not assume a character-library voice has been assigned until the project shows the saved assignment.'
        ]
      },
      {
        title: 'Pronunciation Studio',
        summary: 'Control how names and uncommon words are spoken.',
        items: [
          'Add a written form and the exact pronunciation you want spoken. Use the preview to hear the result with the selected voice profile.',
          'Use Current Book for project-specific overrides and Global Library for reusable entries. A book-specific entry takes precedence over a global entry for the same written form.',
          'AI-suggested and manually entered terms are identified separately. Edit, delete or multi-delete entries after reviewing them.',
          'Use the Enable control and the studio-wide pronunciation toggle to control whether saved rules are applied. The Generate toggle must stay synchronized with this setting.',
          'For Japanese names or foreign words, enter the intended English-letter pronunciation explicitly when the automatic pronunciation is not correct. Check common-word suggestions before accepting them.'
        ]
      },
      {
        title: 'Sound Design Studio',
        summary: 'Choose one background-music strategy and review cues before production.',
        items: [
          'Same BGM uses one book-default track throughout the book. Chapter-Based BGM uses only the explicit track saved for each chapter; an unassigned chapter means No BGM and must not fall back to the book default.',
          'Version 1 uses one BGM bed at a time. Do not layer a second legacy ambience track under the selected BGM. Chapter BGM volume is limited to 50%; the book default starts at 18% and is limited to 50%.',
          'Set the chapter track start offset and end/fade behavior where available. The short chapter preview uses the measured audio boundary after paragraph one when the complete first paragraph is included; if the preview is too short or the boundary is ambiguous, increase the duration or choose Immediate / After 10 seconds.',
          'The supported cue slots are Opening, Next Chapter and Closing. Keep cue files short (up to five seconds), preview them, and use Save Cue Changes. Do not expect a separate Scene Transition slot in Version 1.',
          'Voice Only disables all BGM and cues while preserving saved selections for later. Confirm the live mix summary and levels before opening Production Studio.',
          'Use the full-book mix preview to hear the saved narration with the current BGM strategy and cues. It uses temporary copies of saved narration and must not modify the source chapter audio.'
        ]
      },
      {
        title: 'Music Library',
        summary: 'Import, categorize and audition background tracks.',
        items: [
          'Browse All, Fantasy adventure, Battle & warfare, Mystery, Horror, Romance, Sci-fi, Calm narration or Others.',
          'Use search and category filters to find an installed or imported track. Select a track and use Play/Pause to preview it.',
          'Import a supported audio file, choose its category and wait for validation and metadata saving. The track should remain available after leaving the page or restarting the app.',
          'The master BGM default is 18% and the maximum is 50%. Chapter volume is a separate setting, also limited to 50%.'
        ]
      },
      {
        title: 'Production Studio',
        summary: 'Check metadata, preview a chapter and generate the complete book.',
        items: [
          'Open Input Project Details near the output-folder and job controls. Review title, author, narrator, publisher, series, volume, language, release year, genre and cover image.',
          'Complete the required metadata before full-book generation. Incomplete details are highlighted and block full generation; a short preview remains available.',
          'Select a saved chapter in the chapter-preview selector. Preview Audio should render only that chapter, show the selected chapter and actual duration, and keep the full-book generation action separate.',
          'Choose 10, 30, 60 or 90 seconds for preview (30 seconds by default). Listen to the result and download it only after the preview has completed successfully.',
          'During full generation, monitor the current chapter/stage, progress, elapsed time, remaining-time estimate and any error details. Use Pause, Resume, Cancel, Retry or Recover when the job state offers that action.',
          'Preview and final generation should use the same saved pronunciation, voice assignments, BGM strategy, cues and output settings. Save changes in their studio before starting production.'
        ]
      },
      {
        title: 'Audiobooks',
        summary: 'Listen to completed output and navigate by chapter.',
        items: [
          'Open a completed audiobook and use Play/Pause, the timeline, volume and speed controls.',
          'Use the 15-second forward/back controls and the chapter list to navigate. Selecting a chapter should move the playhead to that chapter.',
          'The mini-player remains available while navigating to other screens. Close it when you no longer need playback.',
          'Check the title, author, narrator, cover and chapter list against the project metadata. If playback or chapter navigation fails, keep the output and record the issue before regenerating.'
        ]
      },
      {
        title: 'History and Background Jobs',
        summary: 'Understand completed work and manage active tasks.',
        items: [
          'History is the durable record of terminal operations, including completed, failed and cancelled tasks. Use date filters and search to locate an operation.',
          'Background Jobs shows active and queued work. Open job details to inspect progress, logs, error messages and the project or chapter involved.',
          'Use View, Cancel, Retry or Recover only when the job state offers that action. Character Analysis can be cancelled at a safe inference or chapter boundary; a cancelled analysis does not replace the saved cast with partial results.',
          'A running synthesis or inference may finish its current safe unit before cancellation takes effect. Check the terminal job state in History instead of assuming the task stopped at the instant Cancel was selected.',
          'A retry should preserve valid completed work and report what will be regenerated. History and Background Jobs should agree about the final state of an operation. If a job disappears from the active queue, check History for its terminal result.'
        ]
      },
      {
        title: 'Models Center',
        summary: 'Manage installed voice models and their storage safely.',
        items: [
          'Review each model/runtime status, version, install location, checksum or health result before using it.',
          'Install missing components, Repair unhealthy installations, Verify files or Uninstall unused models from the model action menu.',
          'Active generation or preview jobs protect models they are using. Wait for those jobs to finish before uninstalling or moving a model.',
          'For Qwen, set the global Base model size preference to 0.6B or 1.7B in Models & Voice Engines. VoiceDesign itself uses its 1.7B model and also requires a compatible Base model for long-form voice identity consistency.',
          'The compute backend can be Automatic or an explicitly selected supported CPU/GPU backend. Automatic attempts a compatible GPU runtime when available; treat a GPU as active only after a real inference reports that device, not merely because Windows lists an adapter.',
          'Uninstalling a model must not delete projects, saved voice profiles or user audio. Check the displayed path before removing files.',
          'Use Settings > Storage to choose supported model, project-library and audio-asset roots. Keep external drives connected during migration and verification.'
        ]
      },
      {
        title: 'Performance Center',
        summary: 'Check hardware and measure actual synthesis performance.',
        items: [
          'Refresh the hardware snapshot to inspect CPU, RAM, GPU, VRAM, CUDA/accelerator availability, operating system, disk and model information.',
          'Run the TTS benchmark separately from the hardware refresh. Review synthesis time, generated audio duration, real-time factor (RTF), throughput, resource use and errors.',
          'Repeat and export benchmark records. Compare results only when hardware, model, provider, settings and test text are comparable.',
          'A 30-second preview under 60 seconds is a performance target, not a guarantee on every CPU, GPU or provider. Use the recorded benchmark and actual preview time to assess the machine.'
        ]
      },
      {
        title: 'Settings and Storage',
        summary: 'Configure paths, appearance and local storage locations.',
        items: [
          'Open Settings > Storage to manage supported project-library, audio-asset and model roots. Review the current and target paths before migration.',
          'Do not unplug an external drive while a storage migration, copy or verification is in progress. Keep it connected until the app confirms completion; if interrupted, reconnect the same drive and use the displayed recovery status before retrying. Keep the source until verification succeeds.',
          'Set the output folder and confirm it is writable before generation. The output path shown in Production Studio should match Settings.',
          'Use the appearance and accessibility controls for theme, text scale, window size and reduced motion where available.',
          'Book text and custom reference audio are stored locally for supported local workflows. Online providers require network access and should be clearly identified.'
        ]
      },
      {
        title: 'Troubleshooting',
        summary: 'Practical checks for common problems.',
        items: [
          'Preview fails or no sound plays: confirm the selected provider/model is ready, check the output device and volume, inspect the job error, then retry a short preview.',
          'Wrong voice is heard: confirm the saved profile, provider voice ID, narrator/character assignment and preview validity. Generate a fresh preview after changing any of them.',
          'No BGM on a chapter: in Chapter-Based mode, assign one explicit track to that chapter. No BGM is intentional when no track is saved; the book default is not a fallback.',
          'Generation cannot start: review empty chapters, missing voices, metadata completeness, output-folder permissions and missing model assets.',
          'A storage migration is interrupted: keep the source drive connected, reopen Settings > Storage and use the displayed recovery/verification status before retrying.',
          'An import looks incomplete: compare extracted text and chapter/word coverage with the source. Scanned PDFs need OCR outside this app before import.',
          'A job fails: open its details in Background Jobs or History, read the actual error, then use Retry or Recover only when offered.'
        ]
      },
      {
        title: 'Known limitations',
        summary: 'Features that should not be mistaken for supported behavior.',
        items: [
          'Scanned/image-only PDF OCR is not supported; use searchable PDFs or another supported text format.',
          'M4B is the supported final audiobook container. M4A and MP3 export are not currently supported as final output formats.',
          'The Production chapter preview preserves paragraph boundaries when the selected Chapter-Based track uses After first paragraph. It can demonstrate that offset only when the generated preview contains the complete first paragraph and its exact measured audio boundary. If the selected preview window ends too early or the boundary cannot be measured exactly, the app explains how to increase the duration or choose another offset. The full-book mix preview remains available for checking the saved narration mix.',
          'GPU acceleration depends on the detected hardware, drivers and installed runtime. A device should be treated as supported only when the app reports it and a real benchmark/preview succeeds.',
          'The installed music catalogue and any imported track must have verified source and licensing information. Do not assume a large track count or a licence that is not displayed.'
        ]
      }
    ];

    const cards = topics.map((topic, index) => (
      '<details class="panel help-guide-card" data-help-guide-card style="padding:14px 16px;border:1px solid var(--border,rgba(127,127,127,.25));border-radius:12px;background:var(--panel,var(--surface,transparent))"' +
      (index === 0 ? ' open' : '') + '>' +
      '<summary style="cursor:pointer;display:flex;flex-wrap:wrap;gap:8px;align-items:baseline;font-weight:650">' +
      esc(topic.title) + '<span style="font-weight:400;color:var(--muted,#888);font-size:12px">' + esc(topic.summary) + '</span></summary>' +
      '<ul style="margin:12px 0 0;padding-left:20px;display:grid;gap:8px;line-height:1.55">' +
      topic.items.map(item => '<li>' + esc(item) + '</li>').join('') +
      '</ul></details>'
    )).join('');

    root.innerHTML =
      '<div class="help-guide-shell" style="display:grid;gap:14px;padding-bottom:24px">' +
        '<header style="display:grid;gap:6px">' +
          '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">' +
            '<h1 style="margin:0">Help &amp; Guide</h1>' +
            '<span class="badge" style="font-size:11px">Stage 8 acceptance candidate</span>' +
          '</div>' +
          '<p class="muted" style="margin:0;line-height:1.5">Task-based instructions for importing a book, preparing voices, configuring sound, generating an audiobook and recovering work. This guide describes the current candidate and calls out known limitations.</p>' +
        '</header>' +
        '<div class="help-guide-toolbar" role="search" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">' +
          '<input id="helpGuideSearch" type="search" aria-label="Search Help and Guide" placeholder="Search a screen, task or setting" style="flex:1;min-width:220px" />' +
          '<button type="button" class="btn small secondary" id="helpGuideExpandAll">Expand all</button>' +
          '<button type="button" class="btn small secondary" id="helpGuideCollapseAll">Collapse all</button>' +
        '</div>' +
        '<div id="helpGuideSections" style="display:grid;gap:10px">' + cards + '</div>' +
        '<p id="helpGuideNoResults" class="muted" hidden>No guide topics match that search. Try a screen name or a shorter phrase.</p>' +
      '</div>';

    const cardsInPage = Array.from(root.querySelectorAll('[data-help-guide-card]'));
    const search = root.querySelector('#helpGuideSearch');
    const noResults = root.querySelector('#helpGuideNoResults');
    search?.addEventListener('input', () => {
      const query = String(search.value || '').trim().toLowerCase();
      let visible = 0;
      cardsInPage.forEach(card => {
        const match = !query || card.textContent.toLowerCase().includes(query);
        card.hidden = !match;
        if (match) visible += 1;
      });
      if (noResults) noResults.hidden = visible > 0;
    });
    root.querySelector('#helpGuideExpandAll')?.addEventListener('click', () => {
      cardsInPage.filter(card => !card.hidden).forEach(card => { card.open = true; });
    });
    root.querySelector('#helpGuideCollapseAll')?.addEventListener('click', () => {
      cardsInPage.forEach(card => { card.open = false; });
    });
  }

  function wireStorageControls() {
    const cleanupButton = $('storageCleanupTemp');
    if (cleanupButton && cleanupButton.dataset.ryuCleanupBound !== 'true') {
      cleanupButton.dataset.ryuCleanupBound = 'true';
      cleanupButton.addEventListener('click', async event => {
        event.preventDefault(); event.stopPropagation();
        const prior = cleanupButton.textContent;
        cleanupButton.disabled = true; cleanupButton.textContent = 'Reviewing…';
        try {
          const result = await call('storage.cleanup_temp');
          if (result?.cancelled) return;
          await refreshStorageRoots();
          message(result?.cleaned
            ? 'Safe cleanup completed. Removed ' + (result.removed || []).length + ' eligible entries.'
            : 'No eligible app-owned temporary/download entries were found.');
        } catch (error) {
          message(error?.message || String(error), true);
        } finally {
          cleanupButton.disabled = false; cleanupButton.textContent = prior;
        }
      });
    }
    const storageTab = document.querySelector('[data-settings-tab="storage"]');
    if (storageTab && storageTab.dataset.ryuStorageRefreshBound !== 'true') {
      storageTab.dataset.ryuStorageRefreshBound = 'true';
      storageTab.addEventListener('click', () => {
        void refreshStorageRoots().catch(error => message(error?.message || String(error), true));
      });
    }
    // The old prototype "Choose Folder" control had no unambiguous root kind.
    // Route it to the real Storage tab instead of leaving a dead disabled button.
    document.querySelectorAll('#settings button').forEach(button => {
      if ((button.textContent || '').trim().toLowerCase() !== 'choose folder') return;
      if (button.dataset.ryuStorageNavigationBound === 'true') return;
      button.dataset.ryuStorageNavigationBound = 'true';
      button.disabled = false;
      button.removeAttribute('aria-disabled');
      button.removeAttribute('data-backend-unavailable');
      button.textContent = 'Manage storage locations';
      button.setAttribute('aria-label', 'Manage storage locations');
      button.title = 'Open Storage settings to manage supported project, audio asset and model locations.';
      button.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        if (storageTab) storageTab.click();
        else message('Storage settings are unavailable in this build.', true);
      });
    });
    document.querySelectorAll('[data-storage-action][data-storage-kind]').forEach(button => {
      if (button.dataset.ryuStorageBound === 'true') return;
      button.dataset.ryuStorageBound = 'true';
      button.addEventListener('click', async event => {
        event.preventDefault(); event.stopPropagation();
        const action = button.dataset.storageAction;
        const kind = button.dataset.storageKind;
        const prior = button.textContent;
        button.disabled = true;
        button.textContent = action === 'choose' ? 'Choose…' : action === 'default' ? 'Applying…' : action === 'open' ? 'Opening…' : 'Copying…';
        try {
          if (action === 'choose' || action === 'default') {
            const result = await call('storage.choose_root', {kind, use_default:action === 'default'});
            if (result?.cancelled) return;
            if (result?.job_id) {
              message('Verified storage migration started. Track its progress in Background Jobs.');
              await refreshJobs();
              await monitorJob(result.job_id, null, async () => {
                await refreshStorageRoots();
                message('Storage migration finished. The original source remains until you explicitly clean it up.');
              });
            } else {
              await refreshStorageRoots();
              message('Storage location saved. Restart Ryu’s Audiobook to apply the new root.');
            }
          } else if (action === 'open') {
            await call('storage.open_root', {kind});
            message('Opened the selected storage folder.');
          } else if (action === 'copy') {
            await call('storage.copy_root', {kind});
            message('Storage path copied to the clipboard.');
          }
        } catch (error) {
          message(error?.message || String(error), true);
        } finally {
          button.disabled = false; button.textContent = prior;
        }
      });
    });
  }
  async function loadSettings() {
    const settings = await call('settings.get');
    wireStorageControls();
    if ($('themeSelectAdvanced') && settings.theme) $('themeSelectAdvanced').value = settings.theme;
    if ($('effectsModeAdvanced') && settings.effects) $('effectsModeAdvanced').value = settings.effects;
    if ($('uiTextScale')) $('uiTextScale').value = String(settings.text_scale || 100);
    if ($('uiWindowSize')) $('uiWindowSize').value = String(settings.window_size || 'auto');
    if ($('reduceMotionAdvanced')) $('reduceMotionAdvanced').checked = settings.reduce_motion === true;
    applyUiTextScale(Number(settings.text_scale || 100));
    applyVisualStabilityPreferences(settings);
    return settings;
  }
  async function runDiagnostics() {
    const result = await call('diagnostics.check');
    const box = $('integrityResults');
    if (box) box.innerHTML = (result.checks || []).map(c => '<div class="list-item"><b>' + esc(c.name) +
      '</b><span>' + esc(c.status) + ' · ' + esc(c.detail) + '</span></div>').join('') ||
      '<p class="muted">No diagnostic results were returned.</p>';
    message(result.passed ? 'Local integrity checks passed.' : 'Some local integrity checks need attention.', !result.passed);
    return result;
  }
  function applyUnavailableControlStates() {
    const hide = (element, reason) => {
      if (!element || element.dataset.backendUnavailable === 'true') return;
      element.hidden = true;
      element.setAttribute('aria-hidden', 'true');
      element.dataset.backendUnavailable = 'true';
      element.title = reason;
    };
    // Character Studio actions are bound only to exact source-backed dialogue.
    // Hide stale prototype queue rows rather than presenting inert disabled actions.
    const dialogueReason = 'This item is not linked to an exact source dialogue passage.';
    document.querySelectorAll('#aiQueue [data-ai-line]:not([data-dialogue-id])')
      .forEach(element => hide(element, dialogueReason));
    // The legacy storage button is routed to the functional Storage tab by wireStorageControls().
    const benchmarkButton = $('runBenchmark');
    if (benchmarkButton) {
      benchmarkButton.disabled = false;
      benchmarkButton.removeAttribute('aria-disabled');
      benchmarkButton.title = 'Refresh CPU, memory, GPU and accelerator runtime information.';
    }
  }

  async function runHardwareBenchmark() {
    const button = $('runBenchmark');
    const prior = button?.textContent;
    if (button) { button.disabled = true; button.textContent = 'Checking hardware…'; }
    try {
      const hardware = await call('performance.info', {refresh:true});
      await refreshPerformance();
      const runtime = hardware.backend_active
        ? hardware.backend.toUpperCase() + ' runtime is active'
        : (hardware.recommended_backend || 'CPU') + ' is the selected backend';
      const summary = [
        'Hardware scan complete.',
        hardware.cpu_percent === null || hardware.cpu_percent === undefined ? 'CPU: unavailable' : 'CPU: ' + Number(hardware.cpu_percent).toFixed(1) + '%',
        hardware.memory_total_bytes ? 'RAM: ' + (hardware.memory_available_bytes/1024**3).toFixed(1) + ' / ' + (hardware.memory_total_bytes/1024**3).toFixed(1) + ' GB available/total' : 'RAM: unavailable',
        hardware.gpu_name ? 'GPU: ' + hardware.gpu_name : 'GPU: not detected',
        runtime,
        hardware.reason || ''
      ].filter(Boolean).join(' · ');
      message(summary);
      return hardware;
    } catch (error) {
      message(error?.message || String(error), true);
      throw error;
    } finally {
      if (button) { button.disabled = false; button.textContent = prior || 'Run benchmark'; }
    }
  }
  function wireTtsBenchmarkButton() {
    const scanButton = $('runBenchmark');
    if (!scanButton || $('runTtsBenchmark')) return;
    const button = document.createElement('button');
    button.id = 'runTtsBenchmark';
    button.type = 'button';
    button.className = scanButton.className;
    button.textContent = 'Run TTS Benchmark';
    button.title = 'Synthesize a real local Piper sample in the background and measure elapsed time, audio duration and realtime factor.';
    scanButton.insertAdjacentElement('afterend', button);
    button.addEventListener('click', act(async () => {
      const prior = button.textContent;
      button.disabled = true;
      button.textContent = 'Benchmarking…';
      try {
        const queued = await call('performance.benchmark', {});
        await refreshJobs();
        message('A real local Piper synthesis benchmark is running in Background Jobs.');
        await monitorJob(queued.job_id, null, async job => {
          await refreshPerformance();
          await refreshJobs();
          const result = job?.result || {};
          if (job?.state === 'completed' && result.success) {
            message('TTS benchmark complete: ' + (result.voice || 'Piper') + ' · ' +
              Number(result.seconds).toFixed(2) + 's for ' +
              Number(result.audio_seconds).toFixed(2) + 's audio · RTF ' +
              Number(result.realtime_factor).toFixed(2));
          } else {
            message(job?.error?.message || job?.message || 'The TTS benchmark failed.', true);
          }
        });
      } finally {
        button.disabled = false;
        button.textContent = prior;
      }
    }));
  }

  function wireModelDetails() {
    if (document.body.dataset.ryuModelDetailsBound === 'true') return;
    document.body.dataset.ryuModelDetailsBound = 'true';

    const loadFiles = async (details, offset = 0, append = false) => {
      const modelId = details?.dataset.modelDetails || '';
      const host = details?.querySelector('[data-model-file-list]');
      if (!modelId || !host) return;
      if (!append) host.innerHTML = '<span class="muted">Reading installed files…</span>';
      try {
        const result = await call('models.files', {model_id:modelId,offset,limit:100});
        const rows = Array.isArray(result.files) ? result.files : [];
        const fileSummary = '<div class="muted" style="font-size:11px;margin:4px 0 8px">' +
          esc(String(result.total_files || 0)) + ' actual file(s) · ' + esc(formatModelBytes(result.total_bytes || 0)) +
          ' · ' + esc(result.accessible ? 'Storage location accessible' : 'Storage location unavailable') + '</div>';
        const markup = rows.map(file =>
          '<div class="model-file-row" style="display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:start;padding:6px 0;border-bottom:1px solid var(--border,rgba(255,255,255,.08))">' +
            '<div style="min-width:0"><strong>' + esc(file.name || 'Installed file') + '</strong>' +
            '<div><code style="font-size:11px;white-space:normal;overflow-wrap:anywhere">' + esc(file.path || '') + '</code></div>' +
            '<span class="muted" style="font-size:11px">' + esc(file.role || 'file') + '</span></div>' +
            '<strong style="white-space:nowrap">' + esc(formatModelBytes(file.size_bytes)) + '</strong></div>'
        ).join('');
        if (append) {
          host.querySelector('[data-model-files-more]')?.remove();
          host.insertAdjacentHTML('beforeend', markup);
        } else {
          host.innerHTML = fileSummary + (markup || '<span class="muted">No installed files were found for this component.</span>');
        }
        const nextOffset = offset + rows.length;
        if (result.has_more) {
          host.insertAdjacentHTML('beforeend',
            '<button type="button" class="btn secondary small" data-model-files-more="' + esc(modelId) +
            '" data-model-files-offset="' + nextOffset + '">Load more files (' + esc(String(result.total_files - nextOffset)) + ' remaining)</button>');
        }
        details.dataset.filesLoaded = 'true';
      } catch (error) {
        host.innerHTML = '<span class="muted">Could not read installed files: ' + esc(error?.message || String(error)) + '</span>';
        details.dataset.filesLoaded = 'false';
      }
    };

    document.addEventListener('toggle', event => {
      const details = event.target;
      if (!details?.matches?.('details[data-model-details]') || !details.open) return;
      if (details.dataset.filesLoaded === 'true' || details.dataset.filesLoading === 'true') return;
      details.dataset.filesLoading = 'true';
      void loadFiles(details).finally(() => { details.dataset.filesLoading = 'false'; });
    }, true);

    document.addEventListener('click', event => {
      const button = event.target?.closest?.('[data-model-open-folder], [data-model-copy-path], [data-model-files-more]');
      if (!button) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      void (async () => {
        if (button.hasAttribute('data-model-files-more')) {
          const details = button.closest('details[data-model-details]');
          await loadFiles(details, Number(button.dataset.modelFilesOffset || 0), true);
          return;
        }
        const modelId = button.dataset.modelOpenFolder || button.dataset.modelCopyPath || '';
        const location = button.dataset.modelLocation || 'model';
        if (button.hasAttribute('data-model-open-folder')) {
          const result = await call('models.open_folder', {model_id:modelId,location});
          message('Opened folder: ' + result.path);
        } else {
          const result = await call('models.copy_path', {model_id:modelId,location});
          message('Copied path: ' + result.path);
        }
      })().catch(error => message(error?.message || String(error), true));
    });
  }

  async function wire() {
    // The native splash is still visible while controls are bound and the first
    // local backend calls are verified. Keep it animated instead of showing a
    // stationary percentage during this real setup work.
    window.__ryuEmitFrontendDiagnostic?.('startup-progress', {
      message:'Preparing studio controls and local services…',
      progress:null
    });
    installUiTextScaleRuntime();
    renderHelpGuide();
    wireModelDetails();
    installCharacterStudioHandlers();
    // Remove the prototype's same-element click handlers synchronously, before
    // any asynchronous backend initialization or real handler registration.
    suppressLegacyVoicePreviewHandlers();
    await call('app.get_info');
    await refreshCurrentProjectCard();
    installProjectCardStatusObserver();

    // The approved HTML prototype attaches a fake timer-based player directly
    // to these buttons. Replace those DOM nodes before attaching real playback,
    // so the demo timer can never masquerade as audiobook audio.
    ensureStableStudioLayout();
    ensureVoiceStudioRuntimeControls();
    ensurePreviewDurationOptions();
    for (const id of ['mainPlay','miniPlay']) {
      const original = $(id);
      if (!original) continue;
      const replacement = original.cloneNode(true);
      replacement.removeAttribute('onclick');
      original.replaceWith(replacement);
    }
    const playSelectedAudiobook = () => {
      if (!selectedAudiobookFolder) {
        message('Open Audiobooks and choose Play audiobook on a finished title first.', true);
        return;
      }
      // Toggle the existing media object directly when the selected book is
      // already loaded. This avoids a backend round-trip racing a mini-player click.
      if (playerAudio && playerAudio.src &&
          playerAudio.dataset?.projectFolder === selectedAudiobookFolder) {
        const current = playerAudio;
        if (current.paused) {
          current.play().catch(err => message(err?.message || 'Audiobook playback could not be resumed.', true));
        } else {
          current.pause();
        }
        syncMiniPlayer();
        setPlaybackButtonState();
        return;
      }
      openPlayer(selectedAudiobookFolder).catch(err => message(err?.message || String(err), true));
    };
    if ($('mainPlay')) $('mainPlay').onclick = playSelectedAudiobook;
    if ($('miniPlay')) $('miniPlay').onclick = playSelectedAudiobook;
    bindAudiobookPlayerControls();
    if ($('playerTimeline')) {
      $('playerTimeline').oninput = () => {
        const duration = playerAudio?.duration || 0;
        if (playerAudio && duration) playerAudio.currentTime = duration * Math.max(0,Math.min(100,Number($('playerTimeline').value || 0))) / 100;
      };
      $('playerTimeline').onchange = () => persistPlayerPosition(true, false, selectedAudiobookFolder, playerAudio);
    }
    clearAudiobookPlayerDisplay();
    applyUnavailableControlStates();
    // Register navigation and action handlers before hydration. A slow local model,
    // history, or sound-library query must not delay the first interactive frame.
    document.addEventListener('click', e => {
      const button = e.target.closest('button');
      const buttonLabel = button?.textContent?.trim().toLowerCase() || '';
      const runAction = async fn => {
        try { await fn(); }
        catch (err) { message(err?.message || String(err), true); }
      };
      if (button && button.dataset.openProjectFolder) {
        e.preventDefault(); e.stopImmediatePropagation();
        void runAction(async () => {
          const folder = String(button.dataset.openProjectFolder || '').trim();
          if (!folder) throw new Error('The selected audiobook card has no project folder.');
          selectedAudiobookFolder = folder;
          miniPlayerDismissed = false;
          await openPlayer(folder, {autoplay:false});
          // Opening a completed book must remain a load-only operation. Refreshing
          // project cards here can run concurrently with media metadata loading
          // and previously allowed the idle-player reset to clear the just-opened UI.
          renderAudiobookLibrary(projects);
          message('Opened ' + (projects.find(project => String(project.folder) === folder)?.title || 'selected audiobook') +
            ' in the player. Press Play when ready.');
        });
        return;
      }
      if (button && button.dataset.playProjectFolder) {
        e.preventDefault(); e.stopImmediatePropagation();
        void runAction(async () => {
          const folder = button.dataset.playProjectFolder;
          selectedAudiobookFolder = folder;
          miniPlayerDismissed = false;
          await openPlayer(folder);
          renderAudiobookLibrary(projects);
          message('Playing ' + (projects.find(project => project.folder === folder)?.title || 'selected audiobook') + '.');
        });
        return;
      }
      if (button && button.dataset.dashboardJobId && button.dataset.dashboardGenerationAction) {
        e.preventDefault(); e.stopImmediatePropagation();
        void runAction(async () => {
          const action = button.dataset.dashboardGenerationAction;
          await call(action === 'pause' ? 'job.pause' : 'job.resume', {job_id:button.dataset.dashboardJobId});
          await refreshJobs();
          await refreshHistory();
          message((action === 'pause' ? 'Pause' : 'Resume') + ' requested for the active audiobook generation.');
        });
        return;
      }
      if (button && button.dataset.dashboardJobId && buttonLabel === 'view job') {
        e.preventDefault(); e.stopImmediatePropagation();
        $('backgroundJobsButton')?.click();
        refreshJobs().catch(err => message(err?.message || String(err), true));
        return;
      }
      if (button && buttonLabel === 'open output folder') {
        e.preventDefault(); e.stopImmediatePropagation();
        call('system.open_output').then(result => message('Opened output folder: ' + (result.path || ''))).catch(err => message(err?.message || String(err), true));
        return;
      }
      if (button && buttonLabel === 'resume production') {
        e.preventDefault(); e.stopImmediatePropagation();
        (async()=> {
          const rows = await call('job.list', {include_hidden:false});
          const paused = rows.find(j => j.type === 'audiobook-generation' && ['paused','pause_requested'].includes(j.state));
          if (!paused) throw new Error('No paused audiobook generation job is available to resume. Start generation from Production Studio to reuse compatible saved checkpoints.');
          await call('job.resume', {job_id:paused.job_id});
          await refreshJobs(); await refreshHistory();
          message('Resume requested for ' + (paused.title || 'audiobook generation') + '.');
        })().catch(err => message(err?.message || String(err), true));
        return;
      }
      const historyFilter = e.target.closest('#historyFilters button');
      if (historyFilter) {
        e.preventDefault(); e.stopImmediatePropagation();
        historyFilter.parentElement?.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === historyFilter));
        refreshHistory().catch(err => message(err?.message || String(err), true));
        return;
      }
      const jobView = e.target.closest('[data-job-view]');
      if (jobView) {
        e.preventDefault(); e.stopImmediatePropagation();
        openJobDetails(jobView.dataset.jobView).catch(err => message(err?.message || String(err), true));
        return;
      }
      const historyJob = e.target.closest('[data-history-job]');
      if (historyJob) {
        e.preventDefault(); e.stopImmediatePropagation();
        openJobDetails(historyJob.dataset.historyJob).catch(err => message(err?.message || String(err), true));
        return;
      }
      const add=e.target.closest('#addLibraryCharacter'), imp=e.target.closest('#importCharacterLibrary'), edit=e.target.closest('[data-edit-library]'), remove=e.target.closest('[data-delete-library]'), test=e.target.closest('[data-test-library]'), studio=e.target.closest('[data-character-studio]'), save=e.target.closest('#saveCharacterProfile'), del=e.target.closest('#deleteCharacter');
      if(add){e.preventDefault();e.stopImmediatePropagation();openLibraryEditor(null);return;}
      if(imp){e.preventDefault();e.stopImmediatePropagation();importCharacterLibraryFile();return;}
      if(edit){e.preventDefault();e.stopImmediatePropagation();openLibraryEditor(libraryCharacters.find(c=>String(c.id)===edit.dataset.editLibrary));return;}
      if(remove){e.preventDefault();e.stopImmediatePropagation();const c=libraryCharacters.find(x=>String(x.id)===remove.dataset.deleteLibrary);if(!c||!window.confirm('Move '+c.name+' to the Character Recovery Bin? You can restore it later.'))return;call('character_library.delete',{id:c.id}).then(refreshCharacterLibrary).then(()=>message('Character moved to the Recovery Bin.')).catch(err=>message(err?.message||String(err),true));return;}
      if(save&&libraryEditorActive){e.preventDefault();e.stopImmediatePropagation();saveLibraryEditor().catch(err=>message(err?.message||String(err),true));return;}
      if(del&&libraryEditorActive){e.preventDefault();e.stopImmediatePropagation();if(!libraryEditorId){libraryEditorActive=false;$('characterEditorModal')?.classList.remove('show');if($('editCharacterVoice'))$('editCharacterVoice').disabled=false;return;}const c=libraryCharacters.find(x=>String(x.id)===String(libraryEditorId));if(!c||!window.confirm('Move '+c.name+' to the Character Recovery Bin? You can restore it later.'))return;call('character_library.delete',{id:libraryEditorId}).then(()=>{libraryEditorActive=false;$('characterEditorModal')?.classList.remove('show');if($('editCharacterVoice'))$('editCharacterVoice').disabled=false;return refreshCharacterLibrary();}).then(()=>message('Character moved to the Recovery Bin.')).catch(err=>message(err?.message||String(err),true));return;}
      if(e.target.closest('#characterLibrarySearch, #characterSeriesFilter'))setTimeout(()=>refreshCharacterLibrary().catch(err=>message(err?.message||String(err),true)),0);
      if(studio){e.preventDefault();e.stopImmediatePropagation();const c=libraryCharacters.find(x=>String(x.id)===studio.dataset.characterStudio);if(!c){message('Choose a saved character first.',true);return;}if(!c.source_project_folder){window.ryuPremiumSelectedCharacter=c.name;window.go?.('characters');message('Opened Character Studio. Open a project from this series to assign a voice.');return;}void (async()=>{try{await openProjectWithPreservedDraft(c.source_project_folder);window.ryuPremiumSelectedCharacter=c.name;window.go?.('characters');const castItem=[...document.querySelectorAll('[data-character-name]')].find(node=>node.dataset.characterName===c.name);castItem?.click();message('Opened Character Studio for '+c.name+'. Manage its voice assignment here.');}catch(err){message(err?.message||String(err),true);}})();return;}
      if(test){e.preventDefault();e.stopImmediatePropagation();const c=libraryCharacters.find(x=>String(x.id)===test.dataset.testLibrary);const profile=voices.find(v=>String(v.name).toLowerCase()===String(c?.voice||'').toLowerCase());if(!c||!profile){message('No matching saved voice profile exists for this character. Choose a saved profile in Voice Studio first.',true);return;}call('voice.preview',{profile_name:profile.name,text:'Hello, my name is '+c.name+'.',duration_seconds:10}).then(data=>monitorJob(data.job_id,async job=>{const url=job?.result?.file_url;if(!url)throw new Error('The character preview finished without a playable audio file.');if(previewAudio)previewAudio.pause();previewAudio=new Audio(url);await previewAudio.play();message('Playing character voice preview.');})).catch(err=>message(err?.message||String(err),true));return;}
    }, true);
    // These selectors change real UI state; the previous HTML prototype left them inert.
    document.addEventListener('click', event => {
      const tab = event.target.closest('#voices [data-etab]');
      if (tab) {
        event.preventDefault(); event.stopImmediatePropagation();
        const provider = tab.closest('.provider[data-provider="eleven"]');
        if (provider) {
          provider.querySelectorAll('[data-etab]').forEach(item => item.classList.toggle('active', item === tab));
          provider.querySelectorAll('[data-epanel]').forEach(panel => panel.classList.toggle('active', panel.dataset.epanel === tab.dataset.etab));
        }
        return;
      }
      const preset = event.target.closest('.provider[data-provider="voicedesign"] .preset-grid .preset');
      if (preset) {
        event.preventDefault(); event.stopImmediatePropagation();
        applyVoiceDesignPreset(preset);
      }
    }, true);

    // Refresh actions call the provider itself; they never report a static catalogue as live.
    document.addEventListener('click', event => {
      const button = event.target.closest('#voices .provider .health button');
      if (!button || !/refresh|catalogue/i.test(button.textContent || '')) return;
      const panel = button.closest('.provider');
      const key = panel?.dataset.provider;
      if (!key) return;
      event.preventDefault(); event.stopImmediatePropagation();
      button.disabled = true;
      const originalText = button.textContent;
      button.textContent = 'Refreshing…';
      refreshProviderCatalog(key, true)
        .then(result => message(result.message || 'Provider catalogue refreshed.'))
        .catch(error => message(error?.message || String(error), true))
        .finally(() => { button.disabled = false; button.textContent = originalText; });
    }, true);
    document.addEventListener('click', e => {
      const b=e.target.closest('[data-voice]');
      if(b){
        const savedProfile = b.dataset.voiceSaved === 'true'
          ? voices.find(profile => profile.saved === true && profile.name === b.dataset.voiceProfileName)
          : null;
        if (savedProfile) {
          applySavedVoiceProfile(savedProfile);
          return;
        }
        const previousName = String($('profileName')?.value || '').trim();
        const hadSavedSelection = Boolean(selectedVoice);
        invalidateVoicePreview();
        selectedVoiceId = b.dataset.voice;
        selectedVoiceProvider = b.dataset.voiceProvider || null;
        selectedVoice=null;profileEditOriginalName='';
        clearSavedProfileSelection();
        const label=b.dataset.voiceLabel || b.dataset.voice;
        if($('profileVoice'))$('profileVoice').textContent=label;
        if($('premiumName') && (!String($('premiumName').value || '').trim() || hadSavedSelection)) $('premiumName').value=label+' Custom';
        if($('profileName') && (!previousName || hadSavedSelection || /^Offline Neural\s*[·•-]/i.test(previousName) || /^Edge TTS\s*[·•-]/i.test(previousName) || /^Qwen VoiceDesign\s*[·•-]/i.test(previousName))) $('profileName').value=label+' Custom';
        updateVoiceSummary({name:$('profileName')?.value||'',provider:selectedVoiceProvider,qwen_mode:'custom'},{saved:false,previewReady:false,assignment:''});
        const assigned=$('assignedSide');if(assigned)assigned.textContent='';const ap=assigned?.closest('p');if(ap)ap.hidden=true;updateVoiceActionButtons();
        document.querySelectorAll('#voices *').forEach(node => {
          if(node.children.length===0 && node.textContent.trim()==='Saved') node.textContent='Unsaved';
        });
        return;
      }
      const provider = e.target.closest('.provider');
      if(provider && !e.target.closest('button,input,textarea,select,label,[data-voice]')) {
        invalidateVoicePreview();
        selectedVoiceId=null;selectedVoice=null;selectedVoiceProvider=null;profileEditOriginalName='';
        clearSavedProfileSelection();
        const key = provider.dataset.provider;
        const defaultLabels = {offline:'Amy',sapi:'David',customvoice:'Serena',voicedesign:'Custom voice description',qwenclone:'Reference voice',customref:'Reference voice',edge:'Edge neural voice',eleven:'ElevenLabs voice'};
        if($('profileVoice'))$('profileVoice').textContent=defaultLabels[key] || 'Custom voice';
        if($('profileName'))$('profileName').value='';
        if($('premiumName'))$('premiumName').value='';
        updateVoiceSummary(null,{saved:false,previewReady:false,assignment:''});
        const assigned=$('assignedSide');if(assigned)assigned.textContent='';const ap=assigned?.closest('p');if(ap)ap.hidden=true;updateVoiceActionButtons();
        void refreshProviderCatalog(key, false).catch(error => console.warn('[Ryu voice catalogue]', error));
        document.querySelectorAll('#voices *').forEach(node => {
          if(node.children.length===0 && node.textContent.trim()==='Saved') node.textContent='Unsaved';
        });
      }
    });

    if ($('checkModelUpdates')) $('checkModelUpdates').onclick=act(async()=>{forceModelInventoryRefreshPending = true;await refreshModels();message('Local model catalogue refreshed. This checks the local catalogue; it does not contact an online update service.');});
    if ($('startQwenInstall')) $('startQwenInstall').onclick=act(async()=>{
      const choice=document.querySelector('input[name="qwenInstall"]:checked')?.value||'customvoice';
      const data=await call('models.install',{selection:choice});
      $('qwenInstallModal')?.classList.remove('show');
      await monitorJob(data.job_id,refreshModels);
    });
    document.querySelectorAll('[data-close-qwen]').forEach(b=>b.addEventListener('click',()=>$('qwenInstallModal')?.classList.remove('show')));
    if ($('clearModelQueue')) $('clearModelQueue').onclick=act(async()=>{await call('job.clear_completed');await refreshJobs();await refreshHistory();message('Completed background jobs cleared from the active queue.');});
    if ($('runIntegrityCheck')) $('runIntegrityCheck').onclick=act(runDiagnostics);
    if ($('runBenchmark')) $('runBenchmark').onclick=act(runHardwareBenchmark);
    wireTtsBenchmarkButton();
    if ($('chapterSearch')) $('chapterSearch').oninput=()=>{
      const q=$('chapterSearch').value.trim().toLowerCase();
      $('chapterList')?.querySelectorAll('[data-chapter-number]').forEach(el=>el.hidden=!el.textContent.toLowerCase().includes(q));
    };
    if ($('manualChapterSearch')) $('manualChapterSearch').oninput=()=>{
      const q=$('manualChapterSearch').value.trim().toLowerCase();
      $('manualChapterList')?.querySelectorAll('[data-chapter-number]').forEach(el=>el.hidden=!el.textContent.toLowerCase().includes(q));
    };
    if ($('pronTermSearch')) $('pronTermSearch').oninput=()=>{
      const q=$('pronTermSearch').value.trim().toLowerCase();
      $('pronTermList')?.querySelectorAll('[data-pron-term]').forEach(el=>el.hidden=!el.textContent.toLowerCase().includes(q));
    };
    if ($('pronSearchAdvanced')) $('pronSearchAdvanced').oninput=renderPronunciationRows;
    if ($('pronScopeFilter')) $('pronScopeFilter').onchange=renderPronunciationRows;
    if ($('pronOriginFilter')) $('pronOriginFilter').onchange=renderPronunciationRows;

  async function openProjectWithPreservedDraft(folder) {
    const targetFolder = String(folder || '').trim();
    if (!targetFolder) throw new Error('Choose a local project before opening it.');

    const metadataDialog = $('inputProjectDetailsDialog');
    if (metadataDialog?.open) {
      if (metadataDialogDirty) {
        throw new Error('Save or explicitly discard Input Project Details before switching projects.');
      }
      metadataDialog.close();
    }

    // This is the only path allowed to switch the backend's active project.
    // A failed save aborts the switch; all open routes then invalidate old
    // chapter/cast reads, verify the new active folder, and hydrate in order.
    await flushChapterDraftBeforeSwitch();
    chapterListEpoch++;
    chapterSelectionEpoch++;
    characterListEpoch++;
    characterSuggestionsEpoch++;

    const opened = await call('project.open', {folder:targetFolder});
    const active = await refreshCurrentProjectCard();
    if (!active || String(active.folder || '') !== targetFolder) {
      throw new Error(
        'The active project could not be verified after opening. The view was not refreshed with potentially stale project data. Retry from Library.'
      );
    }
    await refreshProjects();
    await refreshChapters();
    await refreshCharacters();
    // Current-book identity is scoped to the active project. Do not carry a
    // multi-select or pending AI review list into another project's dictionary.
    pronunciationSelectionKeys.clear();
    pronunciationRowPreviewState.clear();
    lastPronunciationPreview = null;
    window.ryuPendingPronunciationSuggestions = [];
    renderPronunciationSuggestions([]);
    await refreshTerms();

    const listed = projects.find(project => String(project.folder || '') === targetFolder) || {};
    return {...listed, ...(opened && typeof opened === 'object' ? opened : {}), folder:targetFolder};
  }

    // Dashboard recent cards are re-rendered from backend project records. Delegate
    // clicks from the stable dashboard container so refreshed cards open their own project.
    if ($('dashboard')) $('dashboard').addEventListener('click', async e => {
      const card = e.target.closest('.recent-grid [data-project-folder]');
      if (!card) return;
      e.preventDefault();
      e.stopPropagation();
      const folder = card.dataset.projectFolder;
      if (!folder) { message('This dashboard card has no local project folder.', true); return; }
      try {
        const opened = await openProjectWithPreservedDraft(folder);
        if (typeof window.go === 'function') window.go('chapters');
        message('Opened local project: ' + (opened.title || opened.folder || 'project'));
      } catch (err) {
        message(err?.message || String(err), true);
      }
    });
    if ($('libraryGrid')) $('libraryGrid').addEventListener('click', async e => {
      const remove = e.target.closest('[data-delete-project]');
      if (remove) {
        e.preventDefault(); e.stopPropagation();
        const project = projects.find(p => String(p.folder) === String(remove.dataset.deleteProject));
        const title = project?.title || 'this project';
        if (!window.confirm('Move "' + title + '" to Deleted Books? You can restore it later from Deleted Books / Recover.')) return;
        remove.disabled = true;
        try {
          const result = await call('project.trash', {folder:remove.dataset.deleteProject});
          selectedProjectFolders.delete(String(remove.dataset.deleteProject));
          await refreshProjects();
          updateProjectDeleteButton();
          message('Moved "' + (result.title || title) + '" to Deleted Books. Its source and saved work are recoverable until permanently purged.');
        } catch (err) {
          message(err?.message || String(err), true);
        } finally {
          remove.disabled = false;
        }
        return;
      }
      const button = e.target.closest('[data-open-project]'); if (!button) return;
      button.disabled = true;
      try {
        const opened = await openProjectWithPreservedDraft(button.dataset.openProject);
        if (typeof window.go === 'function') window.go('chapters');
        message('Opened local project: ' + (opened.title || opened.folder || 'project'));
      }
      catch (err) { message(err?.message || String(err), true); }
      finally { button.disabled = false; }
    });
    if ($('libraryGrid') && !$('libraryGrid').dataset.bulkDeleteBound) {
      $('libraryGrid').dataset.bulkDeleteBound = 'true';
      $('libraryGrid').addEventListener('change', e => {
        const checkbox = e.target.closest('[data-select-project]');
        if (!checkbox) return;
        const folder = String(checkbox.dataset.selectProject || '');
        if (checkbox.checked) selectedProjectFolders.add(folder);
        else selectedProjectFolders.delete(folder);
        updateProjectDeleteButton();
      });
    }
    if ($('browseBtn')) $('browseBtn').onclick = act(importBook);
    if ($('fileInput')) $('fileInput').onchange = e => {
      const file = e.target.files?.[0]; e.target.value = '';
      if (file) importDroppedFile(file).catch(err => message(err?.message || String(err), true));
    };
    if ($('dropzone')) {
      $('dropzone').onclick = e => { if (!e.target.closest('button')) importBook().catch(x=>message(x.message,true)); };
      $('dropzone').ondrop = e => {
        e.preventDefault(); e.stopPropagation(); $('dropzone').classList.remove('drag');
        const file = e.dataTransfer?.files?.[0];
        if (file) importDroppedFile(file).catch(err => message(err?.message || String(err), true));
      };
    }
    const chapterHistoryLimit = 10;
    const rememberChapterSnapshot = (stack, number, text) => {
      if (typeof text !== 'string' || text.length > 1_000_000) return;
      const rows = stack.get(number) || [];
      if (rows.length && rows[rows.length - 1] === text) return;
      rows.push(text);
      if (rows.length > chapterHistoryLimit) rows.splice(0, rows.length - chapterHistoryLimit);
      stack.set(number, rows);
    };
    const changeChapterHistory = async direction => {
      const chapter = selectedChapter(), editor = $('chapterEditor');
      if (!chapter || !editor) throw new Error('Open a chapter before using undo/redo.');
      if (editor.value.length > 1_000_000) throw new Error('Undo/redo is limited to chapters of 1,000,000 characters to protect memory on low-resource PCs.');
      if (chapterSaveTimer) { clearTimeout(chapterSaveTimer); chapterSaveTimer = null; }
      if (chapterHistoryGroupTimer) { clearTimeout(chapterHistoryGroupTimer); chapterHistoryGroupTimer = null; }
      chapterHistoryGroupOpen = false;
      await chapterSavePromise.catch(() => {});
      const from = direction === 'undo' ? chapterUndoStacks : chapterRedoStacks;
      const to = direction === 'undo' ? chapterRedoStacks : chapterUndoStacks;
      const stack = from.get(chapter.number) || [];
      if (!stack.length) { message('Nothing to ' + direction + ' in this chapter.'); return; }
      rememberChapterSnapshot(to, chapter.number, editor.value);
      const next = stack.pop(); from.set(chapter.number, stack);
      chapterHistoryApplying = true;
      editor.value = next;
      chapterLastText = next;
      editor.dispatchEvent(new Event('input', {bubbles:true}));
      chapterHistoryApplying = false;
      editor.focus();
      message('Chapter ' + direction + ' applied; changes will autosave shortly.');
    };
    const persistChapterSnapshot = async (number, title, text, automatic = false) => {
      const state = $('saveState');
      if (state) state.textContent = automatic ? 'Saving…' : 'Saving changes…';
      const result = await call('chapter.update', {number, title, text});
      const chapter = chapters.find(item => item.number === number);
      if (chapter) { chapter.text = text; chapter.title = result.title || title; chapter.word_count = result.word_count; }
      if (window.ryuPremiumSelectedChapter === number && state) state.textContent = automatic ? 'Autosaved just now' : 'Saved just now';
      return result;
    };
    // Chapter operations missing from the approved visual controls are available
    // from a contextual action menu on the chapter list; no always-visible UI is added.
    const chapterListNode = $('chapterList');
    if (chapterListNode && !chapterListNode.dataset.contextActionsBound) {
      chapterListNode.dataset.contextActionsBound = '1';
      chapterListNode.addEventListener('contextmenu', event => {
        const item = event.target.closest('[data-chapter-number]');
        if (!item) return;
        event.preventDefault();
        const number = Number(item.dataset.chapterNumber);
        const selected = chapters.find(chapter => chapter.number === number);
        if (!selected) return;
        const action = window.prompt(
          'Chapter actions for "' + selected.title + '"\n' +
          'Type one: add, rename, delete, up, down, merge, review, skip, find, replace, undo, redo\n' +
          'Merge combines this chapter into the previous chapter. Review toggles review status; Skip excludes it from generation. Find/replace and undo/redo apply to the open chapter text.',
          'rename'
        );
        if (!action) return;
        const choice = action.trim().toLowerCase();
        const run = async () => {
          // Flush pending editor changes before any structural chapter operation.
          if (chapterSaveTimer) { clearTimeout(chapterSaveTimer); chapterSaveTimer = null; }
          await chapterSavePromise.catch(() => {});
          const editor = $('chapterEditor');
          if (editor && window.ryuPremiumSelectedChapter === number) {
            await persistChapterSnapshot(number, $('chapterTitle')?.textContent || selected.title, editor.value, false);
          }
          if (choice === 'add') {
            const title = window.prompt('New chapter title:', 'Chapter ' + (chapters.length + 1));
            if (title === null) return;
            const created = await call('chapter.add', {title: title.trim() || 'Chapter ' + (chapters.length + 1), text: ''});
            window.ryuPremiumSelectedChapter = created.number;
            await refreshChapters();
            message('New chapter added. Enter its text and save when ready.');
          } else if (choice === 'rename') {
            const title = window.prompt('Chapter title:', selected.title);
            if (title === null) return;
            if (!title.trim()) throw new Error('Chapter title cannot be empty.');
            await call('chapter.update', {number, title: title.trim(), text: selected.text || ''});
            await refreshChapters();
            message('Chapter renamed and saved.');
          } else if (choice === 'delete') {
            if (!window.confirm('Delete "' + selected.title + '" permanently from this project?')) return;
            await call('chapter.delete', {number});
            const remaining = await call('chapter.list');
            chapters = remaining;
            window.ryuPremiumSelectedChapter = remaining[Math.min(number - 1, remaining.length - 1)]?.number || remaining[0]?.number;
            await refreshChapters();
            message('Chapter deleted.');
          } else if (choice === 'up' || choice === 'down') {
            const destination = number + (choice === 'up' ? -1 : 1);
            if (destination < 1 || destination > chapters.length) throw new Error('This chapter cannot move farther in that direction.');
            await call('chapter.reorder', {number, new_number: destination});
            window.ryuPremiumSelectedChapter = destination;
            await refreshChapters();
            message('Chapter order updated.');
          } else if (choice === 'merge') {
            if (number === 1) throw new Error('The first chapter cannot merge into a previous chapter.');
            if (!window.confirm('Merge "' + selected.title + '" into the previous chapter?')) return;
            await call('chapter.merge', {number});
            window.ryuPremiumSelectedChapter = number - 1;
            await refreshChapters();
            message('Chapter merged into the previous chapter.');
          } else if (choice === 'review') {
            const nextStatus = selected.review_status === 'reviewed' ? 'needs_review' : 'reviewed';
            await call('chapter.review', {number, review_status:nextStatus});
            await refreshChapters();
            message(nextStatus === 'reviewed' ? 'Chapter marked reviewed and saved.' : 'Chapter returned to the review queue.');
          } else if (choice === 'skip') {
            const nextSkip = !Boolean(selected.skip_for_generation);
            await call('chapter.skip', {number, skip_for_generation:nextSkip});
            await refreshChapters();
            message(nextSkip ? 'Chapter excluded from audiobook generation; its text is preserved.' : 'Chapter included in audiobook generation again.');
          } else if (choice === 'find' || choice === 'replace') {
            if (!editor || window.ryuPremiumSelectedChapter !== number) throw new Error('Open this chapter in the editor before using find/replace.');
            const needle = window.prompt('Find exact text in this chapter:', '');
            if (needle === null) return;
            if (!needle) throw new Error('Enter non-empty text to find.');
            const source = editor.value;
            const index = source.toLocaleLowerCase().indexOf(needle.toLocaleLowerCase());
            if (choice === 'find') {
              if (index < 0) { message('No matching text was found in this chapter.'); return; }
              editor.focus(); editor.setSelectionRange(index, index + needle.length);
              message('Match selected in the chapter editor.');
            } else {
              const replacement = window.prompt('Replace every case-insensitive match with:', '');
              if (replacement === null) return;
              const lowered = source.toLocaleLowerCase(), target = needle.toLocaleLowerCase();
              let count = 0, cursor = 0, output = '', matchAt = -1;
              while ((matchAt = lowered.indexOf(target, cursor)) !== -1) {
                output += source.slice(cursor, matchAt) + replacement;
                cursor = matchAt + needle.length; count++;
              }
              if (!count) { message('No matching text was found; chapter text was not changed.'); return; }
              if (!window.confirm('Replace ' + count + ' occurrence(s) in this chapter?')) return;
              editor.value = output + source.slice(cursor);
              editor.dispatchEvent(new Event('input', {bubbles:true}));
              message('Replaced ' + count + ' occurrence(s). Changes will autosave shortly.');
            }
          } else if (choice === 'undo' || choice === 'redo') {
            await changeChapterHistory(choice);
          } else {
            throw new Error('Unknown chapter action. Type add, rename, delete, up, down, merge, review, skip, find, replace, undo, or redo.');
          }
        };
        run().catch(error => message(error?.message || String(error), true));
      });
    }

    if ($('chapterEditor')) $('chapterEditor').addEventListener('input', () => {
      const c = selectedChapter(); if (!c) return;
      const editorText = $('chapterEditor').value;
      // Keep derived UI state in sync with the editor immediately; persistence
      // is still serialized/debounced below, so this does not trigger a page reload.
      c.text = editorText;
      c.word_count = editorText.trim() ? editorText.trim().split(/\s+/).filter(Boolean).length : 0;
      renderLiveChapterInsights();
      if (!chapterHistoryApplying && editorText !== chapterLastText) {
        if (!chapterHistoryGroupOpen) {
          if (editorText.length <= 1_000_000 && chapterLastText.length <= 1_000_000) rememberChapterSnapshot(chapterUndoStacks, c.number, chapterLastText);
          chapterRedoStacks.delete(c.number);
          chapterHistoryGroupOpen = true;
        }
        chapterLastText = editorText;
        if (chapterHistoryGroupTimer) clearTimeout(chapterHistoryGroupTimer);
        chapterHistoryGroupTimer = setTimeout(() => { chapterHistoryGroupOpen = false; chapterHistoryGroupTimer = null; }, 700);
      }
      if (chapterSaveTimer) clearTimeout(chapterSaveTimer);
      const number = c.number, title = $('chapterTitle')?.textContent || c.title, text = $('chapterEditor').value;
      if ($('saveState')) $('saveState').textContent = 'Unsaved changes';
      chapterSaveTimer = setTimeout(async () => {
        chapterSaveTimer = null;
        // Serialize snapshots so a slower earlier save can never overwrite newer text.
        const saveTask = chapterSavePromise.catch(() => {}).then(() => persistChapterSnapshot(number, title, text, true));
        chapterSavePromise = saveTask;
        try { await saveTask; }
        catch (err) { if ($('saveState') && window.ryuPremiumSelectedChapter === number) $('saveState').textContent = 'Autosave failed'; message('Chapter autosave failed: ' + (err?.message || String(err)), true); }
        finally { if (chapterSavePromise === saveTask) chapterSavePromise = Promise.resolve(); }
      }, 900);
    });
    if ($('chapterEditor')) $('chapterEditor').addEventListener('keydown', event => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === 'z' || key === 'y') {
        event.preventDefault();
        changeChapterHistory(key === 'z' && !event.shiftKey ? 'undo' : 'redo').catch(error => message(error?.message || String(error), true));
      }
    });
    if ($('cleanText')) $('cleanText').onclick = act(async()=>{const c=selectedChapter();if(!c)throw new Error('Import or open a book first.');const source=$('chapterEditor')?.value||'';const result=await call('chapter.clean',{text:source});if(!result||typeof result.text!=='string')throw new Error('The backend did not return cleaned chapter text.');$('chapterEditor').value=result.text;$('chapterEditor').dispatchEvent(new Event('input',{bubbles:true}));message(result.changed?'Text cleaned; removed '+Number(result.removed_count||0)+' likely page-noise line(s). Changes will autosave shortly.':'No cleanup changes were needed.');});
    if ($('saveChapter')) $('saveChapter').onclick = act(async()=>{const c=selectedChapter();if(!c)throw new Error('Select a chapter first.');if(chapterSaveTimer){clearTimeout(chapterSaveTimer);chapterSaveTimer=null;}await chapterSavePromise.catch(()=>{});const title=$('chapterTitle')?.textContent||c.title;const text=$('chapterEditor')?.value||'';await persistChapterSnapshot(c.number,title,text,false);message('Chapter saved to local project.');await refreshChapters();});
    const splitChapterButton = [...document.querySelectorAll('#chapters button')].find(button => button.textContent.trim().toLowerCase() === 'split chapter');
    if (splitChapterButton) splitChapterButton.onclick = act(async()=>{
      // Cancel a queued snapshot and wait for any already-started save before persisting the split.
      if (chapterSaveTimer) { clearTimeout(chapterSaveTimer); chapterSaveTimer = null; }
      await chapterSavePromise.catch(() => {});
      const c = selectedChapter(), editor = $('chapterEditor');
      if (!c || !editor) throw new Error('Open a chapter before splitting it.');
      if (editor.selectionStart !== editor.selectionEnd) throw new Error('Place the cursor at the split point; do not select a range of text.');
      const splitAt = editor.selectionStart, text = editor.value;
      if (splitAt <= 0 || splitAt >= text.length) throw new Error('Place the cursor inside the chapter text, between two passages.');
      const result = await call('chapter.split',{number:c.number,title:$('chapterTitle')?.textContent||c.title,text,split_at:splitAt});
      window.ryuPremiumSelectedChapter = result.new_number;
      await refreshChapters();
      const next = chapters.find(item=>item.number===result.new_number);
      if (next && editor) { editor.value = next.text; if ($('chapterTitle')) $('chapterTitle').textContent = next.title; }
      message('Chapter split and saved · '+result.chapter_count+' chapters now in this book.');
    });
    // Save Profile and Save Profile Only persist the local voice settings. ElevenLabs
    // "Add Selected to My Voices" has a separate provider-create handler below.
    ['saveProfile','saveOnly'].forEach(id=>{if($(id))$(id).onclick=act(saveVoice);});
    // The previous "Save Draft" button was wired to permanent profile save (not a draft
    // backend) and duplicated the Step 3 save action. Remove this unsupported control.
    $('saveDraft')?.remove();
    if ($('useNarrator')) $('useNarrator').onclick=act(async()=>{
      if(!voicePreviewValid)throw new Error('Generate and validate a preview for this voice before assigning it as the narrator.');
      const v=await saveVoice();
      if(!v)return;
      await call('voice.select',{profile_name:v.name});
      await refreshProjects();
      await refreshSeriesNarratorControls();
      document.querySelectorAll('#voices *').forEach(node => {
        if(node.children.length===0 && node.textContent.trim()==='Narrator unchanged') node.textContent='Assigned to this narrator';
      });
      message('Profile saved and assigned as the active narrator.');
    });
    if ($('generatePreview')) $('generatePreview').onclick=act(previewVoice);
    ensureProductionPreviewMonitorUi();
    if ($('previewGenerate')) $('previewGenerate').onclick=act(async()=>{
      await narratorOnlySavePromise;
      const chapterNumber=Number(productionPreviewSelectedChapter||$('productionPreviewChapterSelect')?.value||0);
      if(!chapterNumber)throw new Error('Select a saved chapter in the Production preview chapter selector.');
      if(productionJobIsActive(productionJobSnapshots.full))throw new Error('Finish or cancel the full audiobook generation before starting a preview.');
      if(productionJobIsActive(productionJobSnapshots.preview))throw new Error('A Production preview is already running.');
      const name=String(selectedVoice||$('profileName')?.value||'').trim();
      if(!name)throw new Error('Select and save a narrator voice profile before previewing this chapter.');
      const group=[...document.querySelectorAll('#generate .segmented')].find(el=>[...el.querySelectorAll('button')].some(b=>/10s|30s|60s|90s/i.test(b.textContent)));
      const duration=group?.querySelector('button.active')?.textContent.match(/\d+/)?.[0]||'30';
      if(![10,30,60,90].includes(Number(duration)))throw new Error('Preview duration must be 10, 30, 60, or 90 seconds.');
      await flushChapterDraftBeforeSwitch();
      const activeProject=await call('project.get_active');
      if(!activeProject?.folder)throw new Error('Open a saved project before creating a Production preview.');
      const knownFolder=String(window.ryuPremiumActiveProject?.folder||'');
      if(knownFolder&&knownFolder!==String(activeProject.folder))throw new Error('The active project changed while the Production preview was being prepared. Refresh the chapter list and try again.');
      const savedChapters=await call('chapter.list');
      chapters=Array.isArray(savedChapters)?savedChapters:[];
      window.ryuPremiumChapters=chapters;
      syncProductionPreviewChapterSelector();
      const chapter=chapters.find(item=>Number(item.number)===chapterNumber);
      if(!chapter||!String(chapter.text||'').trim())throw new Error('The selected saved chapter is empty or no longer available. Refresh Chapter Studio and try again.');
      if(Number(productionPreviewSelectedChapter||0)!==chapterNumber)throw new Error('The selected preview chapter changed while the saved chapter list was refreshing. Select it again and retry.');
      const chapterId=String(chapter.chapter_id||chapter.id||'');
      if(productionPreviewSelectedChapterId&&chapterId&&productionPreviewSelectedChapterId!==chapterId)throw new Error('The selected chapter identity changed. Refresh the saved chapter list and try again.');
      await flushSoundDesignState();
      await refreshTerms();
      productionPreviewRequestProjectFolder=String(activeProject.folder);
      productionPreviewRequestChapterNumber=chapterNumber;
      productionPreviewRequestChapterId=chapterId;
      invalidateVoicePreview();
      const previewToken=voicePreviewEpoch;
      if($('productionPreviewStatus'))$('productionPreviewStatus').textContent='Starting selected-chapter preview…';
      if($('productionPreviewTiming'))$('productionPreviewTiming').textContent='Waiting for the preview worker to start.';
      if($('previewState'))$('previewState').textContent='Preparing';
      if($('validation'))$('validation').textContent='Preparing selected chapter preview.';
      const narratorOnly = $('narratorOnlyGeneration')?.checked === true;
      const data=await call('production.preview',{profile_name:activeProject.voice_profile,chapter_number:chapterNumber,chapter_id:chapterId,narrator_only_generation:narratorOnly,duration_seconds:Number(duration),include_sound_design:true,_production_preview:true});
      if(previewToken!==voicePreviewEpoch)return;
      if(!data?.job_id)throw new Error('The Production preview job was not created.');
      const previewProfileName=String(data.profile_name||name);
      productionPreviewJobId=String(data.job_id);
      await refreshJobs();
      const completed=await monitorProductionJob(data.job_id,'preview',async job=>{
        if(previewToken!==voicePreviewEpoch)return false;
        const activeProject=await call('project.get_active');
        const activeFolder=normalizeProjectFolderIdentity(activeProject?.folder);
        const requestFolder=normalizeProjectFolderIdentity(productionPreviewRequestProjectFolder);
        const jobFolder=normalizeProjectFolderIdentity(job?.project_folder);
        const jobChapter=Number(job?.current_chapter||0);
        const requestChapterId=String(productionPreviewRequestChapterId||'');
        const jobChapterId=String(job?.current_chapter_id||'');
        const ownershipProblem=!activeFolder||!requestFolder||!jobFolder||
          activeFolder!==requestFolder||jobFolder!==requestFolder||
          jobChapter!==productionPreviewRequestChapterNumber||
          Boolean(requestChapterId&&jobChapterId&&requestChapterId!==jobChapterId);
        if(ownershipProblem){
          const detail='Preview ownership validation failed. '+
            'Project active/request/job='+JSON.stringify([activeFolder,requestFolder,jobFolder])+
            '; chapter request/job='+JSON.stringify([productionPreviewRequestChapterNumber,jobChapter])+
            '; chapter IDs request/job='+JSON.stringify([requestChapterId,jobChapterId])+'.';
          if($('productionPreviewStatus'))$('productionPreviewStatus').textContent=detail;
          console.error('[Ryu Production preview ownership]',detail);
          return false;
        }
        if(!productionPreviewRequestChapterId&&jobChapterId){
          productionPreviewRequestChapterId=jobChapterId;
        }
        return preparePreviewPlayback(job,Number(duration),{profileName:previewProfileName,preserveSummary:true});
      });
      if(completed?.state==='completed')await refreshJobs();
    });
    if ($('playPreview')) $('playPreview').onclick=act(async()=>{if(!previewAudio||!voicePreviewValid)throw new Error('Generate a validated preview first.');if(!previewAudio.paused){previewAudio.pause();$('playPreview').textContent='▶ Play';}else{await previewAudio.play();$('playPreview').textContent='Ⅱ Pause';}});
    if ($('stopPreview')) $('stopPreview').onclick=()=>{if(previewAudio){previewAudio.pause();previewAudio.currentTime=0;}if($('playPreview'))$('playPreview').textContent='▶ Play';syncPreviewPlaybackTime();};
    const downloadCurrentPreview=async()=>{
      if(!voicePreviewValid||!lastVoicePreviewPath)throw new Error('Generate a validated preview before downloading it.');
      const baseName=(lastVoicePreviewProfileName||currentVoiceName()||'Ryu Voice Preview').replace(/[<>:"\/\\|?*\x00-\x1f]+/g,'-').trim()||'Ryu Voice Preview';
      const chapterSuffix=lastVoicePreviewChapterNumber
        ? '_Chapter_'+String(lastVoicePreviewChapterNumber).padStart(2,'0')+(lastVoicePreviewChapterTitle?'_'+lastVoicePreviewChapterTitle:'')
        : '';
      const name=(baseName+chapterSuffix+'_Preview').replace(/[<>:"\/\\|?*\x00-\x1f]+/g,'-').trim();
      const result=await call('voice.preview.save',{source_path:lastVoicePreviewPath,suggested_name:name.replace(/\s+/g,'_')});
      if(result.cancelled){message('Preview save cancelled.');return;}
      message('Voice preview saved to '+result.path);
    };
    if ($('downloadPreview')) $('downloadPreview').onclick=act(downloadCurrentPreview);
    const downloadProductionPreview=async()=>{
      const job=productionJobSnapshots.preview;
      if(!productionPreviewJobId||!job||String(job.job_id||'')!==String(productionPreviewJobId)) throw new Error('Generate a Production chapter preview before saving it.');
      if(String(job.state||'').toLowerCase()!=='completed'||!voicePreviewValid||!lastVoicePreviewPath) throw new Error('Wait for the Production preview to complete and pass audio validation before saving it.');
      const activeProject=await call('project.get_active');
      const projectFolder=String(activeProject?.folder||'');
      const chapterNumber=Number(lastVoicePreviewChapterNumber||0);
      const selectedChapterNumber=Number(productionPreviewSelectedChapter||$('productionPreviewChapterSelect')?.value||0);
      const selectedChapter=chapters.find(item=>Number(item.number)===selectedChapterNumber);
      const selectedChapterId=String(selectedChapter?.chapter_id||selectedChapter?.id||'');
      const requestChapterId=String(productionPreviewRequestChapterId||'');
      const jobChapterId=String(job.current_chapter_id||'');
      if(!normalizeProjectFolderIdentity(projectFolder)||
          normalizeProjectFolderIdentity(projectFolder)!==normalizeProjectFolderIdentity(productionPreviewRequestProjectFolder)||
          normalizeProjectFolderIdentity(job.project_folder)!==normalizeProjectFolderIdentity(projectFolder)||
          Number(job.current_chapter||0)!==chapterNumber||
          selectedChapterNumber!==chapterNumber||
          productionPreviewRequestChapterNumber!==chapterNumber||
          Boolean(requestChapterId&&selectedChapterId&&requestChapterId!==selectedChapterId)||
          Boolean(requestChapterId&&jobChapterId&&requestChapterId!==jobChapterId)) throw new Error('The Production preview no longer matches the active project and selected saved chapter. Generate it again.');
      if(!productionPreviewRequestChapterId&&jobChapterId)productionPreviewRequestChapterId=jobChapterId;
      const safeFilePart=value=>String(value||'').replace(/[<>:"\/\\|?*\x00-\x1f]+/g,'-').trim().replace(/\s+/g,'_');
      const folderName=projectFolder.replace(/\\/g,'/').split('/').filter(Boolean).pop()||'Ryu_Audiobook';
      const projectBaseName=safeFilePart(activeProject?.title||activeProject?.name||folderName)||'Ryu_Audiobook';
      const chapterTitlePart=safeFilePart(lastVoicePreviewChapterTitle).slice(0,30);
      const suffix='_Chapter_'+String(chapterNumber).padStart(2,'0')+(chapterTitlePart?'_'+chapterTitlePart:'')+'_Preview';
      const suggestedName=(projectBaseName.slice(0,Math.max(12,100-suffix.length))+suffix).slice(0,100);
      const result=await call('production.preview.save',{job_id:productionPreviewJobId,project_folder:projectFolder,chapter_number:chapterNumber,chapter_id:productionPreviewRequestChapterId,source_path:lastVoicePreviewPath,suggested_name:suggestedName});
      if(result.cancelled){message('Production preview save cancelled.');return;}
      message('Production chapter preview saved to '+result.path);
    };
    if ($('productionPreviewDownload')) {
      $('productionPreviewDownload').textContent='Save Production Preview';
      $('productionPreviewDownload').title='Save the validated preview for the active chapter and project';
      $('productionPreviewDownload').onclick=act(downloadProductionPreview);
    }
    if ($('productionPreviewPlay')) $('productionPreviewPlay').onclick=act(async()=>{
      if(!previewAudio||!voicePreviewValid)throw new Error('Generate a validated production preview first.');
      if(!previewAudio.paused)previewAudio.pause();
      else await previewAudio.play();
      syncPreviewPlaybackTime();
    });
    if ($('productionPreviewStop')) $('productionPreviewStop').onclick=()=>{
      if(previewAudio){previewAudio.pause();previewAudio.currentTime=0;}
      syncPreviewPlaybackTime();
    };
    if ($('productionPreviewReplay')) $('productionPreviewReplay').onclick=act(async()=>{
      if(!previewAudio||!voicePreviewValid)throw new Error('Generate and validate a Production preview before replaying it.');
      previewAudio.pause();
      previewAudio.currentTime=0;
      await previewAudio.play();
      syncPreviewPlaybackTime();
    });
    if ($('productionPreviewCancel')) $('productionPreviewCancel').onclick=act(async()=>{
      const job=productionJobSnapshots.preview;
      if(!productionPreviewJobId||!productionJobIsActive(job))throw new Error('There is no active Production preview to cancel.');
      if(String(job.state||'').toLowerCase()==='cancel_requested')throw new Error('Production preview cancellation has already been requested.');
      await call('job.cancel',{job_id:productionPreviewJobId});
      await refreshJobs();
    });
    if ($('startGenerate')) $('startGenerate').onclick=act(async()=>{
      await narratorOnlySavePromise;
      if(productionJobIsActive(productionJobSnapshots.full)||productionJobIsActive(productionJobSnapshots.preview))throw new Error('Another Production audio operation is already running. Finish or cancel it before starting full generation.');
      await flushSoundDesignState();
      const [activeProject, savedSettings] = await Promise.all([
        call('project.get_active'),
        call('settings.get')
      ]);
      window.ryuPremiumActiveProject = activeProject || null;
      window.ryuPremiumApplicationSettings = savedSettings || {};
      await refreshTerms();
      const bitrate = Number(activeProject?.audio_bitrate || savedSettings?.bitrate || 256);
      const narratorOnly = $('narratorOnlyGeneration')?.checked === true;
      const data = await call('production.generate_book', {
        profile_name:activeProject?.voice_profile,
        narrator_only_generation:narratorOnly,
        bitrate
      });
      if(!data?.job_id)throw new Error('The full audiobook generation job was not created.');
      productionFullJobId=String(data.job_id);
      await refreshJobs();
      await monitorProductionJob(data.job_id,'full');
      await refreshProductionSummary();
      await refreshJobs();
    });
    if ($('pauseGenerate')) $('pauseGenerate').onclick=act(async()=>{
      const job=productionJobSnapshots.full;
      const state=String(job?.state||'').toLowerCase();
      if(!productionFullJobId||!job||!['running','paused'].includes(state))throw new Error('There is no pausable full audiobook generation job.');
      if(state==='paused')await call('job.resume',{job_id:productionFullJobId});
      else await call('job.pause',{job_id:productionFullJobId});
      await refreshJobs();
    });
    if ($('cancelJob')) $('cancelJob').onclick=act(async()=>{
      const job=productionJobSnapshots.full;
      if(!productionFullJobId||!productionJobIsActive(job))throw new Error('There is no active full audiobook generation job to cancel.');
      if(String(job.state||'').toLowerCase()==='cancel_requested')throw new Error('Full audiobook cancellation has already been requested.');
      await call('job.cancel',{job_id:productionFullJobId});
      await refreshJobs();
    });
    ['analyzeCharacters','runAiAnalysis'].forEach(id=>{if($(id))$(id).onclick=act(async()=>{const data=await call('character.analyze');await monitorJob(data.job_id,refreshCharacters);});});
    if ($('previewPronTerm')) $('previewPronTerm').onclick=act(async()=>{
      const profile = $('pronQuickVoice')?.value || '';
      const term = $('pronWord')?.textContent?.trim() || $('pronValue')?.value?.trim() || '';
      if (!profile) throw new Error('Select a saved voice profile for the pronunciation test.');
      if (!term) throw new Error('Select a pronunciation term before testing it.');
      const data = await call('voice.preview', {profile_name:profile, text:term, duration_seconds:10});
      await monitorJob(data.job_id, async job=>{
        const url = job?.result?.file_url;
        if (!url) throw new Error('The pronunciation preview finished without a playable audio file.');
        if (previewAudio) { previewAudio.pause(); previewAudio = null; }
        previewAudio = new Audio(url);
        previewAudio.onerror = () => message('The pronunciation preview audio could not be played.', true);
        try { await previewAudio.play(); message('Playing the selected voice pronunciation preview.'); }
        catch (error) { message(error?.message || 'The pronunciation preview could not be played.', true); }
      });
    });
    if ($('savePronTerm')) $('savePronTerm').onclick=act(async()=>{const result=await call('pronunciation.save',{written_form:$('pronWord')?.textContent?.trim()||'',spoken_form:$('pronValue')?.value||'',scope:$('pronScope')?.value||'Current book',handling_mode:$('pronHandling')?.value||'automatic',language:$('pronDetectedLanguage')?.textContent||'Auto'});window.ryuPremiumSelectedPronunciationScopeKey=pronunciationScopeKey(result.entry||{});await refreshTerms();message(result.conflict_resolved?'Pronunciation rule updated; the previous reading was replaced.':'Pronunciation rule saved locally.');});
    if ($('saveNewPron')) $('saveNewPron').onclick=act(async()=>{
      const edit = window.ryuPronunciationEditing || null;
      const payload = {
        written_form:$('newPronWritten')?.value || '',
        spoken_form:$('newPronValue')?.value || '',
        language:$('newPronLanguage')?.value || 'Auto-detect',
        handling_mode:$('newPronHandling')?.value || 'automatic',
        scope:$('newPronScope')?.value || 'current_book',
        origin:edit?.origin || 'manual',
        enabled:edit ? edit.enabled !== false : true
      };
      if (edit) {
        payload.original_written_form = edit.written_form;
        payload.original_scope = edit.scope;
        payload.original_scope_id = edit.scope_id || '';
      }
      const result = await call('pronunciation.save',payload);
      window.ryuPronunciationEditing = null;
      if ($('newPronScope')) $('newPronScope').disabled = false;
      await refreshTerms();
      $('pronEntryModal')?.classList.remove('show');
      message(result.conflict_resolved ? 'Pronunciation rule updated.' : (edit ? 'Pronunciation entry updated.' : 'Manual pronunciation entry saved.'));
    });
    if ($('analyzePronunciation')) $('analyzePronunciation').onclick=act(async()=>{
      const projectAtStart = await call('project.get_active');
      const started = await call('pronunciation.analyze');
      if (!started?.job_id) throw new Error('The pronunciation analysis job was not created.');
      window.ryuPendingPronunciationSuggestions = [];
      renderPronunciationSuggestions([]);
      const status = $('pronAnalysisStatus');
      if (status) { status.hidden = false; status.textContent = 'Starting local AI analysis of saved chapter text…'; }
      await monitorJob(started.job_id, async job => {
        const activeNow = await call('project.get_active');
        const originalFolder = String(projectAtStart?.folder || started.project_folder || '');
        const resultFolder = String(job?.result?.project_folder || originalFolder);
        if (!originalFolder || !resultFolder || String(activeNow?.folder || '') !== resultFolder) {
          window.ryuPendingPronunciationSuggestions = [];
          renderPronunciationSuggestions([]);
          if (status) status.textContent = 'Analysis completed for a different project. Open that project to review its pronunciation suggestions.';
          job.message = 'Pronunciation analysis completed for another project; its suggestions were not shown in the currently open project.';
          return;
        }
        // Reload the active project's complete applicable dictionary at job
        // completion. A user may have added a manual/series/global entry while
        // AI analysis was running; suppress those now-duplicate suggestions.
        await refreshTerms();
        const currentKeys = new Set(terms.map(term =>
          String(term.written_form || term.word || '').normalize('NFC').toLocaleLowerCase()));
        const completedSuggestions = Array.isArray(job?.result?.suggestions) ? job.result.suggestions : [];
        window.ryuPendingPronunciationSuggestions = completedSuggestions.filter(suggestion =>
          !currentKeys.has(String(suggestion.written_form || '').normalize('NFC').toLocaleLowerCase()));
        renderPronunciationSuggestions(window.ryuPendingPronunciationSuggestions);
        if (status) {
          status.hidden = false;
          status.textContent = window.ryuPendingPronunciationSuggestions.length
            ? window.ryuPendingPronunciationSuggestions.length + ' AI suggestion(s) ready for review. None have been saved or enabled.'
            : 'No new high-confidence pronunciation suggestions were found in the current dictionary.';
        }
      });
    });
    if ($('editAssignedCharacter')) $('editAssignedCharacter').onclick=()=>{
      const name=window.ryuPremiumSelectedCharacter;
      const c=characters.find(x=>x.name===name);
      if(!c){message('Select a character from the assigned cast first.',true);return;}
      if($('characterEditorTitle'))$('characterEditorTitle').textContent='Edit character';
      if($('editCharacterName'))$('editCharacterName').value=c.name||'';
      const voiceSelect=$('editCharacterVoice');
      if(voiceSelect){
        const current=c.voice_profile||'';
        voiceSelect.innerHTML='<option value="">Unassigned</option>'+voices.map(v=>'<option value="'+esc(v.name)+'">'+esc(v.name)+' · '+esc(v.provider||'voice')+'</option>').join('');
        voiceSelect.value=current;
      }
      if($('editCharacterShort'))$('editCharacterShort').value=c.short_description||'';
      if($('editCharacterAliases'))$('editCharacterAliases').value=(c.aliases||[]).join(', ');
      if($('editCharacterVoice'))$('editCharacterVoice').value=c.voice_profile||'';
      if($('editCharacterScope'))$('editCharacterScope').value=c.scope||'Current book only';
      if($('editCharacterNotes'))$('editCharacterNotes').value=c.notes||'';
      $('characterEditorModal')?.classList.add('show');
    };
    if ($('saveCharacterProfile')) $('saveCharacterProfile').onclick=act(async()=>{
      const original=window.ryuPremiumSelectedCharacter;
      if(!original)throw new Error('Select a character before saving.');
      const name=$('editCharacterName')?.value.trim()||'';
      const voice=$('editCharacterVoice')?.value||'';
      await call('character.update',{original_name:original,name,short_description:$('editCharacterShort')?.value||'',
        aliases:$('editCharacterAliases')?.value||'',voice_profile:voice,scope:$('editCharacterScope')?.value||'Current book only',
        notes:$('editCharacterNotes')?.value||''});
      window.ryuPremiumSelectedCharacter=name;
      $('characterEditorModal')?.classList.remove('show');
      await refreshCharacters();
      const c=characters.find(x=>x.name===name);
      if(c){if($('assignedInspectorName'))$('assignedInspectorName').textContent=c.name;if($('assignedAliases'))$('assignedAliases').textContent=(c.aliases||[]).join(', ')||'—';if($('assignedVoiceName'))$('assignedVoiceName').textContent=c.voice_profile||'Unassigned';}
      message('Character profile saved locally.');
    });
    if ($('deleteCharacter')) $('deleteCharacter').onclick=act(async()=>{
      const name=window.ryuPremiumSelectedCharacter;
      if(!name)throw new Error('Select a character before deleting.');
      if(!window.confirm('Remove "'+name+'" from this book’s saved cast?'))return;
      await call('character.delete',{name});
      window.ryuPremiumSelectedCharacter=null;
      $('characterEditorModal')?.classList.remove('show');
      await refreshCharacters();
      if($('assignedInspectorName'))$('assignedInspectorName').textContent='Select a character';
      message('Character removed from this book’s saved cast.');
    });
    if ($('assignCharacter')) $('assignCharacter').onclick=act(openVoiceCharacterAssignment);
    if ($('editCharacterVoice')) $('editCharacterVoice').onchange=act(async()=>{
      const current = selectedCharacterRow();
      if (!current) throw new Error('Select a saved character before changing its voice profile.');
      await call('character.assign',{name:characterCanonical(current),series:characterSeries(current),profile_name:$('editCharacterVoice').value});
      await refreshCharacters();
    });
    // Import buttons are handled once by the delegated Sound Design handler below.
    // Import buttons are handled once by the delegated Sound Design handler below.
    document.querySelectorAll('#cueSourceFilter [data-cue-source]').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('#cueSourceFilter [data-cue-source]').forEach(x => x.classList.toggle('active', x === button)); refreshSoundCues().catch(e => message(e.message, true)); }));
    if ($('soundTrackGrid')) $('soundTrackGrid').addEventListener('click', e => {
      const button = e.target.closest('[data-select-sound]');
      if (!button) return;
      const requestedPath = String(button.dataset.selectSound || '');
      const track = sounds.find(item => String(item.path || '') === requestedPath);
      if (!track) {
        message('That Music Library track is no longer available. Refresh the library and select another track.', true);
        refreshSounds().catch(error => message(error?.message || String(error), true));
        return;
      }
      selectedSoundPath = String(track.path);
      if ($('previewSelectedTrack')) $('previewSelectedTrack').disabled = false;
      // Do not leave a previously selected track playing behind the new
      // Selected Track panel. The user can explicitly preview the new track.
      if (soundPreviewAudio &&
          (soundPreviewKind !== 'music' || soundPreviewPath !== selectedSoundPath)) {
        stopSoundPreview();
      }
      if ($('selectedSoundTitle')) $('selectedSoundTitle').textContent = String(track.title || 'Selected track');
      if ($('selectedSoundMeta')) {
        const duration = Number(track.duration_seconds);
        const details = [
          track.category_label || track.category || 'Others',
          track.source || 'Local catalogue',
          track.format || 'Audio',
          Number.isFinite(duration) && duration > 0 ? duration.toFixed(1) + ' sec' : '',
          track.size_bytes ? Math.round(Number(track.size_bytes) / 1024) + ' KB' : ''
        ].filter(Boolean);
        $('selectedSoundMeta').textContent = details.join(' · ');
      }
      message('Selected ' + (track.title || 'sound track') + '. Preview it or save it as the active book default.');
    });
    // setBookDefaultTrack is handled by the single delegated backend listener.
    // saveSoundPresetAdvanced is handled by the single delegated backend listener.
    // Player controls and the timeline are bound once earlier; preserve those handlers.
    if ($('hideMini')) $('hideMini').onclick=()=>{
      miniPlayerDismissed = true;
      $('miniPlayer')?.classList.add('hidden');
    };
    if ($('saveSettingsAdvanced')) $('saveSettingsAdvanced').onclick=act(async()=>{
      const payload = {
        theme:$('themeSelectAdvanced')?.value||'dark',
        effects:$('effectsModeAdvanced')?.value||'high',
        reduce_motion:Boolean($('reduceMotionAdvanced')?.checked),
        text_scale:Number($('uiTextScale')?.value||100),
        window_size:$('uiWindowSize')?.value||'auto'
      };
      await call('settings.save',payload);
      applyUiTextScale(payload.text_scale);
      applyVisualStabilityPreferences(payload);
      message('Settings saved locally. Text size, native window sizing, and reduced-motion preferences are applied without browser zoom.');
    });
    document.addEventListener('input', e => {
      if (e.target?.id === 'librarySearch') {
        e.stopImmediatePropagation();
        scheduleLibrarySearchRefresh();
      } else if (e.target?.id === 'advancedMusicVolume') {
        e.stopImmediatePropagation();
        markMixLevelsDirty();
        if (soundPreviewAudio && soundPreviewKind === 'music') {
          soundPreviewAudio.volume = Math.max(0, Math.min(0.50, Number(e.target.value || 0) / 100));
        }
        const valueNode = $('advancedMusicVolumeValue');
        if (valueNode) valueNode.textContent = Math.round(Number(e.target.value || 0)) + '%';
        renderSoundMixSummary();
      } else if (e.target?.id === 'chapterVolume') {
        e.stopImmediatePropagation();
        markChapterBgmDraftDirty();
        const valueNode = $('chapterVolumeValue');
        if (valueNode) valueNode.textContent = Math.round(Number(e.target.value || 0)) + '%';
      } else if (e.target?.id === 'narrationVolume') {
        e.stopImmediatePropagation();
        markMixLevelsDirty();
        const valueNode = $('narrationVolumeValue');
        if (valueNode) valueNode.textContent = Math.round(Number(e.target.value || 0)) + '%';
        renderSoundMixSummary();
      } else if (e.target?.id === 'cueVolume') {
        e.stopImmediatePropagation();
        markMixLevelsDirty();
        if (soundPreviewAudio && ['cue','cue-sequence'].includes(soundPreviewKind)) {
          soundPreviewAudio.volume = Math.max(0, Math.min(0.50, Number(e.target.value || 0) / 100));
        }
        const valueNode = $('cueVolumeValue');
        if (valueNode) valueNode.textContent = Math.round(Number(e.target.value || 0)) + '%';
        renderSoundMixSummary();
      } else if (e.target?.id === 'chapterTrackSearch') {
        e.stopImmediatePropagation();
        renderChapterBgm();
      } else if (e.target?.id === 'soundTrackSearch') {
        e.stopImmediatePropagation();
        scheduleSoundSearchRefresh();
      } else if (e.target?.id === 'cueSearch') {
        e.stopImmediatePropagation();
        scheduleCueSearchRefresh();
      }
    }, true);
    document.addEventListener('change', async e => {
      if (e.target?.id === 'chapterStartOffset' || e.target?.id === 'chapterEndBehavior') {
        markChapterBgmDraftDirty();
        return;
      }
      if (['advancedMusicVolume','narrationVolume','cueVolume'].includes(e.target?.id)) {
        e.stopImmediatePropagation();
        markMixLevelsDirty();
        try {
          await saveSoundMixLevels();
          message('Narration, cue, and BGM levels saved for preview and final generation.');
        } catch (error) {
          const status = $('mixLevelsSaveState');
          if (status) status.textContent = 'Save failed. The current level values have not been confirmed as saved.';
          message(error?.message || String(error), true);
        }
      }
    });
    // Handle Sound Design tab clicks in capture phase. This wins over legacy
    // target/bubble handlers in the reference HTML so navigation uses live backend state.
    document.addEventListener('click', async e => {
      const soundTab = e.target?.closest?.('#sound .sound-tabs [data-sound-tab]');
      if (!soundTab) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      const nextView = String(soundTab.dataset.soundTab || '');
      if (!['music', 'chapters', 'cues', 'mix'].includes(nextView)) return;
      const currentView = document.querySelector('#sound .sound-tabs [data-sound-tab].active')?.dataset.soundTab || 'music';
      try {
        if (currentView === 'chapters' && chapterBgmDraftDirty) await saveCurrentChapterBgmDraft();
        document.querySelectorAll('#sound .sound-tabs [data-sound-tab]').forEach(button => button.classList.toggle('active', button === soundTab));
        document.querySelectorAll('#sound .sound-view[data-sound-view]').forEach(view => view.classList.toggle('active', view.dataset.soundView === nextView));
        if (nextView === 'music') await refreshSounds();
        else if (nextView === 'chapters') await refreshChapterBgm();
        else if (nextView === 'cues') await refreshSoundCues();
        else if (nextView === 'mix') {
          await refreshChapterBgm();
          renderSoundMixSummary();
        }
      } catch (error) {
        message(error?.message || String(error), true);
      }
    }, true);
    document.addEventListener('click', async e => {
      const bgmMasterToggle = e.target.closest('#sound [data-bgm-enabled], #generate [data-bgm-enabled]');
      if (bgmMasterToggle) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          await flushSoundDesignState();
          const enabled = bgmMasterToggle.dataset.bgmEnabled === 'true';
          const chapterBased = ['custom', 'chapter-based', 'chapter_based', 'chapter'].includes(String(chapterBgmState.strategy || 'same').toLowerCase());
          const defaultPath = String(chapterBgmState.default_path || '').trim();
          const path = chapterBased ? '' : defaultPath;
          await saveSoundManifest({path, enabled});
          await refreshChapterBgm();
          await refreshSoundCues();
          message(enabled
            ? (chapterBased
              ? 'Sound playback enabled; Chapter-Based BGM and configured story cues will be used.'
              : (path ? 'Background music and configured story cues enabled.' : 'Sound playback enabled; no book-default BGM track is assigned yet.'))
            : 'Voice Only saved. Background music and all story cues are disabled for preview and generation.');
        } catch (err) {
          await refreshChapterBgm().catch(() => {});
          message(err?.message || String(err), true);
        }
        return;
      }
      const chapterBgmItem = e.target.closest('#chapterBgmList [data-chapter-bgm]');
      if (chapterBgmItem) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          await saveCurrentChapterBgmDraft();
          selectedBgmChapter = Number(chapterBgmItem.dataset.chapterBgm);
          renderChapterBgm();
        } catch (error) { message(error?.message || String(error), true); }
        return;
      }
      const chapterStrategy = e.target.closest('#sound [data-bgm-strategy]');
      if (chapterStrategy) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          if (chapterStrategySavePromise) await chapterStrategySavePromise;
          const runSave = (async () => {
            await saveCurrentChapterBgmDraft();
            await call('sound.chapter_bgm.save', {strategy:chapterStrategy.dataset.bgmStrategy});
            chapterBgmCandidateChapter = null;
            chapterBgmCandidateTrackPath = null;
            await refreshChapterBgm();
            message(chapterBgmState.strategy === 'same'
              ? 'Same book-wide BGM strategy saved; chapter assignments were preserved for switching back.'
              : 'Chapter-based BGM strategy enabled; saved chapter assignments are available.');
          })();
          chapterStrategySavePromise = runSave;
          renderSoundMixSummary();
          try {
            await runSave;
          } finally {
            if (chapterStrategySavePromise === runSave) chapterStrategySavePromise = null;
            renderSoundMixSummary();
          }
        } catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const chapterRuleButton = e.target.closest('#sound .chapter-rule [data-chapter-rule]');
      if (chapterRuleButton) {
        e.preventDefault(); e.stopImmediatePropagation();
        document.querySelectorAll('#sound .chapter-rule [data-chapter-rule]').forEach(b => b.classList.toggle('active', b === chapterRuleButton));
        markChapterBgmDraftDirty();
        return;
      }
      const chapterSourceFilter = e.target.closest('#chapterBgmSourceFilter [data-chapter-source]');
      if (chapterSourceFilter) {
        e.preventDefault(); e.stopImmediatePropagation();
        document.querySelectorAll('#chapterBgmSourceFilter [data-chapter-source]').forEach(button => button.classList.toggle('active', button === chapterSourceFilter));
        renderChapterBgm();
        return;
      }
      const chapterCategoryFilter = e.target.closest('#chapterBgmCategoryFilter [data-chapter-category]');
      if (chapterCategoryFilter) {
        e.preventDefault(); e.stopImmediatePropagation();
        document.querySelectorAll('#chapterBgmCategoryFilter [data-chapter-category]').forEach(button => button.classList.toggle('active', button === chapterCategoryFilter));
        renderChapterBgm();
        return;
      }
      const chapterTrack = e.target.closest('#chapterTrackPicker [data-chapter-track]');
      if (chapterTrack) {
        e.preventDefault(); e.stopImmediatePropagation();
        chapterBgmCandidateTrackPath = chapterTrack.dataset.chapterTrack;
        document.querySelectorAll('#chapterTrackPicker [data-chapter-track]').forEach(button =>
          button.classList.toggle('active', button === chapterTrack));
        renderSelectedChapterBgmTrack();
        message('Track candidate selected. Press Select to assign it to the current chapter.');
        return;
      }
      if (e.target.closest('#confirmChapterBgmTrack')) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          const chapterBased = ['custom','chapter-based','chapter_based','chapter'].includes(String(chapterBgmState.strategy || 'same').toLowerCase());
          const candidate = sounds.find(track => String(track.path || '') === String(chapterBgmCandidateTrackPath || '') &&
            isMusicSoundAsset(track));
          if (!chapterBased) throw new Error('Switch to Chapter-Based BGM before assigning a chapter track.');
          if (!candidate) throw new Error('Select an available music track first.');
          if (!selectedBgmChapter) throw new Error('Choose a chapter before assigning its BGM.');
          selectedBgmTrackPath = String(candidate.path);
          document.querySelectorAll('#sound .chapter-rule [data-chapter-rule]').forEach(button =>
            button.classList.toggle('active', button.dataset.chapterRule === 'custom'));
          markChapterBgmDraftDirty();
          await saveCurrentChapterBgmDraft(true);
          message('Saved ' + candidate.title + ' as the BGM for Chapter ' + selectedBgmChapter + '.');
        } catch (error) {
          message(error?.message || String(error), true);
          renderSelectedChapterBgmTrack();
        }
        return;
      }
      if (e.target.closest('#saveChapterBgm')) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          await saveCurrentChapterBgmDraft(true);
          message('Saved BGM assignment for Chapter ' + selectedBgmChapter + '.');
        } catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const recentProject = e.target.closest('#dashboard .recent-grid [data-project-folder]');
      if (recentProject) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          const opened = await openProjectWithPreservedDraft(recentProject.dataset.projectFolder);
          const destination = navigateToProjectStage(opened, routeForResume(opened));
          message('Opened local project: ' + (opened.title || 'project') + ' · ' + destination + '.');
        } catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const dashboardButton = e.target.closest('#dashboard button');
      if (dashboardButton) {
        const label = dashboardButton.textContent.trim().toLowerCase();
        if (dashboardButton.id === 'pauseDash') {
          e.preventDefault(); e.stopImmediatePropagation();
          try {
            const rows = await call('job.list', {include_hidden:false});
            const job = rows.find(j => j.type === 'audiobook-generation' && j.state === 'running');
            if (!job) throw new Error('There is no running audiobook generation job to pause.');
            await call('job.pause', {job_id:job.job_id}); await refreshJobs();
            message('Pause requested for ' + (job.title || 'audiobook generation') + '.');
          } catch (err) { message(err?.message || String(err), true); }
          return;
        }
        if (label === 'create new project') {
          e.preventDefault(); e.stopImmediatePropagation();
          if (typeof window.go === 'function') window.go('import');
          else message('Open Import Studio to start a new audiobook project.');
          return;
        }
        if (label === 'continue project') {
          e.preventDefault(); e.stopImmediatePropagation();
          try {
            const folder = dashboardButton.dataset.continueProjectFolder ||
              dashboardButton.closest('[data-dashboard-project-folder]')?.dataset.dashboardProjectFolder ||
              dashboardProject?.folder || '';
            const candidate = projects.find(project => project.folder === folder) || null;
            if (!candidate) throw new Error('Select a saved project or use Create New Project to import a book.');
            const opened = await openProjectWithPreservedDraft(candidate.folder);
            const destination = navigateToProjectStage(opened, routeForResume(opened));
            message('Continuing ' + (opened.title || candidate.title) + ' · ' + destination + '.');
          } catch (err) { message(err?.message || String(err), true); }
          return;
        }
        if (label === 'view job') {
          e.preventDefault(); e.stopImmediatePropagation();
          try {
            const rows = await call('job.list', {include_hidden:false});
            const requestedJobId = dashboardButton.dataset.dashboardJobId || '';
            const job = requestedJobId
              ? rows.find(j => String(j.job_id) === String(requestedJobId))
              : rows.find(j => !['completed','failed','cancelled'].includes(String(j.state || '').toLowerCase()));
            if (!job) throw new Error('There are no active background jobs to view.');
            $('backgroundJobsButton')?.click();
            message((job.title || job.type) + ' · ' + (job.stage || job.state));
          } catch (err) { message(err?.message || String(err), true); }
          return;
        }
      }
      const libraryFilter = e.target.closest('#libraryFilters button');
      if (libraryFilter) {
        e.preventDefault(); e.stopImmediatePropagation();
        libraryFilter.parentElement?.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === libraryFilter));
        refreshProjects().catch(err => message(err?.message || String(err), true));
        return;
      }
      const source = e.target.closest('#soundSourceFilter [data-source]');
      if (source) {
        e.preventDefault(); e.stopImmediatePropagation();
        source.parentElement?.querySelectorAll('[data-source]').forEach(b => b.classList.toggle('active', b === source));
        refreshSounds().catch(err => message(err?.message || String(err), true));
        return;
      }
      const musicCategory = e.target.closest('#sound .sound-categories-list [data-music-category]');
      if (musicCategory) {
        e.preventDefault(); e.stopImmediatePropagation();
        document.querySelectorAll('#sound .sound-categories-list [data-music-category]').forEach(button => {
          button.classList.toggle('active', button === musicCategory);
        });
        refreshSounds().catch(error => message(error?.message || String(error), true));
        return;
      }
      const cueSlot = e.target.closest('[data-assign-cue]');
      if (cueSlot) {
        e.preventDefault(); e.stopImmediatePropagation();
        pendingCueSlot = cueSlot.dataset.assignCue;
        message('Choose a clip from the Effects library to assign it to ' + pendingCueSlot + '.');
        return;
      }
      const cueTrack = e.target.closest('#cueGrid [data-cue-path]');
      if (cueTrack) {
        e.preventDefault(); e.stopImmediatePropagation();
        const path = cueTrack.dataset.cuePath;
        if (soundPreviewAudio &&
            (soundPreviewKind !== 'cue' || soundPreviewPath !== String(path))) {
          stopSoundPreview();
        }
        selectedCuePath = path;
        const selectedCue = sounds.find(track => String(track.path || '') === String(path));
        if ($('selectedCueTitle')) $('selectedCueTitle').textContent = selectedCue?.title || 'Selected cue';
        if ($('selectedCueMeta')) $('selectedCueMeta').textContent = selectedCue
          ? String(selectedCue.source || 'Local catalogue') + ' · ' + String(selectedCue.format || '')
          : 'Selected cue from the local catalogue';
        document.querySelectorAll('#cueGrid [data-cue-path]').forEach(button => {
          const selected = button.dataset.cuePath === path;
          button.classList.toggle('selected', selected);
          button.setAttribute('aria-pressed', selected ? 'true' : 'false');
        });
        if (pendingCueSlot) {
          pendingCueAssignments[pendingCueSlot] = path;
          cueChangesDirty = true;
          cueSaveError = '';
          const slot = pendingCueSlot;
          pendingCueSlot = null;
          await refreshSoundCues();
          scheduleCueAutoSave();
          message('Draft cue selected for ' + slot + '. It will save automatically; use Save Cue Changes to save now.');
        } else {
          message('Cue clip selected. Play it here, or choose Change beside a cue slot and then Save Cue Changes.');
        }
        return;
      }
      const soundButton = e.target.closest('#importMusicTracks, #importCueClips, #previewSelectedTrack, #setBookDefaultTrack, #applySoundToProduction, #soundPreviewBook, #previewCueSequence, #clearAllCues, #saveChapterBgm, #saveCueChanges, #playSelectedCue, #pauseSelectedCue, #replaySelectedCue');
      if (soundButton) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          if (soundButton.id === 'importMusicTracks' || soundButton.id === 'importCueClips') {
            const result = await call('sound.import', {
              target_kind: soundButton.id === 'importMusicTracks' ? 'music' : 'cue',
              category: soundButton.id === 'importMusicTracks' ? ($('musicImportCategory')?.value || 'universal') : 'universal'
            });
            soundCatalogScanRequested = false;
            soundCatalogLoadedAt = 0;
            forceSoundCatalogRefreshPending = true;
            await refreshSounds();
            await refreshSoundCues();
            await refreshChapterBgm();
            message('Imported ' + (result.imported || []).length + ' audio asset(s) into the local catalogue.');
          } else if (soundButton.id === 'saveCueChanges') {
            const saved = await savePendingCueChanges();
            if (saved) {
              await refreshChapterBgm();
              message('Cue changes saved to the active book and ready for preview/final generation.');
            }
          } else if (soundButton.id === 'playSelectedCue') {
            if (!selectedCuePath) throw new Error('Select a cue clip from the Effects library first.');
            if (soundPreviewAudio && soundPreviewKind === 'cue' && soundPreviewPath === selectedCuePath) {
              if (soundPreviewAudio.paused) await soundPreviewAudio.play();
            } else {
              stopSoundPreview();
              const audio = createSoundPreview(selectedCuePath, 'cue', Number($('cueVolume')?.value ?? 25) / 100);
              await audio.play();
            }
          } else if (soundButton.id === 'pauseSelectedCue') {
            if (soundPreviewAudio && soundPreviewKind === 'cue' && soundPreviewPath === selectedCuePath) {
              soundPreviewAudio.pause();
            } else {
              message('The selected cue is not currently playing.');
            }
          } else if (soundButton.id === 'replaySelectedCue') {
            if (!selectedCuePath) throw new Error('Select a cue clip from the Effects library first.');
            stopSoundPreview();
            const audio = createSoundPreview(selectedCuePath, 'cue', Number($('cueVolume')?.value ?? 25) / 100);
            await audio.play();
          } else if (soundButton.id === 'previewSelectedTrack') {
            const track = sounds.find(item => item.path === selectedSoundPath);
            if (!track) throw new Error('Select a track from the local music catalogue first.');
            if (soundPreviewAudio && soundPreviewKind === 'music' && soundPreviewPath === track.path) {
              if (soundPreviewAudio.paused) await soundPreviewAudio.play();
              else soundPreviewAudio.pause();
              const previewButton = $('previewSelectedTrack');
              if (previewButton) previewButton.textContent = soundPreviewAudio.paused ? '▶ Preview selected track' : 'Ⅱ Pause selected track';
            } else {
              stopSoundPreview();
              const audio = createSoundPreview(track.path, 'music', Number($('advancedMusicVolume')?.value ?? 18) / 100);
              await audio.play();
              $('soundWave')?.classList.add('playing');
              const previewButton = $('previewSelectedTrack');
              if (previewButton) previewButton.textContent = 'Ⅱ Pause selected track';
            }
          } else if (soundButton.id === 'setBookDefaultTrack') {
            if (!selectedSoundPath) throw new Error('Select a track from the local sound catalogue first.');
            const savedMixRevision = mixLevelsRevision;
            await saveSoundManifest({path:selectedSoundPath, enabled:true});
            if (savedMixRevision === mixLevelsRevision) mixLevelsDirty = false;
            await refreshChapterBgm();
            message('Book default background track saved.');
          } else if (soundButton.id === 'applySoundToProduction') {
            await flushSoundDesignState();
            document.querySelector('[data-page="generate"]')?.click();
          } else if (soundButton.id === 'saveChapterBgm') {
            await saveCurrentChapterBgmDraft(true);
          } else if (soundButton.id === 'clearAllCues') {
            if (cueAutoSaveTimer) clearTimeout(cueAutoSaveTimer);
            cueAutoSaveTimer = null;
            if (cueSavePromise) await cueSavePromise;
            pendingCueSlot = null;
            pendingCueAssignments = Object.create(null);
            for (const slot of ['opening','chapter','closing']) pendingCueAssignments[slot] = null;
            cueChangesDirty = true;
            cueSaveError = '';
            cueClearAllStaged = true;
            await refreshSoundCues();
            message('Clear-all is staged. Choose Save Cue Changes to remove the three saved cue assignments.');
          } else if (soundButton.id === 'previewCueSequence') {
            const sequence = ['opening','chapter','closing'].map(slot => cueAssignments[slot]?.path).filter(Boolean);
            if (!sequence.length) throw new Error('Assign at least one saved cue before previewing the sequence.');
            stopSoundPreview();
            let index = 0;
            const playNext = () => {
              if (index >= sequence.length) { stopSoundPreview(); return; }
              const raw = sequence[index++];
              const audio = createSoundPreview(raw, 'cue-sequence', Number($('cueVolume')?.value ?? 25) / 100);
              audio.onended = playNext;
              audio.onerror = () => { stopSoundPreview(); message('A cue clip could not be played in the embedded preview.', true); };
              audio.play().catch(err => { stopSoundPreview(); message(err?.message || 'Cue sequence playback failed.', true); });
            };
            playNext();
            message('Playing assigned cue clips in book order.');

          } else if (soundButton.id === 'soundPreviewBook') {
            await flushSoundDesignState({requireExplicitCueClear:true});
            stopSoundPreview();
            const started = await call('sound.preview_book');
            message('Generating the full-book mix preview from saved chapter narration…');
            let finished = false;
            for (let attempt = 0; attempt < 240; attempt++) {
              await new Promise(resolve => setTimeout(resolve, 1500));
              const rows = await call('job.list', {include_hidden:false});
              const job = rows.find(item => item.job_id === started.job_id);
              if (!job) throw new Error('The Sound Design preview job disappeared. Check Generation History.');
              if (job.state === 'failed' || job.state === 'cancelled') throw new Error(job.message || 'Sound Design preview failed.');
              if (job.state === 'completed') {
                const fileUrl = job.result?.file_url || (job.output_path ? 'file:///' + String(job.output_path).replace(/\\/g, '/') : '');
                if (!fileUrl) throw new Error('The Sound Design preview finished without an audio file.');
                // A replaced preview no longer owns the global playback reference.
                // Catch pause/replacement rejections so rapid preview changes cannot
                // leak unhandled play() promises or clear a newer preview's state.
                stopSoundPreview();
                const previewAudio = new Audio(fileUrl);
                soundPreviewAudio = previewAudio;
                previewAudio.onended = () => {
                  if (soundPreviewAudio === previewAudio) soundPreviewAudio = null;
                };
                previewAudio.onerror = () => {
                  if (soundPreviewAudio === previewAudio) soundPreviewAudio = null;
                  message('The Sound Design mix preview could not be played.', true);
                };
                await previewAudio.play().catch(error => {
                  if (previewAudio !== soundPreviewAudio || previewAudio.paused) return;
                  throw error;
                });
                if (soundPreviewAudio !== previewAudio || previewAudio.paused) return;
                message('Playing the generated Sound Design mix preview.');
                finished = true;
                break;
              }
              if (attempt % 4 === 0) message('Full-book mix preview · ' + Number(job.progress || 0) + '% · ' + (job.stage || 'Mixing saved chapters'));
            }
            if (!finished) throw new Error('Sound Design preview timed out. Check Generation History for its status.');
          }
        } catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const filter = e.target.closest('[data-job-filter]');
      if (filter) {
        e.preventDefault(); e.stopImmediatePropagation();
        backendJobFilter = filter.dataset.jobFilter || 'active';
        filter.parentElement?.querySelectorAll('[data-job-filter]').forEach(b => b.classList.toggle('active', b === filter));
        refreshJobs().catch(err => message(err?.message || String(err), true));
        return;
      }
      const b = e.target.closest('[data-job-action]');
      if (b) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          const commands = {
            pause:'job.pause', resume:'job.resume', cancel:'job.cancel',
            retry:'job.retry', recover:'job.recover'
          };
          const actionName = String(b.dataset.jobAction || '');
          await call(commands[actionName] || 'job.cancel', {job_id:b.dataset.jobId});
          await refreshJobs();
          if (actionName === 'retry' || actionName === 'recover') {
            await refreshHistory().catch(()=>{});
            message(actionName === 'recover' ? 'Generation recovery started from compatible saved checkpoints.' : 'Generation retry started from compatible saved checkpoints.');
          }
        } catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const clear = e.target.closest('#clearCompletedJobs, #clearModelQueue');
      if (clear) {
        e.preventDefault(); e.stopImmediatePropagation();
        try { await call('job.clear_completed'); await refreshJobs(); await refreshHistory().catch(()=>{}); message('Completed background jobs cleared.'); }
        catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const pauseAll = e.target.closest('#pauseAllJobs');
      if (pauseAll) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          const rows = await call('job.list', {include_hidden:false});
          const resumable = rows.filter(j => j.type === 'audiobook-generation' && ['paused','pause_requested'].includes(j.state));
          const pausable = rows.filter(j => j.type === 'audiobook-generation' && j.state === 'running');
          if (pausable.length) {
            for (const job of pausable) await call('job.pause', {job_id:job.job_id});
            message('Pause requested for ' + pausable.length + ' audiobook generation job(s).');
          } else if (resumable.length) {
            for (const job of resumable) await call('job.resume', {job_id:job.job_id});
            message('Resume requested for ' + resumable.length + ' audiobook generation job(s).');
          } else {
            message('No active audiobook generation jobs support pause or resume.');
          }
          await refreshJobs();
        } catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const open = e.target.closest('#backgroundJobsButton');
      if (open) { setTimeout(() => refreshJobs().catch(()=>{}), 0); }
    }, true);

    // Stage 8.2.9 integration guard: intercept legacy prototype handlers where a
    // control now has a real backend action, or explicitly report unsupported work.
    const waitForTerminalJob = async (jobId, maxAttempts = 240) => {
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        const rows = await call('job.list', {include_hidden:true});
        const job = rows.find(row => String(row.job_id) === String(jobId));
        if (!job) throw new Error('The background job disappeared. Check Generation History.');
        if (['completed','failed','cancelled'].includes(job.state)) {
          if (job.state !== 'completed') throw new Error(job.message || ('Job ' + job.state + '.'));
          return job;
        }
        if (attempt % 5 === 0) message((job.title || job.type || 'Task') + ' · ' + Math.round(Number(job.progress || 0)) + '% · ' + (job.stage || job.state));
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      throw new Error('The task is still running. Check Generation History for its latest state.');
    };
    const previewSavedProfile = async (profile, text, label, options = {}) => {
      const payload = {profile_name:profile.name,text,duration_seconds:10};
      if (options.routeCharacterCast === false) payload.route_character_cast = false;
      const data = await call('voice.preview', payload);
      const job = await waitForTerminalJob(data.job_id);
      const url = job?.result?.file_url;
      if (!url) throw new Error((label || profile.name) + ' preview finished without a playable audio file.');
      if (previewAudio) { previewAudio.pause(); previewAudio = null; }
      previewAudio = new Audio(url);
      previewAudio.onerror = () => message((label || profile.name) + ' preview audio could not be played.', true);
      await previewAudio.play();
      message('Playing ' + (label || profile.name) + ' · ' + Number(job.result.actual_duration_seconds || 0).toFixed(1) + ' seconds.');
      return job;
    };
    // The shared preview routine is created during Premium V2 hydration, but
    // Character Studio's selected-dialogue handler is authored in the outer
    // adapter scope. Publish the existing function so the default UI invokes
    // the exact same saved-profile job/player path without copying it.
    window.__ryuPreviewSavedProfile = previewSavedProfile;
    document.addEventListener('click', e => {
      const button = e.target.closest('button');
      if (!button) return;
      const label = button.textContent.trim().replace(/\s+/g,' ').toLowerCase();
      const stop = () => { e.preventDefault(); e.stopImmediatePropagation(); };
      if (button.id === 'testSelectedVoices' || button.id === 'testAllVoices') {
        stop();
        (async () => {
          const term = $('pronWord')?.textContent?.trim() || $('pronWord')?.value?.trim() ||
            $('pronValue')?.value?.trim() || terms[0]?.written_form || terms[0]?.word || '';
          if (!term) throw new Error('Choose or save a pronunciation term before testing voices.');
          const selectedName = $('pronQuickVoice')?.value || '';
          const profiles = button.id === 'testAllVoices'
            ? voices.slice()
            : voices.filter(v => v.name === selectedName);
          if (!profiles.length) throw new Error(button.id === 'testAllVoices'
            ? 'No saved voice profiles are available to test.'
            : 'Choose a saved voice profile in the Test term selector first.');
          for (let i = 0; i < profiles.length; i++) {
            message('Pronunciation test ' + (i + 1) + ' of ' + profiles.length + ' · ' + profiles[i].name);
            await previewSavedProfile(profiles[i], term, profiles[i].name);
          }
          message('Pronunciation test completed for ' + profiles.length + ' saved voice profile(s).');
        })().catch(err => message(err?.message || String(err), true));
        return;
      }
      if (button.id === 'setKey') {
        stop();
        void requestElevenLabsApiKey();
        return;
      }
      if (button.matches('[data-open-elevenlabs-web]')) {
        stop();
        const target = button.dataset.openElevenlabsWeb === 'api_keys' ? 'api_keys' : 'studio';
        void call('elevenlabs.open_web',{target})
          .then(() => message(target === 'api_keys'
            ? 'Opened ElevenLabs API-key settings in your default browser.'
            : 'Opened ElevenLabs website in your default browser. Generate audio there and download it manually.'))
          .catch(error => message(error?.message || String(error),true));
        return;
      }
      if (label === 'get api key') {
        stop();
        void call('elevenlabs.open_web',{target:'api_keys'})
          .then(() => message('Opened ElevenLabs API-key settings in your default browser.'))
          .catch(error => message(error?.message || String(error),true));
        return;
      }
      if (button.id === 'generateCandidates' || button.id === 'generateMore') {
        stop();
        void generateElevenLabsCandidates(button.id === 'generateMore').catch(error => message(error?.message || String(error), true));
        return;
      }
      if (button.id === 'addPremium') {
        stop();
        void createSelectedElevenLabsVoice().catch(error => message(error?.message || String(error), true));
        return;
      }
      if (label === 'manage credentials') {
        stop();
        void requestElevenLabsApiKey();
        return;
      }
      if (/^refresh$/.test(label) || label === 'refresh system voices' || label === 'refresh catalogue') {
        stop();
        refreshVoices().then(() => message('Loaded ' + voices.length + ' voice profile(s) from the local voice catalogue.'))
          .catch(err => message(err?.message || String(err), true));
        return;
      }
      if (label.startsWith('install / repair qwen voice studio') || label === 'install / repair engine') {
        stop();
        (async () => {
          const panel = button.closest('.provider');
          const provider = panel?.dataset.provider || '';
          const selection = provider === 'voicedesign' ? 'voicedesign' :
            /clone/i.test(provider) ? 'voiceclone' : 'customvoice';
          const data = await call('models.install', {selection});
          message('Started local Qwen Voice Studio installation. Progress is shown in Background Jobs.');
          await monitorJob(data.job_id, refreshModels);
        })().catch(err => message(err?.message || String(err), true));
        return;
      }
      if (button.closest('#chapters') && label === 'assign speaker') {
        stop();
        if (typeof window.go === 'function') window.go('characters');
        message('Character Studio opened. Select a saved character and assign its voice profile there.');
        return;
      }
      if (button.closest('#chapters') && label === 'add pronunciation') {
        stop();
        const editor = $('chapterEditor');
        const selected = editor && editor.selectionEnd > editor.selectionStart
          ? editor.value.slice(editor.selectionStart, editor.selectionEnd).trim() : '';
        if (selected && $('newPronWritten')) $('newPronWritten').value = selected.slice(0,500);
        $('pronEntryModal')?.classList.add('show');
        if (typeof window.go === 'function') window.go('pronunciation');
        return;
      }
      if (button.closest('#chapters') && ['all','review','empty'].includes(label)) {
        stop();
        const rows = [...($('chapterList')?.querySelectorAll('[data-chapter-number]') || [])];
        if (label === 'all') rows.forEach(row => row.hidden = false);
        else if (label === 'empty') rows.forEach(row => {
          const chapter = chapters.find(c => c.number === Number(row.dataset.chapterNumber));
          row.hidden = Boolean(chapter?.text?.trim());
        });
        else if (label === 'review') rows.forEach(row => {
          const chapter = chapters.find(c => c.number === Number(row.dataset.chapterNumber));
          row.hidden = chapter?.review_status === 'reviewed';
        });
        message(label === 'empty' ? 'Showing empty chapters.' : label === 'review' ? 'Showing chapters that still need review.' : 'Showing all chapters.');
        return;
      }
      // Player transport buttons are bound directly by bindAudiobookPlayerControls()
      // and the shared mainPlay handler. Do not intercept them in capture phase:
      // the previous '◀'/'▶' glyph routing confused chapter navigation with
      // 15-second seeking and Play/Pause, because Next and mainPlay share '▶'.
      if (button.id === 'backgroundJobsButton') {
        stop();
        $('backgroundJobsModal')?.classList.add('show');
        refreshJobs().catch(err => message(err?.message || String(err), true));
        return;
      }
      if (button.id === 'closeBackgroundJobs') {
        stop();
        $('backgroundJobsModal')?.classList.remove('show');
        return;
      }
      if (button.id === 'openJobHistory') {
        stop();
        $('backgroundJobsModal')?.classList.remove('show');
        if (typeof window.go === 'function') window.go('history');
        refreshHistory().catch(err => message(err?.message || String(err), true));
        return;
      }
      if (button.id === 'openUpdateLog') {
        // The build update log is local static release information, not a live backend action.
        return;
      }
    }, true);


    // Replace remaining legacy demo click listeners with real bridge actions or explicit
    // unavailable states. This capture layer runs before prototype target/bubble handlers.
    document.addEventListener('click', e => {
      const button = e.target.closest('button');
      if (!button) return;
      const label = button.textContent.trim().replace(/\s+/g,' ').toLowerCase();
      const stop = () => { e.preventDefault(); e.stopImmediatePropagation(); };
      const invokeAssigned = async fn => { stop(); try { await fn(); } catch (err) { message(err?.message || String(err), true); } };
      // Do not invoke button.onclick from this bubbling handler: the browser has
      // already executed it at the target. Re-dispatching caused duplicate saves,
      // duplicated narrator assignment and overlapping preview jobs.
      if (button.id === 'testAssignedVoice') {
        void invokeAssigned(async () => {
          const c = characters.find(item => item.name === window.ryuPremiumSelectedCharacter);
          if (!c) throw new Error('Select a character from the assigned cast first.');
          const profileName = c.voice_profile || c.voice || '';
          const profile = voices.find(item => item.name.toLowerCase() === String(profileName).toLowerCase());
          if (!profile) throw new Error('This character has no matching saved voice profile. Assign one before testing.');
          await previewSavedProfile(profile, 'Hello, my name is ' + c.name + '.', c.name);
        });
        return;
      }
      if (button.id === 'editAssignedCharacter') {
        stop();
        const c = characters.find(item => item.name === window.ryuPremiumSelectedCharacter);
        if (!c) { message('Select a character from the assigned cast first.', true); return; }
        if ($('characterEditorTitle')) $('characterEditorTitle').textContent = 'Edit character';
        if ($('editCharacterName')) $('editCharacterName').value = c.name || '';
        if ($('editCharacterVoice')) $('editCharacterVoice').value = c.voice_profile || '';
        if ($('editCharacterShort')) $('editCharacterShort').value = c.short_description || '';
        if ($('editCharacterAliases')) $('editCharacterAliases').value = (c.aliases || []).join(', ');
        if ($('editCharacterScope')) $('editCharacterScope').value = c.scope || 'Current book only';
        if ($('editCharacterNotes')) $('editCharacterNotes').value = c.notes || '';
        $('characterEditorModal')?.classList.add('show');
        return;
      }
      if (button.id === 'saveCharacterProfile' && !libraryEditorActive) {
        void invokeAssigned(async () => {
          const original = window.ryuPremiumSelectedCharacter;
          if (!original) throw new Error('Select a character before saving.');
          const name = $('editCharacterName')?.value.trim() || '';
          if (!name) throw new Error('Enter a character name before saving.');
          await call('character.update', {original_name:original,name,short_description:$('editCharacterShort')?.value||'',
            aliases:$('editCharacterAliases')?.value||'',voice_profile:$('editCharacterVoice')?.value||'',
            scope:$('editCharacterScope')?.value||'Current book only',notes:$('editCharacterNotes')?.value||''});
          window.ryuPremiumSelectedCharacter = name;
          $('characterEditorModal')?.classList.remove('show');
          await refreshCharacters();
          message('Character profile saved to the active book.');
        });
        return;
      }
      if (button.id === 'deleteCharacter' && !libraryEditorActive) {
        void invokeAssigned(async () => {
          const name = window.ryuPremiumSelectedCharacter;
          if (!name) throw new Error('Select a character before deleting.');
          if (!window.confirm('Remove "' + name + '" from this book’s saved cast?')) return;
          await call('character.delete', {name});
          window.ryuPremiumSelectedCharacter = null;
          $('characterEditorModal')?.classList.remove('show');
          await refreshCharacters();
          message('Character removed from the active book.');
        });
        return;
      }
      if (button.id === 'pronTermList' || button.closest('#pronTermList [data-pron-term]') || button.closest('#pronDictionaryBody [data-pron-table-term]')) {
        const termButton = button.closest('#pronTermList [data-pron-term]') || button.closest('#pronDictionaryBody [data-pron-table-term]');
        if (!termButton) return;
        stop();
        const selectedWord = termButton.dataset.pronTerm || termButton.dataset.pronTableTerm;
        const selectedScopeKey = termButton.dataset.pronScopeKey || '';
        const term = terms.find(item => String(item.written_form || item.word) === selectedWord &&
          (!selectedScopeKey || pronunciationScopeKey(item) === selectedScopeKey));
        if (!term) { message('That pronunciation term is no longer in the saved dictionary.', true); return; }
        if ($('pronWord')) $('pronWord').textContent = term.written_form || term.word;
        if ($('pronValue')) $('pronValue').value = term.spoken_form || term.pronunciation || '';
        if ($('pronScope')) $('pronScope').value = term.scope || 'Current book';
        window.ryuPremiumSelectedPronunciationScopeKey = pronunciationScopeKey(term);
        if ($('pronHandling')) $('pronHandling').value = term.handling_mode || 'automatic';
        if ($('pronDetectedLanguage')) $('pronDetectedLanguage').textContent = term.language || 'Auto-detected';
        if ($('pronConfidence')) $('pronConfidence').textContent = term.confidence == null ? 'Saved rule' : String(term.confidence) + '%';
        $('pronTermList')?.querySelectorAll('[data-pron-term]').forEach(row => row.classList.toggle('active', row === termButton));
        return;
      }
      if (button.closest('#voices .panel[data-panel="3"]') && label === 'load') {
        stop();
        const select = button.closest('.panel')?.querySelector('.toolbar select');
        const name = String(select?.value || '').trim();
        const profile = voices.find(item => item.saved === true && item.name.toLowerCase() === name.toLowerCase());
        if (!profile) { message('Choose an existing saved profile from the list before loading.', true); return; }
        applySavedVoiceProfile(profile);
        return;
      }
      if (button.closest('#voices .panel[data-panel="3"]') && label === 'delete') {
        void invokeAssigned(async () => {
          const select = button.closest('.panel')?.querySelector('.toolbar select');
          const name = select?.value && select.value !== 'Select saved profile' ? select.value : $('profileName')?.value.trim();
          if (!name) throw new Error('Choose a saved custom profile before deleting.');
          if (!window.confirm('Delete saved custom voice profile "' + name + '"?')) return;
          await call('voice.delete', {profile_name:name});
          await refreshVoices();
          if ($('profileName')) $('profileName').value = '';
          invalidateVoicePreview();selectedVoice=null;selectedVoiceId=null;selectedVoiceProvider=null;profileEditOriginalName='';
          updateVoiceSummary(null,{saved:false,previewReady:false,assignment:''});
          message('Deleted saved custom voice profile: ' + name);
        });
        return;
      }
      if (button.matches('[data-ai-sentence]')) {
        stop();
        (async () => {
          const item = (window.ryuPremiumDialogueReviewItems || []).find(row => row.id === button.dataset.dialogueId);
          if (!item || !item.text) throw new Error('This dialogue passage is stale. Refresh the chapter list and select it again.');
          const savedCharacters = await call('character.list');
          if (!savedCharacters.length) throw new Error('Run Analyze book with AI and save character candidates before assigning dialogue.');
          window.ryuPremiumPendingDialogueText = item.text;
          window.ryuPremiumPendingDialogueChapter = item.chapterNumber;
          window.ryuPremiumPendingDialogueStart = item.start;
          window.ryuPremiumPendingDialogueEnd = item.end;
          window.ryuPremiumPendingDialogueId = item.id;
          if ($('aiSelectedSentence')) $('aiSelectedSentence').textContent = item.text;
          if ($('predictionList')) $('predictionList').innerHTML = savedCharacters.filter(c => c && c.name)
            .map((c, i) => '<button class="prediction-option ' + (item.speakers.includes(c.name) ? 'active' : (i === 0 && !item.assigned ? 'active' : '')) +
              '" data-prediction="' + esc(c.name) + '"><b>' + esc(c.name) +
              '</b><span>Saved character · explicit selection</span></button>').join('');
          if ($('confirmAiCharacter')) $('confirmAiCharacter').disabled = !savedCharacters.length;
          const removeButton = ensureDialogueUnassignButton();
          if (removeButton) removeButton.hidden = !item.assignmentPresent;
          $('aiPredictionModal')?.classList.add('show');
          message(item.assignmentPresent
            ? 'Change the saved speaker or remove this passage assignment.'
            : 'Choose a saved character to assign this passage. The displayed confidence score is not treated as verified evidence.');
        })().catch(err => message(err?.message || String(err), true));
        return;
      }
      if (button.id === 'removeAiCharacterAssignment') {
        stop();
        (async () => {
          const dialogueText = String(window.ryuPremiumPendingDialogueText || '');
          const chapterNumber = window.ryuPremiumPendingDialogueChapter;
          const start = window.ryuPremiumPendingDialogueStart;
          const end = window.ryuPremiumPendingDialogueEnd;
          if (!dialogueText || !Number.isInteger(chapterNumber) || !Number.isInteger(start) || !Number.isInteger(end)) {
            throw new Error('Select a saved dialogue assignment before removing it.');
          }
          if (!window.confirm('Remove the saved speaker assignment for this exact dialogue passage?')) return;
          const result = await call('chapter.dialogue.unassign', {
            chapter_number:chapterNumber, start, end, dialogue_text:dialogueText
          });
          $('aiPredictionModal')?.classList.remove('show');
          window.ryuPremiumPendingDialogueText = '';
          window.ryuPremiumPendingDialogueChapter = null;
          window.ryuPremiumPendingDialogueStart = null;
          window.ryuPremiumPendingDialogueEnd = null;
          window.ryuPremiumPendingDialogueId = null;
          await refreshChapters();
          message('Removed the saved speaker assignment for Chapter ' + result.chapter_number + '.');
        })().catch(err => message(err?.message || String(err), true));
        return;
      }
      if (button.id === 'confirmAiCharacter') {
        stop();
        (async () => {
          const selected = $('predictionList')?.querySelector('.prediction-option.active')?.dataset.prediction || '';
          const dialogueText = String(window.ryuPremiumPendingDialogueText || '');
          if (!selected || !dialogueText) throw new Error('Choose a saved character and dialogue passage before confirming.');
          const selectedSeries = String(button.dataset.series || button.dataset.liveSeries || '').trim();
          const selectedCast = characterRowForName(selected, selectedSeries);
          const libraryMatches = libraryCharacters.filter(item =>
            characterCanonical(item).toLowerCase() === selected.toLowerCase() ||
            characterAliases(item).some(alias => alias.toLowerCase() === selected.toLowerCase())
          );
          const selectedLibrary = selectedSeries
            ? libraryMatches.find(item => characterSeries(item).toLowerCase() === selectedSeries.toLowerCase())
            : (libraryMatches.length === 1 ? libraryMatches[0] : null);
          if (!selectedCast && !selectedLibrary) {
            throw new Error('Select a saved character with an explicit series before assigning this dialogue.');
          }
          const resolvedSeries = selectedSeries || characterSeries(selectedCast || selectedLibrary);
          const result = await call('chapter.dialogue.assign', {
            dialogue_text:dialogueText, speakers:[selected],
            series:resolvedSeries,
            chapter_number:window.ryuPremiumPendingDialogueChapter
          });
          $('aiPredictionModal')?.classList.remove('show');
          window.ryuPremiumPendingDialogueText = '';
          window.ryuPremiumPendingDialogueChapter = null;
          window.ryuPremiumPendingDialogueStart = null;
          window.ryuPremiumPendingDialogueEnd = null;
          window.ryuPremiumPendingDialogueId = null;
          await refreshChapters();
          message('Saved speaker assignment for Chapter ' + result.chapter_number + '.');
        })().catch(err => message(err?.message || String(err), true));
        return;
      }
      if (button.matches('#aiQueue [data-ai-load-more]')) {
        stop();
        const nextCount = Number(button.dataset.aiNextCount);
        const currentCount = Number(window.ryuPremiumDialogueReviewVisibleCount || 120);
        if (!Number.isInteger(nextCount) || nextCount <= currentCount) {
          message('The review queue changed. Refresh the chapter and try again.', true);
          renderDialogueReview();
          return;
        }
        window.ryuPremiumDialogueReviewVisibleCount = nextCount;
        renderDialogueReview();
        return;
      }
      // Automatic per-line AI speaker suggestions remain prototype-only. Manual source-backed dialogue speaker assignments are persisted.
      if (button.matches('[data-ai-line][data-dialogue-id]')) {
        stop();
        const target = [...document.querySelectorAll('[data-ai-sentence][data-dialogue-id]')]
          .find(node => node.dataset.dialogueId === button.dataset.dialogueId);
        if (target) {
          document.querySelectorAll('[data-ai-sentence].active').forEach(node => node.classList.remove('active'));
          target.classList.add('active');
          target.scrollIntoView({block:'nearest', behavior:'smooth'});
          target.focus({preventScroll:true});
        }
        return;
      }
      // Source-less queue placeholders are hidden during initialization. Real
      // Character Studio controls are handled by their dedicated backend actions above.
      if (button.closest('#settings') && label === 'choose folder') {
        stop();
        const storageTab = document.querySelector('[data-settings-tab="storage"]');
        if (storageTab) {
          storageTab.click();
          message('Manage supported project, audio asset and model storage locations in Settings > Storage.');
        } else {
          message('Storage settings are unavailable in this build.', true);
        }
        return;
      }
      if (button.closest('#settings') && label === 'export logs') {
        stop();
        void call('diagnostics.export_logs').then(result => {
          if (result?.cancelled) return;
          message('Sanitized diagnostics exported to ' + result.path +
            ' · ' + Number(result.files_included || 0) + ' log file(s) included.');
        }).catch(err => message(err?.message || String(err), true));
        return;
      }
    }, true);
    const savedProfileSelect = document.querySelector('#voices .panel[data-panel="3"] .toolbar select');
    if (savedProfileSelect) {
      savedProfileSelect.innerHTML = '<option value="">Select saved profile</option>' + voices.map(v => '<option value="' + esc(v.name) + '">' + esc(v.name) + ' · ' + esc(v.provider) + '</option>').join('');
    }


    // Stage 4 Step 1: bind every Dictionary action to saved bridge records.
    document.addEventListener('input', event => {
      if (['pronSearchAdvanced'].includes(event.target?.id)) renderPronunciationRows();
    }, true);
    document.addEventListener('change', event => {
      const target = event.target;
      if (!target) return;
      if (target.matches('[data-pron-select]')) {
        const term = terms[Number(target.dataset.pronSelect)];
        if (!term) return;
        const key = pronunciationSelectionKey(term);
        if (target.checked) pronunciationSelectionKeys.add(key);
        else pronunciationSelectionKeys.delete(key);
        renderPronunciationRows();
        return;
      }
      if (target.matches('[data-pron-enabled]')) {
        const index = Number(target.dataset.pronEnabled);
        const term = terms[index];
        if (!term) { target.checked = false; message('This pronunciation row is stale. Refresh the dictionary and retry.',true); return; }
        const requested = target.checked;
        void call('pronunciation.save',{
          written_form:term.written_form || term.word,
          spoken_form:term.spoken_form || term.pronunciation,
          language:term.language || 'Auto',
          handling_mode:term.handling_mode || 'automatic',
          scope:term.scope || 'current_book',
          scope_id:term.scope_id || '',
          origin:term.origin || 'manual',
          enabled:requested
        }).then(async result => {
          await refreshTerms();
          message(requested ? 'Pronunciation rule enabled for the next valid synthesis.' : 'Pronunciation rule disabled; it will be excluded from preview and generation.');
        }).catch(error => {
          target.checked = !requested;
          message(error?.message || String(error),true);
        });
        return;
      }
      if (target.matches('#pronunciationGlobalToggle,#productionPronunciationToggle')) {
        const requested = target.checked;
        void saveGlobalPronunciation(requested).catch(error => {
          target.checked = !requested;
          const peer = target.id === 'pronunciationGlobalToggle' ? $('productionPronunciationToggle') : $('pronunciationGlobalToggle');
          if (peer) peer.checked = !requested;
          message(error?.message || String(error),true);
        });
      }
    }, true);
    document.addEventListener('click', event => {
      const button = event.target?.closest?.('button');
      if (!button) return;
      const stop = () => { event.preventDefault(); event.stopImmediatePropagation(); };
      const run = fn => { stop(); void Promise.resolve().then(fn).catch(error => message(error?.message || String(error),true)); };
      if (button.matches('[data-pron-test-matrix]')) {
        run(runPronunciationProfileMatrix);
        return;
      }
      if (button.matches('[data-pron-import]')) {
        run(importPronunciationDictionary);
        return;
      }
      if (button.matches('[data-pron-export]')) {
        run(exportPronunciationDictionary);
        return;
      }
      if (button.id === 'addPronunciationAdvanced') {
        run(() => {
          window.ryuPronunciationEditing = null;
          $('pronEntryModalTitle').textContent = 'Add dictionary entry';
          $('newPronWritten').value = '';
          $('newPronValue').value = '';
          $('newPronLanguage').value = 'Auto-detect';
          $('newPronHandling').value = 'automatic';
          $('newPronScope').disabled = false;
          $('newPronScope').value = 'current_book';
          $('pronEntryModal')?.classList.add('show');
          $('newPronWritten')?.focus();
        });
        return;
      }
      if (button.matches('[data-close-pron]')) {
        stop();
        window.ryuPronunciationEditing = null;
        if ($('newPronScope')) $('newPronScope').disabled = false;
        $('pronEntryModal')?.classList.remove('show');
        return;
      }
      if (button.matches('[data-pron-edit]')) {
        run(() => {
          const term = terms[Number(button.dataset.pronEdit)];
          if (!term) throw new Error('This pronunciation entry is stale. Refresh the dictionary and try again.');
          window.ryuPronunciationEditing = {
            written_form:term.written_form || term.word || '',
            scope:term.scope || 'Current book',
            scope_id:term.scope_id || '',
            origin:term.origin || 'manual',
            enabled:term.enabled !== false
          };
          $('pronEntryModalTitle').textContent = 'Edit pronunciation entry';
          $('newPronWritten').value = term.written_form || term.word || '';
          $('newPronValue').value = term.spoken_form || term.pronunciation || '';
          $('newPronLanguage').value = term.language || 'Auto-detect';
          $('newPronHandling').value = term.handling_mode || 'automatic';
          $('newPronScope').value = term.scope_type === 'current_book' ? 'current_book' :
            (term.scope_type === 'global_library' ? 'global_library' : term.scope || '');
          $('newPronScope').disabled = true;
          $('pronEntryModal')?.classList.add('show');
          $('newPronWritten')?.focus();
        });
        return;
      }
      if (button.id === 'deleteSelectedPron') {
        run(async () => {
          const selected = terms.filter(term => pronunciationSelectionKeys.has(pronunciationSelectionKey(term)))
            .map(term => ({
              written_form:term.written_form || term.word,
              scope:term.scope || 'current_book',
              scope_id:term.scope_id || ''
            }));
          if (!selected.length) throw new Error('Select one or more pronunciation rows before bulk deletion.');
          if (!window.confirm('Delete ' + selected.length + ' selected pronunciation entry/entries from their exact scopes?')) return;
          const result = await call('pronunciation.delete_many',{entries:selected});
          pronunciationSelectionKeys.clear();
          await refreshTerms();
          message('Deleted ' + Number(result.deleted || 0) + ' selected pronunciation entry/entries.');
        });
        return;
      }
      if (button.matches('[data-pron-audio-play]')) {
        run(async () => {
          const term = terms[Number(button.dataset.pronIndex)];
          if (!term) throw new Error('This pronunciation row is stale. Refresh the dictionary and retry.');
          const profileName = $('pronPreviewProfile')?.value || '';
          const textValue = button.dataset.pronAudioPlay === 'written'
            ? (term.written_form || term.word || '')
            : (term.spoken_form || term.pronunciation || '');
          await playPronunciationEntryPreview(
            profileName,textValue,
            (button.dataset.pronAudioPlay === 'written' ? 'Written term' : 'Corrected pronunciation') + ': ' + (term.written_form || term.word),
            pronunciationSelectionKey(term),button.dataset.pronAudioPlay
          );
        });
        return;
      }
      if (button.matches('[data-pron-audio-pause]')) {
        stop();
        const term = terms[Number(button.dataset.pronAudioPause)];
        if (!term) { message('This pronunciation row is stale. Refresh the dictionary and retry.',true); return; }
        const identity = pronunciationSelectionKey(term);
        if (!previewAudio || lastPronunciationPreview?.rowIdentity !== identity) {
          message('This row does not own the currently playing pronunciation preview.',true);
          return;
        }
        previewAudio.pause();
        return;
      }
      if (button.matches('[data-pron-audio-replay]')) {
        run(async () => {
          const term = terms[Number(button.dataset.pronAudioReplay)];
          if (!term) throw new Error('This pronunciation row is stale. Refresh the dictionary and retry.');
          const identity = pronunciationSelectionKey(term);
          const savedPreview = pronunciationRowPreviewState.get(identity);
          if (previewAudio && previewAudio.src && lastPronunciationPreview?.rowIdentity === identity) {
            previewAudio.currentTime = 0;
            await previewAudio.play();
            return;
          }
          const profileName = savedPreview?.profile_name || $('pronPreviewProfile')?.value || '';
          const textValue = savedPreview?.text || term.written_form || term.word || '';
          const label = savedPreview?.label || ('Written term: ' + (term.written_form || term.word));
          const kind = savedPreview?.previewKind || 'written';
          await playPronunciationEntryPreview(profileName,textValue,label,identity,kind);
        });
        return;
      }
      if (button.matches('[data-pron-ai-dismiss]')) {
        run(() => {
          const index = Number(button.dataset.pronAiDismiss);
          const list = window.ryuPendingPronunciationSuggestions || [];
          list.splice(index,1);
          renderPronunciationSuggestions(list);
          message('AI draft dismissed; no dictionary entry was saved.');
        });
        return;
      }
      if (button.matches('[data-pron-ai-accept]')) {
        run(async () => {
          const index = Number(button.dataset.pronAiAccept);
          const list = window.ryuPendingPronunciationSuggestions || [];
          const suggestion = list[index];
          if (!suggestion) throw new Error('This AI suggestion is stale. Analyze the saved book again.');
          const written = $('pronAiSuggestions')?.querySelector('[data-pron-ai-written="' + index + '"]')?.value || '';
          const spoken = $('pronAiSuggestions')?.querySelector('[data-pron-ai-spoken="' + index + '"]')?.value || '';
          const scope = $('pronAiSuggestions')?.querySelector('[data-pron-ai-scope="' + index + '"]')?.value || 'current_book';
          if (!written.trim() || !spoken.trim()) throw new Error('Review both Written and Pronounce as before accepting this AI suggestion.');
          await call('pronunciation.save',{
            written_form:written,spoken_form:spoken,language:suggestion.language || 'Auto-detect',
            handling_mode:suggestion.handling_mode || 'automatic',scope,
            origin:'ai',enabled:false,confidence:suggestion.confidence,
            ipa:suggestion.ipa || '',script:suggestion.script || '',
            reason:suggestion.reason || '',alternatives:suggestion.alternatives || []
          });
          list.splice(index,1);
          window.ryuPendingPronunciationSuggestions = list;
          renderPronunciationSuggestions(list);
          await refreshTerms();
          message('AI pronunciation draft saved as a disabled entry. Review it in the dictionary and enable it only after confirmation.');
        });
        return;
      }
    }, true);
    // Last high-value Stage 8.2.9 guards: bind the legacy pronunciation modal and
    // voice-test matrix to saved backend data; never let mock model actions claim success.
    document.addEventListener('click', e => {
      const button = e.target.closest('button');
      if (!button) return;
      const stop = () => { e.preventDefault(); e.stopImmediatePropagation(); };
      const run = async fn => { stop(); try { await fn(); } catch (err) { message(err?.message || String(err), true); } };
      if (button.matches('[data-delete-pron]')) {
        void run(async () => {
          const written = button.getAttribute('data-delete-pron') || '';
          const scope = button.getAttribute('data-delete-scope') || 'Current book';
          const scope_id = button.getAttribute('data-delete-scope-id') || '';
          if (!written) throw new Error('Choose a saved pronunciation rule before deleting.');
          if (!window.confirm('Delete the pronunciation rule for "' + written + '" from ' + scope + '?')) return;
          const result = await call('pronunciation.delete', {written_form:written,scope,scope_id});
          await refreshTerms();
          if (Number(result.deleted || 0) > 0 && $('pronWord')?.textContent?.trim() === written &&
              window.ryuPremiumSelectedPronunciationScopeKey === result.scope_type + ':' + String(result.scope_id || '')) {
            if ($('pronWord')) $('pronWord').textContent = 'Select a pronunciation term';
            if ($('pronValue')) $('pronValue').value = '';
            window.ryuPremiumSelectedPronunciationScopeKey = '';
          }
          message(result.deleted ? 'Pronunciation rule deleted.' : 'No matching rule existed in that scope.', !result.deleted);
        });
        return;
      }
      if (button.id === 'addPronunciationAdvanced') {
        stop();
        if ($('modalTitle')) $('modalTitle').textContent = 'Add pronunciation';
        $('modalBack')?.classList.add('show');
        $('modalWord')?.focus();
        return;
      }
      if (button.id === 'modalSave') {
        void run(async () => {
          const written = $('modalWord')?.value.trim() || '';
          const spoken = $('modalPron')?.value.trim() || '';
          if (!written || !spoken) throw new Error('Enter both the written term and its pronunciation.');
          await call('pronunciation.save', {written_form:written,spoken_form:spoken,scope:'current_book',handling_mode:'automatic'});
          await refreshTerms();
          $('modalBack')?.classList.remove('show');
          message('Pronunciation entry saved to the active book.');
        });
        return;
      }
      if (button.id === 'modalCancel') { stop(); $('modalBack')?.classList.remove('show'); return; }
      if (button.matches('[data-test-pron]')) {
        void run(async () => {
          const card = button.closest('.pron-profile-card, .voice-card, article');
          const name = card?.querySelector('h3')?.textContent?.trim() || '';
          const profile = voices.find(v => v.name.toLowerCase() === name.toLowerCase() ||
            String(v.voice_id || '').toLowerCase() === String(button.dataset.testPron || '').toLowerCase() ||
            String(v.name || '').toLowerCase() === String(button.dataset.testPron || '').toLowerCase());
          if (!profile) throw new Error('This preview card does not map to a saved backend voice profile. Choose a saved profile in Pronunciation Studio.');
          const word = $('pronWord')?.textContent?.trim() || '';
          if (!word) throw new Error('Select a saved pronunciation term before testing a voice.');
          await previewSavedProfile(profile, word, profile.name);
        });
        return;
      }
      if (button.matches('[data-qwen-install]')) {
        void run(async () => {
          const card = button.closest('.model-card');
          const name = card?.querySelector('h2')?.textContent?.trim() || '';
          const selection = /voicedesign/i.test(name) ? 'voicedesign' : /clone/i.test(name) ? 'voiceclone' : 'customvoice';
          const result = await call('models.install', {selection});
          message('Started ' + name + ' installation. Progress is shown in Background Jobs.');
          await monitorJob(result.job_id, refreshModels);
        });
        return;
      }
      if (button.matches('[data-model-open-provider]')) {
        e.preventDefault(); e.stopImmediatePropagation(); stop();
        const providerKey = button.dataset.modelOpenProvider;
        const target = $('voices');
        if (!target) throw new Error('Voice Studio is unavailable in this build.');
        window.go?.('voices');
        document.querySelectorAll('#voices .provider').forEach(panel => panel.classList.toggle('active', panel.dataset.provider === providerKey));
        const defaults = {offline:'Amy',sapi:'David',customvoice:'Serena',voicedesign:'Custom voice description',qwenclone:'Reference voice',customref:'Reference voice',edge:'Edge neural voice',eleven:'ElevenLabs voice'};
        selectedVoice = null; selectedVoiceId = null; selectedVoiceProvider = null;
        if ($('profileName')) $('profileName').value = '';
        if ($('premiumName')) $('premiumName').value = '';
        if ($('profileVoice')) $('profileVoice').textContent = defaults[providerKey] || 'Select a voice';
        void refreshProviderCatalog(providerKey, false).catch(error => message(error?.message || String(error), true));
        message('Opened Voice Studio for ' + (voiceLibraryTitles[providerKey] || providerKey) + '.');
        return;
      }
      if (button.matches('[data-model-open-page]')) {
        e.preventDefault(); e.stopImmediatePropagation(); stop();
        window.go?.(button.dataset.modelOpenPage);
        message('Opened ' + button.dataset.modelOpenPage + ' for the corresponding local model feature.');
        return;
      }
      if (button.matches('[data-model-install], [data-model-repair], [data-model-verify], [data-model-uninstall]')) {
        e.preventDefault(); e.stopImmediatePropagation(); stop();
        void run(async () => {
          const action = button.hasAttribute('data-model-install') ? 'install' :
            button.hasAttribute('data-model-repair') ? 'repair' :
            button.hasAttribute('data-model-verify') ? 'verify' : 'uninstall';
          const operationId = button.getAttribute('data-model-' + action) || '';
          const card = button.closest('.model-card');
          const visibleModelId = String(card?.dataset.modelId || operationId).trim();
          const model = (window.ryuModelInventoryRows || []).find(item => item.model_id === visibleModelId) ||
            (window.ryuModelInventoryRows || []).find(item => item.model_id === operationId) || {};
          const voiceSelect = card?.querySelector('[data-piper-voice-select]');
          let payload = {model_id:operationId};
          if (visibleModelId === 'piper' && ['repair','uninstall'].includes(action)) {
            const voiceName = String(voiceSelect?.value || '').trim();
            if (!voiceName) throw new Error('Choose one installed local Piper voice first.');
            payload.voice_name = voiceName;
          }
          if (visibleModelId === 'piper' && action === 'install') {
            const name = await requestModelActionDialog({
              title:'Install a Piper voice',
              description:'Choose a Piper voice model ID. The model and its metadata will be stored in the local Models folder and then become available in Offline Neural Voices.',
              confirmLabel:'Download voice',
              input:{label:'Piper voice ID',value:'en_US-lessac-medium',placeholder:'en_US-lessac-medium'}
            });
            if (!name) return;
            payload = {model_id:'piper',voice_name:name};
          } else if (action === 'verify') {
            const result = await call('models.verify', {model_id:operationId});
            await refreshModels();
            message((result.status === 'Ready' ? 'Ready. ' : result.status === 'Installed' ? 'Files and dependencies are present; functional readiness is not yet confirmed. ' : 'Verification needs attention. ') + result.detail, !['Ready','Installed'].includes(result.status));
            return;
          } else {
            const displayName = String(model.name || operationId);
            const details = action === 'uninstall'
              ? 'Only the selected app-managed files will be removed. Projects, source books, generated audiobooks and saved voice profiles will be retained. Uninstall is blocked while a voice preview, generation, analysis or model lifecycle job is running.'
              : action === 'repair'
                ? 'This may re-download model files and can take time or use several GB of network data. Saved projects and voice profiles are kept.'
                : String(model.requirements || model.notes || 'The local installer will check the required files and dependencies before reporting success.');
            const approved = await requestModelActionDialog({
              title:action === 'uninstall' ? 'Uninstall ' + displayName : action === 'repair' ? 'Repair ' + displayName : 'Install ' + displayName,
              description:details,
              confirmLabel:action === 'uninstall' ? 'Uninstall component' : action === 'repair' ? 'Repair component' : 'Start installation',
              danger:action === 'uninstall'
            });
            if (!approved) return;
          }
          if (action === 'uninstall' && operationId === 'qwen-model') payload.model_kind = button.dataset.modelKind || visibleModelId;
          if (action === 'uninstall' && operationId === 'piper') {
            payload.model_id = 'piper';
            payload.voice_name = String(voiceSelect?.value || '').trim();
          }
          const disableLabel = button.textContent;
          if (action === 'uninstall') {
            const componentLabel = String(model.name || operationId);
            const exactTarget = operationId === 'piper'
              ? 'the selected Piper voice and its matching .onnx.json file'
              : operationId === 'qwen-model'
                ? 'only the selected Qwen weight folder'
                : operationId === 'qwen-runtime'
                  ? 'the isolated Qwen Python and virtual environment files; downloaded Qwen weights and saved voice profiles are preserved'
                  : operationId === 'chatterbox' || operationId === 'chatterbox-runtime' || operationId === 'chatterbox-multilingual'
                    ? 'the shared Chatterbox provider runtime; downloaded Chatterbox model cache, saved voice profiles and books are preserved'
                    : operationId === 'chatterbox-model-assets'
                      ? 'only Chatterbox-owned Hugging Face cache folders; other provider caches and the Chatterbox runtime are preserved'
                      : operationId === 'audiobook-ai'
                        ? 'the local Audiobook AI runtime and model files'
                        : 'the selected app-managed component files';
            const accepted = window.confirm(
              'Uninstall ' + componentLabel + '?\\n\\nThis removes ' + exactTarget +
              '.\\n\\nProjects, source books, generated audiobooks and saved voice profiles are not uninstall targets.\\n\\nThe action will be blocked while any other application job is active. Continue?'
            );
            if (!accepted) return;
          }
          button.disabled = true;
          button.textContent = action === 'uninstall' ? 'Removing…' : action === 'repair' ? 'Repairing…' : 'Starting…';
          const modelLifecycleCommands = {install:'models.install',repair:'models.repair',uninstall:'models.uninstall'};
          const modelCommand = modelLifecycleCommands[action];
          if (!modelCommand) throw new Error('Unsupported model lifecycle action: ' + action);
          try {
            const queued = await call(modelCommand, payload);
            await refreshJobs();
            message((action === 'uninstall' ? 'Uninstall' : action === 'repair' ? 'Repair' : 'Install') +
              ' queued for ' + (model.name || operationId) + '. Track real progress in Background Jobs.');
            // Model jobs use the terminal callback for refresh/cleanup. They do not
            // produce preview audio, so they must not use monitorJob's preview
            // output-validation callback (which treats false as a preview failure).
            await monitorJob(queued.job_id, null, async job => {
              await refreshModels().catch(error => console.warn('[Ryu model refresh]', error));
              await refreshVoices().catch(error => console.warn('[Ryu voice refresh]', error));
              const providers = operationId === 'piper' || operationId === 'kokoro' ? ['offline'] :
                /qwen|custom-|design-|base-/.test(operationId) ? ['customvoice','voicedesign','qwenclone'] :
                /chatterbox/.test(operationId) ? ['customref'] : [];
              for (const providerKey of providers) {
                try { await refreshProviderCatalog(providerKey, false); } catch (error) { console.warn('[Ryu provider refresh]', error); }
              }
              button.disabled = false;
              button.textContent = disableLabel;
            });
          } catch (error) {
            button.disabled = false;
            button.textContent = disableLabel;
            throw error;
          }
        });
        return;
      }
      if (button.matches('[data-assign-character]')) {
        void run(async () => {
          const dialogueText = String(window.ryuPremiumPendingDialogueText || '').trim();
          const selected = button.dataset.assignCharacter || button.dataset.character || '';
          if (!dialogueText || !selected) throw new Error('Select an individual source dialogue passage and choose a saved character before assigning a speaker.');
          const selectedCast = characterRowForName(selected);
          const selectedLibrary = libraryCharacters.find(item => characterCanonical(item).toLowerCase() === selected.toLowerCase());
          const result = await call('chapter.dialogue.assign', {
            dialogue_text:dialogueText, speakers:[selected],
            series:characterSeries(selectedCast || selectedLibrary),
            chapter_number:window.ryuPremiumPendingDialogueChapter
          });
          window.ryuPremiumPendingDialogueText = '';
          window.ryuPremiumPendingDialogueChapter = null;
          await refreshChapters();
          message('Saved speaker assignment for Chapter ' + result.chapter_number + '.');
        });
        return;
      }
      if (button.id === 'notifyBtn') {
        stop();
        $('backgroundJobsModal')?.classList.add('show');
        refreshJobs().catch(err => message(err?.message || String(err), true));
        return;
      }
    }, true);

    // Hydrate the visible workflow first, then load secondary panels with a paint
    // opportunity between requests. Keep failures local so one unavailable optional
    // subsystem cannot block the rest of the UI from becoming usable.
    const miniDock = $('miniPlayer');
    if (miniDock) miniDock.classList.add('hidden');
    bindMiniPlayerNavigation();
    syncMiniPlayer();

    const startupMilestones = {
      loadSettings: {
        complete: 39,
        loading: 'Loading saved settings…',
        loaded: 'Saved settings loaded.'
      },
      refreshProjects: {
        complete: 54,
        loading: 'Loading your local project library…',
        loaded: 'Project library loaded.'
      },
      refreshVoices: {
        complete: 69,
        loading: 'Loading saved voice profiles…',
        loaded: 'Voice profiles loaded.'
      },
      refreshChapters: {
        complete: 88,
        loading: 'Restoring the chapter workspace…',
        loaded: 'Chapter workspace restored.'
      }
    };
    const reportStartupProgress = (message, progress) => {
      try {
        window.__ryuEmitFrontendDiagnostic?.('startup-progress', {message, progress});
      } catch (_) {}
    };
    const hydratePhase = async (phase, options = {}) => {
      const required = options.required === true;
      for (const refresh of phase) {
        const milestone = required ? startupMilestones[String(refresh?.name || '')] : null;
        if (milestone) reportStartupProgress(milestone.loading, null);
        try { await refresh(); }
        catch (error) {
          console.warn('[Ryu hydration]', error);
          if (required) {
            const step = String(refresh?.name || 'required data refresh');
            throw new Error(
              'Required Premium V2 startup hydration failed in ' + step + ': ' +
              String(error?.message || error || 'Unknown startup error')
            );
          }
        }
        if (milestone) reportStartupProgress(milestone.loaded, milestone.complete);
        // Give Chromium a paint/dispatch opportunity between backend reads.
        await new Promise(resolve => setTimeout(resolve, 0));
      }
    };
    // Do not reveal the app with default font sizing and empty project widgets
    // while persisted Settings are still loading. PremiumV2Window keeps a native
    // loading surface visible until wire() finishes this essential phase.
    await hydratePhase([loadSettings, refreshProjects, refreshVoices, refreshChapters], {required:true});
    await refreshProductionSummary();
    reportStartupProgress('Essential workspace loaded. Finishing the studio…', 94);
    // Secondary panels remain asynchronous and are isolated: a slow optional
    // sound/model subsystem cannot hold the main interface hostage.
    void (async () => {
      await hydratePhase([refreshCharacters, refreshCharacterLibrary, refreshTerms]);
      await hydratePhase([refreshSounds, refreshSoundCues, refreshChapterBgm]);
      await hydratePhase([refreshJobs, refreshHistory, refreshModels]);
    })();
    applyUnavailableControlStates();
    // The prototype action controls were replaced before any async work above;
    // only backend-owned Voice Studio actions remain active here.

    wireProjectMetadataDialog();
    const productionPage = $('generate');
    if (productionPage && !window.__ryuProductionPageObserver) {
      window.__ryuProductionPageObserver = new MutationObserver(() => {
        if (!isVisiblePage('generate') || window.__ryuProductionSummaryRefresh) return;
        const refresh = refreshProductionSummary()
          .then(() => refreshJobs())
          .catch(err => message(err?.message || String(err), true))
          .finally(() => { window.__ryuProductionSummaryRefresh = null; });
        window.__ryuProductionSummaryRefresh = refresh;
      });
      window.__ryuProductionPageObserver.observe(productionPage, {
        attributes:true, attributeFilter:['class']
      });
    }
    if (!window.__ryuBackendJobTimer) window.__ryuBackendJobTimer=setInterval(()=>refreshJobs().catch(()=>{}),1500);
    const jobsBox = $('backgroundJobsList');
    if (jobsBox && !window.__ryuBackendJobsObserver) {
      window.__ryuBackendJobsObserver = new MutationObserver(() => {
        if (!jobsBox.isConnected) return;
        const hasBackendRows = Boolean(jobsBox.querySelector('[data-backend-job], [data-backend-empty]'));
        if (!hasBackendRows && jobsBox.childElementCount) refreshJobs().catch(()=>{});
      });
      window.__ryuBackendJobsObserver.observe(jobsBox, {childList:true,subtree:false});
    }
    // Keep the approved HTML loader visible until the local bridge is connected,
    // required project/voice/chapter hydration has completed, and all essential
    // handlers have been registered. The desktop host prevents the prototype's
    // short demo timer from dismissing it during this real startup path.
    const legacyLoader = $('appLoader');
    if (legacyLoader) legacyLoader.remove();
    message('Premium V2 local backend connected.');
  }
  const start = () => wire().then(() => {
    window.__ryuPremiumAdapterReady = true;
    window.__ryuEmitFrontendDiagnostic?.('frontend-ready', {message:'Premium V2 adapter initialized'});
  }).catch(error => {
    window.__ryuPremiumAdapterReady = false;
    window.__ryuPremiumAdapterFailure = String(
      error?.message || error || 'Adapter initialization failed'
    ).slice(0, 1000);
    window.__ryuEmitFrontendDiagnostic?.('adapter-start-failed', {
      message:window.__ryuPremiumAdapterFailure,
      stack:String(error?.stack || '')
    });
    message(window.__ryuPremiumAdapterFailure, true);
  });
  if (window.ryuBackend?.invoke) start(); else window.addEventListener('ryu-backend-ready', start, {once:true});
})();
