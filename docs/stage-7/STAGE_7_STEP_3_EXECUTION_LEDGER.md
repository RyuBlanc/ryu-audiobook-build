# Stage 7 — Step 3 Execution Ledger
## Complete Model Lifecycle and Safe Uninstallation

**Project:** Ryu's Audiobook — Dragon Studio Edition  
**Target:** Version 1.2.0  
**Working branch:** \`stage-7/step-2-storage-management\`  
**Accepted predecessor:** Stage 7 Step 2, matching-head package checkpoint #2524  
**Step 3 start:** 6 November 2026

## Scope and acceptance requirements

1. Uninstall one selected Piper voice, including its matching configuration sidecar, without deleting sibling voices or bundled application voices.
2. Uninstall user-installed Kokoro model and voice-pack assets while preserving bundled application assets and unrelated data.
3. Uninstall the shared Chatterbox Python runtime independently from its Hugging Face model cache; preserve cached model assets when removing only the runtime.
4. Provide a separate, user-visible removal action for Chatterbox English/multilingual cached model assets. Remove only Chatterbox-owned Hugging Face cache folders; preserve Qwen and all other providers' cache folders.
5. Uninstall an individual Qwen model folder without removing sibling model weights, the shared Qwen runtime, or voice profiles.
6. Uninstall the Qwen Python runtime independently from Qwen model weights and preserve all model folders.
7. Uninstall Audiobook AI's app-managed runtime/model folder without touching projects, source books, generated audiobooks, saved voices, or other model families.
8. Enforce canonical owned-root boundaries, reject paths outside the component root (including resolved symlink escapes), and never allow deletion of the owned root itself.
9. Refuse lifecycle changes while conflicting preview, generation, analysis, import, or other model lifecycle jobs are active; serialize concurrent model operations.
10. Keep Premium V2 Models Center actions connected to backend commands: explicit destructive confirmation, progress in Background Jobs, disabled/re-enabled action state, terminal inventory refresh, and clear error reporting.
11. After removal, refresh actual inventory so the component becomes Missing (or remains Installed when sibling assets remain); do not rely on stale manifest flags.
12. Keep runtime/model/cache ownership aligned with Step 2's independently configurable Models, Provider Runtime and Model Cache roots.

## Root-cause fixes applied

- Fixed Chatterbox runtime uninstall to validate against the configured Provider Runtime root, not Models. The prior code rejected valid runtime paths after Step 2 separated these roots.
- Fixed individual Qwen model uninstall to validate against \`Models/qwen3-tts\`, not the Qwen Provider Runtime root. Qwen weights and its isolated Python runtime have distinct storage ownership.
- Added a dedicated \`chatterbox-model-assets\` uninstall operation. It removes only cache folders whose Hugging Face directory names identify Chatterbox and preserves other provider caches.
- Exposed Chatterbox cache removal in the authoritative model inventory only when matching cache folders actually exist. Premium V2 renders the Uninstall control from this inventory capability flag; the backend accepts the operation only on the uninstall command, not install.
- Retained the shared Chatterbox runtime removal behaviour that clears both English and multilingual runtime availability while retaining cache assets, projects and saved profiles.
- Kept Qwen runtime removal limited to the isolated Python/venv/bootstrap files; Qwen model weights remain in Models.

## Regression coverage added or corrected

- Separate Models and Provider Runtime roots for Chatterbox runtime uninstall, with Chatterbox cache preservation.
- Separate Models and Provider Runtime roots for Qwen model uninstall, with sibling model and runtime preservation.
- Separate Models and Provider Runtime roots for Qwen runtime uninstall, with every Qwen model weight folder and project file retained.
- Chatterbox cache uninstall removes English and multilingual Chatterbox cache folders while preserving a Qwen cache folder.
- Inventory exposes Chatterbox cache as uninstallable only when Chatterbox cache directories exist.
- Piper uninstall removes only the selected ONNX voice and its JSON sidecar; sibling voice and sidecar remain.
- Kokoro uninstall removes only the app-managed local Kokoro folder and preserves project data.
- Audiobook AI uninstall removes only its app-managed folder and preserves project data and other model families.
- Premium V2 UI contract asserts uninstall action rendering, destructive confirmation, backend command routing, and active-job messaging.
- Existing path-escape, shared-runtime preservation, inventory refresh, partial-asset, active-job and single-operation-slot tests remain in the suite.

## CI evidence so far

- Run #2531 on \`8ef1ecf8be\`: full regression passed, **1,229 tests**.
- Run #2532 on \`379c539145\`: full regression passed, **1,229 tests**.
- Run #2533 on \`32fc7d4e5c\`: full regression passed, **1,229 tests**.
- Run #2534 on \`a7846471cc\`: full regression passed, **1,229 tests**.
- Run #2535 on \`98e5697532\`: full regression passed, **1,231 tests**, including actual inventory capability for Chatterbox cache removal.
- Run #2536 on \`b066095476\`: full regression passed, **1,231 tests**, including Premium V2 uninstall confirmation/action wiring.
- Run #2537 on \`7272a72adf\`: full regression passed, **1,231 tests**, including the corrected Chatterbox cache uninstall allowlist.
- Historical failed runs #2527–#2530 were caused by regression fixtures that still assumed shared Models/Runtime roots or patched the wrong imported path reference. The fixtures were corrected to model Step 2's independent roots; subsequent matching tests passed. Preserve historical failure records.

## Remaining acceptance gates

- Run a final full regression against the latest combined Step 3 source and tests.
- Run a matching-head Windows artifact checkpoint: frozen application, bundled assets, packaged acceptance, installer, portable package, SHA-256 manifest, Defender and artifact uploads.
- Inspect all jobs and release artifacts; do not mark Step 3 closed until the exact final candidate has green tests and package acceptance.
- Actual installed-Windows manual checks are not represented as passed by CI. Where hardware or real installed-app interaction is unavailable to the hosted runner, record the limitation explicitly rather than inventing acceptance evidence.

**Final candidate:** Step 3 implementation and UI/test integration are committed on this branch. The next commit is the matching-head Windows artifact checkpoint; closure depends on its full regression and packaged acceptance gates.

**Status: IN PROGRESS — code and targeted lifecycle/UI regressions implemented; matching-head full regression and packaged acceptance pending.**

## Additional root-separation and AI lifecycle acceptance — 6 November 2026

- A follow-up audit found the legacy desktop `ModelsPage` uninstall worker still validated Qwen model weights against the Provider Runtime root. Corrected it to validate against `Models/qwen3-tts`, matching the configured Step 2 ownership boundary.
- The same audit found the legacy desktop worker still validated Chatterbox runtime deletion against Models. Corrected it to use the configured Provider Runtime root.
- Added isolated Qt worker regressions with separate Models, Provider Runtime and Model Cache directories. They prove Qwen model uninstall preserves sibling weights and the Qwen Python runtime, and Chatterbox runtime uninstall preserves cached model assets.
- Added Qwen individual-model install routing coverage, verifying the selected model is installed through the Qwen model installer while keeping weights under Models and the runtime under Provider Runtime.
- Added Audiobook AI install coverage verifying the installer is invoked and a real inference self-test is required before reporting success. Existing Audiobook AI uninstall coverage confirms its app-managed folder is removed without touching projects or other model families.
- Run #2541 (implementation correction) passed full regression: **1,232 tests**.
- Run #2542 (Qwen split-root worker regression) passed full regression: **1,232 tests**.
- Run #2543 (Qwen + Audiobook AI install lifecycle tests) passed full regression: **1,234 tests**.
- Run #2544 (Chatterbox Provider Runtime root correction) passed full regression: **1,234 tests**.
- Run #2545 (Chatterbox split-root worker regression) passed full regression: **1,235 tests**.
- These test runs include the existing safe path-boundary, shared-runtime preservation, active-job blocking, operation serialization, inventory refresh and partial-asset checks.

**Final packaged acceptance remains required on the exact combined source head.** The previous #2540 package checkpoint passed before these final legacy-worker corrections; it is not being reused as evidence for the newer code.

- Final matching-head artifact checkpoint requested after the combined 1,235-test candidate: installer/portable build, frozen-app verification, bundled assets, packaged feature acceptance, SHA-256 manifest, Defender scans and artifact uploads. Step 3 remains open until this run succeeds.
