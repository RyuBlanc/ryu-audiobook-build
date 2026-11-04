# Stage 5.5 — Final M4B Assembly, Validation and Audiobooks Library Integration

## Baseline and branch

- Accepted Stage 5.4 application checkpoint: `8132097b6028a17d44ddc2f03c8f514d4cd88598`.
- Stage 5.4 closeout documentation checkpoint: `c300e2039d469b54a11a759fdba8d045393ed4b5`.
- Stage 5.4 Windows artifact checkpoint: [Build Windows App #2235](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41755362901).
- Stage 5.4 closeout regression: [Build Windows App #2236](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/41758947383).
- Stage 5.5 branch: `stage-5/step-5-m4b-library-integration`.
- All Stage 5.5 changes are isolated from the accepted Stage 5.4 branch and artifacts.

## Scope

Stage 5.5 closes the final-output and Audiobooks handoff boundary retained in the Stage 5.4 closeout:

- GEN-05: a real chaptered M4B with validated full audio stream, encoded bitrate, chapter titles/timing, required metadata tags and embedded cover.
- PROD-04: verify persisted project metadata, series volume and cover are reflected in the final output file.
- Audiobooks Library: show only completed outputs owned by a saved project; open the exact output file; read actual embedded chapter markers; play and seek chapters; persist listening position against the same project.
- Cross-surface consistency: Generation job, History, saved project output, Audiobooks library item and final file must share one project/output identity.
- Preserve the existing Premium V2 playback flow and FFmpeg assembler; extend validation and acceptance rather than replacing these components.

## Existing implementation retained

The starting source already contains:
- FFmpeg chapter assembly, AAC encoding, metadata mapping and attached JPEG cover muxing in `app/audio/assembler.py`.
- Full primary audio-stream decode validation and a 128 kbps minimum encoded bitrate check.
- The Premium V2 `player.get_active` bridge, which reads chapter markers from the actual M4B probe output.
- Premium V2 Audiobooks library rendering, real file playback, chapter seeking, playback-rate/volume controls and project-scoped playback-position persistence.

## Acceptance gates

1. Assembler must fail closed when any supplied final tag is missing or wrong, chapter count/title/timing is invalid, required cover art is absent, the audio stream cannot be fully decoded, or the measured bitrate falls below 128 kbps.
2. A real FFmpeg output test must include title, author, narrator, publisher, series, series number, language, year, genre, description, two chapter markers and attached cover.
3. Frozen Windows acceptance must read actual timed chapter markers back from the generated M4B through `player.get_active`.
4. Frozen Windows acceptance must open the finished item in Premium V2 Audiobooks, play the real file, seek to its embedded second chapter and confirm listening position persists to the owning project.
5. Exact-commit regression and Windows artifact-checkpoint acceptance must pass. Any failed/cancelled candidate run must be reconciled; do not treat a skipped build or static UI assertion as packaged runtime proof.

## Status

**IN PROGRESS — implementation and acceptance being added.**

Manual listening on the user's own device remains a separate perceptual/hardware check. No version tag or public release is part of Stage 5.5.
