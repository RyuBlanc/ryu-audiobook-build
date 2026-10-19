# Ryu's Audiobook

Local-first Windows audiobook generator.

## Vision

Turn PDF, EPUB, TXT, and DOCX books into chaptered audiobooks locally, with hardware-aware processing and a future path for authorized custom voice generation.

## Project Status

**Phase 0 — Foundation**

The first milestone is a local audiobook pipeline:

1. Import a book
2. Extract and clean text
3. Detect and edit chapters
4. Select a local TTS voice
5. Preview narration
6. Generate chapter audio with resume/retry support
7. Build an M4B audiobook with chapter markers and metadata

Custom authorized voice generation will be added as a separate voice engine after the core pipeline is stable.

## Hardware Targets

The application is intended to run on both NVIDIA RTX 3050 4 GB VRAM and RTX 4060 8 GB VRAM systems. It will detect available hardware, choose an appropriate processing mode, and provide CPU fallback.

## Privacy

Books, generated audio, voice samples, and project data are intended to remain on the user's local computer. No cloud storage is required for the core application.

## Repository

This repository contains source code and build configuration. User books, generated audiobooks, voice samples, model files, and other large/local data must not be committed to Git.


## Current Test Build

Voice library now exposes the offline Qwen character catalogue before installation, with hardware-aware 0.6B/1.7B selection and pronunciation audio testing.

## Premium V2 frontend integration status

The approved HTML source is stored at `assets/frontend/ryu_audiobook_premium_v2.html` and is loaded inside the desktop process using Qt WebEngine when that asset is present. The embedded bridge currently connects app information, persisted local project listing and settings reads. Other actions return a truthful `not_connected` result until each screen's backend command is implemented and tested. See `docs/PREMIUM_V2_SCREEN_FUNCTION_MAP.md`, `docs/PREMIUM_V2_BACKEND_API_MAP.md`, `docs/PREMIUM_V2_DATABASE_SCHEMA.md`, `docs/PREMIUM_V2_KNOWN_LIMITATIONS.md` and `docs/PREMIUM_V2_TEST_REPORT.md`. The integration is in progress; this note is not a release-complete claim.
