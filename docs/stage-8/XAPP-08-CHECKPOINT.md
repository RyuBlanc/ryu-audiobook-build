# XAPP-08 — Explicit Narrator-Only Generation

**Implementation branch:** `fix/xapp-08-explicit-narrator-only-2026-11-08`  
**Base:** `82a39ffa2b54b8ce7cab5468affde0cbaf02db0e` (Build Windows App #2905)  
**Implementation checkpoint:** `57c92bbd3d7cbba88b5a031ab88c4be987ae049b`

This checkpoint implements the explicit per-book narrator-only toggle and its backend persistence, preview routing, and generation contract. It does not close real-audio or full-book runtime acceptance.

The artifact build is intentionally requested separately from ordinary feature commits. This document exists to make the artifact-checkpoint commit unambiguous in the Actions run record.

The Stage 5.3 full-generation preflight also asserts that narrator mode is persisted in project state and exposed in the immediate generation response and durable job result. Real full-book audio and recovery acceptance remain separate.
