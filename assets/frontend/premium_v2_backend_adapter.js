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
  let selectedVoice = null, selectedVoiceId = null, activeJob = null, poll = null, previewAudio = null, playerAudio = null, soundPreviewAudio = null, cueSearchUnavailableNotified = false, chapterSaveTimer = null, chapterSavePromise = Promise.resolve();
  let chapters = [], characters = [], voices = [], terms = [], projects = [], sounds = [], selectedSoundPath = null, pendingCueSlot = null, cueAssignments = {}, chapterBgmState = {strategy:'same',overrides:{}}, selectedBgmChapter = null, selectedBgmTrackPath = null;
  let libraryCharacters = [], libraryEditorId = null, libraryEditorActive = false;
  const selectedChapter = () => chapters.find(c => c.number === window.ryuPremiumSelectedChapter) || chapters[0];
  const renderSelect = (select, rows, value, label) => {
    if (!select) return;
    const previous = select.value;
    select.innerHTML = rows.map(r => '<option value="' + esc(r[value]) + '">' + esc(label(r)) + '</option>').join('');
    if (rows.some(r => String(r[value]) === previous)) select.value = previous;
  };
  async function refreshProjects() {
    projects = await call('project.list');
    const grid = $('libraryGrid');
    const search = ($('librarySearch')?.value || '').trim().toLowerCase();
    const filter = $('libraryFilters')?.querySelector('button.active')?.textContent?.trim().toLowerCase() || 'all';
    const visible = projects.filter(p => {
      const complete = Boolean(p.completed), status = String(p.status || '').toLowerCase();
      const matchesFilter = filter === 'all' || (filter === 'completed' && complete) ||
        (filter === 'active' && !complete && !['failed','error','attention'].includes(status)) ||
        (filter === 'attention' && (['failed','error','attention'].includes(status) || !Number(p.chapter_count || 0)));
      return matchesFilter && (!search || (p.title + ' ' + (p.source_path || '') + ' ' + status).toLowerCase().includes(search));
    });
    if (grid) grid.innerHTML = visible.map(p => {
      const complete = Boolean(p.completed);
      const status = complete ? 'Completed' : (p.status || 'New');
      return '<article class="card project-card" data-name="' + esc(p.title) + '" data-project-folder="' + esc(p.folder) + '"><div class="book-cover"></div><div class="project-pad"><span class="badge ' + (complete ? '' : 'info') + '">' + esc(status) + '</span><h3>' + esc(p.title) + '</h3><p class="muted">' + Number(p.chapter_count || 0) + ' chapters · Local project</p><p class="muted">' + esc(p.source_path || 'Source path unavailable') + '</p><button class="btn small" type="button" data-open-project="' + esc(p.folder) + '">Open project</button></div></article>';
    }).join('') || '<p class="muted">No local projects found. Import a book to start your library.</p>';
    const dash = $('dashboard');
    if (dash) {
      const metrics = dash.querySelectorAll('.metrics .metric strong');
      const completed = projects.filter(p => p.completed).length;
      const active = projects.filter(p => !p.completed && !['failed','error','attention'].includes(String(p.status || '').toLowerCase())).length;
      const attention = projects.filter(p => ['failed','error','attention'].includes(String(p.status || '').toLowerCase()) || !Number(p.chapter_count || 0)).length;
      [projects.length, completed, active, attention].forEach((value, index) => { if (metrics[index]) metrics[index].textContent = value; });
      const recent = dash.querySelector('.recent-grid');
      if (recent) recent.innerHTML = projects.slice(0, 3).map(p => {
        const status = String(p.status || 'new').toLowerCase();
        const badge = p.completed ? 'Completed' : (['failed','error','attention'].includes(status) || !Number(p.chapter_count || 0) ? 'Attention' : 'Active');
        const badgeClass = badge === 'Completed' ? '' : (badge === 'Attention' ? 'warn' : 'info');
        return '<article class="card project-card" data-project-folder="' + esc(p.folder) + '"><div class="book-cover"></div><div class="project-pad"><span class="badge ' + badgeClass + '">● ' + badge + '</span><h3>' + esc(p.title) + '</h3><p class="muted">' + Number(p.chapter_count || 0) + ' chapters · ' + esc(p.status || 'Local project') + '</p></div></article>';
      }).join('') || '<p class="muted">No local projects yet. Import a book to see it here.</p>';
    }
    $('libraryFilters')?.querySelectorAll('button').forEach(button => {
      if (!button.dataset.backendFilterBound) {
        button.dataset.backendFilterBound = '1';
        button.addEventListener('click', () => setTimeout(() => refreshProjects().catch(e=>message(e.message,true)), 0));
      }
    });
    return projects;
  }
  async function refreshVoices() {
    voices = await call('voice.list');
    const rows = voices.map(v => ({...v, label: v.name + ' · ' + v.provider}));
    renderSelect($('editCharacterVoice'), [{name:'',label:'Unassigned'}, ...rows], 'name', v => v.label || 'Unassigned');
    renderSelect($('pronQuickVoice'), rows, 'name', v => v.label);
    if ($('profileName') && !$('profileName').value.trim() && voices[0]) $('profileName').value = voices[0].name;
    return voices;
  }
  async function refreshChapters() {
    chapters = await call('chapter.list'); window.ryuPremiumChapters = chapters;
    if (!chapters.length) return;
    if (!chapters.some(c => c.number === window.ryuPremiumSelectedChapter)) window.ryuPremiumSelectedChapter = chapters[0].number;
    const current = selectedChapter(), list = $('chapterList'), editor = $('chapterEditor'), title = $('chapterTitle');
    if (list) {
      list.innerHTML = chapters.map(c => '<div class="list-item ' + (c.number === current.number ? 'active' : '') + '" data-chapter-number="' + c.number + '">' + esc('Chapter ' + c.number + ' · ' + c.title) + '</div>').join('');
      list.querySelectorAll('[data-chapter-number]').forEach(el => el.addEventListener('click', () => {
        const c = chapters.find(x => x.number === Number(el.dataset.chapterNumber)); if (!c) return;
        window.ryuPremiumSelectedChapter = c.number;
        if (title) title.textContent = c.title; if (editor) editor.value = c.text;
        if ($('wordCount')) $('wordCount').textContent = c.word_count;
        list.querySelectorAll('.list-item').forEach(x => x.classList.toggle('active', x === el));
      }));
    }
    if (title) title.textContent = current.title;
    if (editor && document.activeElement !== editor) editor.value = current.text;
    if ($('wordCount')) $('wordCount').textContent = current.word_count;
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
  const librarySeriesName = c => { const raw = String(c?.series || c?.scope || '').trim(); return /^Series\s*[·:-]\s*Slime$/i.test(raw) ? 'Slime series' : raw; };
  async function refreshCharacterLibrary() {
    libraryCharacters = await call('character_library.list');
    const grid = $('characterLibraryGrid'), query = ($('characterLibrarySearch')?.value || '').trim().toLowerCase(), series = $('characterSeriesFilter')?.value || 'All series';
    const rows = libraryCharacters.filter(c => (!query || [c.name,c.short,c.voice,c.series,c.scope,...(c.aliases||[])].join(' ').toLowerCase().includes(query)) && (series === 'All series' || librarySeriesName(c) === series || c.scope === series));
    if (grid) grid.innerHTML = rows.map(c => '<article class="library-character-card" data-library-id="'+esc(c.id)+'"><div class="library-character-top"><span class="avatar">'+esc((c.short||c.name||'?').slice(0,1))+'</span><div><h3>'+esc(c.name)+'</h3><p>'+esc(librarySeriesName(c)||'Global')+' · '+esc(c.voice||'Unassigned')+'</p></div></div><div class="alias-row">'+((c.aliases||[]).map(x=>'<span class="alias-tag">'+esc(x)+'</span>').join('')||'<span class="alias-tag">No aliases</span>')+'</div><div class="library-character-meta"><span>'+Number(c.lines||0)+' assigned lines</span><span>'+Number(c.chapters||0)+' chapters</span><span>'+Number(c.confidence??100)+'% confidence</span><span>'+esc(c.scope||'Global character library')+'</span></div><div class="library-character-actions"><button class="btn small secondary" data-test-library="'+esc(c.id)+'">▶ Test</button><button class="btn small secondary" data-edit-library="'+esc(c.id)+'">Edit</button><button class="btn small ghost library-delete" data-delete-library="'+esc(c.id)+'">Delete</button></div></article>').join('') || '<div class="card"><b>No characters found</b><p class="muted">Import a cast or add a character to begin your reusable library.</p></div>';
    return libraryCharacters;
  }
  function openLibraryEditor(c) {
    libraryEditorActive = true; libraryEditorId = c?.id || null;
    if ($('characterEditorTitle')) $('characterEditorTitle').textContent = c ? 'Edit character' : 'Add new character';
    if ($('editCharacterName')) $('editCharacterName').value = c?.name || ''; if ($('editCharacterShort')) $('editCharacterShort').value = c?.short || '';
    if ($('editCharacterAliases')) $('editCharacterAliases').value = (c?.aliases||[]).join(', '); if ($('editCharacterVoice')) $('editCharacterVoice').value = c?.voice || (voices[0]?.name || 'Unassigned');
    if ($('editCharacterScope')) $('editCharacterScope').value = c?.scope || 'Series · Slime'; if ($('editCharacterNotes')) $('editCharacterNotes').value = c?.notes || '';
    if ($('deleteCharacter')) $('deleteCharacter').style.visibility = c ? 'visible' : 'hidden'; $('characterEditorModal')?.classList.add('show');
  }
  async function saveLibraryEditor() {
    const name = $('editCharacterName')?.value.trim() || ''; if (!name) throw new Error('Enter a character name before saving it to the Character Library.');
    const scope = $('editCharacterScope')?.value || 'Global character library';
    const series = /^Series\s*[·:-]\s*Slime$/i.test(scope) ? 'Slime series' : scope;
    const result = await call('character_library.save', {id:libraryEditorId||'',name,short:$('editCharacterShort')?.value||'',aliases:$('editCharacterAliases')?.value||'',voice:$('editCharacterVoice')?.value||'Unassigned',scope,series,notes:$('editCharacterNotes')?.value||''});
    libraryEditorId = result.character.id; libraryEditorActive = false; $('characterEditorModal')?.classList.remove('show'); await refreshCharacterLibrary(); message('Character saved to the reusable local Character Library.');
  }
  function importCharacterLibraryFile() {
    const picker=document.createElement('input'); picker.type='file'; picker.accept='.json,application/json';
    picker.onchange=async()=>{const file=picker.files?.[0];if(!file)return;if(file.size>10*1024*1024){message('Character Library imports are limited to 10 MB.',true);return;}try{const data=JSON.parse(await file.text()), rows=Array.isArray(data)?data:data?.characters;if(!Array.isArray(rows))throw new Error('JSON must be an array or contain a characters array.');const result=await call('character_library.import',{characters:rows});await refreshCharacterLibrary();message('Imported '+result.imported+' character(s) into the local Character Library.');}catch(error){message(error?.message||String(error),true);}}; picker.click();
  }
  async function refreshTerms() {
    terms = await call('pronunciation.list');
    const list = $('pronDictionaryBody');
    if (list) list.innerHTML = terms.map(t => '<div class="list-item"><b>' + esc(t.written_form || t.word) + '</b><span> → ' + esc(t.spoken_form || t.pronunciation) + '</span></div>').join('') || '<p class="muted">No saved pronunciation rules for this book.</p>';
    const termList = $('pronTermList');
    if (termList) {
      const selected = $('pronWord')?.textContent?.trim();
      termList.innerHTML = terms.map(t => {
        const word = String(t.written_form || t.word || '');
        const spoken = String(t.spoken_form || t.pronunciation || '');
        return '<button type="button" class="list-item ' + (word === selected ? 'active' : '') + '" data-pron-term="' + esc(word) + '"><b>' + esc(word) + '</b><span>' + esc(spoken) + '</span></button>';
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
    renderChapterBgm();
    return chapterBgmState;
  }
  let backendJobFilter = 'active';
  async function refreshJobs() {
    const allJobs = await call('job.list', {include_hidden:false});
    const jobs = allJobs.filter(j => backendJobFilter === 'all' ||
      (backendJobFilter === 'completed' ? j.state === 'completed' :
      (backendJobFilter === 'failed' ? j.state === 'failed' :
      !['completed','failed','cancelled'].includes(j.state))));
    const box = $('backgroundJobsList');
    if (box) {
      box.innerHTML = jobs.map(j => {
        const id = esc(j.job_id || ''), state = String(j.state || 'unknown');
        const action = (name,label,cls) => '<button class="btn small ' + cls + '" data-job-action="' + name + '" data-job-id="' + id + '">' + label + '</button>';
        const canControlGeneration = j.type === 'audiobook-generation';
        const actions = (canControlGeneration && ['running','pause_requested'].includes(state) ? action('pause','Pause','secondary') : '') +
          (canControlGeneration && ['paused','pause_requested'].includes(state) ? action('resume','Resume','') : '') +
          ((state === 'queued' || (canControlGeneration && ['running','paused','pause_requested','cancel_requested'].includes(state))) ? action('cancel','Cancel','ghost') : '') +
          (state === 'failed' && j.recoverable ? '<small>Retry by restarting this operation from its screen.</small>' : '') +
          (['running','pause_requested'].includes(state) && !canControlGeneration ? '<small>Cancellation and pause are not supported for this operation.</small>' : '');
        return '<article class="job-row" data-backend-job="' + id + '"><b>' + esc(j.title || j.type || id) + '</b><p>' + esc(j.stage || j.message || state) + '</p><div class="progress"><i style="width:' + Math.max(0,Math.min(100,Number(j.progress || 0))) + '%"></i></div><small>' + esc(state) + ' · ' + Math.round(Number(j.progress || 0)) + '%</small>' + (j.message ? '<p>' + esc(j.message) + '</p>' : '') + (j.error?.message ? '<p class="muted">' + esc(j.error.message) + '</p>' : '') + '<div class="toolbar">' + actions + '</div></article>';
      }).join('') || '<p class="muted" data-backend-empty="1">No backend jobs in this view.</p>';
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
          if (job.state === 'completed' && done) await done(job);
          message(job.message || ((job.title || 'Job') + ' ' + job.state), job.state !== 'completed');
          if (job.state === 'completed') { await refreshChapters().catch(()=>{}); await refreshCharacters().catch(()=>{}); }
        }
      } catch (e) { console.error(e); }
    };
    await tick(); poll = setInterval(tick, 1000);
  }
  async function saveVoice() {
    const name = ($('profileName')?.value || $('premiumName')?.value || '').trim();
    if (!name) throw new Error('Enter a name for this voice profile.');
    const choice = document.querySelector('.provider.active')?.dataset.provider || 'offline';
    const providerMap = {offline:'piper',sapi:'windows-sapi',customvoice:'qwen-character',voicedesign:'qwen-character',qwenclone:'qwen-character',customref:'chatterbox',edge:'edge-tts',eleven:'elevenlabs'};
    const provider = providerMap[choice] || (choice.includes('clone') ? 'qwen-character' : 'piper');
    const authorized = Boolean($('clonePermission')?.checked || $('customPermission')?.checked);
    let sample_path = '';
    if (provider === 'chatterbox' || (provider === 'qwen-character' && /clone/i.test(choice))) {
      if (!authorized) throw new Error('Confirm you have permission to use this reference recording.');
      const imported = await call('voice.import_reference', {profile_name:name});
      if (imported.cancelled) return;
      sample_path = imported.sample_path || imported.path || '';
    }
    const voiceLabel = $('profileVoice')?.textContent?.trim() || 'Amy';
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
    selectedVoice = result.name; await refreshVoices();
    if ($('profileName')) $('profileName').value = result.name;
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
    if (!url) { if ($('validation')) $('validation').textContent = 'Preview completed, but the backend did not return a playable local file URL.'; return; }
    if (previewAudio) { previewAudio.pause(); previewAudio = null; }
    previewAudio = new Audio(url);
    previewAudio.preload = 'auto';
    previewAudio.onended = () => { if ($('playPreview')) $('playPreview').textContent = '▶ Play'; };
    previewAudio.onerror = () => { if ($('validation')) $('validation').textContent = 'The preview file exists but the embedded player could not open it. Use the preview output path from job details.'; };
    if ($('playPreview')) $('playPreview').disabled = false;
    const actual = Number(job.result.actual_duration_seconds || 0);
    const requested = Number(requestedSeconds || job.result.requested_duration_seconds || 0);
    if ($('validation')) {
      $('validation').textContent = requested > 0 && actual + 1.5 < requested
        ? 'Preview shorter than requested · ' + actual.toFixed(1) + 's of ' + requested.toFixed(0) + 's. The source text or voice provider produced less audio than requested; try a longer passage and check the selected voice.'
        : 'Preview ready · ' + actual.toFixed(1) + ' seconds' + (requested > 0 ? ' (requested ' + requested.toFixed(0) + 's)' : '');
    }
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
    if ($('previewState')) $('previewState').textContent = 'Generating';
    if ($('validation')) $('validation').textContent = 'Preview job ' + data.job_id + ' is running locally.';
    await monitorJob(data.job_id, async job => { if ($('previewState')) $('previewState').textContent = 'Ready'; preparePreviewPlayback(job, Number(duration)); });
  }
  async function openPlayer() {
    const data = await call('player.get_active');
    if (playerAudio && playerAudio.src === data.file_url) { if (playerAudio.paused) await playerAudio.play(); else playerAudio.pause(); return; }
    if (playerAudio) playerAudio.pause();
    playerAudio = new Audio(data.file_url);
    playerAudio.preload = 'metadata';
    playerAudio.ontimeupdate = () => {
      const duration = playerAudio.duration || 0, current = playerAudio.currentTime || 0;
      if ($('playerTimeline') && duration) $('playerTimeline').value = current / duration * 100;
      if ($('miniProgress') && duration) $('miniProgress').style.width = current / duration * 100 + '%';
      if ($('currentTime')) $('currentTime').textContent = formatTime(current);
      const main = $('mainPlay'), mini = $('miniPlay');
      if (main) main.textContent = playerAudio.paused ? '▶' : 'Ⅱ';
      if (mini) mini.textContent = playerAudio.paused ? '▶' : 'Ⅱ';
    };
    playerAudio.onloadedmetadata = () => {
      const headings = $('player')?.querySelectorAll('h2') || [];
      if (headings[0]) headings[0].textContent = data.title;
      if (headings[1]) headings[1].textContent = data.chapters?.[0]?.title || 'Audiobook ready';
      const mini = $('miniPlayer'); if (mini) mini.querySelector('b').textContent = data.title;
    };
    playerAudio.onerror = () => message('The local audiobook file could not be opened in the embedded player.', true);
    await playerAudio.play();
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
  async function wire() {
    await call('app.get_info');
    await refreshProjects().catch(()=>{}); await refreshVoices().catch(()=>{}); await refreshChapters().catch(()=>{});
    await refreshCharacters().catch(()=>{}); await refreshCharacterLibrary().catch(()=>{}); await refreshTerms().catch(()=>{}); await refreshSounds().catch(()=>{}); await refreshSoundCues().catch(()=>{}); await refreshChapterBgm().catch(()=>{}); await refreshJobs().catch(()=>{}); await refreshHistory().catch(()=>{}); await refreshModels().catch(()=>{}); await refreshPerformance().catch(()=>{}); await loadSettings().catch(()=>{});
    document.addEventListener('click', e => {
      const button = e.target.closest('button');
      const buttonLabel = button?.textContent?.trim().toLowerCase() || '';
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
      const add=e.target.closest('#addLibraryCharacter'), imp=e.target.closest('#importCharacterLibrary'), edit=e.target.closest('[data-edit-library]'), remove=e.target.closest('[data-delete-library]'), test=e.target.closest('[data-test-library]'), save=e.target.closest('#saveCharacterProfile'), del=e.target.closest('#deleteCharacter');
      if(add){e.preventDefault();e.stopImmediatePropagation();openLibraryEditor(null);return;}
      if(imp){e.preventDefault();e.stopImmediatePropagation();importCharacterLibraryFile();return;}
      if(edit){e.preventDefault();e.stopImmediatePropagation();openLibraryEditor(libraryCharacters.find(c=>String(c.id)===edit.dataset.editLibrary));return;}
      if(remove){e.preventDefault();e.stopImmediatePropagation();const c=libraryCharacters.find(x=>String(x.id)===remove.dataset.deleteLibrary);if(!c||!window.confirm('Delete '+c.name+' from the reusable Character Library?'))return;call('character_library.delete',{id:c.id}).then(refreshCharacterLibrary).then(()=>message('Character removed from the reusable library.')).catch(err=>message(err?.message||String(err),true));return;}
      if(save&&libraryEditorActive){e.preventDefault();e.stopImmediatePropagation();saveLibraryEditor().catch(err=>message(err?.message||String(err),true));return;}
      if(del&&libraryEditorActive){e.preventDefault();e.stopImmediatePropagation();if(!libraryEditorId){libraryEditorActive=false;$('characterEditorModal')?.classList.remove('show');return;}const c=libraryCharacters.find(x=>String(x.id)===String(libraryEditorId));if(!c||!window.confirm('Delete '+c.name+' from the reusable Character Library?'))return;call('character_library.delete',{id:libraryEditorId}).then(()=>{libraryEditorActive=false;$('characterEditorModal')?.classList.remove('show');return refreshCharacterLibrary();}).then(()=>message('Character removed from the reusable library.')).catch(err=>message(err?.message||String(err),true));return;}
      if(e.target.closest('#characterLibrarySearch, #characterSeriesFilter'))setTimeout(()=>refreshCharacterLibrary().catch(err=>message(err?.message||String(err),true)),0);
      if(test){e.preventDefault();e.stopImmediatePropagation();const c=libraryCharacters.find(x=>String(x.id)===test.dataset.testLibrary);const profile=voices.find(v=>String(v.name).toLowerCase()===String(c?.voice||'').toLowerCase());if(!c||!profile){message('No matching saved voice profile exists for this character. Choose a saved profile in Voice Studio first.',true);return;}call('voice.preview',{profile_name:profile.name,text:'Hello, my name is '+c.name+'.',duration_seconds:10}).then(data=>monitorJob(data.job_id,async job=>{const url=job?.result?.file_url;if(!url)throw new Error('The character preview finished without a playable audio file.');if(previewAudio)previewAudio.pause();previewAudio=new Audio(url);await previewAudio.play();message('Playing character voice preview.');})).catch(err=>message(err?.message||String(err),true));return;}
    }, true);
    document.addEventListener('click', e => { const b=e.target.closest('[data-voice]'); if(b){selectedVoiceId=b.dataset.voice;const label=b.dataset.voice;if($('profileVoice'))$('profileVoice').textContent=label;if($('premiumName')&&!$('premiumName').value.trim())$('premiumName').value=label+' Custom';if($('profileName')&&!$('profileName').value.trim())$('profileName').value=label+' Custom';return;}if(e.target.closest('.provider'))selectedVoiceId=null; });
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
    if ($('libraryGrid')) $('libraryGrid').addEventListener('click', async e => {
      const button = e.target.closest('[data-open-project]'); if (!button) return;
      button.disabled = true;
      try { const opened = await call('project.open', {folder:button.dataset.openProject}); await refreshProjects(); await refreshChapters(); await refreshCharacters(); if (typeof window.go === 'function') window.go('chapters'); message('Opened local project: ' + (opened.title || opened.folder || 'project')); }
      catch (err) { message(err?.message || String(err), true); }
      finally { button.disabled = false; }
    });
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
    const persistChapterSnapshot = async (number, title, text, automatic = false) => {
      const state = $('saveState');
      if (state) state.textContent = automatic ? 'Saving…' : 'Saving changes…';
      const result = await call('chapter.update', {number, title, text});
      const chapter = chapters.find(item => item.number === number);
      if (chapter) { chapter.text = text; chapter.title = result.title || title; chapter.word_count = result.word_count; }
      if (window.ryuPremiumSelectedChapter === number && state) state.textContent = automatic ? 'Autosaved just now' : 'Saved just now';
      return result;
    };
    if ($('chapterEditor')) $('chapterEditor').addEventListener('input', () => {
      const c = selectedChapter(); if (!c) return;
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
    if ($('cleanText')) $('cleanText').onclick = act(async()=>{const c=selectedChapter();if(!c)throw new Error('Import or open a book first.');const text=$('chapterEditor')?.value||'';$('chapterEditor').value=text.replace(/[ \\t]+\\n/g,'\\n').replace(/\\n{3,}/g,'\\n\\n').trim();$('chapterEditor').dispatchEvent(new Event('input',{bubbles:true}));message('Text cleaned. Changes will autosave shortly.');});
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
    if ($('useNarrator')) $('useNarrator').onclick=act(async()=>{const v=await saveVoice();if(v)await call('voice.select',{profile_name:v.name});message('Saved and selected narrator.');});
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
    if ($('savePronTerm')) $('savePronTerm').onclick=act(async()=>{await call('pronunciation.save',{written_form:$('pronWord')?.textContent?.trim()||'',spoken_form:$('pronValue')?.value||'',scope:$('pronScope')?.value||'current_book',handling_mode:$('pronHandling')?.value||'automatic'});await refreshTerms();message('Pronunciation rule saved locally.');});
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
    if ($('importMusicTracks')) $('importMusicTracks').onclick = act(async()=>{const r=await call('sound.import');await refreshSounds();message('Imported '+(r.imported||[]).length+' sound file(s) into the local Audio Library.');});
    if ($('importCueClips')) $('importCueClips').onclick = act(async()=>{const r=await call('sound.import');await refreshSounds();message('Imported '+(r.imported||[]).length+' sound clip(s) into the local Audio Library.');});
    if ($('soundTrackSearch')) $('soundTrackSearch').oninput = () => refreshSounds().catch(e=>message(e.message,true));
    document.querySelectorAll('#cueSourceFilter [data-cue-source]').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('#cueSourceFilter [data-cue-source]').forEach(x => x.classList.toggle('active', x === button)); refreshSoundCues().catch(e => message(e.message, true)); }));
    if ($('soundTrackGrid')) $('soundTrackGrid').addEventListener('click', e=>{const b=e.target.closest('[data-select-sound]');if(!b)return;selectedSoundPath=b.dataset.selectSound;if($('selectedSoundTitle'))$('selectedSoundTitle').textContent=sounds.find(t=>t.path===selectedSoundPath)?.title||'Selected track';if($('selectedSoundMeta'))$('selectedSoundMeta').textContent='Selected from the local catalogue';message('Selected sound track. Save it to the active book to apply it.');});
    if ($('setBookDefaultTrack')) $('setBookDefaultTrack').onclick = act(async()=>{if(!selectedSoundPath)throw new Error('Select a track from the local sound catalogue first.');await call('sound.assign',{path:selectedSoundPath,volume:Number($('advancedMusicVolume')?.value||18)/100});await refreshChapterBgm();message('Background track assigned to the active book.');});
    if ($('saveSoundPresetAdvanced')) $('saveSoundPresetAdvanced').onclick = act(async()=>{await call('sound.save_manifest',{path:selectedSoundPath||'',enabled:Boolean(selectedSoundPath),volume:Number($('advancedMusicVolume')?.value||18)/100});await refreshChapterBgm();message('Sound manifest saved to the active book.');});
    ['mainPlay','miniPlay'].forEach(id=>{if($(id))$(id).onclick=act(openPlayer);});
    if ($('playerTimeline')) $('playerTimeline').oninput=()=>{if(playerAudio&&playerAudio.duration)playerAudio.currentTime=Number($('playerTimeline').value)/100*playerAudio.duration;};
    if ($('hideMini')) $('hideMini').onclick=()=> $('miniPlayer')?.classList.add('hidden');
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
          await refreshProjects(); await refreshChapters();
          if (typeof window.go === 'function') window.go('chapters');
          message('Opened local project: ' + (opened.title || 'project'));
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
        if (label === 'continue project') {
          e.preventDefault(); e.stopImmediatePropagation();
          try {
            const activeProject = await call('project.get_active');
            const candidate = activeProject || projects.find(p => !p.completed && Number(p.chapter_count || 0) > 0) || projects[0];
            if (!candidate) throw new Error('Import a book before continuing a project.');
            const opened = await call('project.open', {folder:candidate.folder});
            await refreshProjects(); await refreshChapters();
            if (typeof window.go === 'function') window.go('chapters');
            message('Continuing ' + (opened.title || candidate.title) + '.');
          } catch (err) { message(err?.message || String(err), true); }
          return;
        }
        if (label === 'view job') {
          e.preventDefault(); e.stopImmediatePropagation();
          try {
            const rows = await call('job.list', {include_hidden:false});
            const job = rows.find(j => !['completed','failed','cancelled'].includes(j.state));
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
            const result = await call('sound.import');
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
            await call('sound.assign', {path:selectedSoundPath,volume:Number($('advancedMusicVolume')?.value || 18)/100});
            message('Book default background track saved.');
          } else if (soundButton.id === 'saveSoundPresetAdvanced') {
            const result = await call('sound.save_manifest', {path:selectedSoundPath || '',enabled:Boolean(selectedSoundPath),volume:Number($('advancedMusicVolume')?.value || 18)/100});
            message(result.enabled ? 'Book sound manifest saved.' : 'Book sound manifest saved with background music disabled.');
          } else if (soundButton.id === 'applySoundToProduction') {
            await call('sound.save_manifest', {path:selectedSoundPath || '',enabled:Boolean(selectedSoundPath),volume:Number($('advancedMusicVolume')?.value || 18)/100});
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
        else {
          rows.forEach(row => row.hidden = false);
          message('Review status is not yet supplied by the chapter backend; showing all chapters rather than inventing review flags.', true);
          return;
        }
        message(label === 'empty' ? 'Showing empty chapters.' : 'Showing all chapters.');
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
      if (button.id === 'pronTermList' || button.closest('#pronTermList [data-pron-term]')) {
        const termButton = button.closest('#pronTermList [data-pron-term]');
        if (!termButton) return;
        stop();
        const term = terms.find(item => String(item.written_form || item.word) === termButton.dataset.pronTerm);
        if (!term) { message('That pronunciation term is no longer in the saved dictionary.', true); return; }
        if ($('pronWord')) $('pronWord').textContent = term.written_form || term.word;
        if ($('pronValue')) $('pronValue').value = term.spoken_form || term.pronunciation || '';
        if ($('pronScope')) $('pronScope').value = term.scope || 'Current book';
        if ($('pronHandling')) $('pronHandling').value = term.handling_mode || 'automatic';
        if ($('pronDetectedLanguage')) $('pronDetectedLanguage').textContent = term.language || 'Auto-detected';
        if ($('pronConfidence')) $('pronConfidence').textContent = term.confidence == null ? 'Saved rule' : String(term.confidence) + '%';
        $('pronTermList')?.querySelectorAll('[data-pron-term]').forEach(row => row.classList.toggle('active', row === termButton));
        return;
      }
      if (button.closest('#voices .panel[data-panel="3"]') && label === 'load') {
        stop();
        const select = button.closest('.panel')?.querySelector('.toolbar select');
        const name = select?.value && select.value !== 'Select saved profile' ? select.value : $('profileName')?.value.trim();
        const profile = voices.find(item => item.name.toLowerCase() === String(name || '').toLowerCase());
        if (!profile) { message('Choose an existing profile from the saved-profile list before loading.', true); return; }
        selectedVoice = profile.name; selectedVoiceId = profile.voice_id;
        if ($('profileName')) $('profileName').value = profile.name;
        if ($('profileLibrary')) $('profileLibrary').textContent = profile.provider;
        if ($('profileVoice')) $('profileVoice').textContent = profile.voice_id;
        if ($('previewProfile')) $('previewProfile').textContent = profile.name;
        if ($('useNarrator')) $('useNarrator').disabled = false;
        if ($('saveOnly')) $('saveOnly').disabled = false;
        document.querySelectorAll('.provider').forEach(panel => panel.classList.toggle('active', panel.dataset.provider === profile.provider));
        message('Loaded saved voice profile: ' + profile.name);
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
      if (button.id === 'acceptHighConfidence' || button.id === 'skipAiSuggestion' ||
          button.id === 'confirmAiCharacter' || button.matches('[data-ai-sentence],[data-ai-line]') ||
          button.id === 'aiUseLibrary' || button.id === 'aiCreateNew' || button.id === 'createCharacterQuick') {
        stop();
        message('Per-line AI speaker suggestions are still prototype-only; this action did not change the saved cast. Use Analyze book with AI for the real backend analysis and assign voices in the saved cast panel.', true);
        return;
      }
      if (button.closest('#settings') && label === 'choose folder') {
        stop();
        message('Custom project-library and audio-assets root selection is not implemented in this build; the existing local storage paths were not changed.', true);
        return;
      }
      if (button.closest('#settings') && label === 'export logs') {
        stop();
        message('Sanitized log export is not connected yet; no export file was created.', true);
        return;
      }
    }, true);
    const savedProfileSelect = document.querySelector('#voices .panel[data-panel="3"] .toolbar select');
    if (savedProfileSelect) {
      savedProfileSelect.innerHTML = '<option value="">Select saved profile</option>' + voices.map(v => '<option value="' + esc(v.name) + '">' + esc(v.name) + ' · ' + esc(v.provider) + '</option>').join('');
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
    message('Premium V2 local backend connected.');
  }
  const start = () => wire().catch(e=>message(e.message,true));
  if (window.ryuBackend?.invoke) start(); else window.addEventListener('ryu-backend-ready', start, {once:true});
})();