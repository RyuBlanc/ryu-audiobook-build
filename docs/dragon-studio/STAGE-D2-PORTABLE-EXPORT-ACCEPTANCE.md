# Stage D2 — Portable Qwen Profile Export Acceptance Record

Stage: D2 — portable profile export and bundle validation
Branch: dragon-studio/stage-d-qwen-voice-profile-library-2026-11-14
Stage C baseline: 154bf0e0c1c1fe8334f68655d1629a3a9d1e3691
Current source head: 18e5391c2d42d18afb8d830ffee114746febdc38
Status: source implementation and hosted test gates passed; exact-head Windows artifact checkpoint pending

## 1. Deliverable

D2 adds a Qwen-only portable profile exporter and archive inspector in app/tts/qwen_profile_bundle.py.

- Container: ZIP
- User-facing extension: .ryuvoice
- Format identifier: ryu.qwen-voice-profile-bundle
- Bundle format version: 1
- Profile schema version: 1
- Integrity: SHA-256 for every profile and asset payload
- No Qwen model weights, private Python runtime, PyTorch runtime or GPU driver is included.

The exporter does not import or install profiles. Transactional import, conflict resolution and catalogue changes remain D3. Voice Library UI and actions remain D4.

## 2. Profile and asset fidelity

The exporter accepts Qwen CustomVoice, VoiceDesign and Clone profiles and preserves their saved profile fields, stable qwen_profile_id, revision fingerprint and model-role compatibility metadata.

Assets:
- Clone: the exact active normalized conditioning WAV referenced by sample_path; original source recordings found beside it are included as sidecars when present.
- VoiceDesign: the exact explicit neutral anchor when qwen_anchor_path is set; otherwise the existing worker-derived neutral anchor is located using the same shared cache-path function used by the Qwen worker.
- If a derived anchor is not found at its deterministic cache location, the bundle reports not_found_in_source_cache. It does not claim that the anchor was never generated and does not synthesize a new anchor during export.
- CustomVoice profiles normally have no profile-owned audio asset.

The worker and exporter share qwen_design_anchor_cache_path() and QWEN_EXPRESSION_BANK_VERSION. This avoids a second anchor path implementation drifting away from the real Qwen runtime.

Portable profile JSON sets machine-local sample_path and qwen_anchor_path values to null. Asset references are relative paths inside the bundle. The source profile objects, catalogue and audio files are not modified by export.

## 3. Archive and integrity protections

The exporter writes to a temporary file, checks that source assets remain byte-identical while copying, inspects the completed archive, and only then atomically replaces the destination. Existing destination files are not overwritten unless the caller explicitly allows it.

The inspector validates:
- recognized bundle identifier and supported bundle/profile versions;
- safe relative paths; no traversal, absolute paths, duplicate names or symlink entries;
- bounded manifest/profile/asset and total expanded sizes, plus compression-ratio limits;
- exact match between listed archive payloads and manifest integrity entries;
- no duplicate asset references and no orphan/unreferenced payload files;
- SHA-256, declared sizes, canonical profile revision fingerprints and Qwen profile IDs;
- model compatibility metadata against the actual profile mode and source preference;
- exactly one required active Clone conditioning WAV for Clone profiles;
- no more than one canonical neutral VoiceDesign anchor;
- readable WAV conditioning/anchor audio and canonical media type.

Current defensive limits: 100 profiles per bundle, 2 MiB manifest, 2 MiB profile record, 512 MiB per asset and 2 GiB total expanded payload; audio member compression ratio is capped at 200 for large members.

## 4. D1/D2 test gates and workflow history

The first D2 candidate exposed three existing source-contract tests that expected the expression-bank constant and voice_anchors path literal to remain physically in qwen_character_worker.py. D2 intentionally centralized that identity calculation in the shared helper. The implementation retained the existing source-contract markers as comments without duplicating the live value or resolver. The failed attempt remains visible and was not relabeled green.

| Build | Commit | Result | Notes |
|---|---|---|---|
| #3430 | 22966e1 | Failed | 16/16 new D2 exporter tests passed; cumulative suite ran 1,621 tests and had three legacy source-text contract failures. |
| #3432 | 7af561a | Passed | Restored source-contract markers; full regression 1,621/1,621. |
| #3433 | 16e5fdb | Passed | Explicit D1/D2 CI step added; 29/29 focused schema/bundle tests; full regression 1,624/1,624. |
| #3434 | 40d60ec | Passed | 29/29 focused tests; full regression 1,625/1,625; no artifact build was requested on this ordinary commit. |
| #3435 | 18e5391 | Passed | 29/29 focused tests; full regression 1,625/1,625. Added physical bundling of both shared Qwen helper modules and package-time hash checks in the subsequent source head. |

The 29 focused tests comprise nine D1 schema tests and 20 D2 bundle/export tests. The D2 cases cover CustomVoice, Clone, Clone sidecar byte fidelity, explicit/derived VoiceDesign anchors, multilingual/Unicode metadata, multiple profiles, stable revision hashes, invalid/future schemas, missing/invalid references, overwrite safety, duplicate IDs/assets, archive traversal, corrupt payloads, orphan files, model-compatibility mismatch and standalone-worker helper packaging.

## 5. Standalone Qwen worker package dependency

The Qwen worker runs in an external Python process. It imports app.tts.qwen_profile_schema, which in turn imports the pure preference normalizer from app.tts.qwen_model_preference. PyInstaller's regular module collection does not make source modules available to this separate interpreter.

The Windows build now physically copies both files beside qwen_character_worker.py under app/tts, and package acceptance compares their SHA-256 values with repository source. The existing standalone-worker smoke removes PYTHONPATH before launching the packaged worker with --help; it must pass to clear the package gate.

## 6. Final D2 acceptance still pending

The current source/test head is 18e5391c2d42d18afb8d830ffee114746febdc38. The final artifact-checkpoint Build Windows App run must pass:
- explicit focused Stage D schema and bundle tests;
- full regression;
- frozen application build;
- physical Qwen helper source/hash checks;
- standalone packaged worker launch without PYTHONPATH;
- installer, HTML installer, install/launch/upgrade/uninstall, Defender and artifact/hash checks.

D2 is not declared complete until that exact-head Windows package run passes. Even after it passes, D2 acceptance does not claim that import, UI or two-PC transfer is complete.

## 7. Out of scope / next stages

- D3: validated, additive, transactional import; path and archive safety; profile collision/revision decisions; rollback and restart recovery.
- D4: Voice Library UI, profile grouping/search/model filters, compatibility display and import/export actions.
- D5: exact-head cumulative regression and packaged end-to-end import/export acceptance.
- D6: transfer real saved profiles between two PCs and verify IDs, settings, exact assets and resulting voice consistency.

No application profile catalogue or source user asset is modified by D2 export.
