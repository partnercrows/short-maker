# Short Maker — Architecture

Status: Step 1 (repository audit), Step 3 (architecture proposal), and Step 2 (Active
Speaker technical spike) from `Short_Maker_PRD.md` Section 55 are complete. Active
Speaker detection, face tracking, smooth camera-following, and rendering are real,
working code today — see `docs/ACTIVE_SPEAKER_SPIKE.md` for results across the PRD's 8
test scenarios. Step 4 (full MVP pipeline: Whisper, AI clip selection, subtitles, Social
Kit, job-system wiring) is the remaining follow-up work — see "What's stubbed" below.

## Stack

```
Tauri 2 (Rust shell)
  + React 19 / TypeScript / Vite / Tailwind CSS v4 (frontend/)
  + Python FastAPI sidecar (backend/), PyInstaller-packaged for release
  + FFmpeg (subprocess, not a wrapper library)
  + SQLite (plain sqlite3, no ORM)
```

Rationale for each choice, and what was validated against the repository audit
(`docs/THIRD_PARTY_NOTICES.md`), is in the Step 1/3 plan this scaffold implements.

## Repository layout (as built)

```
short-maker/
  frontend/                 Vite + React 19 + TS + Tailwind v4. Placeholder shell with
                             the PRD S48 nav (Projects/History/AI Providers/Settings).
  src-tauri/                Tauri 2 Rust shell. Dev server fixed at :1420 (tauri.conf.json
                             beforeDevCommand/devUrl), productName "Short Maker",
                             identifier com.shortmaker.app. Plugin wiring (stronghold,
                             dialog, shell, notification, updater) is MVP work — the
                             default `tauri-plugin-log` is the only plugin registered
                             so far.
  backend/
    app/
      main.py                FastAPI app, lifespan hook runs init_db() +
                              get_or_create_api_token() on startup, /health route.
      core/
        config.py             Per-OS app-data dir resolution (PRD S35): env var
                              SHORT_MAKER_DATA_DIR overrides; otherwise
                              %APPDATA%/ShortMaker, ~/Library/Application Support/
                              ShortMaker, or $XDG_DATA_HOME/ShortMaker.
        security.py            Local API token (Bearer) auth between Tauri and the
                              sidecar; token generated on first run, stored in
                              <data_dir>/.api_token. Real key material for AI providers
                              never touches this file or SQLite — that's OS-keychain
                              work via Tauri Stronghold, still pending (MVP).
      db/
        schema.py              CREATE TABLE statements: projects, clips, social_kits,
                              social_kit_versions, ai_providers, jobs (PRD S34 + a
                              jobs table the PRD's schema section didn't enumerate but
                              S37 requires).
        connection.py           init_db() + a context-managed sqlite3 connection with
                              foreign_keys=ON.
      jobs/
        models.py, manager.py   SQLite-persisted job tracking (queued/running/
                              completed/failed/cancelled per PRD S37) with
                              process-local cancellation Events per job — durable
                              across sidecar restarts, unlike both audited reference
                              apps (auto-clipper: in-memory threads only, clipforge:
                              a JSON file).
      ai_providers/
        registry.py             ProviderType enum (openai/gemini/deepseek/groq/
                              openrouter/xai/mistral/custom) + a working
                              test-connection check for every OpenAI-compatible
                              provider via httpx. Gemini's native google-genai
                              adapter and actual clip-selection/social-kit prompts
                              are MVP work.
      pipeline/
        transcribe/             Interface only (Word/TranscriptResult models,
                              Transcriber.transcribe raises NotImplementedError).
                              faster-whisper is already an installed dependency;
                              wiring it up is MVP work.
        common/
          face_detector.py        Shared YuNet DNN face detector (OpenCV Zoo model,
                              bundled at common/models/face_detection_yunet_2023mar.onnx)
                              used by both active_speaker and reframe/face_tracking.
                              Picked over MediaPipe after MediaPipe's FaceLandmarker
                              returned zero detections on this machine across two
                              versions and a clean venv -- a platform bug, not a code
                              or license issue (recorded in THIRD_PARTY_NOTICES.md).
          tracker.py               Greedy IOU tracker with an occlusion grace period
                              (persistent track IDs survive a few missed-detection
                              frames -- this is what makes PRD scenario 6, partial
                              occlusion, actually work).
        active_speaker/
          detector/ tracker/ scorer/ pipeline/   Mirrors the PRD S11 recommended
                              layout, now with real detection: detector wraps the
                              shared YuNet+IOU tracker, scorer computes mouth-region
                              (lower-third-of-face-box) grayscale pixel-motion energy
                              per track and picks whichever track is moving most (no
                              neural ASD model -- see THIRD_PARTY_NOTICES.md for why
                              Light-ASD/LR-ASD were deferred), pipeline.run() drives a
                              full video pass and returns real
                              `ActiveSpeakerResult(available=True, segments=[...],
                              track_trajectories={...})` when it finds confident
                              speaking segments, `available=False` otherwise (still a
                              normal, expected outcome the fallback chain handles).
        reframe/
          modes.py               The PRD S12/S14 fallback chain: Active Speaker ->
                              Face Tracking -> Person Detection -> Center Crop. Now
                              wraps every rung's attempt in a broad try/except so a
                              bug in one detector (bad file, corrupt video, ...) falls
                              through instead of propagating -- the actual mechanism
                              behind "must never be a single point of failure."
                              `_windows_from_active_speaker` joins segments with
                              per-track face trajectories and smooths the result.
          smoothing.py            EMA + deadband position smoothing (PRD S13: no
                              instant jumps between speakers), reimplementing the
                              idea validated in the auto-clipper audit.
          center_crop.py          The only rung with zero external dependency: pure
                              geometry, computes a centered static crop window (or,
                              via `target_crop_size`, just the crop dimensions other
                              rungs need) for any source/target aspect ratio.
          face_tracking.py        Real now: same YuNet+IOU tracker as active_speaker,
                              minus the mouth-motion scoring -- follows the largest
                              detected face, smoothed the same way.
          person_detection.py    Still a stub (full-body/HOG person detection is
                              separate scope, out of the Step 2 spike).
        render.py                 OpenCV frame-by-frame crop+resize (interpolating
                              between a ReframePlan's sparse CropWindows) into a
                              silent video, then an FFmpeg subprocess muxes the
                              original audio back in and encodes final H.264/AAC.
                              Simpler to get frame-accurate than an FFmpeg crop-filter
                              expression for a POC; continuous-filter/hardware-encoded
                              rendering is MVP polish.
        subtitle/               Interface only (SubtitleRenderer.render_ass raises
                              NotImplementedError). ASS/SRT generation is MVP work.
      api/
        projects.py, clips.py,
        jobs.py, ai_providers.py,
        subtitles.py, social_kit.py   FastAPI routers, all behind the local API
                              token. projects/clips/jobs/ai_providers are fully
                              functional CRUD against SQLite today.
                              subtitles/social_kit expose the real PRD-shaped contract
                              (e.g. regenerate-social-kit-only, never re-run
                              Whisper/Active Speaker/FFmpeg per S28) but their
                              generation endpoints return HTTP 501 until the MVP
                              pipeline lands.
    tests/                    29 passing tests: health/auth, schema creation, job
                              lifecycle + cancellation, IOU tracker persistence/
                              occlusion/eviction, mouth-motion scorer + segment
                              merging, EMA/deadband smoothing, and the full reframe
                              fallback chain (AUTO degrades to Center Crop when
                              nothing else is available; explicit Center Crop never
                              touches other detectors; crop geometry is correct for a
                              16:9 -> 9:16 conversion).
    requirements.txt           fastapi, uvicorn, pydantic, faster-whisper,
                              opencv-python-headless, openai, google-genai, httpx,
                              pytest(-asyncio). (mediapipe was tried and removed --
                              see THIRD_PARTY_NOTICES.md.)
  docs/
    ARCHITECTURE.md            This file.
    THIRD_PARTY_NOTICES.md     The Step 1 audit + license findings + reuse decisions,
                              including the Step 2 ASD technology decision.
    ACTIVE_SPEAKER_SPIKE.md    Step 2 results: per-scenario outcomes against real
                              test footage, known limitations, measured timings.
  .gitignore
```

## What's stubbed (by design, not oversight)

`transcribe/` and `subtitle/` are still `NotImplementedError` -- Whisper transcription,
subtitle rendering, and AI-driven clip selection/Social Kit content are all Step 4 (MVP)
work, along with `reframe/person_detection.py` (full-body detection, separate scope).
Everything in `active_speaker/` and `reframe/{face_tracking,modes,center_crop}.py` is now
real, tested code (Step 2, see `docs/ACTIVE_SPEAKER_SPIKE.md`). The point of stubbing the
remaining pieces *now*, rather than leaving TODOs, is the same as before: the code paths
around them — the reframe fallback chain, the job state machine, the API contracts — are
real and tested today, so MVP work fills in the remaining detectors/renderers behind
interfaces that already work end-to-end.

## Local-only guarantees already in place

- Video never leaves the machine: there is no upload path anywhere in the sidecar.
- The sidecar only binds to localhost and requires the local API token on every route
  except `/health`.
- SQLite holds metadata and filesystem paths only — no video binaries, no plaintext API
  keys (the `ai_providers.encrypted_api_key` column exists per the PRD schema but is
  intentionally left unused; real secrets go through Tauri's OS-keychain-backed storage,
  still to be wired up).

## Verified locally

- `cargo check` in `src-tauri/` compiles cleanly.
- `npm run build` in `frontend/` produces a working Vite + Tailwind bundle.
- A live `cargo tauri dev` run opened the actual desktop window successfully.
- `pytest` in `backend/` (with a `.venv`): 29/29 passing.
- A live `uvicorn` run confirmed `/health` returns 200, project creation persists to
  SQLite, and requests without the local API token are rejected with 401.
- FFmpeg 9.0 (NVENC/CUDA-enabled build) installed via winget.
- The full Active Speaker + reframe + render pipeline run end-to-end against 7 real test
  clips (a 2-3 person Indonesian podcast) covering most of the PRD S43 scenarios; output
  MP4s visually confirmed to follow the speaking face with smooth transitions. Full
  results, timings, and known limitations: `docs/ACTIVE_SPEAKER_SPIKE.md`.

## Deliberately not done in this pass

- Wiring `cargo tauri dev` end-to-end with the FastAPI sidecar as a managed subprocess
  (currently they run independently; sidecar process management is MVP work).
- Any Stronghold/keychain wiring on the Rust side.
- Whisper transcription, AI clip selection, subtitle rendering, Social Kit generation, and
  wiring any of the reframe/render pipeline into the FastAPI job system/API routes — all
  Step 4 (MVP) work.
- A GitHub remote — this repo is local-only until the project owner creates the upstream
  repo and shares the URL.
