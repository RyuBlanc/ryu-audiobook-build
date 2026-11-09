# XAPP-08 — Explicit Narrator-Only Generation

**Implementation branch:** `fix/xapp-08-explicit-narrator-only-2026-11-08`  
**Base:** `82a39ffa2b54b8ce7cab5468affde0cbaf02db0e` (Build Windows App #2905)  
**Implementation checkpoint:** `76f4b5edfedbe25d9af09c07a8fa5add2b022b4b`

This checkpoint implements the explicit per-book narrator-only toggle and its backend persistence, preview routing, and generation contract. It does not close real-audio or full-book runtime acceptance.

The artifact build is intentionally requested separately from ordinary feature commits. This document exists to make the artifact-checkpoint commit unambiguous in the Actions run record.

The Stage 5.3 full-generation preflight also asserts that narrator mode is persisted in project state and exposed in the immediate generation response and durable job result. Real full-book audio and recovery acceptance remain separate.


**Automated evidence:** Build #2911 — SUCCESS, 1,399 tests passed on the implementation checkpoint SHA above. The build job was skipped; this is regression evidence, not a package.


**Current branch tip:** `76f4b5edfedbe25d9af09c07a8fa5add2b022b4b`. This document update is the exact-head artifact-checkpoint trigger.

**Exact package marker commit:** this commit must be used as the build/package source; tests were run immediately before the marker commit without code changes.


**Critical implementation correction:** narrator-only full generation now skips character-profile resolution and `CastAwareProvider` construction. This ensures the selected saved narrator is the only TTS profile used for the book. The new production-path regression test `test_narrator_only_full_generation_bypasses_all_character_profiles` covers this behavior; a fresh matching-head Windows test and package checkpoint is required.

**New regression:** narrator-only full generation must bypass the cast provider, even when Character Studio has an assigned voice. Test: `test_narrator_only_full_generation_bypasses_all_character_profiles`.


**Current implementation source:** `76f4b5edfedbe25d9af09c07a8fa5add2b022b4b`. **Exact-head package marker follows this record update.**


## Recovery-reentry implementation and matching-head regression — 9 November 2026

**Current implementation branch:** `stage-5/xapp08-recovery-reentry-2026-11-08`  
**Verified source commit:** `b9ce3be284718a03edabaeecf9e788cfb35c1084`  
**Matching workflow:** [Build Windows App #2983](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/42548758031) — SUCCESS

### Implemented and regression-verified

- Narrator-only remains an explicit per-book setting and is eligible only when the project has zero valid saved character voice-profile assignments.
- A stale or unavailable character-profile name is not counted as a configured valid profile for narrator-only eligibility; the reference remains reported as an assignment issue in cast-aware mode.
- If a valid character voice profile is added after narrator-only was enabled, the resolver persists narrator-only OFF, returns to strict multi-character speaker review and explains why generation is blocked.
- Production Preview and full-book generation use the shared narrator/mode resolver. Narrator-only preview sets character-cast routing OFF; the saved narrator remains authoritative.
- The immediate full-generation response, project state and durable job result expose the same generation mode, narrator-only flag and configured character-profile count.
- Production project readiness consumes the canonical revision-aware passage index. Dashboard and Production gates use backend-derived index readiness, review state, assignment issues, pending/conflicting passages and index issues. A stale narrator-only flag cannot make the Dashboard green when a valid character voice profile is present.
- Legacy Qwen profile backend values (including the incorrect provider ID stored in the compute-backend field) migrate to canonical `automatic` and are atomically persisted on profile load; supported explicit compute backends are preserved. Qwen profile saves also normalize the backend.

### Exact-head automated evidence

- #2968 — 1,432 regression tests passed.
- #2970 — 1,433 regression tests passed, including persisted legacy Qwen backend migration.
- #2981 — 1,436 regression tests passed; Generation job identity contract.
- #2982 — 1,436 regression tests passed; Dashboard readiness fail-closed implementation.
- #2983 — 1,436 regression tests passed; Dashboard stale narrator-only regression.
- #2981–#2983 also passed frontend JavaScript syntax, isolated native Qt lifecycle, and the focused 45-test History/Task Manager and UI preflight.

The earlier #2954–#2959 and #2969–#2980 failures remain visible historical attempts; only the later matching-head successes above are accepted as passing evidence.

### Acceptance still open — do not infer from regression CI

- A matching-head `[artifact-checkpoint]` run must freeze the current source, pass packaged Windows acceptance and upload installer/portable/SHA-256 artifacts.
- Run the full narrator-only and multi-character book flows in the frozen app, including actual voice output, interruption, pause/resume, cancel, retry/recovery, M4B metadata/chapter checks and Audiobooks playback/seek.
- Dedicated self-hosted NVIDIA and AMD/Intel Qwen preview acceptance is still required. The dedicated hardware runs must produce real inference/device/timing artifacts; synthetic accelerator tests or a hosted CPU run are not hardware proof.
- The Qwen 30-second preview target under 60 seconds is **not met** by previously measured 1.7B CPU previews (approximately 268–305 seconds). No matching-head physical NVIDIA/AMD/Intel result currently proves the target.
- Validate the actual saved novel's dialogue-count reconciliation and character identity; verify real multilingual pronunciation and Sound Design mix audibly in Production and final output.
- Complete the target-PC cold-scan/concurrent-preview responsiveness check and full Premium V2 display/DPI/multi-monitor/Help & Guide acceptance.

### Integration and release boundary

The current recovery branch is a direct descendant of PR #31's head `82a39ffa2b54b8ce7cab5468affde0cbaf02db0e` (94 commits ahead, zero behind at this checkpoint). PR #31 remains open and draft; do not merge a second divergent branch or duplicate its integration work. The version remains 1.1.1 until the frozen Master acceptance gates pass; 1.2.0 is not approved for release by this checkpoint.
