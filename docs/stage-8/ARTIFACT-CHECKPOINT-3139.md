# Artifact Checkpoint 3139 — Integrated Repairs

This checkpoint validates the current PR #33 candidate after correcting the packaged Help & Guide acceptance contract.

## Protected work
- Preserve the Qwen runtime, model selection, saved-profile identity and accelerator policy inherited from the PR #32 base.
- Do not change Qwen model-quality settings, GPU-selection policy, or existing generation routing as part of installer and Help Guide work.
- Preserve the original detailed seven-stage Help & Guide in the Premium V2 HTML. The packaged acceptance must accept that approved static guide and verify its current instructions; the adapter fallback guide remains independently validated when used.

## Requested repair areas represented by this branch
- Production Studio organization and production/preview behavior.
- Artwork presentation, including no embedded Ryu watermark in user-uploaded images and a clean no-image state.
- Application startup and refresh responsiveness.
- Windows app, setup, taskbar and installer branding/transparency.
- Compact, centered, resizable installer layout with all navigation and footer controls visible.
- Help & Guide parity, including narrator-only generation, Qwen runtime guidance and current format/hardware limitations.
- Packaged Sound Design and Music Library navigation, audio preview and workflow acceptance.
- Windows install, launch, upgrade, uninstall, Defender scan, artifact hashes and installer/portable artifact generation.

## Required automated checkpoint gates
1. Full regression suite and JavaScript syntax validation.
2. Frozen application build/startup and bundled voice/model asset verification.
3. External Qwen runtime import and simulated accelerator-selection smoke without modifying the runtime policy.
4. Packaged Help & Guide, Sound Design, Music Library and Production workflow acceptance.
5. Inno Setup and functional HTML installer build/startup.
6. Install, launch, upgrade, uninstall and user-data preservation.
7. PNG/ICO transparency and Windows shell icon resource checks.
8. Defender scan, SHA-256/size manifest and installer/portable artifact upload.

## Manual acceptance not implied by CI
- Actual saved Qwen profile audio and voice identity on the target PC.
- Physical NVIDIA/AMD/Intel/integrated-GPU inference and 10-/30-second timing.
- Full-book narrator-only and multi-character audio listening, interruption and recovery.
- Target-PC responsiveness and full display/DPI/multi-monitor visual matrix.

A green Actions run proves only the gates that actually execute and pass. Do not mark manual or physical-device acceptance complete from simulated CI evidence.
