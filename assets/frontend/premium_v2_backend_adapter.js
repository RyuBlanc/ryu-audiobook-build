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
  let selectedVoice = null, selectedVoiceId = null, activeJob = null, poll = null;
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
    const visible = sounds.filter(t => !query || (t.title + ' ' + t.source + ' ' + t.format).toLowerCase().includes(query));
    if (grid) grid.innerHTML = visible.map(t => '<article class="sound-track card"><div class="sound-track-info"><b>' + esc(t.title) + '</b><small>' + esc(t.source) + ' · ' + esc(t.format) + ' · ' + Math.round(Number(t.size_bytes || 0)/1024) + ' KB</small></div><button class="btn small secondary" data-select-sound="' + esc(t.path) + '">Select</button></article>').join('') || '<p class="muted">No local or bundled sound tracks found. Import your own licensed audio files.</p>';
    return sounds;
  }
  async function refreshJobs() {
    const jobs = await call('job.list', {include_hidden:false}), box = $('backgroundJobsList');
    if (box) box.innerHTML = jobs.map(j => '<article class="job-row"><b>' + esc(j.title || j.type || j.job_id) + '</b><p>' + esc(j.stage || j.message || j.state) + '</p><div class="progress"><i style="width:' + Math.max(0,Math.min(100,Number(j.progress || 0))) + '%"></i></div><small>' + esc(j.state) + ' · ' + Math.round(Number(j.progress || 0)) + '%</small><div class="toolbar">' + (j.state === 'running' ? '<button class="btn small secondary" data-job-action="pause" data-job-id="' + esc(j.job_id) + '">Pause</button>' : '') + (j.state === 'paused' ? '<button class="btn small" data-job-action="resume" data-job-id="' + esc(j.job_id) + '">Resume</button>' : '') + '<button class="btn small ghost" data-job-action="cancel" data-job-id="' + esc(j.job_id) + '">Cancel</button></div></article>').join('') || '<p class="muted">No backend jobs yet.</p>';
    if ($('jobsRunningCount')) $('jobsRunningCount').textContent = jobs.filter(j => ['running','pause_requested'].includes(j.state)).length;
    if ($('jobsQueuedCount')) $('jobsQueuedCount').textContent = jobs.filter(j => j.state === 'queued').length;
    if ($('jobsCompletedCount')) $('jobsCompletedCount').textContent = jobs.filter(j => j.state === 'completed').length;
    if ($('backgroundJobCount')) $('backgroundJobCount').textContent = jobs.filter(j => !['completed','failed','cancelled'].includes(j.state)).length + ' background jobs';
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
    const voice_id = provider === 'piper' ? (matchedPiper?.voice_id || voices.find(v => v.name === name)?.voice_id || 'en_US-amy-medium') : (selectedVoiceId || voiceLabel || name);
    const result = await call('voice.save', {name,provider,voice_id,sample_path,authorized,
      model_id:provider === 'chatterbox' ? 'chatterbox' : provider === 'qwen-character' ? 'qwen3-tts' : provider,
      backend:provider === 'piper' ? 'automatic' : provider,language:'English',
      qwen_mode:provider === 'qwen-character' ? (/clone/i.test(choice) ? 'clone' : 'custom') : 'custom',
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
  async function importBook() {
    const chosen = await call('import.choose_file');
    if (chosen.cancelled || !chosen.path) return;
    if ($('importStatus')) $('importStatus').textContent = 'Importing ' + chosen.path.split(/[\\/]/).pop() + '…';
    if ($('importBar')) $('importBar').style.width = '8%';
    const result = await call('import.start', {file_path:chosen.path,title:chosen.path.split(/[\\/]/).pop().replace(/\.[^.]+$/,'')});
    if (result.job_id) await monitorJob(result.job_id, async () => { await refreshProjects(); await refreshChapters(); if (typeof window.go === 'function') window.go('chapters'); });
    else { await refreshChapters(); message('Book imported into the local library.'); }
  }
  async function previewVoice() {
    const name = (selectedVoice || $('profileName')?.value || '').trim();
    if (!name) throw new Error('Save or select a voice profile first.');
    const c = selectedChapter();
    const duration = document.querySelector('#voices .segmented button.active')?.textContent.match(/\d+/)?.[0] || '30';
    const data = await call('voice.preview', {profile_name:name,text:c?.text || '',duration_seconds:Number(duration),chapter_number:c?.number});
    if ($('previewState')) $('previewState').textContent = 'Generating';
    if ($('validation')) $('validation').textContent = 'Preview job ' + data.job_id + ' is running locally.';
    await monitorJob(data.job_id, async () => { if ($('previewState')) $('previewState').textContent = 'Ready'; if ($('playPreview')) $('playPreview').disabled = false; });
  }
  async function wire() {
    await call('app.get_info');
    await refreshProjects().catch(()=>{}); await refreshVoices().catch(()=>{}); await refreshChapters().catch(()=>{});
    await refreshCharacters().catch(()=>{}); await refreshTerms().catch(()=>{}); await refreshSounds().catch(()=>{}); await refreshJobs().catch(()=>{});
    document.addEventListener('click', e => { const b=e.target.closest('[data-voice]'); if(b){selectedVoiceId=b.dataset.voice;const label=b.dataset.voice;if($('profileVoice'))$('profileVoice').textContent=label;if($('premiumName')&&!$('premiumName').value.trim())$('premiumName').value=label+' Custom';if($('profileName')&&!$('profileName').value.trim())$('profileName').value=label+' Custom';return;}if(e.target.closest('.provider'))selectedVoiceId=null; });
    if ($('librarySearch')) $('librarySearch').oninput = () => refreshProjects().catch(e=>message(e.message,true));
    if ($('libraryGrid')) $('libraryGrid').addEventListener('click', async e => {
      const button = e.target.closest('[data-open-project]'); if (!button) return;
      button.disabled = true;
      try { const opened = await call('project.open', {folder:button.dataset.openProject}); await refreshProjects(); await refreshChapters(); await refreshCharacters(); if (typeof window.go === 'function') window.go('chapters'); message('Opened local project: ' + (opened.title || opened.folder || 'project')); }
      catch (err) { message(err?.message || String(err), true); }
      finally { button.disabled = false; }
    });
    if ($('browseBtn')) $('browseBtn').onclick = act(importBook);
    if ($('dropzone')) $('dropzone').onclick = e => { if (!e.target.closest('button')) importBook().catch(x=>message(x.message,true)); };
    if ($('cleanText')) $('cleanText').onclick = act(async()=>{const c=selectedChapter();if(!c)throw new Error('Import or open a book first.');const text=$('chapterEditor')?.value||'';$('chapterEditor').value=text.replace(/[ \t]+\n/g,'\n').replace(/\n{3,}/g,'\n\n').trim();message('Whitespace cleaned. Save changes to persist it.');});
    if ($('saveChapter')) $('saveChapter').onclick = act(async()=>{const c=selectedChapter();if(!c)throw new Error('Select a chapter first.');const title=$('chapterTitle')?.textContent||c.title;const text=$('chapterEditor')?.value||'';const result=await call('chapter.update',{number:c.number,title,text});c.text=text;c.word_count=result.word_count;message('Chapter saved to local project.');await refreshChapters();});
    ['saveProfile','saveDraft','addPremium','saveOnly'].forEach(id=>{if($(id))$(id).onclick=act(saveVoice);});
    if ($('useNarrator')) $('useNarrator').onclick=act(async()=>{const v=await saveVoice();if(v)await call('voice.select',{profile_name:v.name});message('Saved and selected narrator.');});
    if ($('generatePreview')) $('generatePreview').onclick=act(previewVoice);
    if ($('previewGenerate')) $('previewGenerate').onclick=act(async()=>{const name=selectedVoice||$('profileName')?.value;const data=await call('production.preview',{profile_name:name,duration_seconds:30});await monitorJob(data.job_id);});
    if ($('startGenerate')) $('startGenerate').onclick=act(async()=>{const data=await call('production.generate_book',{profile_name:selectedVoice||$('profileName')?.value,bitrate:256});await monitorJob(data.job_id);});
    if ($('pauseGenerate')) $('pauseGenerate').onclick=act(async()=>{if(!activeJob)throw new Error('There is no active job to pause.');await call('job.pause',{job_id:activeJob});await refreshJobs();});
    if ($('cancelJob')) $('cancelJob').onclick=act(async()=>{if(!activeJob)throw new Error('There is no active job to cancel.');await call('job.cancel',{job_id:activeJob});await refreshJobs();});
    ['analyzeCharacters','runAiAnalysis'].forEach(id=>{if($(id))$(id).onclick=act(async()=>{const data=await call('character.analyze');await monitorJob(data.job_id,refreshCharacters);});});
    if ($('savePronTerm')) $('savePronTerm').onclick=act(async()=>{await call('pronunciation.save',{written_form:$('pronWord')?.textContent?.trim()||'',spoken_form:$('pronValue')?.value||'',scope:$('pronScope')?.value||'current_book',handling_mode:$('pronHandling')?.value||'automatic'});await refreshTerms();message('Pronunciation rule saved locally.');});
    if ($('saveNewPron')) $('saveNewPron').onclick=act(async()=>{await call('pronunciation.save',{written_form:$('newPronWritten')?.value||'',spoken_form:$('newPronValue')?.value||'',language:$('newPronLanguage')?.value||'Auto',scope:$('newPronScope')?.value||'current_book'});await refreshTerms();$('pronEntryModal')?.classList.remove('show');message('Pronunciation entry saved.');});
    if ($('analyzePronunciation')) $('analyzePronunciation').onclick=act(async()=>{const r=await call('pronunciation.analyze');const list=$('pronDictionaryBody');if(list)list.innerHTML=(r.suggestions||[]).map(t=>'<div class="list-item"><b>'+esc(t.written_form)+'</b><span> → '+esc(t.spoken_form)+'</span></div>').join('')||'<p class="muted">No new suggestions found.</p>';message('Found '+(r.suggestions||[]).length+' suggestions to review.');});
    if ($('assignCharacter')) $('assignCharacter').onclick=act(async()=>{const name=window.ryuPremiumSelectedCharacter;if(!name)throw new Error('Select a character first.');await call('character.assign',{name,profile_name:selectedVoice||$('profileName')?.value});await refreshCharacters();});
    if ($('editCharacterVoice')) $('editCharacterVoice').onchange=act(async()=>{if(!window.ryuPremiumSelectedCharacter)return;await call('character.assign',{name:window.ryuPremiumSelectedCharacter,profile_name:$('editCharacterVoice').value});await refreshCharacters();});
    if ($('importMusicTracks')) $('importMusicTracks').onclick = act(async()=>{const r=await call('sound.import');await refreshSounds();message('Imported '+(r.imported||[]).length+' sound file(s) into the local Audio Library.');});
    if ($('importCueClips')) $('importCueClips').onclick = act(async()=>{const r=await call('sound.import');await refreshSounds();message('Imported '+(r.imported||[]).length+' sound clip(s) into the local Audio Library.');});
    if ($('soundTrackSearch')) $('soundTrackSearch').oninput = () => refreshSounds().catch(e=>message(e.message,true));
    if ($('soundTrackGrid')) $('soundTrackGrid').addEventListener('click', e=>{const b=e.target.closest('[data-select-sound]');if(!b)return;selectedSoundPath=b.dataset.selectSound;if($('selectedSoundTitle'))$('selectedSoundTitle').textContent=sounds.find(t=>t.path===selectedSoundPath)?.title||'Selected track';if($('selectedSoundMeta'))$('selectedSoundMeta').textContent='Selected from the local catalogue';message('Selected sound track. Save it to the active book to apply it.');});
    if ($('setBookDefaultTrack')) $('setBookDefaultTrack').onclick = act(async()=>{if(!selectedSoundPath)throw new Error('Select a track from the local sound catalogue first.');await call('sound.assign',{path:selectedSoundPath,volume:Number($('advancedMusicVolume')?.value||18)/100});message('Background track assigned to the active book.');});
    if ($('saveSoundPresetAdvanced')) $('saveSoundPresetAdvanced').onclick = act(async()=>{await call('sound.save_manifest',{path:selectedSoundPath||'',enabled:Boolean(selectedSoundPath),volume:Number($('advancedMusicVolume')?.value||18)/100});message('Sound manifest saved to the active book.');});
    if ($('saveSettingsAdvanced')) $('saveSettingsAdvanced').onclick=act(async()=>{await call('settings.save',{theme:$('themeSelectAdvanced')?.value||'dark',effects:$('effectsModeAdvanced')?.value||'high'});message('Settings saved to this PC.');});
    document.addEventListener('click',async e=>{const b=e.target.closest('[data-job-action]');if(!b)return;e.preventDefault();try{const commands={pause:'job.pause',resume:'job.resume',cancel:'job.cancel'};await call(commands[b.dataset.jobAction]||'job.cancel',{job_id:b.dataset.jobId});await refreshJobs();}catch(err){message(err?.message||String(err),true);}});
    if (!window.__ryuBackendJobTimer) window.__ryuBackendJobTimer=setInterval(()=>refreshJobs().catch(()=>{}),3000);
    message('Premium V2 local backend connected.');
  }
  const start = () => wire().catch(e=>message(e.message,true));
  if (window.ryuBackend?.invoke) start(); else window.addEventListener('ryu-backend-ready', start, {once:true});
})();