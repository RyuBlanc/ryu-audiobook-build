# Artifact Checkpoint 3143 — Production Narrator-Only Clarity

This exact-head artifact checkpoint verifies the latest packaged Production acceptance repair.

## User-facing correction
- When a book has zero configured character voice profiles and a valid available narrator, Production automatically enables narrator-only generation.
- Production now states explicitly: "Automatically enabled because this book has no configured character voice profiles · the saved narrator reads all narration and dialogue."
- Manual narrator-only selection, user opt-out, unavailable narrator state and multi-character routing messages remain distinct.
- The packaged GEN-07 acceptance checks the exact visible explanation and then performs an actual narrator-only generation workflow.

## Preserve previous integrated repairs
- Preserve the original static seven-stage Help Guide and its current GEN-07/Qwen/M4B/hardware guidance.
- Preserve the separate chapter-BGM paragraph/ten-second offset verification.
- Preserve Production preview, metadata, cover handling, job lifecycle and output ownership.
- Preserve Sound Design, Music Library, cue import/playback, and chapter assignments.
- Preserve full-book M4B generation, chapter markers, player, history and recovery checks.
- Preserve transparent logo/ICO, shell icon identity and installer layout fixes.
- Preserve all Qwen model, saved-profile, cancellation and GPU selection implementation without changing model quality or accelerator policy.

## Required gates
1. Full regression suite and JavaScript syntax validation.
2. Frozen Windows EXE build/startup and bundled asset/module checks.
3. External Qwen runtime import and simulated accelerator smoke.
4. Packaged static Help Guide, Sound Design/Music Library, Production, narrator-only GEN-07, full-book generation, M4B, player and history acceptance.
5. Inno Setup and functional HTML installer build/startup.
6. Install, launch, upgrade and uninstall.
7. PNG/ICO transparency and Windows shell icon checks.
8. Microsoft Defender scan, SHA-256/size manifest and installer/portable artifact upload.

Physical GPU inference, saved-profile voice listening, 10-/30-second Qwen timing and target-PC DPI/multi-monitor checks remain separate manual/device gates and must not be inferred from simulated CI.
