# Stage 5.5 — Final M4B Assembly, Validation and Audiobooks Library Integration

## Baseline and branch

- Accepted Stage 5.4 application checkpoint: `8132097b6028a17d44ddc2f03c8f514d4cd88598`.
- Stage 5.4 closeout documentation checkpoint: `c300e2039d469b54a11a759fdba8d045393ed4b5`.
- Stage 5.4 Windows artifact checkpoint: [Build Windows App #2235](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41755362901).
- Stage 5.4 closeout regression: [Build Windows App #2236](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41758947383).
- Stage 5.5 branch: `stage-5/step-5-m4b-library-integration`.
- Stage 5.5 tested source checkpoint: `9234cd4a9da632050dbfac873975fd05051bd343`.
- Matching regression workflow: [Build Windows App #2250](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41763886592).
- All Stage 5.5 changes remain isolated from the accepted Stage 5.4 branch and artifacts.

## Scope

Stage 5.5 closes the final-output and Audiobooks handoff boundary retained in the Stage 5.4 closeout:

- GEN-05: a real chaptered M4B with a fully decodable AAC stream, encoded bitrate, chapter titles/timing, required metadata tags and embedded cover.
- PROD-04: verify persisted project metadata, series volume and cover are reflected in the final output file.
- Audiobooks Library: show completed outputs owned by saved projects; open the exact output; read actual embedded chapter markers; play and seek chapters; persist listening position against the same project.
- Cross-surface consistency: Generation job, History, saved project output, Audiobooks library item and final file share one project/output identity.
- Preserve the existing Premium V2 playback flow and FFmpeg assembler; extend validation and acceptance rather than replacing these components.

## Implementation now present

- FFmpeg produces the final M4B with the audio stream, chapter metadata and attached JPEG cover in the known-good `+faststart` mux path. The previous `+use_metadata_tags` path was dropped because the Windows probe showed it emitted audio plus chapter data but no MJPEG cover stream.
- Mutagen (`mutagen>=1.47,<2`) writes standard MP4 atoms and iTunes freeform audiobook fields in-place after the final cover-bearing M4B is assembled. No second FFmpeg stream remux is used for custom tags.
- Standard atoms include title, album, artist, genre, date, description, publisher copyright and series grouping. Freeform fields include narrator, publisher, series and series number.
- The final-file validator reads the saved MP4 tags back, checks the audio-track language, requires the expected chapter count/titles and valid contiguous timing, requires an attached MJPEG cover stream, decodes that cover stream, fully decodes the AAC audio and enforces the 128 kbps minimum bitrate.
- Coverless preview/test-double assembly paths do not invoke the final-book MP4 tag writer or final-book metadata/cover gate.
- Packaged acceptance now reads chapter markers from the actual completed M4B via `player.get_active`, opens that project in the existing Premium V2 Audiobooks page, starts the real output file, seeks to the second embedded chapter and verifies the listening position persists to the owning project.

## Regression evidence

- [Run #2250](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41763886592) — SUCCESS on exact source `9234cd4a...`.
- **1,138 tests passed** in 52.028 seconds.
- Frontend JavaScript syntax validation passed.
- Isolated native Qt lifecycle regression passed.
- The real FFmpeg M4B fixture passed with title, author, narrator, publisher, series, series number, language, year, genre, description, two embedded chapter markers, attached MJPEG cover, image decode and full AAC decode.
- Run #2250 is a regression-only checkpoint; its Windows Build job was skipped by the artifact-checkpoint policy. It is not Windows packaged acceptance.

## Failed candidate runs — root causes and reconciliation

| Run | Candidate / observed issue | Root cause and correction |
|---|---|---|
| #2238 | Early validator produced multiple assembler test errors | Generated regex source was double-escaped; corrected on following candidate. |
| #2239 | Coverless mocked preview paths reached the final M4B validator; remux also dropped custom tags | Final-book validation was scoped to the cover-bearing output path; metadata remux behavior was investigated. |
| #2240–#2241 | Language tag assertion failed | FFmpeg exposes language on the audio stream header; output now writes and validates an ISO-639-2 stream language code. |
| #2242–#2245 | Cover probe failed or parser patterns were malformed; actual file contained only AAC and a chapter data stream, no MJPEG image | The `+use_metadata_tags` output path lost the cover stream. Restored the known-good `+faststart` mux and verified attached-picture disposition plus image decoding. |
| #2246 | One-pass output still had no MJPEG stream | `+use_metadata_tags` remained the cause; removed it from the final cover mux. |
| #2247 | Attached cover and chapters passed, but custom narrator atom was absent | Standard MP4 muxer dropped custom audiobook tags; introduced in-place Mutagen metadata writing without a stream remux. |
| #2248 | Metadata writing worked on the actual output, but mock preview tests tried to parse fake MP4s and a test checked optional stream labels not preserved by in-place tagging | Scoped Mutagen writer to cover-bearing final books and asserted attached-picture disposition plus successful cover decode. |
| #2249 | One test errored with `NameError: re is not defined` after reaching the M4B validation assertions | Added the missing test import; #2250 passed the complete suite. |

All failed runs remain historical. None was manually cancelled or counted as a successful checkpoint.

## Windows artifact acceptance — pending

Run #2250 established the exact-head regression baseline. The next `[artifact-checkpoint]` workflow must verify the frozen Windows build and execute the Stage 5.5 packaged markers:

1. `stage55_final_m4b_embedded_chapters` — actual embedded chapter titles and contiguous timing read back from the final M4B.
2. `stage55_audiobooks_real_playback_chapter_seek_and_position` — real file playback, seek to the second chapter and persisted project-scoped listening position.
3. Preserve all prior Stage 5.4 packaged generation, job ownership, Retry and restart-recovery acceptance.

The installer, portable package and SHA-256 manifest must be created only after the exact-head packaged acceptance passes. No version tag or public release is part of Stage 5.5.

## Status

**REGRESSION GREEN — WINDOWS PACKAGED ACCEPTANCE PENDING.**

Manual listening on the user's own device remains a separate perceptual/hardware check. It is not claimed by automated CI.
