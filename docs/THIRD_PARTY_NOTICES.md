# Third-Party Notices

This document records the Step 1 repository audit required by `Short_Maker_PRD.md`
(top-of-file rule + Section 55), the license findings behind every reuse decision, and
which patterns/assets Short Maker builds on. **No code was copied from any of the
repositories below** — everything in `frontend/`, `src-tauri/`, and `backend/` is our own
implementation. Nothing here grants any relationship to, or endorsement from, the
original authors, and Short Maker's Git history and repository are fully independent of
`DhimasPH/auto-clipper` per the top-of-PRD rule.

Audit performed via read-only inspection (`raw.githubusercontent.com` / GitHub API) —
no repository was cloned locally, pushed to, or modified.

---

## DhimasPH/auto-clipper

- Source: https://github.com/DhimasPH/auto-clipper
- License: MIT (copyright DhimasPH, 2026, per the repo's `LICENSE` file)
- Role: primary architectural reference for the desktop-shell pattern

**What we reimplemented independently, inspired by patterns validated here** (own code,
not copied):
- Tauri 2 + React/Vite frontend talking to a Python FastAPI sidecar over a token-secured
  local HTTP API.
- Multi-vendor AI provider abstraction (OpenAI SDK + OpenAI-compatible endpoints for
  DeepSeek/Groq/OpenRouter/xAI/Mistral/custom, native SDK for Gemini).
- NVENC-probe-with-`libx264`-fallback hardware encoding strategy.
- `tauri-plugin-stronghold`-backed secret storage instead of plaintext SQLite.
- PyInstaller-based sidecar packaging approach.

**What we deliberately did not copy**: its "active speaker" logic, which is Haar-cascade
face-position heuristics (median/EMA-smoothed face-center-x, deadband stabilization) —
not real audio-visual active-speaker detection. Short Maker needs the real thing (PRD
S10-S12), so this was not treated as a reference for that subsystem.

Standard MIT terms apply (permission to use/copy/modify/merge/publish/distribute/
sublicense/sell, provided the copyright notice and permission notice are retained in any
substantial portion of the software actually reused — since nothing was copied verbatim
here, no notice-inclusion obligation currently applies, but this section itself serves as
the attribution record). Verify the exact license text against the live `LICENSE` file
before any future verbatim reuse.

---

## mallexibra-dev/clipforge

- Source: https://github.com/mallexibra-dev/clipforge
- License: MIT (copyright mallexibra, 2026, per the repo's `LICENSE` file)
- Role: secondary reference — turned out to be a Dockerized Next.js + FastAPI **web** app,
  not a desktop app, so architecturally less relevant than auto-clipper.

**Bundled third-party asset noted in its own `NOTICE` file**:
`backend/models/face_detection_yunet_2023mar.onnx`, sourced from OpenCV Zoo
(huggingface.co/opencv/face_detection_yunet), itself MIT-licensed.

**Ideas borrowed (reimplemented independently, not copied)**:
- Using **YuNet** (OpenCV Zoo's DNN face detector) as the primary local face detector —
  **now actually in use**, not just planned (see the Active Speaker section below). We
  downloaded the same model file directly from its canonical source
  (`github.com/opencv/opencv_zoo`, `models/face_detection_yunet/`, MIT-licensed) rather
  than copying clipforge's bundled copy, and it lives at
  `backend/app/pipeline/common/models/face_detection_yunet_2023mar.onnx`, shared between
  `active_speaker/detector` and `reframe/face_tracking.py`. Its OpenCV Zoo attribution is
  preserved in this notice per its own NOTICE requirement.
- A lenient JSON-repair strategy for parsing LLM chat-completion output (strip
  think-tags/code fences, tolerate minor malformation) for the future AI clip-selection
  and Social Kit work.

**What we deliberately did not copy**: like auto-clipper, it has no real active-speaker
detection — just a single static per-clip focal-x point from face/HOG detection, no
per-frame tracking or panning.

---

## Active Speaker Detection technology survey

Neither reference app solves real Active Speaker Detection, so this was researched
separately as the PRD's identified hardest/most differentiating piece (PRD S10-S12).

### TaoRuijie/TalkNet-ASD
- License: MIT
- Considered but **not selected** as the primary foundation: hardcodes `cuda` (CPU
  support requires manually editing two files, not a runtime flag), weights are hosted on
  Google Drive (offline-install risk, supply-chain fragility), repo has been stale since
  Oct 2023, bundled face detector (S3FD) is dated versus modern alternatives.

### sieve-community/fast-asd
- License: MIT
- **Disqualified outright**: calls Sieve's *hosted cloud* models (`sieve/yolov8`,
  `sieve/talknet-asd`) via the `sieve` SDK — this directly violates the PRD's
  local-processing requirement (S4, S41). Also dormant since May 2024.

### Junhua-Liao/Light-ASD and Junhua-Liao/LR-ASD — deferred, not used
- License: MIT (repo-wide), but **redistribution rights for the weight files are not
  actually settled**: both repos' own bundled S3FD face detector downloads its weight
  from Google Drive via `gdown` at runtime (`model/faceDetector/s3fd/__init__.py`) — the
  same red flag that disqualified TalkNet, unfixed in both "Light" forks. CUDA is also
  still hardcoded with no CPU flag in their `Columbia_test.py` entry point. Light-ASD's
  own maintainers have an **open, unanswered issue** (#30, opened 2026-08-10) asking
  whether `weight/finetuning_TalkSet.model` can be legally redistributed in a commercial
  app. Given this, **neither was used** for the Step 2 spike — deferred, not ruled out
  permanently, pending either a maintainer response or an independently-trained model.

### google-ai-edge/mediapipe — attempted, abandoned for a platform bug, not a license issue
- License: Apache 2.0 (library); the `face_landmarker.task` model bundle downloads from
  Google's own `storage.googleapis.com/mediapipe-models/...` (a clean, official source,
  unlike the gdown-hacked links above).
- **Not a reuse-eligibility problem — a reproducible runtime bug**: `FaceLandmarker.detect()`
  returned zero faces on every test image, across mediapipe 1.0.0 and 0.10.21, in both the
  project venv and a from-scratch clean venv, despite the same images having a clearly
  visible, verifiably-present face (confirmed via an independent OpenCV Haar-cascade
  check). This looks like a Windows-specific regression in mediapipe's Tasks API/TFLite
  delegate on this machine, not a licensing or code issue. Abandoned in favor of YuNet
  after this was isolated; not re-attempted for this spike. Worth retrying on a future
  mediapipe release or a different OS if landmark-quality mouth tracking is wanted later.

### opencv/opencv_zoo (YuNet) + a from-scratch mouth-motion heuristic — what the spike
actually runs
- License: MIT (YuNet, from OpenCV Zoo — see the clipforge section above for how it's
  bundled here).
- **No neural active-speaker model is used at all.** `active_speaker/scorer` computes
  frame-to-frame grayscale pixel-difference energy in the lower third of each YuNet-
  tracked face's bounding box (an approximate mouth region) and picks whichever tracked
  face has the most motion, gated by a floor and a margin-based confidence. This is
  entirely our own code — no model weights, no license exposure beyond YuNet's face
  detector itself. See `docs/ACTIVE_SPEAKER_SPIKE.md` for results and known limitations
  (fooled by non-speech mouth movement, no ground truth to measure real accuracy against).

---

## Summary of obligations going forward

1. If any literal code snippet is ever adapted from an MIT-licensed source above, retain
   that project's copyright + permission notice in the adapting file or a bundled
   `LICENSE-THIRD-PARTY` file.
2. **YuNet's ONNX model file is now bundled** at
   `backend/app/pipeline/common/models/face_detection_yunet_2023mar.onnx` — its OpenCV
   Zoo attribution (MIT, `opencv/opencv_zoo`) is recorded above; keep that section if the
   model file is ever moved or re-vendored.
3. Do not adopt Light-ASD/LR-ASD weights/code without first resolving the open weight-
   redistribution question (Light-ASD issue #30) or independently retraining — the
   current pipeline doesn't depend on them, so there's no unresolved exposure today.
4. If mediapipe is retried on a different platform/version and works, re-evaluate whether
   its Apache-2.0-licensed `face_landmarker.task` model bundle is preferable to the
   current YuNet + pixel-motion heuristic for mouth-tracking accuracy.
5. Never add `DhimasPH/auto-clipper` (or any repo audited here) as a Git remote for this
   project — Short Maker's repository must remain fully independent (see the rule at the
   top of `Short_Maker_PRD.md`).
