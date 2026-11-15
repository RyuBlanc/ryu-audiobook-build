# Stage D2 — Portable Qwen Profile Export Acceptance Record

Stage: D2 — portable profile export and bundle validation
Branch: dragon-studio/stage-d-qwen-voice-profile-library-2026-11-14
Stage C baseline: 154bf0e0c1c1fe8334f68655d1629a3a9d1e3691
Current accepted source head: 06895803d859e748dc8c7292c6a3bfd895af9304
Status: COMPLETE — exact-head Windows artifact checkpoint passed at Build #3436; repeated on the same accepted SHA by Build #3437

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

The first D2 candidate exposed three existing source-contract tests that expected the expression-bank constant and `voice_anchors` path literal to remain physically in `qwen_character_worker.py`. D2 intentionally centralized that identity calculation in the shared helper. The implementation retained the existing source-contract markers as comments without duplicating the live value or resolver.

| Build | Commit | Result | Notes |
|---|---|---|---|
| #3430 | `22966e1` | Failed | 16/16 new D2 exporter tests passed; cumulative suite ran 1,621 tests and had three legacy source-text contract failures. |
| #3431 | `a60dc9d` | Failed | The full suite again failed on the same three legacy worker source-contract assertions. The WAV media-type change in the commit title was not the cause shown by the test log. |
| #3432 | `7af561a` | Passed | Restored source-contract markers; full regression 1,621/1,621. |
| #3433 | `16e5fdb` | Passed | Explicit D1/D2 CI gate added; 29/29 focused schema/bundle tests; full regression 1,624/1,624. |
| #3434 | `40d60ec` | Passed | 29/29 focused tests; full regression 1,625/1,625; no artifact build was requested on this ordinary commit. |
| #3435 | `18e5391` | Passed | 29/29 focused tests; full regression 1,625/1,625. Added physical bundling of both shared Qwen helper modules and package-time hash checks in the subsequent source head. |
| #3436 | `0689580` | **Passed — final D2 artifact checkpoint** | 29/29 focused tests; 1,625/1,625 full regression; Windows package, standalone worker, installer, install/launch/upgrade/uninstall, Defender and all expected artifacts passed. |
| #3437 | `0689580` | **Passed — repeat artifact checkpoint** | Same exact D2 source SHA; 29/29 focused tests; 1,625/1,625 full regression; Windows installer/portable/manifest/M4B/benchmark artifacts uploaded. This is a second run on the accepted D2 source, not a new code head. |

The 29 focused tests comprise nine D1 schema tests and 20 D2 bundle/export tests. The D2 cases cover CustomVoice, Clone, Clone sidecar byte fidelity, explicit/derived VoiceDesign anchors, multilingual/Unicode metadata, multiple profiles, stable revision hashes, invalid/future schemas, missing/invalid references, overwrite safety, duplicate IDs/assets, archive traversal, corrupt payloads, orphan files, model-compatibility mismatch and standalone-worker helper packaging.

## 5. Standalone Qwen worker package dependency

The Qwen worker runs in an external Python process. It imports app.tts.qwen_profile_schema, which in turn imports the pure preference normalizer from app.tts.qwen_model_preference. PyInstaller's regular module collection does not make source modules available to this separate interpreter.

The Windows build now physically copies both files beside qwen_character_worker.py under app/tts, and package acceptance compares their SHA-256 values with repository source. The existing standalone-worker smoke removes PYTHONPATH before launching the packaged worker with --help; it must pass to clear the package gate.

## 6. Final D2 hosted artifact acceptance — COMPLETE

Accepted D2 source SHA: `06895803d859e748dc8c7292c6a3bfd895af9304`.

Build Windows App **#3436** / [run 43671334770](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43671334770) passed both jobs on the exact accepted D2 head:
- Focused D1/D2 schema and bundle tests: **29/29**.
- Full regression: **1,625/1,625**.
- Frozen application, voice assets, Qwen standalone-worker helper source/hash checks, and standalone `qwen_character_worker.py --help` launch with `PYTHONPATH` removed.
- Real bundled-Piper multi-chapter M4B and packaged Sound Design/Music Library acceptance.
- Core and HTML installer, HTML installer startup, install/launch/upgrade/uninstall, branding transparency/hash checks, package-size report and Microsoft Defender scans.
- Installer, portable, release SHA manifest, M4B and Stage 7 benchmark artifacts uploaded.

Build Windows App **#3437** / [run 43676558316](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/43676558316) repeated the same exact SHA `0689580` checkpoint and completed successfully. It provides a second artifact set; it does not change the accepted D2 code head.

### Build #3436 artifacts

| Artifact | ID | Size (bytes) | GitHub artifact ZIP digest |
|---|---:|---:|---|
| Installer | `14145491117` | 847,191,828 | `sha256:b756853364102119a92a3fa1163605be810b5da520ece51914f0c7d687bcd46a` |
| Portable | `14145530088` | 1,190,907,115 | `sha256:e7a98198b097bcc14be2f6761ebddaa81dabf366c58c6f123a6e02d29df8159f` |
| Release SHA-256 manifest | `14145202810` | 3,050 | `sha256:c4064b6bbf3817f576985ccbfce40322644077b5428cfbecc2c09f9944228af0` |
| Real multi-chapter M4B | `14145285194` | 8,988,945 | `sha256:f267a06223e86f2f2857bb075912150d247bf62672ee38517fd782305a8a1a5f` |
| Stage 7 Piper benchmark | `14144822662` | 804 | `sha256:36e1e49128da636b863c2dacc6f157702900ffd309ed15fdb6cfaf05de678c68` |

### Build #3437 artifacts

| Artifact | ID | Size (bytes) | GitHub artifact ZIP digest |
|---|---:|---:|---|
| Installer | `14147582177` | 847,239,315 | `sha256:68f2c2508e037b532dbb999c3e24fb3b57fefc5d6f1b9ccb41ddb049217eb6a1` |
| Portable | `14147452566` | 1,190,907,115 | `sha256:91fa9a26e813c3e4e9638b8172add27e633cb53a57269f4c575ef94427839310` |
| Release SHA-256 manifest | `14146799665` | 3,053 | `sha256:81adbf92d9bce913bf881a73d2e1e81417aaaa51c2b239e8a5c5772985295bd4` |
| Real multi-chapter M4B | `14146609762` | 8,977,778 | `sha256:442a918ee7ea9b6f616e3fad4937d4b19d438a7262f3911a70a34019ab6c9a18` |
| Stage 7 Piper benchmark | `14147532383` | 800 | `sha256:46aa907223d3dc356c09d2e5b8a1c6dba0c92191e0e522e0edc053f17bdd32d7` |

The digests above identify the uploaded GitHub artifact ZIPs. The application/installer file hashes are recorded inside each run's release SHA-256 manifest. Artifacts are retained by GitHub Actions until their configured expiry; these runs reported an expiry of 15 December 2026.

D2 acceptance does **not** claim that import, the Voice Library UI, packaged import/export round-trip, or two-PC transfer is complete. Those remain D3, D4, D5 and D6 respectively.

## 7. Out of scope / next stages

- D3: validated, additive, transactional import; path and archive safety; profile collision/revision decisions; rollback and restart recovery.
- D4: Voice Library UI, profile grouping/search/model filters, compatibility display and import/export actions.
- D5: exact-head cumulative regression and packaged end-to-end import/export acceptance.
- D6: transfer real saved profiles between two PCs and verify IDs, settings, exact assets and resulting voice consistency.

No application profile catalogue or source user asset is modified by D2 export.
