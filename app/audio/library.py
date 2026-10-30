from __future__ import annotations

"""Real local audio files for audiobook music and book-transition effects.

The app does not download, scrape, generate, or bundle stock audio. Users import
files they have rights to use; local source/license notes are retained beside
each imported file so the app remains offline-first.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from app.core.paths import audio_library_root

AUDIO_EXTENSIONS={".wav",".mp3",".m4a",".aac",".flac",".ogg",".opus",".wma",".aiff"}
MUSIC_CATEGORIES=(
 ("fantasy","Epic fantasy / magic"),("action","Action / battle / anime-rock"),
 ("mystery","Mystery / suspense / investigation"),("horror","Dark / supernatural / horror"),
 ("romance","Romance / warmth / tenderness"),("emotional","Emotional / tragedy / heartfelt"),
 ("adventure","Adventure / exploration / travel"),("sci-fi","Sci-fi / futuristic / cyber"),
 ("slice-of-life","Slice of life / cozy / everyday"),("comedy","Comedy / playful"),
 ("calm","Quiet narration bed / ambient / reflective"),
 ("universal","Universal / low-distraction narration bed"))
MUSIC_CATEGORY_LABELS=dict(MUSIC_CATEGORIES)
CUE_KINDS=(("opening","Book opening / cover lift"),("page","Chapter transition / page turn"),("ending","Book closing / final cue"))
CUE_KIND_LABELS=dict(CUE_KINDS)
# Link out to source searches only: users choose files and review current licenses.
AUDIO_SOURCE_LINKS=(
 {"label":"SoundDino — audiobook music","url":"https://sounddino.com/en/effects/audiobooks-music/","group":"music"},
 {"label":"Pixabay — audiobook music","url":"https://pixabay.com/music/search/audiobook/","group":"music"},
 {"label":"Pixabay — storytelling / podcast beds","url":"https://pixabay.com/music/search/storytelling%20podcast/","group":"music"},
 {"label":"Pixabay — cinematic ambient beds","url":"https://pixabay.com/music/search/cinematic%20ambient/","group":"music"},
 {"label":"Pixabay — epic fantasy / orchestral","url":"https://pixabay.com/music/search/fantasy%20orchestral/","group":"music"},
 {"label":"Pixabay — action / epic battle","url":"https://pixabay.com/music/search/epic%20action/","group":"music"},
 {"label":"Pixabay — mystery / suspense","url":"https://pixabay.com/music/search/mystery%20suspense/","group":"music"},
 {"label":"Pixabay — emotional piano / orchestral","url":"https://pixabay.com/music/search/emotional%20piano/","group":"music"},
 {"label":"Pixabay — calm / reflective ambience","url":"https://pixabay.com/music/search/ambient/","group":"music"},
 {"label":"SoundDino — music library","url":"https://sounddino.com/en/effects/music/","group":"music"},
 {"label":"SoundDino — sound effects library","url":"https://sounddino.com/","group":"cue"},
 {"label":"Pixabay — book opening sounds","url":"https://pixabay.com/sound-effects/search/book-open/","group":"cue"},
 {"label":"Pixabay — book page-turn / paper sounds","url":"https://pixabay.com/sound-effects/search/book-page-turn/","group":"cue"},
 {"label":"Pixabay — book closing sounds","url":"https://pixabay.com/sound-effects/search/book-closing/","group":"cue"},
 {"label":"Storyblocks — flip-book and page-turn sounds","url":"https://www.storyblocks.com/audio/search/flip-book","group":"cue"},
 {"label":"Audio.com — BGM and sound effects","url":"https://audio.com/category/sound-effect/bgm","group":"both"},
 {"label":"OpenGameArt — CC0 fantasy song pack","url":"https://opengameart.org/content/fantasy-song-pack-volume-1","group":"music"},
 {"label":"OpenGameArt — CC0 music collection","url":"https://opengameart.org/content/good-cc0-music","group":"music"},
 {"label":"Freesound — book and page-turn recordings","url":"https://freesound.org/search/?q=book+page+turn","group":"cue"},
 {"label":"OpenGameArt — Dark Sci-Fi Audio Pack (CC0)","url":"https://opengameart.org/content/dark-sci-fi-audio-pack","group":"music"},
 {"label":"OpenGameArt — Subspace (CC0)","url":"https://opengameart.org/content/subspace","group":"music"},
 {"label":"OpenGameArt — Aftermath (CC0)","url":"https://opengameart.org/content/aftermath","group":"music"},
 {"label":"OpenGameArt — Hero's Reprise (CC0)","url":"https://opengameart.org/content/heros-reprise","group":"music"},
 {"label":"OpenGameArt — Orchestral and World Music Pack (CC0)","url":"https://opengameart.org/content/orchestral-and-world-music-pack","group":"music"},
)
@dataclass(frozen=True)
class AudioTrack:
 path: Path
 category: str
 category_label: str
 license_note: str=""

def _bundled_starter_audio_root():
 candidates=[]
 frozen=getattr(sys,"_MEIPASS",None)
 if frozen: candidates.append(Path(frozen)/"assets"/"starter_audio")
 candidates.append(Path(__file__).resolve().parents[2]/"assets"/"starter_audio")
 for candidate in candidates:
  if (candidate/"manifest.json").is_file(): return candidate
 return None

def _seed_bundled_starter_audio(root):
 """Seed redistributed starter tracks once without overwriting user changes."""
 bundle=_bundled_starter_audio_root()
 if bundle is None: return 0
 try: manifest=json.loads((bundle/"manifest.json").read_text(encoding="utf-8"))
 except (OSError,ValueError,TypeError): return 0
 marker=root/".starter-audio-state.json"
 try: state=json.loads(marker.read_text(encoding="utf-8"))
 except (OSError,ValueError,TypeError): state={}
 seeded=state.get("seeded_files") if isinstance(state.get("seeded_files"),dict) else {}
 added=0
 for entry in manifest.get("tracks",[]):
  if not isinstance(entry,dict): continue
  rel=str(entry.get("bundle_path") or "").replace(chr(92),"/")
  if not rel or rel in seeded: continue
  source=(bundle/rel).resolve()
  try: source.relative_to(bundle.resolve())
  except ValueError: continue
  if not source.is_file(): continue
  role=str(entry.get("type") or "").casefold()
  category=str(entry.get("category") or "")
  if role=="music" and category in MUSIC_CATEGORY_LABELS:
   dest_dir=root/"music"/category
  elif role=="cue" and category in {key for key,_label in CUE_KINDS}:
   dest_dir=root/"cues"/category
  else: continue
  dest_dir.mkdir(parents=True,exist_ok=True)
  target=dest_dir/source.name
  if target.exists():
   suffix=2
   while target.exists():
    target=dest_dir/f"{source.stem} (Starter {suffix}){source.suffix}"
    suffix+=1
  shutil.copy2(source,target)
  license_name=str(entry.get("license") or "License not specified")
  note=str(entry.get("license_note") or "")
  metadata={
   "role":role if role=="music" else category,
   "category":category,
   "title":str(entry.get("title") or source.stem),
   "author":str(entry.get("author") or ""),
   "original_filename":source.name,
   "source_url":str(entry.get("source_url") or ""),
   "license":license_name,
   "license_note":f"{license_name}. {note}".strip(),
   "starter_pack_version":str(manifest.get("version") or ""),
   "imported_at":datetime.now(timezone.utc).isoformat(),
  }
  try: _metadata_path(target).write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
  except OSError: pass
  seeded[rel]=str(target.relative_to(root)).replace(chr(92),"/")
  added+=1
 if added or not marker.exists():
  try: marker.write_text(json.dumps({"version":str(manifest.get("version") or ""),"seeded_files":seeded},ensure_ascii=False,indent=2),encoding="utf-8")
  except OSError: pass
 credits=bundle/"ATTRIBUTION.md"
 local_credits=root/"Starter Audio Credits.md"
 if credits.is_file() and not local_credits.exists():
  try: shutil.copy2(credits,local_credits)
  except OSError: pass
 return added

def ensure_audio_library():
 root=audio_library_root()
 for key,_ in MUSIC_CATEGORIES: (root/"music"/key).mkdir(parents=True,exist_ok=True)
 for key,_ in CUE_KINDS: (root/"cues"/key).mkdir(parents=True,exist_ok=True)
 _seed_bundled_starter_audio(root)
 return root

def music_category_root(category):
 key=str(category or "universal").strip().casefold()
 if key not in MUSIC_CATEGORY_LABELS: key="universal"
 return ensure_audio_library()/"music"/key

def cue_category_root(kind):
 aliases={"opening":"opening","page":"page","chapter":"page","page-turn":"page","page_turn":"page",
          "transition":"page","ending":"ending","closing":"ending","book-close":"ending"}
 key=aliases.get(str(kind or "").strip().casefold())
 if key is None: raise ValueError(f"Unknown audiobook cue type: {kind}")
 return ensure_audio_library()/"cues"/key

def _metadata_path(path): return path.with_name(path.name+".license.json")

def metadata_for(path):
 try:
  data=json.loads(_metadata_path(path).read_text(encoding="utf-8"))
  return data if isinstance(data,dict) else {}
 except FileNotFoundError:
  return {}
 except (OSError,ValueError,TypeError) as exc:
  raise ValueError(f"Audio metadata for {Path(path).name} could not be read: {exc}") from exc

def license_note_for(path):
 data=metadata_for(path)
 return str(data.get("license_note") or data.get("source_note") or data.get("license") or "")

def probe_audio_duration_seconds(path):
 """Ask bundled FFmpeg to read an asset; reject corrupt/empty audio."""
 path=Path(path).expanduser()
 if not path.is_file():
  raise FileNotFoundError(f"Audio asset is missing: {path}. Reassign it in Sound Design.")
 if path.suffix.casefold() not in AUDIO_EXTENSIONS:
  raise ValueError(f"Unsupported audio format for {path.name}. Choose a supported audio file in Sound Design.")
 try:
  import imageio_ffmpeg
  result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),"-hide_banner","-i",str(path)],
                        capture_output=True,text=True,timeout=20,check=False)
 except (OSError,subprocess.SubprocessError) as exc:
  raise RuntimeError(f"Could not inspect audio asset {path.name}: {exc}") from exc
 output=str(result.stderr or "")+"\\n"+str(result.stdout or "")
 match=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",output)
 if not match:
  raise ValueError(f"Audio asset {path.name} is unreadable or has no measurable duration. Re-import a valid audio file.")
 seconds=int(match.group(1))*3600+int(match.group(2))*60+float(match.group(3))
 if seconds<=0:
  raise ValueError(f"Audio asset {path.name} has zero duration. Choose a valid audio file.")
 return seconds

def import_audio_files(files,*,target_kind,category="universal",license_note=""):
 target=str(target_kind or "").strip().casefold()
 if target not in {"music", *(key for key,_label in CUE_KINDS)}:
  raise ValueError(f"Unknown audio import type: {target_kind}")
 destination=music_category_root(category) if target=="music" else cue_category_root(target)
 note=str(license_note or "").strip()
 added=[]
 for raw in files:
  source=Path(raw).expanduser()
  if not source.is_file() or source.suffix.casefold() not in AUDIO_EXTENSIONS:
   raise ValueError(f"Unsupported or missing audio asset: {source}")
  if source.resolve().parent==destination.resolve(): dest=source.resolve()
  else:
   dest=destination/source.name
   serial=2
   while dest.exists() and dest.resolve()!=source.resolve():
    dest=destination/f"{source.stem} ({serial}){source.suffix}";serial+=1
   if dest.resolve()!=source.resolve(): shutil.copy2(source,dest)
  payload={"role":target,"category":category if target=="music" else target,
           "original_filename":source.name,"license_note":note,
           "imported_at":datetime.now(timezone.utc).isoformat()}
  try: _metadata_path(dest).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
  except OSError as exc:
   if dest != source.resolve():
    try: dest.unlink()
    except OSError: pass
   raise RuntimeError(f"Could not save audio metadata for {dest.name}: {exc}") from exc
  added.append(dest)
 return added

def list_music_tracks():
 root=ensure_audio_library()/"music";out=[]
 for key,label in MUSIC_CATEGORIES:
  for path in sorted((root/key).iterdir(),key=lambda p:p.name.casefold()):
   if path.is_file() and path.suffix.casefold() in AUDIO_EXTENSIONS:
    out.append(AudioTrack(path.resolve(),key,label,license_note_for(path)))
 return out

def list_cue_tracks(kind):
 return sorted((p.resolve() for p in cue_category_root(kind).iterdir()
                if p.is_file() and p.suffix.casefold() in AUDIO_EXTENSIONS),
               key=lambda p:p.name.casefold())

def _seed_index(seed,count):
 if count<=1:return 0
 h=hashlib.blake2b(str(seed or "").encode("utf-8",errors="replace"),digest_size=8).digest()
 return int.from_bytes(h,"big")%count

def resolve_music_track(mood,selected_track=None,*,seed_text=""):
 if selected_track is not None:
  p=Path(str(selected_track)).expanduser()
  if not p.is_file():
   raise FileNotFoundError(f"Selected music track is missing or no longer exists: {p}. Reassign it in Sound Design.")
  if p.suffix.casefold() not in AUDIO_EXTENSIONS:
   raise ValueError(f"Selected music track has an unsupported audio format: {p.name}")
  return p.resolve()
 key=str(mood or "universal").strip().casefold()
 key={"dark":"horror","anime-rock":"action","fantasy / adventure":"fantasy",
      "science-fiction":"sci-fi","sci fi":"sci-fi","drama":"emotional"}.get(key,key)
 if key not in MUSIC_CATEGORY_LABELS:key="universal"
 fallback={
  "fantasy":("fantasy","adventure","emotional","universal","calm"),
  "action":("action","fantasy","sci-fi","adventure","universal"),
  "mystery":("mystery","horror","sci-fi","universal","calm"),
  "horror":("horror","mystery","sci-fi","universal","calm"),
  "romance":("romance","emotional","calm","universal"),
  "emotional":("emotional","romance","calm","universal"),
  "adventure":("adventure","fantasy","action","universal","calm"),
  "sci-fi":("sci-fi","action","mystery","universal"),
  "slice-of-life":("slice-of-life","calm","comedy","universal"),
  "comedy":("comedy","slice-of-life","universal","calm"),
  "calm":("calm","slice-of-life","emotional","universal"),
  "universal":("universal","calm","adventure")}
 all_tracks=list_music_tracks();by={}
 for track in all_tracks:by.setdefault(track.category,[]).append(track)
 candidates=[]
 for category in fallback.get(key,(key,"universal","calm")):
  if by.get(category): candidates=by[category];break
 if not candidates:return None
 return candidates[_seed_index(seed_text,len(candidates))].path

def validate_saved_audio_paths(state):
 """Validate only sound assets active under the saved strategy and master switch."""
 overrides_value=state.get("chapter_bgm_overrides")
 overrides=overrides_value if isinstance(overrides_value,dict) else {}
 raw_mode=state.get("background_audio_mode")
 if raw_mode is None:
  raw_mode="manual" if (
   state.get("background_audio_path") or state.get("background_audio_preferred_path")
   or state.get("opening_cue_path") or state.get("page_turn_cue_path")
   or state.get("ending_cue_path") or overrides
  ) else "off"
 audio_mode=str(raw_mode or "off").strip().casefold()
 if audio_mode not in {"off","auto","manual"}:
  raise ValueError(f"Unsupported background audio mode: {audio_mode}")
 strategy=str(state.get("chapter_bgm_strategy") or ("custom" if overrides else "same")).strip().casefold()
 chapter_based=strategy in {"custom","chapter-based","chapter_based","chapter"}
 if strategy not in {"same","same-bgm","same_bgm","custom","chapter-based","chapter_based","chapter"}:
  raise ValueError(f"Unsupported chapter BGM strategy: {strategy}")
 audio_enabled=audio_mode!="off" and bool(state.get("background_audio_enabled",True))
 if not audio_enabled:
  # Voice Only retains preferences for later re-enabling; inactive files must
  # not block narration-only preview or final generation.
  return

 fields=[]
 if audio_mode=="manual":
  if chapter_based:
   for chapter,override in overrides.items():
    if not isinstance(override,dict) or str(override.get("rule") or "").casefold()!="custom":
     continue
    raw=override.get("path")
    if not raw:
     raise ValueError(f"Chapter {chapter} uses custom BGM but no track is saved. Reassign it in Sound Design.")
    fields.append((raw,"custom BGM for chapter "+str(chapter),None))
  else:
   book_path=state.get("background_audio_path") or state.get("background_audio_preferred_path")
   if book_path:
    fields.append((book_path,"book background music",None))
   ambience=state.get("ambience_audio_path")
   if ambience:
    fields.append((ambience,"book ambience",None))
 elif audio_mode=="auto":
  auto_path=state.get("auto_music_track_path")
  if auto_path:
   fields.append((auto_path,"automatic BGM selection",None))

 for key,label in (
  ("opening_cue_path","opening cue"),
  ("page_turn_cue_path","next-chapter cue"),
  ("ending_cue_path","closing cue"),
 ):
  raw=state.get(key)
  if raw:
   fields.append((raw,label,5.0))

 for raw,label,max_duration in fields:
  path=Path(str(raw)).expanduser()
  if not path.is_file():
   raise FileNotFoundError(f"Saved {label} is missing: {path}. Reassign it in Sound Design.")
  try:
   duration=probe_audio_duration_seconds(path)
  except (ValueError,RuntimeError) as exc:
   raise ValueError(f"Saved {label} is unreadable: {exc}. Reassign it in Sound Design.") from exc
  if max_duration is not None and duration>max_duration:
   raise ValueError(
    f"Saved {label} is {duration:.1f} seconds long. Fixed cue clips must be 5 seconds or shorter; reassign it in Sound Design."
   )
def resolve_cue_track(kind,selected_path=None,*,seed_text=""):
 if selected_path:
  p=Path(selected_path).expanduser()
  if not p.is_file():
   raise FileNotFoundError(f"Selected audiobook cue no longer exists: {p}")
  if p.suffix.casefold() not in AUDIO_EXTENSIONS:
   raise ValueError(f"Selected audiobook cue has an unsupported audio format: {p.name}")
  return p.resolve()
 tracks=list_cue_tracks(kind)
 return tracks[_seed_index(seed_text,len(tracks))] if tracks else None
