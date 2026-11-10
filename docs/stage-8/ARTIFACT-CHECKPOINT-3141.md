# Artifact Checkpoint 3141 — Help Guide and Integrated Release Candidate

This exact-head checkpoint validates the packaged Windows build after aligning Help Guide acceptance with the approved static Premium V2 guide.

## Help Guide acceptance
- Preserve the original detailed static seven-stage Help Guide.
- Validate its real topic headings and shipped wording: M4B output, narrator-only GEN-07, zero configured character voice-profile eligibility, Qwen acceleration verification, isolated Qwen runtime self-test, and explicit GPU-selection failure behavior.
- Do not require fallback-only labels from the static guide. The fallback guide remains separately checked for its search, no-results, expand/collapse and current limitations behavior.
- The Sound Design packaged acceptance independently validates the actual Chapter BGM offset selector and persisted `after_first_paragraph` setting.

## Protected Qwen/GPU work
- Preserve Qwen 0.6B/1.7B selection, saved-profile identity, CustomVoice/VoiceDesign/Clone routing, cancellation and accelerator-selection policy.
- This checkpoint may validate the isolated Qwen runtime import and simulated CUDA selection, but must not claim physical NVIDIA/AMD/Intel inference without the dedicated hardware runners.
- Do not modify Qwen model-quality settings or silently change the user's selected compute backend.

## Integrated repairs to package and verify
- Production Studio ordering, preview, metadata, artwork/cover behavior and job-state feedback.
- Uploaded cover art must not receive a placeholder watermark overlay; retain the clean branded empty-cover state when no image is supplied.
- Smooth startup/refresh and responsive layout safeguards.
- Transparent PNG/ICO, app/setup/taskbar shell identity and compact centered/resizable installer.
- Help Guide, Sound Design/Music Library and Stage 5.3 generation UI acceptance.
- Windows installer and portable package, functional HTML installer startup, real install/launch/upgrade/uninstall, user-data preservation, logo transparency, SHA-256/size manifest, Microsoft Defender scan and artifact upload.

## Required gates
1. Full regression suite and frontend syntax checks.
2. Frozen Windows EXE build/startup and bundled offline voice/model validation.
3. External Qwen runtime import and simulated accelerator smoke.
4. Packaged Help Guide and complete Sound Design/Music Library/Production acceptance.
5. Inno Setup and functional HTML installer generation and startup.
6. Install, launch, upgrade and uninstall.
7. PNG/ICO transparency and Windows shell icon checks.
8. Microsoft Defender scan, SHA-256/size report and installer/portable artifact upload.

CI does not replace target-device listening, physical GPU inference, full-book audio acceptance or the 41-viewport/DPI/multi-monitor manual matrix.
