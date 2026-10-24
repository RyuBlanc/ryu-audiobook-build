(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const call = async (command, payload = {}) => {
    if (!window.ryuBackend?.invoke) throw new Error('Local backend bridge is unavailable.');
    const response = await window.ryuBackend.invoke(command, payload);
    if (!response?.success) throw new Error(response?.error?.message || command + ' failed.');
    return response.data;
  };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const message = (text, error = false) => {
    const node = $('importStatus'); if (node) node.textContent = text;
    const validation = $('validation'); if (validation && error) validation.textContent = text;
    const toasts = $('toasts'); if (toasts) { toasts.textContent = text; toasts.classList.add('show'); }
    if (error) console.error('[Ryu backend]', text);
  };
  const act = fn => async event => { event?.preventDefault?.(); try { await fn(event); } catch (e) { message(e?.message || String(e), true); } };
  let selectedVoice = null, selectedVoiceId = null, activeJob = null, poll = null, previewAudio = null, playerAudio = null, soundPreviewAudio = null, cueSearchUnavailableNotified = false, chapterSaveTimer = null, chapterSavePromise = Promise.resolve(), activePlayerChapters = [], playerPositionSaveAt = 0, playerRate = 1, playerVolume = 0.8;
  let chapters = [], characters = [], voices = [], terms = [], projects = [], sounds = [], selectedSoundPath = null, pendingCueSlot = null, cueAssignments = {}, chapterBgmState = {strategy:'same',overrides:{}}, selectedBgmChapter = null, selectedBgmTrackPath = null;
  let dashboardProject = null, selectedAudiobookFolder = null, miniPlayerDismissed = false;
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
  // The approved HTML ships legacy prototype listeners. Replace only sound controls
  // whose actions are handled by the real backend adapter; visual markup is unchanged.
  ['importMusicTracks','importCueClips','previewSelectedTrack','setBookDefaultTrack',
   'saveChapterBgm','previewCueSequence','clearAllCues','soundPreviewBook',
   'saveSoundPresetAdvanced','applySoundToProduction'].forEach(id => {
    const node = $(id);
    if (node?.parentNode) node.replaceWith(node.cloneNode(true));
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
    const quotePattern = /“[^”]{2,}”|「[^」]{2,}」|『[^』]{2,}』|"[^"\n]{2,}"/g;
    const normalize = value => String(value || '').replace(/[^\p{L}\p{N}]+/gu, ' ').toLocaleLowerCase().trim();
    const items = [];
    for (const chapter of chapters) {
      const source = String(chapter.text || '');
      quotePattern.lastIndex = 0;
      let match;
      while ((match = quotePattern.exec(source)) && items.length < 250) {
        const text = match[0].trim();
        if (text.length < 4) continue;
        const assignment = (chapter.dialogue_assignments || []).find(item =>
          item && typeof item === 'object' &&
          Number.isInteger(item.start) && Number.isInteger(item.end) &&
          item.start === match.index && item.end === match.index + match[0].length &&
          source.slice(item.start, item.end) === String(item.text || '')
        );
        const names = assignment
          ? (Array.isArray(assignment.speakers) && assignment.speakers.length
              ? assignment.speakers : [assignment.speaker]).filter(Boolean)
          : [];
        items.push({
          id: 'dialogue-' + chapter.number + '-' + match.index,
          chapterNumber: Number(chapter.number),
          chapterTitle: String(chapter.title || ('Chapter ' + chapter.number)),
          text, start: match.index, end: match.index + match[0].length,
          speakers: names, assigned: Boolean(names.length), assignmentPresent: Boolean(assignment)
        });
      }
    }
    window.ryuPremiumDialogueReviewItems = items;
    const assignedCount = items.filter(item => item.assigned).length;
    const remaining = Math.max(0, items.length - assignedCount);
    const percent = items.length ? Math.round(assignedCount / items.length * 100) : 0;
    if (progressText) progressText.textContent = assignedCount + ' of ' + items.length + ' dialogue passages assigned';
    if (progressBar) progressBar.style.width = percent + '%';
    if (progressLabel) progressLabel.textContent = percent + '% assigned';
    if (pendingBadge) pendingBadge.textContent = remaining + ' left';
    if (title) title.textContent = items.length
      ? 'Chapter ' + items[0].chapterNumber + ' · ' + items[0].chapterTitle
      : 'Dialogue review';
    if (subtitle) subtitle.textContent = items.length
      ? 'Select a real dialogue passage from the imported chapters to assign or change its saved speaker.'
      : 'Import a book with quoted dialogue to review source-backed speaker assignments.';
    if (queue) queue.innerHTML = items.slice(0, 40).map(item => {
      const preview = item.text.length > 62 ? item.text.slice(0, 59) + '…' : item.text;
      const status = item.assigned ? 'Saved: ' + item.speakers.join(', ') : 'Needs speaker assignment';
      return '<button class="ai-queue-item" data-ai-line="' + esc(item.id) + '" data-dialogue-id="' + esc(item.id) + '">' +
        '<span>Chapter ' + item.chapterNumber + '</span><b>' + esc(preview) + '</b><small>' +
        esc(status) + '</small></button>';
    }).join('') || '<p class="muted">No quoted dialogue passages found in the saved chapters.</p>';
    if (storyDocument) {
      storyDocument.innerHTML = items.slice(0, 120).map(item => {
        const speakerLabel = item.assigned ? item.speakers.join(' + ') + ' · saved' : 'Unassigned · select to assign';
        const classes = 'ai-sentence ' + (item.assigned ? 'confirmed' : 'review');
        return '<button class="' + classes + '" data-ai-sentence="source-backed" data-dialogue-id="' + esc(item.id) +
          '" data-chapter-number="' + item.chapterNumber + '"><span class="ai-speaker">' + esc(speakerLabel) +
          '</span>' + esc(item.text) + '</button>';
      }).join('') || '<p class="muted">No quoted dialogue passages found in the saved chapters.</p>';
    }
  }
  function documentRef() {
    return document.querySelector('.char-view[data-char-view="ai"] .ai-document') ||
      document.querySelector('#chapters .ai-document');
  }
  const renderSelect = (select, rows, value, label) => {
    if (!select) return;
    const previous = select.value;
    select.innerHTML = rows.map(r => '<option value="' + esc(r[value]) + '">' + esc(label(r)) + '</option>').join('');
    if (rows.some(r => String(r[value]) === previous)) select.value = previous;
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
    const chaptersReady = chapterCount > 0 && preparedChapters === chapterCount;
    const hasChapterText = preparedChapters > 0;
    const narratorName = String(project.narrator || project.voice_profile || '').trim();
    const narratorReady = Boolean(String(project.voice_profile || '').trim());
    const characterCount = Number(project.character_count || 0);
    const characterVoiceCount = Number(project.character_voice_count || 0);
    const characterReviewed = Boolean(project.character_analysis_done);
    const charactersReady = characterReviewed &&
      (characterCount === 0 || characterVoiceCount >= characterCount);
    const outputReady = Boolean(project.output_configured);
    const canGenerate = chapterCount > 0 && hasChapterText && narratorReady && outputReady;
    const pronunciationCount = Number(project.pronunciation_rule_count || 0);
    const soundConfigured = Boolean(project.sound_design_configured);

    const stageState = [
      {key:'import', ready:Boolean(project.source_exists), detail:project.source_exists ? 'Book & metadata' : 'Source file missing'},
      {key:'chapters', ready:chaptersReady, detail:chaptersReady ? 'Structure & text' :
        (chapterCount ? preparedChapters + '/' + chapterCount + ' chapters ready' : 'No chapters imported')},
      {key:'voices', ready:narratorReady, detail:narratorReady ? (narratorName || project.voice_profile) : 'Choose a voice profile'},
      {key:'characters', ready:charactersReady, detail:!characterReviewed ? 'Not analyzed' :
        (characterCount === 0 ? 'No characters found' :
          (charactersReady ? 'Voices assigned' : (characterCount-characterVoiceCount) + ' need review'))},
      {key:'pronunciation', ready:true, detail:pronunciationCount ? pronunciationCount + ' saved rules' : 'Names & terms'},
      {key:'sound', ready:true, detail:soundConfigured ? 'Configured' : 'Music & effects'},
      {key:'generate', ready:canGenerate, detail:project.completed ? 'Audiobook ready' : (canGenerate ? 'Build audiobook' : 'Setup required')}
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
      container.className = 'section';
      page.insertBefore(container, page.firstElementChild);
    }
    const available = rows.filter(project => project.completed && project.output_path);
    container.innerHTML = '<div class="section-head"><div><p class="eyebrow">YOUR LIBRARY</p><h2>Generated audiobooks</h2></div><p class="muted">' +
      available.length + ' ready to play</p></div><div class="recent-grid">' +
      (available.map(project => '<article class="card project-card" data-project-folder="' + esc(project.folder || '') +
        '" data-cover-path="' + esc(project.cover_path || '') + '"><div class="book-cover"></div><div class="project-pad"><span class="badge">Ready</span><h3>' +
        esc(project.title || 'Untitled audiobook') + '</h3><p class="muted">' + esc(project.narrator || 'Narrator not set') + ' · ' +
        Number(project.chapter_count || 0) + ' chapters</p><button class="btn small" type="button" data-play-project-folder="' +
        esc(project.folder || '') + '">Play audiobook</button></div></article>').join('') ||
        '<p class="muted">No finished audiobooks yet. Generate one in Production Studio to see it here.</p>') + '</div>';
    applyProjectCovers(container);
  }
  function dashboardGenerationCard(root) {
    const title = dashboardFindText(root, 'production status') || dashboardFindText(root, 'active generation');
    let node = title?.parentElement || null;
    while (node && node !== root) {
      const text = dashboardText(node.textContent);
      const buttons = [...node.querySelectorAll('button,[role="button"],a')];
      if (text.includes('current chapter') && text.includes('processing stage') &&
          buttons.some(button => ['view job','pause','resume'].includes(dashboardText(button.textContent)))) return node;
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
      if (siblings.length) { siblings[siblings.length - 1].textContent = value; return; }
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
    const control = buttons.find(button => ['pause','resume'].includes(dashboardText(button.textContent)));
    if (!job) {
      const selectedProject = dashboardProject || null;
      setDashboardRow(card, 'current chapter', selectedProject
        ? (Number(selectedProject.completed_chapter_count || 0) + ' chapters prepared')
        : 'No project selected');
      setDashboardRow(card, 'processing stage', selectedProject
        ? (selectedProject.completed && selectedProject.output_path ? 'Audiobook ready' :
          ('Setup checkpoint · ' + (savedResumeStage(selectedProject) || routeForResume(selectedProject))))
        : 'No active generation job');
      if (percentLabel) percentLabel.textContent = '';
      if (etaLabel) etaLabel.textContent = '';
      if (fill) { fill.style.width = '0%'; fill.setAttribute('aria-valuenow','0'); if (fill.tagName === 'PROGRESS') fill.value = 0; }
      if (track) track.style.visibility = 'hidden';
      if (view) { view.disabled = true; delete view.dataset.dashboardJobId; }
      if (control) { control.disabled = true; delete control.dataset.dashboardJobId; delete control.dataset.dashboardGenerationAction; }
      return;
    }
    const project = projects.find(row => row.folder === job.project_folder);
    const total = Number(job.chapters_total || project?.chapter_count || 0);
    const current = Number(job.current_chapter || 0);
    setDashboardRow(card, 'current chapter', current > 0 ? current + ' of ' + (total || '—') : (total ? '0 of ' + total : '—'));
    setDashboardRow(card, 'processing stage', job.stage || job.message || 'Working');
    const percent = Math.max(0, Math.min(100, Math.round(Number(job.progress || 0))));
    if (percentLabel) percentLabel.textContent = percent + '% complete';
    const eta = Number(job.eta_seconds);
    if (etaLabel) etaLabel.textContent = Number.isFinite(eta) && eta > 0 ? Math.floor(eta/60) + 'm ' + String(Math.floor(eta%60)).padStart(2,'0') + 's remaining' : '';
    if (track) track.style.visibility = '';
    if (fill) { fill.style.width = percent + '%'; fill.setAttribute('aria-valuenow',String(percent)); if (fill.tagName === 'PROGRESS') fill.value = percent; }
    if (view) { view.disabled = false; view.dataset.dashboardJobId = job.job_id || ''; }
    if (control) {
      const paused = ['paused','pause_requested'].includes(String(job.state || '').toLowerCase());
      control.textContent = paused ? 'Resume' : 'Pause';
      control.disabled = !['running','paused'].includes(String(job.state || '').toLowerCase());
      control.dataset.dashboardGenerationAction = paused ? 'resume' : 'pause';
      control.dataset.dashboardJobId = job.job_id || '';
    }
  }
  function audiobookPageActive() {
    const nav = [...document.querySelectorAll('nav .active,aside .active,.sidebar .active,[aria-current="page"]')]
      .find(node => /audiobooks/i.test(node.textContent || ''));
    if (nav) return true;
    const page = $('player');
    if (!page || page.hidden || page.classList.contains('hidden')) return false;
    const style = window.getComputedStyle(page);
    return style.display !== 'none' && style.visibility !== 'hidden' && page.getClientRects().length > 0;
  }
  function syncMiniPlayer() {
    const dock = $('miniPlayer');
    if (dock) dock.classList.toggle('hidden', !(playerAudio && playerAudio.src && !miniPlayerDismissed && !audiobookPageActive()));
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
          refreshProjects().catch(() => {});
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
      }, 3000);
    }
  }
  function updateProjectDeleteButton() {
    const button = $('deleteSelectedProjects');
    if (!button) return;
    const count = selectedProjectFolders.size;
    button.textContent = 'Delete Selected (' + count + ')';
    button.disabled = count === 0;
    button.title = count ? 'Move ' + count + ' selected book(s) to Deleted Books' : 'Select one or more books first';
    button.style.opacity = count ? '1' : '.55';
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
      deleteButton.textContent = 'Delete Selected (0)';
      deleteButton.title = 'Select one or more books first';
      deleteButton.style.cssText = 'margin-left:8px;white-space:nowrap;';
      deleteButton.addEventListener('click', () => deleteSelectedProjects().catch(err => message(err?.message || String(err), true)));
      parent.appendChild(deleteButton);
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
  async function refreshProjects() {
    projects = (await call('project.list')).sort((a,b) => (Date.parse(b.modified_at || '') || 0) - (Date.parse(a.modified_at || '') || 0));
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
    if (grid) {
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
      if (recent) {
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
    renderAudiobookLibrary(projects);
    if (!playerAudio || !playerAudio.src) clearAudiobookPlayerDisplay();
    return projects;
  }
  async function refreshVoices() {
    voices = await call('voice.list');
    const rows = voices.map(v => ({...v, label: v.name + ' · ' + v.provider}));
    renderSelect($('editCharacterVoice'), [{name:'',label:'Unassigned'}, ...rows], 'name', v => v.label || 'Unassigned');
    if ($('characterEditorModal')?.classList.contains('show') && $('editCharacterVoice')) $('editCharacterVoice').disabled = true;
    renderSelect($('pronQuickVoice'), rows, 'name', v => v.label);
    const profileSelect = document.querySelector('#voices .panel[data-panel="3"] .toolbar select');
    if (profileSelect) {
      const previous = profileSelect.value;
      const saved = voices.filter(v => v.saved === true);
      profileSelect.innerHTML = '<option value="">Select saved profile</option>' +
        saved.map(v => '<option value="' + esc(v.name) + '">' + esc(v.name) + ' · ' + esc(v.provider) + '</option>').join('');
      profileSelect.value = saved.some(v => v.name === previous) ? previous : '';
      profileSelect.disabled = saved.length === 0;
      profileSelect.title = saved.length ? 'Choose a saved voice profile to load' : 'No saved profiles yet. Configure and save a voice profile first.';
    }
    // A catalogue selection is not a saved custom profile; never prefill this name.
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
    root.innerHTML = cards.map(([label,value]) =>
      '<div style="background:rgba(9,12,18,.72);border:1px solid rgba(148,163,184,.15);border-radius:10px;padding:10px 12px;min-width:0">' +
      '<div style="font-size:11px;letter-spacing:.04em;color:var(--muted,#9ca3af);margin-bottom:6px">' + esc(label) + '</div>' +
      '<div style="font-size:17px;font-weight:750;overflow-wrap:anywhere;color:var(--text,#f3f4f6)">' + esc(value) + '</div></div>'
    ).join('');
    // Chapter Insights is a read-only metrics card; remove placeholder values
    // and render only current backend-derived measurements inside the same card.
    panel.replaceChildren(title, root);
  }

  async function refreshChapters() {
    chapters = await call('chapter.list'); window.ryuPremiumChapters = chapters;
    if (!chapters.length) { renderDialogueReview(); return; }
    if (!chapters.some(c => c.number === window.ryuPremiumSelectedChapter)) window.ryuPremiumSelectedChapter = chapters[0].number;
    const current = selectedChapter(), list = $('chapterList'), editor = $('chapterEditor'), title = $('chapterTitle');
    if (list) {
      list.style.maxHeight = 'calc(100vh - 270px)';
      list.style.overflowY = 'auto';
      list.style.overscrollBehavior = 'contain';
      list.style.minHeight = '0';
      list.style.paddingRight = '4px';
      list.setAttribute('aria-label', 'Scrollable chapter list');
      list.innerHTML = chapters.map(c => '<div class="list-item ' + (c.number === current.number ? 'active' : '') + '" data-chapter-number="' + c.number + '">' + esc('Chapter ' + c.number + ' · ' + c.title) + '</div>').join('');
      list.querySelectorAll('[data-chapter-number]').forEach(el => el.addEventListener('click', () => {
        const c = chapters.find(x => x.number === Number(el.dataset.chapterNumber)); if (!c) return;
        window.ryuPremiumSelectedChapter = c.number;
        if (title) title.textContent = c.title; if (editor) editor.value = c.text;
        if ($('wordCount')) $('wordCount').textContent = c.word_count;
        chapterLastText = c.text || ''; chapterHistoryGroupOpen = false;
        if (chapterHistoryGroupTimer) { clearTimeout(chapterHistoryGroupTimer); chapterHistoryGroupTimer = null; }
        list.querySelectorAll('.list-item').forEach(x => x.classList.toggle('active', x === el));
      }));
    }
    if (title) title.textContent = current.title;
    if (editor && document.activeElement !== editor) editor.value = current.text;
    if ($('wordCount')) $('wordCount').textContent = current.word_count;
    chapterLastText = current.text || '';
    chapterHistoryGroupOpen = false;
    if (chapterHistoryGroupTimer) { clearTimeout(chapterHistoryGroupTimer); chapterHistoryGroupTimer = null; }
    renderDialogueReview();
    renderLiveChapterInsights();
  }
  async function refreshCharacters() {
    characters = await call('character.list');
    const list = $('assignedCharacterList');
    if (list) list.innerHTML = characters.map(c => '<button class="assigned-character" data-character-name="' + esc(c.name) + '">' + esc(c.name) + '<small>' + esc(c.role || 'Character') + ' · ' + Number(c.dialogue_count || 0) + ' lines</small></button>').join('') || '<p class="muted">No saved characters yet. Run analysis on an imported book.</p>';
    if ($('charFoundMetric')) $('charFoundMetric').textContent = characters.length;
    if ($('assignedCountBadge')) $('assignedCountBadge').textContent = characters.length;
    list?.querySelectorAll('[data-character-name]').forEach(el => el.addEventListener('click', () => {
      const c = characters.find(x => x.name === el.dataset.characterName); if (!c) return;
      if ($('assignedInspectorName')) $('assignedInspectorName').textContent = c.name;
      if ($('assignedLineCount')) $('assignedLineCount').textContent = c.dialogue_count || 0;
      if ($('assignedAliases')) $('assignedAliases').textContent = (c.aliases || []).join(', ') || '—';
      if ($('assignedQuotes')) $('assignedQuotes').innerHTML = (c.examples || []).map(q => '<p>' + esc(q) + '</p>').join('');
      if ($('assignedVoiceName')) $('assignedVoiceName').textContent = c.voice_profile || 'Unassigned';
      if ($('editCharacterVoice')) $('editCharacterVoice').value = c.voice_profile || '';
      window.ryuPremiumSelectedCharacter = c.name;
    }));
  }
  const librarySeriesName = c => {
    const raw = String(c?.series || c?.scope || '').trim();
    return raw.replace(/^Series\s*[·:-]\s*/i, '').replace(/^Global character library$/i, '').trim();
  };
  function ensureCharacterSeriesField() {
    const modal = $('characterEditorModal');
    if (!modal) return;
    const legacyScope = $('editCharacterScope');
    const legacyGroup = legacyScope?.closest('.form-group, .form-row, .field') || legacyScope?.parentElement;
    if (legacyGroup) legacyGroup.style.display = 'none';
    let input = $('editCharacterSeries');
    if (!input) {
      const wrap = document.createElement('div');
      wrap.className = 'form-group';
      wrap.style.cssText = 'display:flex;flex-direction:column;gap:7px;margin-top:12px;';
      const label = document.createElement('label');
      label.htmlFor = 'editCharacterSeries';
      label.textContent = 'Series';
      label.style.cssText = 'font-size:13px;font-weight:700;color:#e6e9f0;';
      input = document.createElement('input');
      input.id = 'editCharacterSeries';
      input.type = 'text';
      input.maxLength = 300;
      input.placeholder = 'e.g. That Time I Got Reincarnated as a Slime';
      input.autocomplete = 'off';
      input.style.cssText = 'width:100%;box-sizing:border-box;padding:10px 12px;border-radius:10px;border:1px solid #343b49;background:#0d1119;color:#f4f5f8;font:inherit;';
      wrap.append(label, input);
      const name = $('editCharacterName');
      const anchor = name?.closest('.form-group, .form-row, .field') || name?.parentElement;
      if (anchor?.parentElement) anchor.parentElement.insertBefore(wrap, anchor.nextSibling);
      else (modal.querySelector('.modal-body') || modal).appendChild(wrap);
    }
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
      voice.title = 'Voice assignments are managed in Character Studio so all volumes stay consistent.';
      if (!modal.__ryuVoiceLockObserver && typeof MutationObserver !== 'undefined') {
        modal.__ryuVoiceLockObserver = new MutationObserver(() => {
          if (!modal.classList.contains('show')) voice.disabled = false;
        });
        modal.__ryuVoiceLockObserver.observe(modal, {attributes:true, attributeFilter:['class']});
      }
      if (modal.classList.contains('show')) voice.disabled = true;
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
    const selectedSeries = $('characterSeriesFilter')?.value || 'All series';
    if ($('editCharacterSeries')) $('editCharacterSeries').value = c?.series || (selectedSeries !== 'All series' ? selectedSeries : '');
    ensureCharacterDialogueSampleField();
    if ($('editCharacterDialogueSample')) $('editCharacterDialogueSample').value = c?.dialogue_sample || '';
    if ($('deleteCharacter')) $('deleteCharacter').style.visibility = c ? 'visible' : 'hidden';
    $('characterEditorModal')?.classList.add('show');
    if ($('editCharacterVoice')) $('editCharacterVoice').disabled = true;
  }
  async function saveLibraryEditor() {
    const name = $('editCharacterName')?.value.trim() || ''; if (!name) throw new Error('Enter a character name before saving it to the Character Library.');
    const requestedSeries = $('editCharacterSeries')?.value.trim() || '';
    const scope = requestedSeries ? 'Series · ' + requestedSeries : 'Global character library';
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
  async function refreshTerms() {
    terms = await call('pronunciation.list');
    const list = $('pronDictionaryBody');
    if (list) list.innerHTML = terms.map(t => {
      const word = String(t.written_form || t.word || '');
      const spoken = String(t.spoken_form || t.pronunciation || '');
      const scope = String(t.scope || 'Current book');
      const scopeKey = pronunciationScopeKey(t);
      const language = String(t.language || 'Auto');
      const status = t.enabled === false ? 'Disabled' : 'Enabled';
      return '<tr><td><button type="button" class="btn small ghost" data-pron-table-term="' + esc(word) + '" data-pron-scope-key="' + esc(scopeKey) + '">' + esc(word) + '</button></td>' +
        '<td>' + esc(spoken) + '</td><td>' + esc(language) + '</td><td>' + esc(scope) + '</td>' +
        '<td>' + esc(t.test_status || 'Not tested') + '</td><td><span>' + status + '</span> ' +
        '<button type="button" class="btn small ghost" data-delete-pron="' + esc(word) + '" data-delete-scope="' + esc(scope) + '" data-delete-scope-id="' + esc(String(t.scope_id || '')) + '" aria-label="Delete pronunciation rule for ' + esc(word) + '">Delete</button></td></tr>';
    }).join('') || '<tr><td colspan="6" class="muted">No saved pronunciation rules for this book.</td></tr>';
    const termList = $('pronTermList');
    if (termList) {
      const selected = $('pronWord')?.textContent?.trim();
      const selectedKey = window.ryuPremiumSelectedPronunciationScopeKey || '';
      termList.innerHTML = terms.map(t => {
        const word = String(t.written_form || t.word || '');
        const spoken = String(t.spoken_form || t.pronunciation || '');
        const scopeKey = pronunciationScopeKey(t);
        return '<button type="button" class="list-item ' + (word === selected && scopeKey === selectedKey ? 'active' : '') + '" data-pron-term="' + esc(word) + '" data-pron-scope-key="' + esc(scopeKey) + '"><b>' + esc(word) + '</b><span>' + esc(spoken) + ' · ' + esc(t.scope || 'Current book') + '</span></button>';
      }).join('') || '<p class="muted">No saved pronunciation terms yet. Use Analyze book or Add entry.</p>';
    }
  }
  async function refreshSounds() {
    sounds = await call('sound.catalog');
    const grid = $('soundTrackGrid');
    const query = ($('soundTrackSearch')?.value || '').trim().toLowerCase();
    const sourceFilter = document.querySelector('#soundSourceFilter [data-source].active')?.dataset.source || 'all';
    const visible = sounds.filter(t => {
      const matchesQuery = !query || (t.title + ' ' + t.source + ' ' + t.format).toLowerCase().includes(query);
      const matchesSource = sourceFilter === 'all' ||
        (sourceFilter === 'built-in' && String(t.source).toLowerCase().includes('bundled')) ||
        (sourceFilter === 'imported' && String(t.source).toLowerCase().includes('imported'));
      return matchesQuery && matchesSource;
    });
    if (grid) grid.innerHTML = visible.map(t => '<article class="sound-track card"><div class="sound-track-info"><b>' + esc(t.title) + '</b><small>' + esc(t.source) + ' · ' + esc(t.format) + ' · ' + Math.round(Number(t.size_bytes || 0)/1024) + ' KB</small></div><button class="btn small secondary" data-select-sound="' + esc(t.path) + '">Select</button></article>').join('') || '<p class="muted">No local or bundled sound tracks found. Import your own licensed audio files.</p>';
    return sounds;
  }
  async function refreshSoundCues() {
    cueAssignments = await call('sound.cues.get');
    const names = {opening:'openingCueName',chapter:'chapterCueName',scene:'sceneCueName',closing:'closingCueName'};
    for (const [slot,id] of Object.entries(names)) {
      const node = $(id);
      if (node) node.textContent = cueAssignments[slot]?.title || 'Not assigned';
    }
    const grid = $('cueGrid');
    if (!grid) return cueAssignments;
    const query = ($('cueSearch')?.value || '').trim().toLowerCase();
    const sourceFilter = document.querySelector('#cueSourceFilter [data-cue-source].active')?.dataset.cueSource || 'all';
    const visible = sounds.filter(t => {
      const text = (t.title + ' ' + t.source + ' ' + t.format).toLowerCase();
      const source = String(t.source || '').toLowerCase();
      return (!query || text.includes(query)) &&
        (sourceFilter === 'all' || (sourceFilter === 'built-in' && source.includes('bundled')) ||
         (sourceFilter === 'imported' && source.includes('imported')));
    });
    grid.innerHTML = visible.map(t => '<button type="button" class="cue-track card" data-cue-path="' + esc(t.path) + '"><b>' + esc(t.title) + '</b><small>' + esc(t.source) + ' · ' + esc(t.format) + '</small></button>').join('') ||
      '<p class="muted">No matching local cue clips. Import licensed audio clips to use them here.</p>';
    return cueAssignments;
  }
  function renderChapterBgm() {
    const list = $('chapterBgmList'), picker = $('chapterTrackPicker');
    const rows = chapterBgmState.chapters || chapters.map(ch => ({number:ch.number,title:ch.title}));
    if (!rows.length) {
      if (list) list.innerHTML = '<p class="muted">Import a book to assign chapter music.</p>';
      if (picker) picker.innerHTML = '<p class="muted">No chapters are available.</p>';
      return;
    }
    if (!rows.some(ch => Number(ch.number) === Number(selectedBgmChapter))) selectedBgmChapter = Number(rows[0].number);
    const overrides = chapterBgmState.overrides || {};
    if (list) list.innerHTML = rows.map(ch => {
      const o = overrides[String(ch.number)] || {};
      const rule = o.rule || 'default';
      const label = rule === 'custom' ? (o.title || (o.available === false ? 'Missing custom track' : 'Custom track')) : rule === 'none' ? 'No BGM' : 'Book default';
      return '<button type="button" class="chapter-bgm-item ' + (Number(ch.number) === Number(selectedBgmChapter) ? 'active' : '') + (rule === 'custom' ? ' override' : '') + '" data-chapter-bgm="' + Number(ch.number) + '"><b>' + esc('Chapter ' + ch.number + ' · ' + ch.title) + '</b><small>' + esc(label) + '</small></button>';
    }).join('');
    const chapter = rows.find(ch => Number(ch.number) === Number(selectedBgmChapter)) || rows[0];
    const current = overrides[String(chapter.number)] || {};
    const rule = current.rule || 'default';
    selectedBgmTrackPath = current.path || null;
    if ($('chapterBgmTitle')) $('chapterBgmTitle').textContent = 'Chapter ' + chapter.number + ' · ' + chapter.title;
    document.querySelectorAll('#sound [data-bgm-strategy]').forEach(b => b.classList.toggle('active', b.dataset.bgmStrategy === (chapterBgmState.strategy || 'same')));
    document.querySelectorAll('#sound .chapter-rule [data-chapter-rule]').forEach(b => b.classList.toggle('active', b.dataset.chapterRule === rule));
    if ($('chapterVolume')) $('chapterVolume').value = Math.round(Number(current.volume ?? chapterBgmState.default_volume ?? 0.18) * 100);
    const selects = document.querySelectorAll('#sound [data-sound-view="chapters"] .chapter-mix-row select');
    if (selects[0]) selects[0].selectedIndex = ({immediate:0,after_first_paragraph:1,after_10_seconds:2})[current.start_offset || 'immediate'] ?? 0;
    if (selects[1]) selects[1].selectedIndex = ({fade_before_end:0,continue_to_transition:1,stop_immediately:2})[current.end_behavior || 'fade_before_end'] ?? 0;
    if (picker) {
      const visible = sounds;
      picker.innerHTML = visible.map(t => '<button type="button" class="chapter-track-option ' + (t.path === selectedBgmTrackPath ? 'active' : '') + '" data-chapter-track="' + esc(t.path) + '"><b>' + esc(t.title) + '</b><small>' + esc(t.source) + ' · ' + esc(t.format) + '</small></button>').join('') ||
        '<p class="muted">No local music tracks found. Import a licensed audio file first.</p>';
    }
    const mixStrategy = $('mixStrategy');
    if (mixStrategy) mixStrategy.textContent = chapterBgmState.strategy === 'custom' ? 'Chapter-based BGM' : 'Same BGM';
    const mixOverrides = $('mixOverrides');
    if (mixOverrides) mixOverrides.textContent = Object.values(overrides).filter(o => o.rule === 'custom' || o.rule === 'none').length + ' chapters';
  }
  async function refreshChapterBgm() {
    chapterBgmState = await call('sound.chapter_bgm.get');
    const fadeIn = Number(chapterBgmState.fade_in_seconds ?? 2);
    const fadeOut = Number(chapterBgmState.fade_out_seconds ?? 3);
    if ($('bgmFadeIn')) $('bgmFadeIn').selectedIndex = ({0:0,2:1,3:2,5:3})[fadeIn] ?? 0;
    if ($('bgmFadeOut')) $('bgmFadeOut').selectedIndex = ({0:0,3:1,5:2,8:3})[fadeOut] ?? 0;
    renderChapterBgm();
    return chapterBgmState;
  }
  let backendJobFilter = 'active';
  async function refreshJobs() {
    const allJobs = await call('job.list', {include_hidden:false});
    refreshDashboardGeneration(allJobs);
    const jobs = allJobs.filter(j => backendJobFilter === 'all' ||
      (backendJobFilter === 'completed' ? j.state === 'completed' :
      (backendJobFilter === 'failed' ? j.state === 'failed' :
      !['completed','failed','cancelled'].includes(j.state))));
    const box = $('backgroundJobsList');
    // The jobs modal is normally hidden. Avoid rebuilding its DOM on every poll;
    // when open, preserve row nodes and update only changing fields/progress.
    const panelVisible = Boolean($('backgroundJobsModal')?.classList.contains('show'));
    if (box && panelVisible) {
      const signature = jobs.map(j => [
        j.job_id, j.state, j.type, j.title, Boolean(j.recoverable),
        Boolean(j.message), Boolean(j.error?.message)
      ].join('\u001f')).join('\u001e');
      if (box.dataset.backendJobsSignature !== signature) {
        box.innerHTML = jobs.map(j => {
          const id = esc(j.job_id || ''), state = String(j.state || 'unknown');
          const action = (name,label,cls) => '<button class="btn small ' + cls + '" data-job-action="' + name + '" data-job-id="' + id + '">' + label + '</button>';
          const canControlGeneration = j.type === 'audiobook-generation';
          const canCancelImport = j.type === 'import';
          const actions = (canControlGeneration && ['running','pause_requested'].includes(state) ? action('pause','Pause','secondary') : '') +
            (canControlGeneration && ['paused','pause_requested'].includes(state) ? action('resume','Resume','') : '') +
            ((state === 'queued' || (canControlGeneration && ['running','paused','pause_requested','cancel_requested'].includes(state)) || (canCancelImport && ['running','cancel_requested'].includes(state))) ? action('cancel','Cancel','ghost') : '') +
            (state === 'failed' && j.recoverable ? '<small>Retry by restarting this operation from its screen.</small>' : '') +
            (['running','pause_requested'].includes(state) && !canControlGeneration && !canCancelImport ? '<small>Cancellation and pause are not supported for this operation.</small>' : '');
          return '<article class="job-row" data-backend-job="' + id + '">' +
            '<b data-job-title>' + esc(j.title || j.type || id) + '</b>' +
            '<p data-job-stage>' + esc(j.stage || j.message || state) + '</p>' +
            '<div class="progress"><i data-job-progress style="width:' + Math.max(0,Math.min(100,Number(j.progress || 0))) + '%"></i></div>' +
            '<small data-job-state>' + esc(state) + ' · ' + Math.round(Number(j.progress || 0)) + '%</small>' +
            '<p data-job-message' + (j.message ? '' : ' hidden') + '>' + esc(j.message || '') + '</p>' +
            '<p class="muted" data-job-error' + (j.error?.message ? '' : ' hidden') + '>' + esc(j.error?.message || '') + '</p>' +
            '<div class="toolbar">' + actions + '</div></article>';
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
          const messageNode = row.querySelector('[data-job-message]');
          const errorNode = row.querySelector('[data-job-error]');
          if (stage) stage.textContent = j.stage || j.message || j.state || 'unknown';
          if (progress) progress.style.width = pct + '%';
          if (state) state.textContent = String(j.state || 'unknown') + ' · ' + Math.round(pct) + '%';
          if (messageNode) messageNode.textContent = j.message || '';
          if (messageNode) messageNode.hidden = !j.message;
          if (errorNode) errorNode.textContent = j.error?.message || '';
          if (errorNode) errorNode.hidden = !j.error?.message;
        });
      }
      box.dataset.backendJobsRendered = '1';
    }
    if ($('jobsRunningCount')) $('jobsRunningCount').textContent = allJobs.filter(j => ['running','pause_requested','cancel_requested'].includes(j.state)).length;
    if ($('jobsQueuedCount')) $('jobsQueuedCount').textContent = allJobs.filter(j => j.state === 'queued').length;
    if ($('jobsCompletedCount')) $('jobsCompletedCount').textContent = allJobs.filter(j => j.state === 'completed').length;
    if ($('backgroundJobCount')) $('backgroundJobCount').textContent = allJobs.filter(j => !['completed','failed','cancelled'].includes(j.state)).length + ' background jobs';
  }
  async function monitorJob(jobId, done) {
    activeJob = jobId; if (poll) clearInterval(poll);
    const tick = async () => {
      try {
        const jobs = await call('job.list', {include_hidden:true}), job = jobs.find(j => j.job_id === jobId);
        if (!job) return;
        const pct = Math.max(0, Math.min(100, Number(job.progress || 0)));
        if ($('genPercent')) $('genPercent').textContent = Math.round(pct) + '%';
        if ($('genRing')) $('genRing').style.setProperty('--progress', pct + '%');
        if ($('importBar')) $('importBar').style.width = pct + '%';
        if ($('genStage')) $('genStage').textContent = job.stage || job.message || job.state;
        if ($('aiProgressText')) $('aiProgressText').textContent = job.stage || job.message || job.state;
        if ($('aiProgressBar')) $('aiProgressBar').style.width = pct + '%';
        if ($('previewProgress')) $('previewProgress').style.width = pct + '%';
        if ($('previewState') && job.type === 'voice-preview') $('previewState').textContent = job.stage || job.state;
        await refreshJobs();
        if (['completed','failed','cancelled'].includes(job.state)) {
          clearInterval(poll); poll = null;
          const completionResult = job.state === 'completed' && done ? await done(job) : undefined;
          if (completionResult === false) {
            message('The preview job ended, but its output did not pass playback validation. Check the preview status and retry.', true);
          } else {
            // Import results carry review warnings separately from the concise job status.
            // Surface those warnings to the user instead of silently dropping them.
            const importWarnings = job.type === 'import' && job.state === 'completed' &&
              Array.isArray(job.result?.warnings) ? job.result.warnings.filter(Boolean) : [];
            const completionMessage = importWarnings.length
              ? importWarnings.join(' ')
              : (job.message || ((job.title || 'Job') + ' ' + job.state));
            message(completionMessage, job.state !== 'completed');
          }
          if (job.state === 'completed') { await refreshChapters().catch(()=>{}); await refreshCharacters().catch(()=>{}); }
        }
      } catch (e) { console.error(e); }
    };
    await tick(); poll = setInterval(tick, 1000);
  }
  function requestVoiceProfileSaveName(initialName, providerKey, voiceLabel) {
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
      eyebrow.textContent = 'CONFIRM VOICE PROFILE';
      eyebrow.style.cssText = 'color:#e8b957;font-size:11px;font-weight:800;letter-spacing:.13em;margin-bottom:8px';
      const title = document.createElement('h2');
      title.id = 'ryuVoiceSaveTitle'; title.textContent = 'Save this voice profile?';
      title.style.cssText = 'margin:0 0 8px;font-size:22px';
      const description = document.createElement('p');
      description.textContent = 'This saves profile settings locally. It does not generate audio or change your narrator until you choose “Save and Use as Narrator”.';
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
      save.type = 'button'; save.textContent = 'Confirm & Save Profile';
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

  async function saveVoice(options = {}) {
    const name = String(options.nameOverride ?? ($('profileName')?.value || $('premiumName')?.value || '')).trim();
    const choice = document.querySelector('.provider.active')?.dataset.provider || 'offline';
    const providerMap = {offline:'piper',sapi:'windows-sapi',customvoice:'qwen-character',voicedesign:'qwen-character',qwenclone:'qwen-character',customref:'chatterbox',edge:'edge-tts',eleven:'elevenlabs'};
    const provider = providerMap[choice] || (choice.includes('clone') ? 'qwen-character' : 'piper');
    const voiceLabel = $('profileVoice')?.textContent?.trim() || selectedVoiceId || 'Amy';
    if (!options.confirmed) {
      const confirmedName = await requestVoiceProfileSaveName(name, choice, voiceLabel);
      if (!confirmedName) { message('Voice profile save cancelled.'); return null; }
      return saveVoice({confirmed:true,nameOverride:confirmedName});
    }
    if (!name) throw new Error('Enter a name for this voice profile.');
    if (name.length > 160) throw new Error('Profile names must be 160 characters or fewer.');
    const authorized = Boolean($('clonePermission')?.checked || $('customPermission')?.checked);
    let sample_path = '';
    if (provider === 'chatterbox' || (provider === 'qwen-character' && /clone/i.test(choice))) {
      if (!authorized) throw new Error('Confirm you have permission to use this reference recording.');
      const imported = await call('voice.import_reference', {profile_name:name});
      if (imported.cancelled) return;
      sample_path = imported.sample_path || imported.path || '';
    }
    const matchedPiper = voices.find(v => v.provider === 'piper' && String(v.voice_id || '').toLowerCase().includes(voiceLabel.toLowerCase()));
    const designPanel = document.querySelector('.provider[data-provider="voicedesign"]');
    const designPrompt = designPanel?.querySelector('textarea')?.value?.trim() || '';
    const designLanguage = designPanel?.querySelector('select')?.value || 'English';
    const rawSeed = Number(designPanel?.querySelector('input[type="number"]')?.value || 0);
    const designSeed = Number.isFinite(rawSeed) && rawSeed > 0 ? Math.trunc(rawSeed) : null;
    if (choice === 'voicedesign' && !designPrompt) throw new Error('Enter a voice description before saving a VoiceDesign profile.');
    const qwenMode = choice === 'voicedesign' ? 'design' : /clone/i.test(choice) ? 'clone' : 'custom';
    const voice_id = provider === 'piper' ? (matchedPiper?.voice_id || voices.find(v => v.name === name)?.voice_id || 'en_US-amy-medium') : (selectedVoiceId || voiceLabel || name);
    const result = await call('voice.save', {name,provider,voice_id,sample_path,authorized,
      model_id:provider === 'chatterbox' ? 'chatterbox' : provider === 'qwen-character' ? 'auto' : provider,
      backend:provider === 'piper' ? 'automatic' : provider,language:choice === 'voicedesign' ? designLanguage : 'English',
      qwen_mode:provider === 'qwen-character' ? qwenMode : 'custom',
      qwen_prompt:choice === 'voicedesign' ? designPrompt : '',
      qwen_seed:choice === 'voicedesign' ? designSeed : null,
      notes:choice === 'voicedesign' ? designPrompt : '',
      reference_text:$('cloneTranscript')?.value || ''});
    selectedVoice = result.name; selectedVoiceId = result.voice_id; await refreshVoices();
    if ($('profileName')) $('profileName').value = result.name;
    const savedSelect = document.querySelector('#voices .panel[data-panel="3"] .toolbar select');
    if (savedSelect) savedSelect.value = result.name;
    document.querySelectorAll('#voices *').forEach(node => {
      if (node.children.length === 0 && node.textContent.trim() === 'Unsaved') node.textContent = 'Saved';
    });
    if ($('profileLibrary')) $('profileLibrary').textContent = result.provider;
    if ($('profileVoice')) $('profileVoice').textContent = result.voice_id;
    if ($('previewProfile')) $('previewProfile').textContent = result.name;
    if ($('useNarrator')) $('useNarrator').disabled = false;
    if ($('saveOnly')) $('saveOnly').disabled = false;
    message('Saved voice profile locally: ' + result.name); return result;
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
  function preparePreviewPlayback(job, requestedSeconds) {
    const url = job?.result?.file_url;
    const actual = Number(job?.result?.actual_duration_seconds);
    const requested = Number(requestedSeconds || job?.result?.requested_duration_seconds || 0);
    const play = $('playPreview');
    if (!url || !Number.isFinite(actual) || actual <= 0) {
      if (play) play.disabled = true;
      if ($('previewState')) $('previewState').textContent = 'Failed';
      if ($('validation')) $('validation').textContent = !url
        ? 'Preview job completed without a playable local audio file. Check the job details and retry.'
        : 'Preview job completed without a valid measured audio duration. The result cannot be marked ready.';
      return false;
    }
    if (previewAudio) { previewAudio.pause(); previewAudio = null; }
    previewAudio = new Audio(url);
    previewAudio.preload = 'auto';
    previewAudio.onended = () => { if (play) play.textContent = '▶ Play'; };
    previewAudio.onerror = () => {
      if (play) play.disabled = true;
      if ($('previewState')) $('previewState').textContent = 'Playback error';
      if ($('validation')) $('validation').textContent = 'The preview file exists but the embedded player could not open it. Use the preview output path from job details.';
    };
    if (play) play.disabled = false;
    if ($('validation')) {
      $('validation').textContent = requested > 0 && actual + 1.5 < requested
        ? 'Preview shorter than requested · ' + actual.toFixed(1) + 's of ' + requested.toFixed(0) + 's. The source text or voice provider produced less audio than requested; try a longer passage and check the selected voice.'
        : 'Preview ready · ' + actual.toFixed(1) + ' seconds' + (requested > 0 ? ' (requested ' + requested.toFixed(0) + 's)' : '');
    }
    return true;
  }
  async function previewVoice() {
    const name = (selectedVoice || $('profileName')?.value || '').trim();
    if (!name) throw new Error('Save or select a voice profile first.');
    const c = selectedChapter();
    const lengthGroup = [...document.querySelectorAll('#voices .toolbar')].find(el => /Length/.test(el.textContent));
    const duration = lengthGroup?.querySelector('.seg button.active')?.textContent.match(/\d+/)?.[0] || '30';
    const modeGroup = [...document.querySelectorAll('#voices .seg')].find(el => [...el.querySelectorAll('button')].some(b => /Current Chapter|Selected Passage|Custom Text/.test(b.textContent)));
    const mode = modeGroup?.querySelector('button.active')?.textContent.trim() || 'Current Chapter';
    const previewBox = [...document.querySelectorAll('#voices textarea')].find(el => /Preview text/.test(el.closest('label')?.textContent || ''));
    let previewText = c?.text || '';
    if (/Custom Text/i.test(mode)) previewText = previewBox?.value || '';
    if (/Selected Passage/i.test(mode)) {
      const editor = $('chapterEditor');
      previewText = editor && editor.selectionEnd > editor.selectionStart ? editor.value.slice(editor.selectionStart, editor.selectionEnd) : window.getSelection()?.toString() || '';
      if (!previewText.trim()) throw new Error('Select a passage in Chapter Studio before generating a passage preview.');
    }
    if (!previewText.trim()) throw new Error('The selected preview text is empty.');
    const data = await call('voice.preview', {profile_name:name,text:previewText,duration_seconds:Number(duration),chapter_number:c?.number});
    if (previewAudio) { previewAudio.pause(); previewAudio = null; }
    if ($('playPreview')) { $('playPreview').disabled = true; $('playPreview').textContent = '▶ Play'; }
    if ($('previewProgress')) $('previewProgress').style.width = '0%';
    if ($('previewState')) $('previewState').textContent = 'Queued';
    if ($('validation')) $('validation').textContent = 'Preview job ' + data.job_id + ' is running locally.';
    await monitorJob(data.job_id, async job => {
      const playable = preparePreviewPlayback(job, Number(duration));
      if ($('previewState') && playable) $('previewState').textContent = 'Ready';
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
      chapterList.innerHTML = chapters.map(chapter => {
        const start = Number(chapter.start_seconds);
        const hasTiming = Number.isFinite(start) && start >= 0;
        return '<div class="list-item" role="button" tabindex="' + (hasTiming ? '0' : '-1') +
          '" data-audiobook-chapter-start="' + (hasTiming ? String(start) : '') + '"' +
          (hasTiming ? '' : ' aria-disabled="true"') + '>' +
          esc('Chapter ' + Number(chapter.number || 0) + ' · ' + String(chapter.title || 'Untitled chapter')) +
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
    const hasTimedChapters = chapters.some(chapter => Number.isFinite(Number(chapter.start_seconds)));
    if (playerButtons[1]) {
      playerButtons[1].disabled = !hasTimedChapters;
      playerButtons[1].title = hasTimedChapters ? 'Previous chapter' : 'Chapter navigation is unavailable for this audiobook file';
    }
    if (playerButtons[3]) {
      playerButtons[3].disabled = !hasTimedChapters;
      playerButtons[3].title = hasTimedChapters ? 'Next chapter' : 'Chapter navigation is unavailable for this audiobook file';
    }
    const duration = playerAudio?.duration || 0;
    if ($('playerTimeline')) { $('playerTimeline').value = duration ? (playerAudio.currentTime / duration) * 100 : 0; $('playerTimeline').disabled = false; }
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
    setPlaybackButtonState();
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
  function applyPlayerRate(value, persist = true) {
    const rate = Number(value);
    if (!Number.isFinite(rate) || rate < 0.5 || rate > 2) {
      message('Playback speed must be between 0.5× and 2.0×.', true);
      return;
    }
    playerRate = rate;
    if (playerAudio) playerAudio.playbackRate = rate;
    const page = $('player');
    [...(page?.querySelectorAll('.player-grid .toolbar .segmented button') || [])].forEach(button => {
      const candidate = Number(String(button.textContent || '').replace('×','').trim());
      button.classList.toggle('active', Number.isFinite(candidate) && Math.abs(candidate-rate) < 0.01);
    });
    if (persist) void call('settings.save', {player_rate:rate})
      .catch(error => message(error?.message || String(error), true));
  }
  function applyPlayerVolume(value, persist = false) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return;
    playerVolume = Math.max(0, Math.min(1, amount / 100));
    if (playerAudio) playerAudio.volume = playerVolume;
    const control = $('player')?.querySelector('.player-grid .toolbar input.range');
    if (control) control.value = String(Math.round(playerVolume * 100));
    if (persist) void call('settings.save', {player_volume:playerVolume})
      .catch(error => message(error?.message || String(error), true));
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
      .filter(chapter => Number.isFinite(Number(chapter.start_seconds)))
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
        applyPlayerRate(rate, true);
      };
    });
    const volumeControl = page.querySelector('.player-grid .toolbar input.range');
    if (volumeControl) {
      volumeControl.oninput = () => applyPlayerVolume(volumeControl.value, false);
      volumeControl.onchange = () => applyPlayerVolume(volumeControl.value, true);
    }
    page.addEventListener('click', event => {
      const chapter = event.target.closest('[data-audiobook-chapter-start]');
      if (!chapter || chapter.getAttribute('aria-disabled') === 'true') return;
      if (!playerAudio || !playerAudio.src) {
        message('Choose Play audiobook on a finished title before selecting a chapter.', true);
        return;
      }
      const start = Number(chapter.dataset.audiobookChapterStart);
      if (Number.isFinite(start) && start >= 0) playerAudio.currentTime = start;
    });
    page.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const chapter = event.target.closest('[data-audiobook-chapter-start]');
      if (!chapter || chapter.getAttribute('aria-disabled') === 'true') return;
      event.preventDefault();
      const start = Number(chapter.dataset.audiobookChapterStart);
      if (playerAudio && playerAudio.src && Number.isFinite(start) && start >= 0) playerAudio.currentTime = start;
    });
    applyPlayerRate(playerRate, false);
    applyPlayerVolume(playerVolume * 100, false);
  }
  async function openPlayer(projectFolder = selectedAudiobookFolder) {
    const folder = String(projectFolder || '').trim();
    if (!folder) throw new Error('Select a finished audiobook from the Audiobooks library before playing.');
    const data = await call('player.get_active', {folder});
    if (playerAudio && playerAudio.src === data.file_url) {
      selectedAudiobookFolder = folder;
      miniPlayerDismissed = false;
      playerRate = Number.isFinite(Number(data.playback_rate)) ? Number(data.playback_rate) : playerRate;
      playerVolume = Number.isFinite(Number(data.playback_volume)) ? Math.max(0,Math.min(1,Number(data.playback_volume))) : playerVolume;
      playerAudio.playbackRate = playerRate;
      playerAudio.volume = playerVolume;
      renderSelectedAudiobook(data);
      if (playerAudio.paused) await playerAudio.play(); else playerAudio.pause();
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
    const audioFolder = folder;
    audio.preload = 'metadata';
    audio.playbackRate = playerRate;
    audio.volume = playerVolume;
    audio.ontimeupdate = () => {
      const duration = audio.duration || 0, current = audio.currentTime || 0;
      if ($('playerTimeline') && duration) $('playerTimeline').value = current / duration * 100;
      if ($('miniProgress') && duration) $('miniProgress').style.width = current / duration * 100 + '%';
      if ($('currentTime')) $('currentTime').textContent = formatTime(current);
      const time = $('miniPlayer')?.querySelector('span.muted');
      if (time) time.textContent = formatTime(current);
      setPlaybackButtonState();
      persistPlayerPosition(false, false, audioFolder, audio);
    };
    audio.onplay = () => { setPlaybackButtonState(); syncMiniPlayer(); };
    audio.onpause = () => {
      persistPlayerPosition(true, false, audioFolder, audio);
      setPlaybackButtonState();
      syncMiniPlayer();
    };
    audio.onended = () => {
      persistPlayerPosition(true, true, audioFolder, audio);
      setPlaybackButtonState();
      syncMiniPlayer();
    };
    audio.onloadedmetadata = () => {
      if (playerAudio !== audio) return;
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
      miniPlayerDismissed = true;
      syncMiniPlayer();
      message('The local audiobook file could not be opened in the embedded player.', true);
    };
    await audio.play();
    miniPlayerDismissed = false;
    renderSelectedAudiobook(data);
    syncMiniPlayer();
    setPlaybackButtonState();
  }
  const formatTime = seconds => {
    const n = Math.max(0, Math.floor(Number(seconds) || 0)), h = Math.floor(n / 3600), m = Math.floor((n % 3600) / 60), sec = n % 60;
    return h ? h + ':' + String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0') : m + ':' + String(sec).padStart(2,'0');
  };
  async function refreshHistory() {
    const rows = await call('history.list');
    const section = $('history');
    const filter = $('historyFilters')?.querySelector('button.active')?.textContent?.trim().toLowerCase() || 'all';
    section?.querySelectorAll('.history-row').forEach(el => el.remove());
    const host = $('historyFilters')?.parentElement;
    const visible = rows.filter(j => {
      const state = String(j.state || '').toLowerCase();
      if (filter === 'completed') return state === 'completed';
      if (filter === 'running') return ['queued','running','pause_requested','paused','retrying'].includes(state);
      if (filter === 'failed') return ['failed','cancelled'].includes(state);
      return true;
    });
    if (host) {
      let empty = host.querySelector('[data-history-empty]');
      if (!visible.length) {
        if (!empty) { empty = document.createElement('p'); empty.dataset.historyEmpty='1'; empty.className='muted'; host.appendChild(empty); }
        empty.textContent = 'No matching backend jobs yet.';
      } else if (empty) empty.remove();
      visible.forEach(j => {
        const row = document.createElement('div');
        row.className = 'history-row'; row.dataset.backendHistory='1';
        const label = String(j.state || 'queued');
        const duration = j.elapsed_seconds ? formatTime(j.elapsed_seconds) : 'Elapsed time unavailable';
        row.innerHTML = '<div><b>' + esc(j.title || j.type || 'Background task') + '</b><br><span class="muted">' +
          esc(j.project_title || 'Local task') + ' · ' + esc(j.stage || j.message || '') + ' · ' + esc(duration) +
          '</span></div><span class="badge ' + (label==='failed'?'red':label==='running'?'info':'') + '">' + esc(label) +
          '</span><span>' + Math.round(Number(j.progress || 0)) + '%</span><button class="btn small secondary" data-history-job="' +
          esc(j.job_id) + '">View</button>';
        host.appendChild(row);
      });
    }
    return rows;
  }
    async function refreshPerformance() {
    let result;
    try {
      result = await call('performance.info');
    } catch (error) {
      result = {available:false, reason:error?.message || 'Live hardware telemetry is unavailable in this build.'};
    }
    const section = $('performance');
    if (!result.available) {
      const metrics = section?.querySelectorAll('.grid.metrics .metric');
      const labels = [
        ['Unavailable', 'CPU telemetry unavailable'],
        ['Unavailable', 'GPU / VRAM telemetry unavailable'],
        ['Not tested', 'Generation performance'],
        ['Unavailable', 'Recommended backend']
      ];
      metrics?.forEach((metric, index) => {
        const strong = metric.querySelector('strong');
        const detail = metric.querySelector('span');
        if (strong && labels[index]) strong.textContent = labels[index][0];
        if (detail && labels[index]) detail.textContent = labels[index][1];
      });
      section?.querySelectorAll('.ready-list .ready b').forEach(node => { node.textContent = 'Not measured'; });
      if ($('benchmarkResult')) $('benchmarkResult').textContent = 'Unavailable';
      const note = $('benchmarkResult')?.parentElement?.querySelector('p.muted');
      if (note) note.textContent = result.reason || 'Live hardware telemetry and benchmark results are not connected in this build.';
    }
    return result;
  }
  async function refreshModels() {
    const rows = await call('models.list');
    const grid = $('modelGrid');
    if (grid) grid.innerHTML = rows.map(m => '<article class="card model-card"><div><span class="badge ' +
      (m.installed ? '' : 'info') + '">' + (m.installed ? 'Installed' : 'Available') + '</span><h3>' + esc(m.name) +
      '</h3><p class="muted">' + esc(m.provider || 'Local model') + ' · ' +
      (m.voice_cloning ? 'Voice cloning capable' : 'Narration / speech') + '</p><p class="muted">' +
      esc(m.notes || (m.multilingual ? 'Multilingual support' : 'Local voice model')) + '</p></div></article>').join('') ||
      '<p class="muted">No model catalogue entries were returned by the local backend.</p>';
    applyUnavailableControlStates();
    const heading = $('models')?.querySelector('.model-runtime h2');
    if (heading) heading.textContent = rows.filter(m => m.installed).length + ' installed · ' + rows.filter(m => !m.installed).length + ' available in catalogue';
    return rows;
  }
  async function loadSettings() {
    const settings = await call('settings.get');
    if ($('themeSelectAdvanced') && settings.theme) $('themeSelectAdvanced').value = settings.theme;
    if ($('effectsModeAdvanced') && settings.effects) $('effectsModeAdvanced').value = settings.effects;
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
    const disable = (element, reason) => {
      if (!element || element.dataset.backendUnavailable === 'true') return;
      element.disabled = true;
      element.setAttribute('aria-disabled', 'true');
      element.dataset.backendUnavailable = 'true';
      element.title = reason;
      const label = (element.getAttribute('aria-label') || element.textContent || element.id || 'Control').trim();
      element.setAttribute('aria-label', label + '. Unavailable: ' + reason);
    };
    const dialogueReason = 'Bulk AI predictions are not verified against source passages in this build. Select an individual source-backed dialogue passage to assign a saved character.';
    document.querySelectorAll('#acceptHighConfidence, #skipAiSuggestion, #aiUseLibrary, #aiCreateNew, #createCharacterQuick, [data-ai-line]:not([data-dialogue-id])')
      .forEach(element => disable(element, dialogueReason));
    document.querySelectorAll('[data-model-update], [data-model-repair], [data-model-uninstall]')
      .forEach(element => disable(element, 'Per-model update, repair, and uninstall are not implemented. No model files will be changed by these controls.'));
    document.querySelectorAll('#settings button').forEach(element => {
      if ((element.textContent || '').trim().toLowerCase() === 'choose folder') {
        disable(element, 'Changing the application storage root is not implemented. Existing project and asset paths remain unchanged.');
      }
    });
    disable($('runBenchmark'), 'Live hardware telemetry and repeatable benchmark execution are not implemented in this build; performance is intentionally marked Not tested.');
  }

  async function wire() {
    await call('app.get_info');

    // The approved HTML prototype attaches a fake timer-based player directly
    // to these buttons. Replace those DOM nodes before attaching real playback,
    // so the demo timer can never masquerade as audiobook audio.
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
      const historyJob = e.target.closest('[data-history-job]');
      if (historyJob) {
        e.preventDefault(); e.stopImmediatePropagation();
        (async()=> {
          const id = historyJob.dataset.historyJob;
          const rows = await call('history.list');
          const job = rows.find(j => String(j.job_id) === String(id));
          if (!job) throw new Error('This history job is no longer available. Refresh History and try again.');
          await refreshJobs();
          $('backgroundJobsButton')?.click();
          message((job.title || job.type || 'Background task') + ' · ' + (job.stage || job.message || job.state) + ' · ' + Math.round(Number(job.progress || 0)) + '%');
        })().catch(err => message(err?.message || String(err), true));
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
      if(studio){e.preventDefault();e.stopImmediatePropagation();const c=libraryCharacters.find(x=>String(x.id)===studio.dataset.characterStudio);if(!c){message('Choose a saved character first.',true);return;}if(!c.source_project_folder){window.ryuPremiumSelectedCharacter=c.name;window.go?.('characters');message('Opened Character Studio. Open a project from this series to assign a voice.');return;}void (async()=>{try{await call('project.open',{folder:c.source_project_folder});await refreshProjects();await refreshChapters();await refreshCharacters();window.ryuPremiumSelectedCharacter=c.name;window.go?.('characters');const castItem=[...document.querySelectorAll('[data-character-name]')].find(node=>node.dataset.characterName===c.name);castItem?.click();message('Opened Character Studio for '+c.name+'. Manage its voice assignment here.');}catch(err){message(err?.message||String(err),true);}})();return;}
      if(test){e.preventDefault();e.stopImmediatePropagation();const c=libraryCharacters.find(x=>String(x.id)===test.dataset.testLibrary);const profile=voices.find(v=>String(v.name).toLowerCase()===String(c?.voice||'').toLowerCase());if(!c||!profile){message('No matching saved voice profile exists for this character. Choose a saved profile in Voice Studio first.',true);return;}call('voice.preview',{profile_name:profile.name,text:'Hello, my name is '+c.name+'.',duration_seconds:10}).then(data=>monitorJob(data.job_id,async job=>{const url=job?.result?.file_url;if(!url)throw new Error('The character preview finished without a playable audio file.');if(previewAudio)previewAudio.pause();previewAudio=new Audio(url);await previewAudio.play();message('Playing character voice preview.');})).catch(err=>message(err?.message||String(err),true));return;}
    }, true);
    document.addEventListener('click', e => {
      const b=e.target.closest('[data-voice]');
      if(b){
        selectedVoiceId=b.dataset.voice;
        selectedVoice=null;
        const label=b.dataset.voice;
        if($('profileVoice'))$('profileVoice').textContent=label;
        if($('premiumName')&&!$('premiumName').value.trim())$('premiumName').value=label+' Custom';
        if($('profileName')&&!$('profileName').value.trim())$('profileName').value=label+' Custom';
        document.querySelectorAll('#voices *').forEach(node => {
          if(node.children.length===0 && node.textContent.trim()==='Saved') node.textContent='Unsaved';
        });
        return;
      }
      const provider = e.target.closest('.provider');
      if(provider && !e.target.closest('button,input,textarea,select,label,[data-voice]')) {
        selectedVoiceId=null; selectedVoice=null;
        const key = provider.dataset.provider;
        const defaultLabels = {offline:'Amy',sapi:'David',customvoice:'Serena',voicedesign:'Custom voice description',qwenclone:'Reference voice',customref:'Reference voice',edge:'Edge neural voice',eleven:'ElevenLabs voice'};
        if($('profileVoice'))$('profileVoice').textContent=defaultLabels[key] || 'Custom voice';
        if($('profileName'))$('profileName').value='';
        if($('premiumName'))$('premiumName').value='';
        document.querySelectorAll('#voices *').forEach(node => {
          if(node.children.length===0 && node.textContent.trim()==='Saved') node.textContent='Unsaved';
        });
      }
    });
    if ($('historyFilters')) $('historyFilters').querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
      $('historyFilters').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===button));
      refreshHistory().catch(e=>message(e.message,true));
    }));
    if ($('history')) $('history').addEventListener('click', e => {
      const b=e.target.closest('[data-history-job]'); if(!b)return;
      const jobId=b.dataset.historyJob;
      call('job.list',{include_hidden:true}).then(rows=>{const j=rows.find(x=>x.job_id===jobId);if(j)message((j.title||j.type)+' — '+(j.state||'unknown')+' · '+(j.stage||j.message||''));}).catch(x=>message(x.message,true));
    });
    if ($('checkModelUpdates')) $('checkModelUpdates').onclick=act(async()=>{await refreshModels();message('Local model catalogue refreshed. This checks the local catalogue; it does not contact an online update service.');});
    if ($('startQwenInstall')) $('startQwenInstall').onclick=act(async()=>{
      const choice=document.querySelector('input[name="qwenInstall"]:checked')?.value||'customvoice';
      const data=await call('models.install',{selection:choice});
      $('qwenInstallModal')?.classList.remove('show');
      await monitorJob(data.job_id,refreshModels);
    });
    document.querySelectorAll('[data-close-qwen]').forEach(b=>b.addEventListener('click',()=>$('qwenInstallModal')?.classList.remove('show')));
    if ($('clearModelQueue')) $('clearModelQueue').onclick=act(async()=>{await call('job.clear_completed');await refreshJobs();await refreshHistory();message('Completed background jobs cleared from the active queue.');});
    if ($('runIntegrityCheck')) $('runIntegrityCheck').onclick=act(runDiagnostics);
    if ($('runBenchmark')) $('runBenchmark').onclick=act(async()=>{
      const result=await refreshPerformance();
      message(result.reason||'Hardware benchmark is not available in this build.',!result.available);
    });
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
    if ($('pronSearchAdvanced')) $('pronSearchAdvanced').oninput=()=>{
      const q=$('pronSearchAdvanced').value.trim().toLowerCase();
      $('pronDictionaryBody')?.querySelectorAll('tr,[data-pron-row]').forEach(el=>el.hidden=!el.textContent.toLowerCase().includes(q));
    };
    if ($('librarySearch')) $('librarySearch').oninput = () => refreshProjects().catch(e=>message(e.message,true));
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
        const opened = await call('project.open', {folder});
        await refreshProjects();
        await refreshChapters();
        await refreshCharacters();
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
      try { const opened = await call('project.open', {folder:button.dataset.openProject}); await refreshProjects(); await refreshChapters(); await refreshCharacters(); if (typeof window.go === 'function') window.go('chapters'); message('Opened local project: ' + (opened.title || opened.folder || 'project')); }
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
    ['saveProfile','saveDraft','addPremium','saveOnly'].forEach(id=>{if($(id))$(id).onclick=act(saveVoice);});
    if ($('useNarrator')) $('useNarrator').onclick=act(async()=>{
      const v=await saveVoice();
      if(!v)return;
      await call('voice.select',{profile_name:v.name});
      await refreshProjects();
      document.querySelectorAll('#voices *').forEach(node => {
        if(node.children.length===0 && node.textContent.trim()==='Narrator unchanged') node.textContent='Assigned to this narrator';
      });
      message('Profile saved and assigned as the active narrator.');
    });
    if ($('generatePreview')) $('generatePreview').onclick=act(previewVoice);
    if ($('previewGenerate')) $('previewGenerate').onclick=act(async()=>{const name=selectedVoice||$('profileName')?.value;const group=[...document.querySelectorAll('#generate .segmented')].find(el=>[...el.querySelectorAll('button')].some(b=>/10s|30s|60s/i.test(b.textContent)));const duration=group?.querySelector('button.active')?.textContent.match(/\d+/)?.[0]||'30';const data=await call('production.preview',{profile_name:name,duration_seconds:Number(duration)});await monitorJob(data.job_id,job=>preparePreviewPlayback(job,Number(duration)));});
    if ($('playPreview')) $('playPreview').onclick=act(async()=>{if(!previewAudio)throw new Error('Generate a preview first.');if(!previewAudio.paused){previewAudio.pause();$('playPreview').textContent='▶ Play';}else{await previewAudio.play();$('playPreview').textContent='Ⅱ Pause';}});
    if ($('stopPreview')) $('stopPreview').onclick=()=>{if(previewAudio){previewAudio.pause();previewAudio.currentTime=0;}if($('playPreview'))$('playPreview').textContent='▶ Play';};
    if ($('startGenerate')) $('startGenerate').onclick=act(async()=>{const data=await call('production.generate_book',{profile_name:selectedVoice||$('profileName')?.value,bitrate:256});await monitorJob(data.job_id);});
    if ($('pauseGenerate')) $('pauseGenerate').onclick=act(async()=>{if(!activeJob)throw new Error('There is no active job to pause.');await call('job.pause',{job_id:activeJob});await refreshJobs();});
    if ($('cancelJob')) $('cancelJob').onclick=act(async()=>{if(!activeJob)throw new Error('There is no active job to cancel.');await call('job.cancel',{job_id:activeJob});await refreshJobs();});
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
    if ($('saveNewPron')) $('saveNewPron').onclick=act(async()=>{await call('pronunciation.save',{written_form:$('newPronWritten')?.value||'',spoken_form:$('newPronValue')?.value||'',language:$('newPronLanguage')?.value||'Auto',scope:$('newPronScope')?.value||'current_book'});await refreshTerms();$('pronEntryModal')?.classList.remove('show');message('Pronunciation entry saved.');});
    if ($('analyzePronunciation')) $('analyzePronunciation').onclick=act(async()=>{const r=await call('pronunciation.analyze');const list=$('pronDictionaryBody');if(list)list.innerHTML=(r.suggestions||[]).map(t=>'<div class="list-item"><b>'+esc(t.written_form)+'</b><span> → '+esc(t.spoken_form)+'</span></div>').join('')||'<p class="muted">No new suggestions found.</p>';message('Found '+(r.suggestions||[]).length+' suggestions to review.');});
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
    if ($('assignCharacter')) $('assignCharacter').onclick=act(async()=>{const name=window.ryuPremiumSelectedCharacter;if(!name)throw new Error('Select a character first.');await call('character.assign',{name,profile_name:selectedVoice||$('profileName')?.value});await refreshCharacters();});
    if ($('editCharacterVoice')) $('editCharacterVoice').onchange=act(async()=>{if(!window.ryuPremiumSelectedCharacter)return;await call('character.assign',{name:window.ryuPremiumSelectedCharacter,profile_name:$('editCharacterVoice').value});await refreshCharacters();});
    // Import buttons are handled once by the delegated Sound Design handler below.
    // Import buttons are handled once by the delegated Sound Design handler below.
    if ($('soundTrackSearch')) $('soundTrackSearch').oninput = () => refreshSounds().catch(e=>message(e.message,true));
    document.querySelectorAll('#cueSourceFilter [data-cue-source]').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('#cueSourceFilter [data-cue-source]').forEach(x => x.classList.toggle('active', x === button)); refreshSoundCues().catch(e => message(e.message, true)); }));
    if ($('soundTrackGrid')) $('soundTrackGrid').addEventListener('click', e=>{const b=e.target.closest('[data-select-sound]');if(!b)return;selectedSoundPath=b.dataset.selectSound;if($('selectedSoundTitle'))$('selectedSoundTitle').textContent=sounds.find(t=>t.path===selectedSoundPath)?.title||'Selected track';if($('selectedSoundMeta'))$('selectedSoundMeta').textContent='Selected from the local catalogue';message('Selected sound track. Save it to the active book to apply it.');});
    // setBookDefaultTrack is handled by the single delegated backend listener.
    // saveSoundPresetAdvanced is handled by the single delegated backend listener.
    ['mainPlay','miniPlay'].forEach(id=>{if($(id))$(id).onclick=act(openPlayer);});
    if ($('playerTimeline')) $('playerTimeline').oninput=()=>{if(playerAudio&&playerAudio.duration)playerAudio.currentTime=Number($('playerTimeline').value)/100*playerAudio.duration;};
    if ($('hideMini')) $('hideMini').onclick=()=>{
      miniPlayerDismissed = true;
      $('miniPlayer')?.classList.add('hidden');
    };
    if ($('saveSettingsAdvanced')) $('saveSettingsAdvanced').onclick=act(async()=>{await call('settings.save',{theme:$('themeSelectAdvanced')?.value||'dark',effects:$('effectsModeAdvanced')?.value||'high'});message('Settings saved to this PC.');});
    document.addEventListener('input', e => {
      if (e.target?.id === 'librarySearch') {
        e.stopImmediatePropagation();
        refreshProjects().catch(err => message(err?.message || String(err), true));
      } else if (e.target?.id === 'soundTrackSearch') {
        e.stopImmediatePropagation();
        refreshSounds().catch(err => message(err?.message || String(err), true));
      } else if (e.target?.id === 'cueSearch') {
        e.stopImmediatePropagation();
        refreshSoundCues().catch(err => message(err?.message || String(err), true));
      }
    }, true);
    document.addEventListener('click', async e => {
      const chapterBgmItem = e.target.closest('#chapterBgmList [data-chapter-bgm]');
      if (chapterBgmItem) {
        e.preventDefault(); e.stopImmediatePropagation();
        selectedBgmChapter = Number(chapterBgmItem.dataset.chapterBgm);
        renderChapterBgm();
        return;
      }
      const chapterStrategy = e.target.closest('#sound [data-bgm-strategy]');
      if (chapterStrategy) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          await call('sound.chapter_bgm.save', {strategy:chapterStrategy.dataset.bgmStrategy});
          await refreshChapterBgm();
          message(chapterBgmState.strategy === 'same' ? 'Same book-wide BGM strategy saved; chapter overrides cleared.' : 'Chapter-based BGM strategy enabled.');
        } catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const chapterRuleButton = e.target.closest('#sound .chapter-rule [data-chapter-rule]');
      if (chapterRuleButton) {
        e.preventDefault(); e.stopImmediatePropagation();
        document.querySelectorAll('#sound .chapter-rule [data-chapter-rule]').forEach(b => b.classList.toggle('active', b === chapterRuleButton));
        return;
      }
      const chapterTrack = e.target.closest('#chapterTrackPicker [data-chapter-track]');
      if (chapterTrack) {
        e.preventDefault(); e.stopImmediatePropagation();
        selectedBgmTrackPath = chapterTrack.dataset.chapterTrack;
        document.querySelectorAll('#chapterTrackPicker [data-chapter-track]').forEach(b => b.classList.toggle('active', b === chapterTrack));
        return;
      }
      if (e.target.closest('#saveChapterBgm')) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          const rule = document.querySelector('#sound .chapter-rule [data-chapter-rule].active')?.dataset.chapterRule || 'default';
          if (rule === 'custom' && !selectedBgmTrackPath) throw new Error('Choose a custom music track for this chapter first.');
          const selects = document.querySelectorAll('#sound [data-sound-view="chapters"] .chapter-mix-row select');
          const startOffset = ['immediate','after_first_paragraph','after_10_seconds'][selects[0]?.selectedIndex || 0];
          const endBehavior = ['fade_before_end','continue_to_transition','stop_immediately'][selects[1]?.selectedIndex || 0];
          await call('sound.chapter_bgm.save', {
            number:selectedBgmChapter, rule, path:rule === 'custom' ? selectedBgmTrackPath : null,
            volume:Number($('chapterVolume')?.value || 18)/100,
            start_offset:startOffset, end_behavior:endBehavior
          });
          await refreshChapterBgm();
          message('Saved BGM assignment for Chapter ' + selectedBgmChapter + '.');
        } catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const recentProject = e.target.closest('#dashboard .recent-grid [data-project-folder]');
      if (recentProject) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          const opened = await call('project.open', {folder:recentProject.dataset.projectFolder});
          await refreshProjects(); await refreshChapters(); await refreshCharacters();
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
            const opened = await call('project.open', {folder:candidate.folder});
            await refreshProjects();
            await refreshChapters();
            await refreshCharacters();
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
        try {
          const path = cueTrack.dataset.cuePath;
          if (pendingCueSlot) {
            const assignedSlot = pendingCueSlot;
            const result = await call('sound.cues.save', {slot:assignedSlot,path});
            pendingCueSlot = null;
            await refreshSoundCues();
            message(result.generation_supported ? (assignedSlot === 'scene' ? 'Scene transition cue saved to this book and will be included during audiobook assembly.' : 'Cue assignment saved to this book.') : 'Cue assignment saved, but this build reports that the selected cue is not used during audiobook assembly.');
          } else {
            selectedSoundPath = path;
            message('Cue clip selected. Choose Change beside a cue slot, then select this clip to assign it.');
          }
        } catch (err) { message(err?.message || String(err), true); }
        return;
      }
      const soundButton = e.target.closest('#importMusicTracks, #importCueClips, #previewSelectedTrack, #setBookDefaultTrack, #saveSoundPresetAdvanced, #applySoundToProduction, #soundPreviewBook, #previewCueSequence, #clearAllCues, #saveChapterBgm');
      if (soundButton) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          if (soundButton.id === 'importMusicTracks' || soundButton.id === 'importCueClips') {
            const result = await call('sound.import', {target_kind: soundButton.id === 'importMusicTracks' ? 'music' : 'cue'});
            await refreshSounds();
            await refreshSoundCues();
            await refreshChapterBgm();
            message('Imported ' + (result.imported || []).length + ' audio asset(s) into the local catalogue.');
          } else if (soundButton.id === 'previewSelectedTrack') {
            const track = sounds.find(item => item.path === selectedSoundPath);
            if (!track) throw new Error('Select a track from the local catalogue first.');
            if (soundPreviewAudio) { soundPreviewAudio.pause(); soundPreviewAudio = null; }
            const normalized = String(track.path).replace(/\\/g, '/');
            const fileUrl = 'file:///' + normalized.split('/').map((part, i) => i === 0 && /^[A-Za-z]:$/.test(part) ? part : encodeURIComponent(part)).join('/');
            soundPreviewAudio = new Audio(fileUrl);
            soundPreviewAudio.onended = () => $('soundWave')?.classList.remove('playing');
            soundPreviewAudio.onerror = () => message('The selected local audio file could not be played in the embedded preview.', true);
            await soundPreviewAudio.play();
            $('soundWave')?.classList.add('playing');
          } else if (soundButton.id === 'setBookDefaultTrack') {
            if (!selectedSoundPath) throw new Error('Select a track from the local sound catalogue first.');
            await call('sound.assign', {path:selectedSoundPath,volume:Number($('advancedMusicVolume')?.value ?? 18)/100,fade_in_seconds:fadeSeconds('bgmFadeIn'),fade_out_seconds:fadeSeconds('bgmFadeOut')});
            await refreshChapterBgm();
            message('Book default background track saved.');
          } else if (soundButton.id === 'saveSoundPresetAdvanced') {
            const result = await call('sound.save_manifest', {path:selectedSoundPath || '',enabled:Boolean(selectedSoundPath),volume:Number($('advancedMusicVolume')?.value ?? 18)/100,fade_in_seconds:fadeSeconds('bgmFadeIn'),fade_out_seconds:fadeSeconds('bgmFadeOut')});
            await refreshChapterBgm();
            message(result.enabled ? 'Book sound manifest saved.' : 'Book sound manifest saved with background music disabled.');
          } else if (soundButton.id === 'applySoundToProduction') {
            await call('sound.save_manifest', {path:selectedSoundPath || '',enabled:Boolean(selectedSoundPath),volume:Number($('advancedMusicVolume')?.value ?? 18)/100,fade_in_seconds:fadeSeconds('bgmFadeIn'),fade_out_seconds:fadeSeconds('bgmFadeOut')});
            await refreshChapterBgm();
            document.querySelector('[data-page="generate"]')?.click();
          } else if (soundButton.id === 'saveChapterBgm') {
            await refreshChapterBgm();
          } else if (soundButton.id === 'clearAllCues') {
            await call('sound.cues.clear');
            pendingCueSlot = null;
            await refreshSoundCues();
            message('All book cue assignments cleared.');
          } else if (soundButton.id === 'previewCueSequence') {
            const sequence = ['opening','chapter','scene','closing'].map(slot => cueAssignments[slot]?.path).filter(Boolean);
            if (!sequence.length) throw new Error('Assign at least one cue before previewing the sequence.');
            if (soundPreviewAudio) { soundPreviewAudio.pause(); soundPreviewAudio = null; }
            let index = 0;
            const playNext = () => {
              if (index >= sequence.length) { soundPreviewAudio = null; return; }
              const raw = sequence[index++];
              const normalized = String(raw).replace(/\\/g, '/');
              const fileUrl = 'file:///' + normalized.split('/').map((part, i) => i === 0 && /^[A-Za-z]:$/.test(part) ? part : encodeURIComponent(part)).join('/');
              soundPreviewAudio = new Audio(fileUrl);
              soundPreviewAudio.onended = playNext;
              soundPreviewAudio.onerror = () => { soundPreviewAudio = null; message('A cue clip could not be played in the embedded preview.', true); };
              soundPreviewAudio.play().catch(err => { soundPreviewAudio = null; message(err?.message || 'Cue sequence playback failed.', true); });
            };
            playNext();
            message('Playing assigned cue clips in book order.');

          } else if (soundButton.id === 'soundPreviewBook') {
            if (soundPreviewAudio) { soundPreviewAudio.pause(); soundPreviewAudio = null; }
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
                soundPreviewAudio = new Audio(fileUrl);
                soundPreviewAudio.onended = () => { soundPreviewAudio = null; };
                soundPreviewAudio.onerror = () => { soundPreviewAudio = null; message('The Sound Design mix preview could not be played.', true); };
                await soundPreviewAudio.play();
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
          const commands = {pause:'job.pause',resume:'job.resume',cancel:'job.cancel'};
          await call(commands[b.dataset.jobAction] || 'job.cancel', {job_id:b.dataset.jobId});
          await refreshJobs();
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
    const previewSavedProfile = async (profile, text, label) => {
      const data = await call('voice.preview', {profile_name:profile.name,text,duration_seconds:10});
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
      if (button.id === 'generateCandidates' || button.id === 'generateMore' || button.id === 'setKey' ||
          label === 'get api key' || label === 'manage credentials') {
        stop();
        const reason = button.id === 'setKey' || label === 'get api key' || label === 'manage credentials'
          ? 'Credential management is not connected to a secure provider-specific credential store in this build. No API key was requested or saved.'
          : 'Premium cloud candidate generation is not connected to a provider endpoint in this build. No mock candidates were generated; choose a supported saved voice profile and use Generate Preview instead.';
        message(reason, true);
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
      if (button.closest('#player')) {
        const audioLabel = label.replace(/\s+/g,'');
        if (['↶15','15↷','0.75×','1×','1.25×','1.5×','◀','▶'].includes(audioLabel)) {
          stop();
          (async () => {
            if (!playerAudio) await openPlayer();
            if (!playerAudio) throw new Error('No audiobook is loaded in the player.');
            if (audioLabel === '↶15') playerAudio.currentTime = Math.max(0, playerAudio.currentTime - 15);
            else if (audioLabel === '15↷') playerAudio.currentTime = Math.min(playerAudio.duration || Infinity, playerAudio.currentTime + 15);
            else if (['0.75×','1×','1.25×','1.5×'].includes(audioLabel)) {
              playerAudio.playbackRate = Number(audioLabel.replace('×',''));
              button.parentElement?.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === button));
              message('Playback speed set to ' + playerAudio.playbackRate + '×.');
            } else if (audioLabel === '◀') playerAudio.currentTime = Math.max(0, playerAudio.currentTime - 15);
            else {
              if (playerAudio.paused) await playerAudio.play(); else playerAudio.pause();
            }
          })().catch(err => message(err?.message || String(err), true));
          return;
        }
      }
      if (button.id === 'backgroundJobsButton') {
        stop();
        $('backgroundJobsModal')?.classList.add('show');
        refreshJobs().catch(err => message(err?.message || String(err), true));
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
      if (['generatePreview','playPreview','stopPreview','useNarrator','assignCharacter','startGenerate','pauseGenerate','cancelJob','previewGenerate','saveProfile','saveDraft','addPremium','saveOnly'].includes(button.id) && typeof button.onclick === 'function') {
        stop();
        Promise.resolve(button.onclick()).catch(err => message(err?.message || String(err), true));
        return;
      }
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
        selectedVoice = profile.name; selectedVoiceId = profile.voice_id;
        if ($('profileName')) $('profileName').value = profile.name;
        if ($('profileLibrary')) $('profileLibrary').textContent = profile.provider;
        if ($('profileVoice')) $('profileVoice').textContent = profile.voice_id;
        if ($('previewProfile')) $('previewProfile').textContent = profile.name;
        if ($('useNarrator')) $('useNarrator').disabled = false;
        if ($('saveOnly')) $('saveOnly').disabled = false;
        const providerPanel = {
          piper:'offline', kokoro:'offline', 'windows-sapi':'sapi',
          'qwen-character':profile.qwen_mode === 'design' ? 'voicedesign' : /clone/i.test(profile.qwen_mode || '') ? 'qwenclone' : 'customvoice',
          chatterbox:'customref', 'edge-tts':'edge', elevenlabs:'eleven'
        }[profile.provider];
        document.querySelectorAll('.provider').forEach(panel => panel.classList.toggle('active', panel.dataset.provider === providerPanel));
        const designPanel = document.querySelector('.provider[data-provider="voicedesign"]');
        if (designPanel) {
          const prompt = designPanel.querySelector('textarea');
          const language = designPanel.querySelector('select');
          const seed = designPanel.querySelector('input[type="number"]');
          if (prompt && profile.qwen_prompt != null) prompt.value = profile.qwen_prompt;
          if (language && profile.language) language.value = profile.language;
          if (seed) seed.value = profile.qwen_seed ?? '';
        }
        const clonePanel = document.querySelector('.provider[data-provider="qwenclone"]');
        if (clonePanel) {
          const transcript = clonePanel.querySelector('textarea');
          if (transcript && profile.reference_text) transcript.value = profile.reference_text;
        }
        message('Loaded saved voice profile: ' + profile.name + '. Its saved settings are selected; preview audio is a separate action.');
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
          const result = await call('chapter.dialogue.assign', {
            dialogue_text:dialogueText, speakers:[selected], chapter_number:window.ryuPremiumPendingDialogueChapter
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
      if (button.id === 'acceptHighConfidence' || button.id === 'skipAiSuggestion' ||
          button.matches('[data-ai-line]') || button.id === 'aiUseLibrary' ||
          button.id === 'aiCreateNew' || button.id === 'createCharacterQuick') {
        stop();
        message('Bulk acceptance and queue predictions are not connected to verified source passages. Select an individual dialogue passage and explicitly assign a saved character instead.', true);
        return;
      }
      if (button.closest('#settings') && label === 'choose folder') {
        stop();
        message('Custom project-library and audio-assets root selection is not implemented in this build; the existing local storage paths were not changed.', true);
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
      if (button.matches('[data-model-update], [data-model-repair], [data-model-verify], [data-model-uninstall]')) {
        void run(async () => {
          const action = button.hasAttribute('data-model-update') ? 'update' :
            button.hasAttribute('data-model-repair') ? 'repair' :
            button.hasAttribute('data-model-verify') ? 'verify' : 'uninstall';
          const id = button.getAttribute('data-model-update') || button.getAttribute('data-model-repair') ||
            button.getAttribute('data-model-verify') || button.getAttribute('data-model-uninstall') || '';
          if (action === 'verify') {
            const result = await call('models.verify', {model_id:id});
            await refreshModels();
            message((result.available ? 'Model verification passed. ' : 'Model verification found missing files. ') +
              result.detail + ' Checked: ' + result.models.map(model => model.model_id).join(', '),
              !result.available);
            return;
          }
          throw new Error('Per-model ' + action + ' is not connected to a backend operation for "' + id + '". No model state was changed.');
        });
        return;
      }
      if (button.matches('[data-assign-character]')) {
        void run(async () => {
          const dialogueText = String(window.ryuPremiumPendingDialogueText || '').trim();
          const selected = button.dataset.assignCharacter || button.dataset.character || '';
          if (!dialogueText || !selected) throw new Error('Select an individual source dialogue passage and choose a saved character before assigning a speaker.');
          const result = await call('chapter.dialogue.assign', {
            dialogue_text:dialogueText, speakers:[selected], chapter_number:window.ryuPremiumPendingDialogueChapter
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

    const hydrateInitialState = async () => {
      const phases = [
        [refreshProjects, refreshVoices, refreshChapters, loadSettings],
        [refreshCharacters, refreshCharacterLibrary, refreshTerms],
        [refreshSounds, refreshSoundCues, refreshChapterBgm],
        [refreshJobs, refreshHistory, refreshModels]
      ];
      for (const phase of phases) {
        for (const refresh of phase) {
          try { await refresh(); } catch (error) { console.warn('[Ryu hydration]', error); }
          await new Promise(resolve => setTimeout(resolve, 0));
        }
      }
    };
    void hydrateInitialState();
    applyUnavailableControlStates();

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
    message('Premium V2 local backend connected.');
  }
  const start = () => wire().catch(e=>message(e.message,true));
  if (window.ryuBackend?.invoke) start(); else window.addEventListener('ryu-backend-ready', start, {once:true});
})();