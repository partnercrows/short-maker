# Active Speaker Technical Spike — Results (PRD Step 2, S43/S55)

## What this proves

A landscape multi-speaker video can be turned into a 9:16 vertical clip where the camera
follows whoever is talking, with smooth (not instant) transitions between speakers — the
PRD's stated most-important success criterion (S56). This is real, working, tested code
today: `backend/app/pipeline/active_speaker/`, `backend/app/pipeline/reframe/`, and
`backend/app/pipeline/render.py`.

## Test material

Real footage, provided by the project owner:
`video/#BossMama 52 _ Kafka CoC & Bunda _ ... _720p60.mp4` — a ~77-minute Indonesian
parenting-talk-show podcast, 1280x720 @ ~60fps, 2-3 people across different segments
(a 2-person interview segment and a later 3-person product-review segment, plus what
looks like brief non-linear cutaways between them). Timeline thumbnails were sampled
every 3 minutes and visually inspected to pick 7 short (25-40s) clips covering as many
PRD scenarios as the footage actually contains — no clip was cherry-picked for a good
result; several were re-labeled after inspection once cut, because the source video
cuts between camera setups more often than the coarse thumbnail sampling suggested.

Clip 07 is the one exception to "real footage only": the source has no genuinely dark
segment, so it's clip 01 with brightness/contrast reduced via FFmpeg's `eq` filter,
clearly labeled synthetic, not a substitute for real low-light footage.

## Results by PRD S43 scenario

| # | Scenario | Clip(s) | Result | Notes |
|---|----------|---------|--------|-------|
| 1 | One speaker | `03_solo_speaker_b`, `06_solo_speaker_c` | **Pass** | Tight, correctly-centered face framing throughout. |
| 2 | Two speakers | `01_two_speakers`, `02_two_speakers_gesture`, `04_two_speakers_b` | **Pass** | Camera correctly moves to whichever of the two is talking; segments 0.3-1.5s apart show real back-and-forth. |
| 3 | Three speakers | — | **Not tested** | The source's 3-person wide shot only appears as brief cutaways between longer 1-2-person segments; none of our 3-minute-spaced samples landed on a *sustained* 3-person conversation. Needs different/additional footage, not a pipeline gap. |
| 4 | Speaker switching | `01`, `02`, `04`, `06` | **Pass** | Same evidence as #2 — multiple switches per clip, each a distinct `SpeakerSegment`. |
| 5 | Simultaneous talking | — | **Inconclusive** | Not deliberately captured or verified (would need audio inspection to confirm two people spoke over each other in a given clip). The scorer's design handles it by picking the higher-motion track with reduced confidence, but this wasn't validated against a confirmed overlapping-speech moment. |
| 6 | Speaker partially occluded | — | **Mechanism unit-tested only** | `IouTracker`'s occlusion grace period is covered by `tests/test_face_tracker.py` (survives a synthetic multi-frame gap), but no real occluded moment in the footage was specifically identified and checked end-to-end. |
| 7 | Speaker moving | `02_two_speakers_gesture` (hand gestures), general head movement in all clips | **Pass** | Tracking held up through natural seated movement/gestures; no track loss observed. |
| 8 | Low-light | `07_synthetic_low_light` | **Pass (synthetic)** | YuNet still detected and tracked faces after brightness/contrast reduction; camera followed speakers correctly even in the darkened frames. Not a substitute for a real low-light test. |

5/8 scenarios pass on real (or synthetic-but-reasonable) footage; 1 is architecturally
untested (occlusion, mechanism proven in isolation); 2 need footage this video doesn't
contain (3+ simultaneous speakers, genuine low-light).

## How it works (no neural ASD model)

1. **Face detection** (`app.pipeline.common.face_detector`): OpenCV's YuNet DNN detector
   (MIT, OpenCV Zoo — see `THIRD_PARTY_NOTICES.md`), not MediaPipe. MediaPipe's
   `FaceLandmarker` returned **zero detections on every test image**, across mediapipe
   1.0.0 and 0.10.21, in both the project venv and a from-scratch clean venv — reproduced
   with the exact code from Google's own documentation, on images independently confirmed
   to contain a clear face via OpenCV's Haar cascade. This looks like a Windows-specific
   regression, not a licensing or code problem; noted for a future retry.
2. **Tracking** (`app.pipeline.common.tracker`): greedy IOU matching assigns persistent
   track IDs across frames, tolerating a short run of missed detections (occlusion grace
   period).
3. **Scoring** (`app.pipeline.active_speaker.scorer`): for each tracked face, crop the
   lower third of its box (approximate mouth region) and measure frame-to-frame grayscale
   pixel-difference energy. Whichever track has the most motion — above a floor, so
   "nobody is clearly talking" is a real outcome — wins that frame; a margin-based
   confidence compares the top two tracks. Consecutive same-winner frames merge into
   `SpeakerSegment`s.
4. **Reframe** (`app.pipeline.reframe.modes`): the PRD S14 fallback chain (Active Speaker
   → Face Tracking → Person Detection → Center Crop) joins segments with each speaker's
   face-position trajectory, applies EMA + deadband smoothing (PRD S13: no instant
   jumps), and produces a sparse list of `CropWindow`s.
5. **Render** (`app.pipeline.render`): OpenCV reads/crops/resizes frame-by-frame,
   linearly interpolating between the sparse crop windows; an FFmpeg subprocess muxes the
   original audio back in and encodes final H.264/AAC.

## Known limitations (be honest about these before MVP hardening)

- **No ground truth.** There's no per-frame labeled "who is actually speaking" for this
  footage, so results were judged by eyeballing rendered output and reading confidence/
  switch-count logs — not a measured accuracy percentage. Don't quote one.
- **Heuristic, not semantic.** Mouth-region motion energy can be fooled by any mouth
  movement that isn't speech (chewing, laughing, exaggerated reactions) and by camera/
  lighting changes that alter the crop region's pixel values without anyone moving.
- **Track ID churn.** The IOU tracker sometimes assigns a *new* ID to the same physical
  person after a detection gap exceeds the grace period (observed: up to ~7 short-lived
  tracks in a 30s 2-person clip, though the two real speakers still dominate with
  hundreds of samples each). Harmless for this spike's purposes but worth tightening
  before relying on `speaker_id` continuity for anything user-facing.
- **Empty-frame transitions — fixed.** The original continuous EMA+deadband smoothing
  interpolated the crop position across silent gaps between segments, which could
  briefly show a framing with nobody in it (observed at ~t=16s in
  `01_two_speakers_vertical.mp4`). Reworked in the Step 4 pass: `reframe/smoothing.py`
  now computes one target position per segment and holds it steady (including across
  gaps) with a single short eased pan only when the next segment actually starts, per
  PRD S13's own diagram. Also fixed a related stutter-then-jump artifact in the old
  deadband (it compared against its own smoothed output, so small real movements got
  discarded until they piled up and jumped at once) that the project owner caught by
  eye ("looks like a hesitant cameraman") before this was otherwise noticed.
- **Performance.** CPU-only YuNet + Python frame loop takes ~45-90s of analysis plus
  ~30-60s of rendering per 25-40s clip (roughly 2-4x slower than realtime on this
  machine). Fine for a POC; production will want a faster detector/model, a tuned frame
  stride, and/or GPU-accelerated inference.
- **False-positive detections.** YuNet occasionally flags a static object (e.g. a flower
  arrangement) as a face at high confidence. Harmless here because the scorer requires
  actual motion to win, but adds wasted computation.

## Where the outputs live

`backend/spike/clips/` (7 input test clips) and `backend/spike/output/` (7 rendered 9:16
outputs + `batch_run.log` with per-clip timings) — gitignored (large binaries), kept
locally for manual review. The pipeline code itself (`app/pipeline/active_speaker/`,
`app/pipeline/reframe/`, `app/pipeline/render.py`) and its 29 passing unit tests
(`backend/tests/`) are the actual deliverable and are committed.

## Explicitly out of scope for this pass (see the approved plan)

Any trained neural ASD model, `reframe/person_detection.py`, production FFmpeg-native
cropping, any scenario this footage doesn't contain, and wiring this into the FastAPI job
system/API — all deferred to Step 4 (MVP), per the plan this spike executed.
