# XAPP-08 — Explicit Narrator-Only Generation

**Implementation branch:** `fix/xapp-08-explicit-narrator-only-2026-11-08`  
**Base:** `82a39ffa2b54b8ce7cab5468affde0cbaf02db0e` (Build Windows App #2905)  
**Implementation checkpoint:** `c881d9349a48208d5deeac1b6e0f85101d467eb5`

This checkpoint implements the explicit per-book narrator-only toggle and its backend persistence, preview routing, and generation contract. It does not close real-audio or full-book runtime acceptance.

The artifact build is intentionally requested separately from ordinary feature commits. This document exists to make the artifact-checkpoint commit unambiguous in the Actions run record.

The Stage 5.3 full-generation preflight also asserts that narrator mode is persisted in project state and exposed in the immediate generation response and durable job result. Real full-book audio and recovery acceptance remain separate.


**Automated evidence:** Build #2911 — SUCCESS, 1,399 tests passed on the implementation checkpoint SHA above. The build job was skipped; this is regression evidence, not a package.


**Current branch tip:** `c881d9349a48208d5deeac1b6e0f85101d467eb5`. This document update is the exact-head artifact-checkpoint trigger.

**Exact package marker commit:** this commit must be used as the build/package source; tests were run immediately before the marker commit without code changes.


**Critical implementation correction:** narrator-only full generation now skips character-profile resolution and `CastAwareProvider` construction. This ensures the selected saved narrator is the only TTS profile used for the book. The new production-path regression test `test_narrator_only_full_generation_bypasses_all_character_profiles` covers this behavior; a fresh matching-head Windows test and package checkpoint is required.
