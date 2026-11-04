# Stage 5.5 — Final M4B Assembly, Validation and Audiobooks Library Integration

## Baseline and branch

- Accepted Stage 5.4 application checkpoint: `8132097b6028a17d44ddc2f03c8f514d4cd88598`.
- Stage 5.4 closeout documentation checkpoint: `c300e2039d469b54a11a759fdba8d045393ed4b5`.
- Stage 5.4 Windows artifact checkpoint: [Build Windows App #2235](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41755362901).
- Stage 5.4 closeout regression: [Build Windows App #2236](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41758947383).
- Stage 5.5 branch: `stage-5/step-5-m4b-library-integration`.
- Stage 5.5 current application candidate: `5d620525e98668fede228cd19b3836078346152f`.
- Matching regression workflow: [Build Windows App #2252](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41769708812).
- All Stage 5.5 changes remain isolated from the accepted Stage 5.4 branch and artifacts.

## Scope

Stage 5.5 closes the final-output and Audiobooks handoff boundary retained in the Stage 5.4 closeout:

- GEN-05: a real chaptered M4B with a fully decodable AAC stream, encoded bitrate, chapter titles/timing, required metadata tags and embedded cover.
- PROD-04: verify persisted project metadata, series volume and cover are reflected in the final output file.
- Audiobooks Library: show completed outputs owned by saved projects; open the exact output; read actual embedded chapter markers; play and seek chapters; persist listening position against the same project.
- Cross-surface consistency: Generation job, History, saved project output, Audiobooks library item and final file share one project/output identity.
- Preserve the existing Premium V2 playback flow and FFmpeg assembler; extend validation and acceptance rather than replacing these components.

## Implementation now present

- FFmpeg produces the final M4B with the audio stream, chapter metadata and attached JPEG cover in the known-good `+faststart` mux path. The `+use_metadata_tags` path was dropped because the Windows probe showed it emitted audio plus chapter data but no MJPEG cover stream.
- Mutagen (`mutagen>=1.47,<2`) writes standard MP4 atoms and iTunes freeform audiobook fields in-place after the final cover-bearing M4B is assembled. No second FFmpeg stream remux is used for custom tags.
- Standard atoms include title, album, artist, genre, date, description, publisher copyright and series grouping. Freeform fields include narrator, publisher, series and series number.
- The final-file validator reads the saved MP4 tags back, checks the audio-track language, requires the expected chapter count/titles and valid contiguous timing, requires an attached MJPEG cover stream, decodes that cover stream, fully decodes the AAC audio and enforces the 128 kbps minimum bitrate.
- Coverless preview/test-double assembly paths do not invoke the final-book MP4 tag writer or final-book metadata/cover gate.
- Qt WebEngine may not have an AAC decoder. The authoritative chaptered AAC M4B therefore remains the Audiobooks library/download file, and a cached MP3 derivative is prepared for HTMLAudioElement playback. The derivative is keyed to the source M4B path, size and mtime, checked for duration parity and full decode, and never replaces or rewrites the M4B.
- New full-generation jobs prepare the playback derivative in the GenerationManager completion worker before the project/job is published as completed. Older existing M4B projects are supported by a validated lazy-cache path on first open.
- The Premium V2 player receives the playback derivative URL but obtains embedded chapter markers from the original M4B. Chapter seeking therefore continues to use the original M4B timing table; listening position continues to persist against the owning project.

## Regression evidence

- [Run #2250](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41763886592) — SUCCESS on source `9234cd4a...`; 1,138 tests in 52.028 seconds.
- [Run #2252](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41769708812) — SUCCESS on exact source `5d620525...`; **1,141 tests in 54.048 seconds**.
- Both runs passed frontend JavaScript syntax validation and isolated native Qt lifecycle regression.
- #2252 added and passed three playback-source tests: preserve the original M4B while creating and caching a real MP3 copy; reuse browser-supported source formats without re-encoding; reject invalid MP4/M4B files.
- The full M4B fixture still verifies title, author, narrator, publisher, series, series number, language, year, genre, description, two embedded chapter markers, attached MJPEG cover, image decode and full AAC decode.
- Run #2252 was regression-only; its Windows Build job was skipped by the artifact-checkpoint policy. It is not packaged acceptance and produced no installer/portable/hash artifacts.

## Failed candidate runs — root causes and reconciliation

| Run | Candidate / observed issue | Root cause and correction |
|---|---|---|
| #2238 | Early validator produced multiple assembler test errors | Generated regex source was double-escaped; corrected on following candidate. |
| #2239 | Coverless mocked preview paths reached the final M4B validator; custom tags were also lost through FFmpeg remux | Final-book validation was scoped to cover-bearing outputs; metadata remux behavior was investigated. |
| #2240–#2241 | Language tag assertion failed | FFmpeg exposes language on the audio stream header; output now writes and validates an ISO-639-2 stream language code. |
| #2242–#2246 | Cover probe failed or parser patterns were malformed; actual file contained only AAC and chapter data, no MJPEG image | The `+use_metadata_tags` path lost the cover stream. Restored the known-good `+faststart` mux and validated attached-picture disposition plus image decode. |
| #2247 | Cover restored but custom narrator tag was dropped by the standard MP4 muxer | Write the custom audiobook atoms in-place with Mutagen. |
| #2248 | Mutagen path tried to tag mock preview outputs and a test expected stream labels not retained by in-place tagging | Scope Mutagen to cover-bearing final books; validate attached-picture disposition and successful image decode. |
| #2249 | Test raised `NameError: re is not defined` | Add the missing test import; #2250 passed the complete suite. |
| #2251 | Windows freeze and frozen-app verification passed; GEN-05 embedded chapter check passed; actual Audiobooks playback timed out before seeking/position persistence | FFmpeg AAC M4B was sent directly to Qt WebEngine HTML Audio, whose packaged Chromium runtime did not play the AAC source. Preserve the M4B and prepare a verified browser-compatible MP3 playback derivative. |
| #2252 | Regression-only playback compatibility candidate | **SUCCESS** — 1,141 tests; conversion, duration, decode, cache reuse and source immutability checks passed. |

All failed runs remain historical. None was manually cancelled or counted as a successful checkpoint. #2251 produced no installer, portable app or SHA-256 artifact because packaged acceptance failed.

## Windows artifact acceptance — pending

The next exact-head `[artifact-checkpoint]` workflow must run the frozen Windows application and prove all Stage 5.5 markers:

1. `stage55_final_m4b_embedded_chapters` — actual embedded chapter titles and contiguous timing read back from the original M4B.
2. `stage55_browser_compatible_playback_source` — the Audiobooks backend returns a cached playback derivative linked to the exact authoritative M4B source.
3. `stage55_audiobooks_real_playback_chapter_seek_and_position` — real audio plays in the packaged Audiobooks page, chapter navigation seeks to the second embedded M4B marker and listening position persists to the owning project.
4. Preserve the prior Stage 5.4 packaged generation, job ownership, Retry and restart-recovery acceptance.

The installer, portable package and SHA-256 manifest must be created only after the exact-head packaged acceptance passes. No version tag or public release is part of Stage 5.5.

## Status

**REGRESSION GREEN — WINDOWS PACKAGED ACCEPTANCE PENDING.**

Manual listening on the user's own device remains a separate perceptual/hardware check. It is not claimed by automated CI.
