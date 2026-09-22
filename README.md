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
