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
  let selectedVoice = null, selectedVoiceId = null, activeJob = null, poll = null, previewAudio = null, playerAudio = null, soundPreviewAudio = null, cueSearchUnavailableNotified = false;
  let chapters = [], characters = [], voices = [], terms = [], projects = [], sounds = [], selectedSoundPath = null;
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
      dash.querySelectorAll('[data-project-folder]').forEach(c => c.remove());
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
  async function refreshTerms() {
    terms = await call('pronunciation.list');
    const list = $('pronDictionaryBody');
    if (list) list.innerHTML = terms.map(t => '<div class="list-item"><b>' + esc(t.written_form || t.word) + '</b><span> → ' + esc(t.spoken_form || t.pronunciation) + '</span></div>').join('') || '<p class="muted">No saved pronunciation rules for this book.</p>';
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
  function preparePreviewPlayback(job) {
    const url = job?.result?.file_url;
    if (!url) { if ($('validation')) $('validation').textContent = 'Preview completed, but the backend did not return a playable local file URL.'; return; }
    if (previewAudio) { previewAudio.pause(); previewAudio = null; }
    previewAudio = new Audio(url);
    previewAudio.preload = 'auto';
    previewAudio.onended = () => { if ($('playPreview')) $('playPreview').textContent = '▶ Play'; };
    previewAudio.onerror = () => { if ($('validation')) $('validation').textContent = 'The preview file exists but the embedded player could not open it. Use the preview output path from job details.'; };
    if ($('playPreview')) $('playPreview').disabled = false;
    if ($('validation')) $('validation').textContent = 'Preview ready · ' + Number(job.result.actual_duration_seconds || 0).toFixed(1) + ' seconds';
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
    await monitorJob(data.job_id, async job => { if ($('previewState')) $('previewState').textContent = 'Ready'; preparePreviewPlayback(job); });
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
    await refreshCharacters().catch(()=>{}); await refreshTerms().catch(()=>{}); await refreshSounds().catch(()=>{}); await refreshJobs().catch(()=>{}); await refreshHistory().catch(()=>{}); await refreshModels().catch(()=>{}); await loadSettings().catch(()=>{});
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
      const result=await call('performance.info');
      if($('benchmarkResult'))$('benchmarkResult').textContent=result.available?'Benchmark available':'Not connected';
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
    if ($('cleanText')) $('cleanText').onclick = act(async()=>{const c=selectedChapter();if(!c)throw new Error('Import or open a book first.');const text=$('chapterEditor')?.value||'';$('chapterEditor').value=text.replace(/[ \t]+\n/g,'\n').replace(/\n{3,}/g,'\n\n').trim();message('Whitespace cleaned. Save changes to persist it.');});
    if ($('saveChapter')) $('saveChapter').onclick = act(async()=>{const c=selectedChapter();if(!c)throw new Error('Select a chapter first.');const title=$('chapterTitle')?.textContent||c.title;const text=$('chapterEditor')?.value||'';const result=await call('chapter.update',{number:c.number,title,text});c.text=text;c.word_count=result.word_count;message('Chapter saved to local project.');await refreshChapters();});
    ['saveProfile','saveDraft','addPremium','saveOnly'].forEach(id=>{if($(id))$(id).onclick=act(saveVoice);});
    if ($('useNarrator')) $('useNarrator').onclick=act(async()=>{const v=await saveVoice();if(v)await call('voice.select',{profile_name:v.name});message('Saved and selected narrator.');});
    if ($('generatePreview')) $('generatePreview').onclick=act(previewVoice);
    if ($('previewGenerate')) $('previewGenerate').onclick=act(async()=>{const name=selectedVoice||$('profileName')?.value;const group=[...document.querySelectorAll('#generate .segmented')].find(el=>[...el.querySelectorAll('button')].some(b=>/10s|30s|60s/i.test(b.textContent)));const duration=group?.querySelector('button.active')?.textContent.match(/\d+/)?.[0]||'30';const data=await call('production.preview',{profile_name:name,duration_seconds:Number(duration)});await monitorJob(data.job_id,preparePreviewPlayback);});
    if ($('playPreview')) $('playPreview').onclick=act(async()=>{if(!previewAudio)throw new Error('Generate a preview first.');if(!previewAudio.paused){previewAudio.pause();$('playPreview').textContent='▶ Play';}else{await previewAudio.play();$('playPreview').textContent='Ⅱ Pause';}});
    if ($('stopPreview')) $('stopPreview').onclick=()=>{if(previewAudio){previewAudio.pause();previewAudio.currentTime=0;}if($('playPreview'))$('playPreview').textContent='▶ Play';};
    if ($('startGenerate')) $('startGenerate').onclick=act(async()=>{const data=await call('production.generate_book',{profile_name:selectedVoice||$('profileName')?.value,bitrate:256});await monitorJob(data.job_id);});
    if ($('pauseGenerate')) $('pauseGenerate').onclick=act(async()=>{if(!activeJob)throw new Error('There is no active job to pause.');await call('job.pause',{job_id:activeJob});await refreshJobs();});
    if ($('cancelJob')) $('cancelJob').onclick=act(async()=>{if(!activeJob)throw new Error('There is no active job to cancel.');await call('job.cancel',{job_id:activeJob});await refreshJobs();});
    ['analyzeCharacters','runAiAnalysis'].forEach(id=>{if($(id))$(id).onclick=act(async()=>{const data=await call('character.analyze');await monitorJob(data.job_id,refreshCharacters);});});
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
    if ($('soundTrackGrid')) $('soundTrackGrid').addEventListener('click', e=>{const b=e.target.closest('[data-select-sound]');if(!b)return;selectedSoundPath=b.dataset.selectSound;if($('selectedSoundTitle'))$('selectedSoundTitle').textContent=sounds.find(t=>t.path===selectedSoundPath)?.title||'Selected track';if($('selectedSoundMeta'))$('selectedSoundMeta').textContent='Selected from the local catalogue';message('Selected sound track. Save it to the active book to apply it.');});
    if ($('setBookDefaultTrack')) $('setBookDefaultTrack').onclick = act(async()=>{if(!selectedSoundPath)throw new Error('Select a track from the local sound catalogue first.');await call('sound.assign',{path:selectedSoundPath,volume:Number($('advancedMusicVolume')?.value||18)/100});message('Background track assigned to the active book.');});
    if ($('saveSoundPresetAdvanced')) $('saveSoundPresetAdvanced').onclick = act(async()=>{await call('sound.save_manifest',{path:selectedSoundPath||'',enabled:Boolean(selectedSoundPath),volume:Number($('advancedMusicVolume')?.value||18)/100});message('Sound manifest saved to the active book.');});
    ['mainPlay','miniPlay'].forEach(id=>{if($(id))$(id).onclick=act(openPlayer);});
    if ($('playerTimeline')) $('playerTimeline').oninput=()=>{if(playerAudio&&playerAudio.duration)playerAudio.currentTime=Number($('playerTimeline').value)/100*playerAudio.duration;};
    if ($('hideMini')) $('hideMini').onclick=()=> $('miniPlayer')?.classList.add('hidden');
    if ($('saveSettingsAdvanced')) $('saveSettingsAdvanced').onclick=act(async()=>{await call('settings.save',{theme:$('themeSelectAdvanced')?.value||'dark',effects:$('effectsModeAdvanced')?.value||'high'});message('Settings saved to this PC.');});
    document.addEventListener('input', e => {
      if (e.target?.id === 'soundTrackSearch') {
        e.stopImmediatePropagation();
        refreshSounds().catch(err => message(err?.message || String(err), true));
      } else if (e.target?.id === 'cueSearch') {
        e.stopImmediatePropagation();
        if (!cueSearchUnavailableNotified) {
          cueSearchUnavailableNotified = true;
          message('Cue search is unavailable because chapter cue assets are not yet connected to the local catalogue.', true);
        }
      }
    }, true);
    document.addEventListener('click', async e => {
      const source = e.target.closest('#soundSourceFilter [data-source]');
      if (source) {
        e.preventDefault(); e.stopImmediatePropagation();
        source.parentElement?.querySelectorAll('[data-source]').forEach(b => b.classList.toggle('active', b === source));
        refreshSounds().catch(err => message(err?.message || String(err), true));
        return;
      }
      const soundButton = e.target.closest('#importMusicTracks, #importCueClips, #previewSelectedTrack, #setBookDefaultTrack, #saveSoundPresetAdvanced, #applySoundToProduction, #soundPreviewBook, #previewCueSequence, #clearAllCues, #saveChapterBgm');
      if (soundButton) {
        e.preventDefault(); e.stopImmediatePropagation();
        try {
          if (soundButton.id === 'importMusicTracks' || soundButton.id === 'importCueClips') {
            const result = await call('sound.import');
            await refreshSounds();
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
            document.querySelector('[data-page="generate"]')?.click();
          } else if (soundButton.id === 'saveChapterBgm') {
            throw new Error('Per-chapter BGM overrides are not connected yet. Use Set Book Default Track to save the supported book-wide setting.');
          } else if (soundButton.id === 'clearAllCues') {
            throw new Error('Story cue assignments are not connected to persistent backend storage yet; no saved cue data was changed.');
          } else if (soundButton.id === 'previewCueSequence') {
            throw new Error('Cue-sequence preview is not available until story cue assets are connected to the backend.');
          } else if (soundButton.id === 'soundPreviewBook') {
            throw new Error('Full-book mix preview is not connected yet. You can preview an individual local track.');
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