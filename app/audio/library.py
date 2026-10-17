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
import shutil
import sys
from app.core.paths import audio_library_root

AUDIO_EXTENSIONS={".wav",".mp3",".m4a",".aac",".flac",".ogg",".opus",".wma"}
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

def license_note_for(path):
 try:
  data=json.loads(_metadata_path(path).read_text(encoding="utf-8"))
  return str(data.get("license_note") or data.get("source_note") or "")
 except (OSError,ValueError,TypeError): return ""

def import_audio_files(files,*,target_kind,category="universal",license_note=""):
 target=str(target_kind or "").strip().casefold()
 destination=music_category_root(category) if target=="music" else cue_category_root(target)
 note=str(license_note or "").strip()
 added=[]
 for raw in files:
  source=Path(raw).expanduser()
  if not source.is_file() or source.suffix.casefold() not in AUDIO_EXTENSIONS: continue
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
  except OSError: pass
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
  if p.is_file() and p.suffix.casefold() in AUDIO_EXTENSIONS:return p.resolve()
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

def resolve_cue_track(kind,selected_path=None,*,seed_text=""):
 if selected_path:
  p=Path(selected_path).expanduser()
  if p.is_file() and p.suffix.casefold() in AUDIO_EXTENSIONS:return p.resolve()
 tracks=list_cue_tracks(kind)
 return tracks[_seed_index(seed_text,len(tracks))] if tracks else None
