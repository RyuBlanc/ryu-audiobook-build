'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const adapterPath = path.resolve(__dirname, '..', 'assets', 'frontend', 'premium_v2_backend_adapter.js');
const source = fs.readFileSync(adapterPath, 'utf8');

function section(start, end) {
  const startAt = source.indexOf(start);
  assert.notEqual(startAt, -1, 'missing adapter helper: ' + start);
  const endAt = source.indexOf(end, startAt + start.length);
  assert.notEqual(endAt, -1, 'missing adapter helper boundary: ' + end);
  return source.slice(startAt, endAt);
}

const helpers = [
  section('function characterVoiceAssignments(name) {', 'function characterMatchesAssignedCastSearch(item, query) {'),
  section('function characterMatchesAssignedCastSearch(item, query) {', 'function assignedDialogueVisibleCount(passages, selectedId, requestedCount) {'),
  section('function assignedDialogueVisibleCount(passages, selectedId, requestedCount) {', 'function assignedDialogueRowsMarkup(passages, selectedId, visibleCount) {'),
  section('function assignedDialogueRowsMarkup(passages, selectedId, visibleCount) {', 'function renderCharacterInspector() {')
].join('\n');

const character = {name:'Mira Vale', aliases:['Miri','The Wayfinder'], series:'North Saga', voice_profile:'Qwen Mira'};
const chapterOneText = '“Hello there.” Then she paused. “I am ready.”';
const chapterTwoText = '“We are safe.” “Move now.”';

function assignment(text, speaker, source, chapterText) {
  const start = chapterText.indexOf(text);
  assert.notEqual(start, -1, 'fixture span not found: ' + text);
  return {speakers:[speaker], start, end:start + text.length, text, source};
}

const chapters = [
  {number:1,title:'The Arrival',text:chapterOneText,dialogue_assignments:[
    assignment('“Hello there.”','Miri','local-dialogue-analysis',chapterOneText),
    assignment('“I am ready.”','Mira Vale','manual',chapterOneText),
    {speakers:['Miri'],start:999,end:1010,text:'stale passage',source:'ai'},
    {speakers:['Miri'],start:0,end:4,text:'not the saved source span',source:'ai'}
  ]},
  {number:2,title:'The Crossing',text:chapterTwoText,dialogue_assignments:[
    assignment('“We are safe.”','Miri','ai',chapterTwoText),
    assignment('“Move now.”','Mira Vale','manual',chapterTwoText)
  ]}
];

const sandbox = {
  characters:[character],
  chapters,
  characterCanonical:item => String(item?.name || item?.primary_name || '').trim(),
  characterAliases:item => (Array.isArray(item?.aliases) ? item.aliases : []).map(value => String(value || '').trim()).filter(Boolean),
  characterSeries:item => String(item?.series || 'Unassigned series'),
  characterRowForName:name => {
    const key = String(name || '').trim().toLocaleLowerCase();
    return [character].find(item => String(item.name || '').trim().toLocaleLowerCase() === key || (item.aliases || []).some(alias => String(alias).trim().toLocaleLowerCase() === key)) || null;
  },
  characterAssignmentsFor:chapter => Array.isArray(chapter?.dialogue_assignments) ? chapter.dialogue_assignments : [],
  esc:value => String(value ?? '').replace(/[&<>\"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[char]))
};

vm.createContext(sandbox);
const behaviorCode = [
  "const snapshot = characterVoiceAssignments('Mira Vale');",
  "const noMatches = characterVoiceAssignments('Nobody');",
  "const pages = Array.from({length:65}, (_, index) => ({id:'row-' + (index + 1),chapter_number:1 + Math.floor(index / 10),chapter_title:'Chapter ' + (1 + Math.floor(index / 10)),start:index * 3,end:index * 3 + 2,text:'Line ' + (index + 1),source:index % 2 === 0 ? 'ai' : 'manual',sourceLabel:index % 2 === 0 ? 'AI analyzed' : 'Manual'}));",
  "const firstCount = assignedDialogueVisibleCount(pages, '', 30);",
  "const firstMarkup = assignedDialogueRowsMarkup(pages, '', firstCount);",
  "const selectedCount = assignedDialogueVisibleCount(pages, 'row-45', 30);",
  "const selectedMarkup = assignedDialogueRowsMarkup(pages, 'row-45', selectedCount);",
  "const allCount = assignedDialogueVisibleCount(pages, '', 90);",
  "const allMarkup = assignedDialogueRowsMarkup(pages, '', allCount);",
  "globalThis.behaviorResult = {snapshot,noMatches,searchByName:characterMatchesAssignedCastSearch(characters[0],'mira'),searchByAlias:characterMatchesAssignedCastSearch(characters[0],'wayfinder'),searchByVoice:characterMatchesAssignedCastSearch(characters[0],'qwen mira'),searchMiss:characterMatchesAssignedCastSearch(characters[0],'unrelated'),firstCount,firstMarkup,selectedCount,selectedMarkup,allCount,allMarkup};"
].join('\n');
vm.runInContext(helpers + '\n' + behaviorCode, sandbox);
const result = JSON.parse(JSON.stringify(sandbox.behaviorResult));

assert.equal(result.snapshot.assignedVoice, 'Qwen Mira');
assert.equal(result.snapshot.passages.length, 4, 'only exact saved assignment spans should count');
assert.deepEqual(result.snapshot.chapters, [1,2], 'multiple dialogue lines in one chapter count once');
assert.equal(result.snapshot.aiAssignedCount, 2);
assert.equal(result.snapshot.manualAssignedCount, 2);
assert.equal(result.snapshot.aiAssignedPercent, 50);
assert.deepEqual(result.snapshot.passages.map(row => row.source), ['ai','manual','ai','manual']);
assert.equal(result.noMatches.passages.length, 0);
assert.deepEqual(result.noMatches.chapters, []);
assert.equal(result.noMatches.aiAssignedPercent, 0);
assert.equal(result.noMatches.assignedVoice, '');

assert.equal(result.searchByName, true);
assert.equal(result.searchByAlias, true);
assert.equal(result.searchByVoice, true);
assert.equal(result.searchMiss, false);

const rowCount = markup => (markup.match(/data-assigned-dialogue=\"/g) || []).length;
assert.equal(result.firstCount, 30);
assert.equal(rowCount(result.firstMarkup), 30);
assert.match(result.firstMarkup, /data-assigned-dialogue-more/);
assert.match(result.firstMarkup, /30 of 65/);
assert.match(result.firstMarkup, /data-assigned-dialogue=\"row-30\"/);
assert.doesNotMatch(result.firstMarkup, /data-assigned-dialogue=\"row-31\"/);
assert.equal(result.selectedCount, 60, 'selected row beyond initial page is visible after refresh');
assert.equal(rowCount(result.selectedMarkup), 60);
assert.match(result.selectedMarkup, /data-assigned-dialogue=\"row-45\"/);
assert.match(result.selectedMarkup, /is-ai is-selected/);
assert.equal(result.allCount, 65);
assert.equal(rowCount(result.allMarkup), 65, 'all assigned lines remain reachable');
assert.match(result.allMarkup, /data-assigned-dialogue=\"row-65\"/);
assert.match(result.allMarkup, /is-manual/);
assert.match(result.allMarkup, /is-ai/);

process.stdout.write('Stage 3 Character Studio behavior checks passed: provenance, unique chapters, zero case, name/alias/voice search, 65-row pagination and selected-row visibility.\\n');