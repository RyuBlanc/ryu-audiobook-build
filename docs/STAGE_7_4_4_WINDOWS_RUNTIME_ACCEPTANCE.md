# Stage 7.4.4 — Windows Runtime Acceptance Record

**Project:** Ryu's Audiobook  
**Branch:** `fix/import-qa-speaker-hover-hardware`  
**Acceptance date:** 2026-10-19  
**Evidence type:** User-reported manual smoke-test results  
**Related CI build:** [Windows Build #491](https://github.com/RyuBlanc/ryu-audiobook-build/actions/runs/39155353968)  
**Build commit:** `e1f7c8a7044772bda06fc80ccd982958fdbd1858`

## Result

The user reported PASS for all seven Stage 7.4.4 Windows smoke-test checks. On that basis, Stage 7.4.4 is accepted as user-tested for the tested machine/build. These are user-reported results, not independently observed by CI. They do not establish compatibility with every supported PC/GPU configuration.

## Manual smoke-test checklist

- [x] **Installer:** installed and launched without Python or developer tools.
- [x] **Portable build:** extracted to a separate folder and launched without installing.
- [x] **Navigation and UI:** Generate, Library, Voice Studio and Settings opened; no inaccessible menus or clipped controls were reported.
- [x] **Voice preview:** selected a voice, generated a preview, and verified in-app playback, pause and stop.
- [x] **M4B generation:** generated a short multi-chapter book and verified chapter navigation, title, author, cover and audio playback.
- [x] **Local-first behavior:** existing local projects and custom voice references remained accessible; offline behavior was handled honestly.
- [x] **Cleanup safety:** uninstall did not unexpectedly delete user books or generated audiobooks.

## Acceptance boundary / remaining release gates

Stage 7.4.4 acceptance covers the above smoke test only. Do not interpret it as full release certification. Remaining work includes:

1. Stage 8: regressions and end-to-end reliability for custom voice persistence/propagation, character detection and assignment, mixed empty-chapter handling, preview target durations, accurate progress/elapsed/ETA, and long-book resume/stale-chunk invalidation.
2. Confirm the complete HTML-referenced UI and all navigation destinations against the acceptance checklist.
3. Verify measured output bitrate, duration and chapter timing across representative inputs; the automated M4B test passed in Build #491.
4. Test both target GPU configurations (RTX 3050 4 GB and RTX 4060 8 GB) and CPU/DirectML fallback where supported.
5. Confirm the final release candidate's exact commit passes CI and that its installer/portable build are the ones tested.

## Next stage

**Stage 8 — Final application completion and release hardening.**

Begin with the remaining Priority 0 critical workflows, add/strengthen automated regression coverage, run the Windows build, and fix any failing tests before proceeding to full UI parity and release cleanup. Do not claim the application is bug-free; document and verify each release gate.
