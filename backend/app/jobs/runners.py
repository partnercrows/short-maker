"""Background job bodies: the actual work behind POST /projects/{id}/analyze
and POST /clips/{id}/generate. Each runs in its own daemon thread (started
by the API routers) and drives `job_manager` through the same
queued->running->completed/failed lifecycle every job uses.
"""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.ai_providers.registry import ProviderConfig
from app.core.clip_export import copy_clip_to_folder, export_clip_to_folder
from app.core.config import get_settings
from app.core.ffmpeg_utils import NoVideoStreamError, VideoMetadata, cut_subclip, extract_audio, probe_metadata
from app.core.gpu_pack import download_gpu_pack
from app.core.gpu_utils import ensure_cuda_dlls_on_path
from app.core.system_capabilities import probe_capabilities
from app.core.youtube_download import download_youtube_audio, download_youtube_video
from app.db.connection import get_connection
from app.jobs.manager import job_manager
from app.pipeline.ai_analysis.clip_selector import select_clips
from app.pipeline.intro import load_intro_frame
from app.pipeline.recipe import assemble as recipe_assemble
from app.pipeline.recipe import face_check, frame_sampler, recipe_analyzer, store, vision_capability, vision_labeler
from app.pipeline.recipe.models import AudioMode, RecipeAnalysis, TargetDuration
from app.pipeline.recipe.vision_capability import VisionUnsupportedError
from app.pipeline.reframe.models import ReframeMode
from app.pipeline.reframe.modes import resolve as resolve_reframe
from app.pipeline.render import render as render_clip
from app.pipeline.subtitle import build_initial_document, burn_ass_subtitles, load_clip_words
from app.pipeline.subtitle.ass_render import render_ass
from app.pipeline.subtitle.models import load_document, save_document
from app.pipeline.transcribe import TranscriptResult, get_transcriber

TARGET_WIDTH = 720
TARGET_HEIGHT = 1280

# Every clip render runs ffmpeg (VP9/H.264 decode + x264 encode), which
# already saturates the machine's cores on its own. Generating a batch of
# clips used to start one thread -- and one ffmpeg -- per clicked clip, all
# at once: eight concurrent encodes of a 1080p60 source thrashed the box hard
# enough that some ffmpeg processes died mid-cut with a bare
# AVERROR_EXTERNAL, which surfaced as a "Gagal membuat klip" the user could
# do nothing with. Queue them instead: same throughput, no failures.
MAX_CONCURRENT_RENDERS = 2
_RENDER_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_RENDERS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_mmss(seconds: float) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes}:{secs:02d}"


class JobCancelled(Exception):
    """Raised internally to unwind a job after the user cancels it.
    `job_manager.cancel()` already set the job's status/finished_at --
    this just stops the work from continuing, it isn't a failure."""


def _raise_if_cancelled(job_id: str) -> None:
    if job_manager.is_cancelled(job_id):
        raise JobCancelled()


@contextmanager
def _render_slot(job_id: str) -> Iterator[None]:
    """Holds one of the render slots for the duration of the block, keeping
    the job cancellable (and honest about why nothing is happening) while it
    waits for its turn."""
    waiting_announced = False
    while not _RENDER_SLOTS.acquire(timeout=0.5):
        _raise_if_cancelled(job_id)
        if not waiting_announced:
            job_manager.update_progress(job_id, 5, "Waiting for another clip to finish rendering")
            waiting_announced = True
    try:
        yield
    finally:
        _RENDER_SLOTS.release()


def _usable_video_duration(source_video_path: str, container_duration: float | None) -> float:
    """How far into the source there are actually *frames* to work with.

    A download interrupted partway through (the 403-mid-download case) can
    leave a file whose audio runs the full length while its picture track
    stops early. The container duration -- what `projects.source_duration`
    holds -- reports the longer of the two, so without this every clip past
    the last frame would be proposed, cut into an audio-only segment, and
    then fail deep in the crop stage."""
    try:
        metadata = probe_metadata(source_video_path)
    except Exception:  # noqa: BLE001 -- an unprobeable source is the next stage's problem to report, not this helper's
        return container_duration or 0.0
    if container_duration:
        return min(metadata.video_duration, container_duration)
    return metadata.video_duration


def run_analyze_job(
    job_id: str, project_id: str, provider: ProviderConfig, num_clips: int | None, use_gpu: bool = False
) -> None:
    settings = get_settings()
    try:
        job_manager.start(job_id)
        with get_connection() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            raise ValueError(f"Project not found: {project_id}")

        analysis_dir = settings.project_analysis_dir(project_id)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = analysis_dir / "transcript.json"

        if transcript_path.is_file():
            # A prior attempt on this project already finished the slow part
            # (audio extraction + transcription) -- if this run is a retry
            # after e.g. the AI provider step failing, redoing minutes of
            # transcription over again just to reach that same step is pure
            # waste. The source video is immutable for a project once
            # created, so the existing transcript is always still valid.
            job_manager.update_progress(job_id, 55, "Reusing existing transcript")
            transcript = TranscriptResult.model_validate_json(transcript_path.read_text(encoding="utf-8"))
        else:
            job_manager.update_progress(job_id, 10, "Extracting audio")
            audio_path = analysis_dir / "audio.wav"
            extract_audio(project["source_video_path"], str(audio_path))
            _raise_if_cancelled(job_id)

            total_duration = project["source_duration"] or 0.0
            job_manager.update_progress(job_id, 30, f"Transcribing (0:00 / {_format_mmss(total_duration)})")

            def on_transcribe_progress(fraction: float) -> None:
                _raise_if_cancelled(job_id)
                elapsed = fraction * total_duration
                step_label = f"Transcribing ({_format_mmss(elapsed)} / {_format_mmss(total_duration)})"
                job_manager.update_progress(job_id, 30 + fraction * 30, step_label)

            try:
                transcriber = get_transcriber("cuda", "float16") if use_gpu else get_transcriber()
            except Exception:  # noqa: BLE001 -- GPU requested but not actually usable; don't fail the whole job over it
                job_manager.update_progress(job_id, 30, "GPU unavailable, falling back to CPU for transcription")
                transcriber = get_transcriber()

            transcript = transcriber.transcribe(str(audio_path), on_progress=on_transcribe_progress)
            transcript_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
        _raise_if_cancelled(job_id)

        job_manager.update_progress(job_id, 60, "Finding best moments (waiting for AI provider)")
        usable_duration = _usable_video_duration(project["source_video_path"], project["source_duration"])
        candidates = select_clips(provider, transcript, num_clips, video_duration=usable_duration)
        (analysis_dir / "clips.json").write_text(json.dumps([c.model_dump() for c in candidates], indent=2), encoding="utf-8")
        _raise_if_cancelled(job_id)

        job_manager.update_progress(job_id, 90, "Saving candidate clips")
        _save_candidate_clips(project_id, candidates, transcript)

        job_manager.update_progress(job_id, 100, "Done")
        job_manager.complete(job_id)
    except JobCancelled:
        return
    except Exception as exc:  # noqa: BLE001 -- reported through the job row, not raised into a thread nobody awaits
        job_manager.fail(job_id, str(exc))


def _save_candidate_clips(project_id: str, candidates: list, transcript: TranscriptResult) -> None:
    now = _now()
    with get_connection() as conn:
        for candidate in candidates:
            clip_id = str(uuid.uuid4())
            overlapping_segments = [
                s.model_dump() for s in transcript.segments if s.start < candidate.end and s.end > candidate.start
            ]
            conn.execute(
                """
                INSERT INTO clips (
                    id, project_id, start_time, end_time, duration, score,
                    analysis_json, transcript_json, video_path, subtitle_path,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 'candidate', ?, ?)
                """,
                (
                    clip_id,
                    project_id,
                    candidate.start,
                    candidate.end,
                    candidate.end - candidate.start,
                    candidate.score,
                    json.dumps(candidate.model_dump()),
                    json.dumps(overlapping_segments),
                    now,
                    now,
                ),
            )
        conn.commit()


def _raise_if_beyond_last_frame(project, clip) -> None:
    """Stops a clip that starts past the source's last video frame before it
    reaches the crop stage, where the only symptom was an opaque
    "list index out of range" from probing an audio-only segment."""
    usable = _usable_video_duration(project["source_video_path"], project["source_duration"])
    if clip["start_time"] < usable:
        return
    raise ValueError(
        f"This clip starts at {_format_mmss(clip['start_time'])}, but the source video only has picture "
        f"up to {_format_mmss(usable)} (its audio runs to {_format_mmss(project['source_duration'] or usable)}) "
        "-- the source file is incomplete, most likely a download that was interrupted partway through. "
        "Re-download the full video, create the project again from it, and re-run Analyze."
    )


def _probe_subclip(subclip_path: Path) -> VideoMetadata:
    """`probe_metadata` on a freshly cut segment, with the audio-only case
    (a cut that landed past the source's last frame despite the pre-cut
    guard) reported as something a user can act on."""
    try:
        return probe_metadata(str(subclip_path))
    except NoVideoStreamError as exc:
        raise ValueError(
            "The cut segment came out with audio but no picture -- the source video file is incomplete "
            "(its video track is shorter than its audio track). Re-download the full video, create the "
            "project again from it, and re-run Analyze."
        ) from exc


def run_generate_job(job_id: str, clip_id: str, include_subtitle: bool, output_folder: str | None = None) -> None:
    settings = get_settings()
    try:
        job_manager.start(job_id)
        with get_connection() as conn:
            clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            if clip is None:
                raise ValueError(f"Clip not found: {clip_id}")
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (clip["project_id"],)).fetchone()

        clip_dir = settings.clip_dir(clip["project_id"], clip_id)
        clip_dir.mkdir(parents=True, exist_ok=True)
        subclip_path = clip_dir / "source_segment.mp4"
        rendered_path = settings.clip_rendered_path(clip["project_id"], clip_id)
        final_path = clip_dir / "video.mp4"

        with _render_slot(job_id):
            job_manager.update_progress(job_id, 15, "Cutting segment")
            _raise_if_beyond_last_frame(project, clip)
            cut_subclip(project["source_video_path"], clip["start_time"], clip["duration"], str(subclip_path))
            _raise_if_cancelled(job_id)

            job_manager.update_progress(job_id, 30, "Resolving active speaker crop")
            metadata = _probe_subclip(subclip_path)
            plan = resolve_reframe(
                video_path=str(subclip_path),
                requested_mode=ReframeMode.AUTO,
                source_width=metadata.width,
                source_height=metadata.height,
                target_width=TARGET_WIDTH,
                target_height=TARGET_HEIGHT,
            )
            _raise_if_cancelled(job_id)

            job_manager.update_progress(job_id, 55, "Rendering")
            # `rendered_path` (the crop+audio master, no subtitles) is kept
            # permanently from here on -- Subtitle Studio re-derives video.mp4
            # from it any time the subtitle document changes, without ever
            # re-cropping or re-transcribing.
            render_clip(str(subclip_path), plan, str(rendered_path), TARGET_WIDTH, TARGET_HEIGHT)
            _raise_if_cancelled(job_id)

            subtitle_path: str | None = None
            subtitle_json_path: str | None = None
            if include_subtitle:
                job_manager.update_progress(job_id, 80, "Burning subtitles")
                subtitle_json_path = str(settings.clip_subtitle_json_path(clip["project_id"], clip_id))
                subtitle_path = str(clip_dir / "subtitle.ass")
                _burn_default_subtitles_for_clip(
                    clip_id, clip["project_id"], clip["start_time"], clip["end_time"], str(rendered_path), subtitle_json_path, subtitle_path, str(final_path)
                )
            else:
                shutil.copyfile(rendered_path, final_path)

            subclip_path.unlink(missing_ok=True)

        now = _now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE clips SET video_path = ?, subtitle_path = ?, subtitle_json_path = ?,
                    status = 'completed', updated_at = ? WHERE id = ?
                """,
                (str(final_path), subtitle_path, subtitle_json_path, now, clip_id),
            )
            conn.commit()

        if output_folder:
            job_manager.update_progress(job_id, 95, "Copying to output folder")
            _copy_to_output_folder(clip, final_path, subtitle_path, output_folder)

        job_manager.update_progress(job_id, 100, "Done")
        job_manager.complete(job_id)
    except JobCancelled:
        with get_connection() as conn:
            conn.execute("UPDATE clips SET status = 'candidate', updated_at = ? WHERE id = ?", (_now(), clip_id))
            conn.commit()
    except Exception as exc:  # noqa: BLE001 -- reported through the job row
        job_manager.fail(job_id, str(exc))
        with get_connection() as conn:
            conn.execute("UPDATE clips SET status = 'failed', updated_at = ? WHERE id = ?", (_now(), clip_id))
            conn.commit()


def _copy_to_output_folder(clip, final_path: Path, subtitle_path: str | None, output_folder: str) -> None:
    copy_clip_to_folder(clip, final_path, subtitle_path, output_folder)


def _burn_default_subtitles_for_clip(
    clip_id: str,
    project_id: str,
    clip_start: float,
    clip_end: float,
    rendered_path: str,
    subtitle_json_path: str,
    ass_path: str,
    final_path: str,
) -> None:
    """Seeds a default-styled `SubtitleDocument` from the project transcript
    and burns it -- the "Include subtitles" checkbox's path. The saved
    `subtitle.json` is the same document Subtitle Studio opens afterwards,
    so a subsequent edit re-renders from here rather than starting over."""
    settings = get_settings()
    transcript_path = settings.project_analysis_dir(project_id) / "transcript.json"
    words = load_clip_words(transcript_path, clip_start, clip_end)
    document = build_initial_document(clip_id, words)
    save_document(subtitle_json_path, document)
    Path(ass_path).write_text(render_ass(document), encoding="utf-8")
    burn_ass_subtitles(rendered_path, ass_path, final_path)


def run_render_subtitle_job(job_id: str, clip_id: str) -> None:
    """The real Subtitle Studio "Render" action: re-derives `video.mp4` from
    the permanent `rendered.mp4` master + the clip's current
    `SubtitleDocument` -- no re-crop, no re-transcribe. Also the recovery
    path for a legacy clip whose `rendered.mp4` doesn't exist yet (it burned
    straight to `video.mp4` before this feature existed): one-time rebuilds
    the master from the original source video first.
    """
    settings = get_settings()
    try:
        job_manager.start(job_id)
        with get_connection() as conn:
            clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            if clip is None:
                raise ValueError(f"Clip not found: {clip_id}")
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (clip["project_id"],)).fetchone()

        clip_dir = settings.clip_dir(clip["project_id"], clip_id)
        clip_dir.mkdir(parents=True, exist_ok=True)
        rendered_path = settings.clip_rendered_path(clip["project_id"], clip_id)
        final_path = clip_dir / "video.mp4"

        with _render_slot(job_id):
            if not rendered_path.exists():
                job_manager.update_progress(job_id, 5, "Rebuilding clip (one-time, no video previously saved)")
                subclip_path = clip_dir / "source_segment.mp4"
                _raise_if_beyond_last_frame(project, clip)
                cut_subclip(project["source_video_path"], clip["start_time"], clip["duration"], str(subclip_path))
                _raise_if_cancelled(job_id)
                metadata = _probe_subclip(subclip_path)
                plan = resolve_reframe(
                    video_path=str(subclip_path),
                    requested_mode=ReframeMode.AUTO,
                    source_width=metadata.width,
                    source_height=metadata.height,
                    target_width=TARGET_WIDTH,
                    target_height=TARGET_HEIGHT,
                )
                _raise_if_cancelled(job_id)
                render_clip(str(subclip_path), plan, str(rendered_path), TARGET_WIDTH, TARGET_HEIGHT)
                subclip_path.unlink(missing_ok=True)
            _raise_if_cancelled(job_id)

            job_manager.update_progress(job_id, 50, "Loading subtitle document")
            subtitle_json_path = settings.clip_subtitle_json_path(clip["project_id"], clip_id)
            if subtitle_json_path.is_file():
                document = load_document(subtitle_json_path)
            else:
                transcript_path = settings.project_analysis_dir(clip["project_id"]) / "transcript.json"
                words = load_clip_words(transcript_path, clip["start_time"], clip["end_time"])
                document = build_initial_document(clip_id, words)
                save_document(subtitle_json_path, document)
            _raise_if_cancelled(job_id)

            job_manager.update_progress(job_id, 70, "Rendering subtitles")
            ass_path = clip_dir / "subtitle.ass"
            ass_path.write_text(render_ass(document), encoding="utf-8")
            burn_ass_subtitles(str(rendered_path), str(ass_path), str(final_path))

        now = _now()
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE clips SET video_path = ?, subtitle_path = ?, subtitle_json_path = ?,
                    status = 'completed', updated_at = ? WHERE id = ?
                """,
                (str(final_path), str(ass_path), str(subtitle_json_path), now, clip_id),
            )
            conn.commit()

        job_manager.update_progress(job_id, 100, "Done")
        job_manager.complete(job_id)
    except JobCancelled:
        return
    except Exception as exc:  # noqa: BLE001 -- reported through the job row
        job_manager.fail(job_id, str(exc))


def run_export_clip_job(job_id: str, clip_id: str, destination_folder: str) -> None:
    """The Download action, upgraded from a synchronous copy to a job so it
    can also run the (potentially slow) Intro Frame ffmpeg encode. A clip
    with no intro enabled still just falls through to a plain, near-instant
    copy inside `export_clip_to_folder` -- one code path either way."""
    settings = get_settings()
    try:
        job_manager.start(job_id)
        with get_connection() as conn:
            clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            if clip is None:
                raise ValueError(f"Clip not found: {clip_id}")
        if not clip["video_path"]:
            raise ValueError("This clip hasn't been generated yet")

        job_manager.update_progress(job_id, 20, "Preparing export")
        intro_json_path = settings.clip_intro_json_path(clip["project_id"], clip_id)
        intro = load_intro_frame(intro_json_path) if intro_json_path.is_file() else None
        intro_image_path = settings.clip_intro_image_path(clip["project_id"], clip_id)
        _raise_if_cancelled(job_id)

        job_manager.update_progress(job_id, 40, "Exporting" if intro and intro.enabled else "Copying to output folder")
        export_clip_to_folder(
            clip,
            clip["video_path"],
            clip["subtitle_path"],
            destination_folder,
            intro=intro,
            intro_image_path=intro_image_path if intro_image_path.is_file() else None,
        )

        job_manager.update_progress(job_id, 100, "Done")
        job_manager.complete(job_id)
    except JobCancelled:
        return
    except Exception as exc:  # noqa: BLE001 -- reported through the job row
        job_manager.fail(job_id, str(exc))


def run_download_gpu_pack_job(job_id: str) -> None:
    try:
        job_manager.start(job_id)

        def on_progress(fraction: float) -> None:
            _raise_if_cancelled(job_id)
            job_manager.update_progress(job_id, fraction * 100, "Downloading GPU pack")

        download_gpu_pack(on_progress=on_progress)

        # Make the freshly-downloaded DLLs usable immediately, in this same
        # process, instead of requiring an app restart -- and drop the
        # cached (previously "not ready") capability probe so the next
        # /system/capabilities call re-checks for real.
        ensure_cuda_dlls_on_path()
        probe_capabilities.cache_clear()

        job_manager.update_progress(job_id, 100, "Done")
        job_manager.complete(job_id)
    except JobCancelled:
        return
    except Exception as exc:  # noqa: BLE001 -- reported through the job row
        job_manager.fail(job_id, str(exc))


def run_download_youtube_job(
    job_id: str, url: str, media_format: str, resolution: int | None, output_folder: str
) -> None:
    try:
        job_manager.start(job_id)

        def on_progress(fraction: float, step: str) -> None:
            _raise_if_cancelled(job_id)
            job_manager.update_progress(job_id, fraction * 100, step)

        if media_format == "audio":
            final_path = download_youtube_audio(url, output_folder, on_progress=on_progress)
        else:
            assert resolution is not None  # enforced by the API layer before the job is created
            final_path = download_youtube_video(url, resolution, output_folder, on_progress=on_progress)

        # No DB row exists for this one-shot download -- stash the filename
        # in current_step (left untouched by complete()) so the frontend has
        # something to show beyond "100%, Done".
        job_manager.update_progress(job_id, 100, f"Saved as {final_path.name}")
        job_manager.complete(job_id)
    except JobCancelled:
        return
    except Exception as exc:  # noqa: BLE001 -- reported through the job row
        job_manager.fail(job_id, str(exc))


# ---------------------------------------------------------------------------
# Recipe Clipper (PRD docs/RECIPE_CLIPER.md)
# ---------------------------------------------------------------------------


def run_recipe_analyze_job(
    job_id: str,
    project_id: str,
    provider: ProviderConfig,
    target_duration: str = "auto",
    faceless: bool = True,
    use_gpu: bool = False,
) -> None:
    """Understand the cooking video and build a timeline from it.

    Deliberately stops before rendering: the user reviews and edits the
    timeline first (PRD S18), and rendering is a separate job so an edit
    never re-spends the AI budget.
    """
    settings = get_settings()
    try:
        job_manager.start(job_id)
        with get_connection() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            raise ValueError(f"Project not found: {project_id}")

        source_video = project["source_video_path"]
        target = TargetDuration(target_duration)
        video_duration = _usable_video_duration(source_video, project["source_duration"])

        transcript = _recipe_transcript(job_id, project_id, source_video, video_duration, use_gpu)
        _raise_if_cancelled(job_id)

        job_manager.update_progress(job_id, 32, "Detecting cooking steps")
        frames_dir = settings.recipe_frames_dir(project_id)
        probe_frames, interval = frame_sampler.extract_probe_frames(source_video, frames_dir, video_duration)
        segments = frame_sampler.segment_shots(probe_frames, interval)
        frame_sampler.save_frame_index(settings.recipe_frame_index_path(project_id), segments, interval)
        keyframes = frame_sampler.select_keyframes(segments, video_duration)
        _raise_if_cancelled(job_id)

        notes: list[str] = []
        labels, degraded_warning = _label_keyframes(job_id, project_id, provider, keyframes, transcript, notes)
        _raise_if_cancelled(job_id)

        if not labels and (transcript is None or not transcript.text.strip()):
            raise ValueError(
                "This video has no usable speech, and the selected AI model cannot read images, so there is "
                "nothing to analyze. Switch to a vision-capable model under Settings > AI Model and try again."
            )

        job_manager.update_progress(job_id, 74, "Finding important scenes")
        analysis = recipe_analyzer.analyze_recipe(
            provider,
            labels,
            transcript,
            target,
            segments,
            video_duration,
            faceless=faceless,
            on_model_switch=_model_switch_note(notes),
        )
        if degraded_warning:
            analysis.visual_analysis = "unavailable"
            analysis.warnings.insert(0, degraded_warning)
        analysis.warnings.extend(note for note in notes if note not in analysis.warnings)
        if not analysis.scenes:
            raise ValueError(
                "No cooking steps could be identified in this video. If this is not a cooking video, "
                "AI Clipper is the menu you want."
            )
        recipe_analyzer.save_analysis(settings.recipe_analysis_path(project_id), analysis)
        _raise_if_cancelled(job_id)

        job_manager.update_progress(job_id, 82, "Building recipe timeline")
        clip_id = store.ensure_recipe_clip(project_id, analysis.model_dump_json())
        store.replace_scenes(clip_id, analysis.scenes)

        _prepare_scene_framing(job_id, project_id, clip_id, source_video, analysis, faceless)

        job_manager.update_progress(job_id, 100, "Done")
        job_manager.complete(job_id)
    except JobCancelled:
        return
    except Exception as exc:  # noqa: BLE001 -- reported through the job row
        job_manager.fail(job_id, str(exc))


def _recipe_transcript(job_id, project_id, source_video, video_duration, use_gpu):
    """The same transcript AI Clipper builds, cached in the same place -- a
    project analysed by both flows only ever transcribes once."""
    settings = get_settings()
    analysis_dir = settings.project_analysis_dir(project_id)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = analysis_dir / "transcript.json"

    if transcript_path.is_file():
        job_manager.update_progress(job_id, 28, "Reusing existing transcript")
        return TranscriptResult.model_validate_json(transcript_path.read_text(encoding="utf-8"))

    job_manager.update_progress(job_id, 6, "Extracting audio")
    audio_path = analysis_dir / "audio.wav"
    try:
        extract_audio(source_video, str(audio_path))
    except Exception:  # noqa: BLE001 -- a cooking video with no audio is normal (PRD S6)
        return None
    _raise_if_cancelled(job_id)

    def on_transcribe_progress(fraction: float) -> None:
        _raise_if_cancelled(job_id)
        elapsed = fraction * video_duration
        step = f"Transcribing ({_format_mmss(elapsed)} / {_format_mmss(video_duration)})"
        job_manager.update_progress(job_id, 10 + fraction * 18, step)

    job_manager.update_progress(job_id, 10, f"Transcribing (0:00 / {_format_mmss(video_duration)})")
    try:
        transcriber = get_transcriber("cuda", "float16") if use_gpu else get_transcriber()
    except Exception:  # noqa: BLE001 -- GPU requested but unusable; CPU still works
        transcriber = get_transcriber()
    transcript = transcriber.transcribe(str(audio_path), on_progress=on_transcribe_progress)
    transcript_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    return transcript


def _label_keyframes(job_id, project_id, provider, keyframes, transcript, notes: list[str]):
    """Pass 1, resumable, with the honest degrade path (PRD S6, S44, S46).

    Frames labelled by an earlier run are reused as they are, and each new
    batch is written to disk as it arrives -- so a provider that falls over
    halfway costs the user the remaining batches, not all of them.
    """
    settings = get_settings()
    labels_path = settings.recipe_labels_path(project_id)

    done = vision_labeler.load_labels(labels_path)
    already = {label.index for label in done}
    todo = [keyframe for keyframe in keyframes if keyframe.index not in already]
    if done and todo:
        notes.append(f"Reused {len(done)} frames already analysed earlier; {len(todo)} left to look at.")
    if not todo:
        return done, None

    job_manager.update_progress(job_id, 40, "Understanding recipe")

    def on_progress(fraction: float) -> None:
        _raise_if_cancelled(job_id)
        job_manager.update_progress(job_id, 40 + fraction * 32, "Understanding recipe")

    def on_batch(batch_labels) -> None:
        done.extend(batch_labels)
        vision_labeler.save_labels(labels_path, done)

    try:
        vision_labeler.label_frames(
            provider,
            todo,
            transcript,
            on_progress=on_progress,
            on_batch=on_batch,
            on_model_switch=_model_switch_note(notes),
        )
    except VisionUnsupportedError:
        alternative = vision_capability.find_vision_model(provider)
        return [], vision_capability.degraded_message(provider, alternative)

    return sorted(done, key=lambda label: label.time), None


def _model_switch_note(notes: list[str]):
    """Records a model substitution so the finished analysis can say which
    model actually did the work."""

    def note(previous: str, replacement: str) -> None:
        message = (
            f'"{previous}" was overloaded, so the analysis continued on "{replacement}". '
            "Set that model under Settings > AI Model if you want to keep using it."
        )
        if message not in notes:
            notes.append(message)

    return note


def _prepare_scene_framing(job_id, project_id, clip_id, source_video, analysis: RecipeAnalysis, faceless: bool) -> None:
    """Work out each scene's 9:16 framing now, so the timeline can already
    say which scenes could not be kept faceless (PRD S17)."""
    settings = get_settings()
    scenes = analysis.scenes
    for index, scene in enumerate(scenes):
        _raise_if_cancelled(job_id)
        job_manager.update_progress(
            job_id, 84 + 14 * index / max(1, len(scenes)), "Preparing faceless 9:16 preview"
        )
        scene_dir = settings.recipe_scene_dir(project_id, clip_id, scene.scene_id)
        scene_dir.mkdir(parents=True, exist_ok=True)
        segment_path = scene_dir / "framing_probe.mp4"
        try:
            cut_subclip(source_video, scene.source_start, scene.duration, str(segment_path))
            plan, check = face_check.resolve_faceless(
                video_path=str(segment_path),
                target_width=TARGET_WIDTH,
                target_height=TARGET_HEIGHT,
                faceless=faceless,
            )
        except Exception as exc:  # noqa: BLE001 -- a scene that won't scan still gets a usable crop
            metadata = probe_metadata(source_video)
            plan = face_check.center_fallback_plan(metadata.width, metadata.height, TARGET_WIDTH, TARGET_HEIGHT)
            check = None
            plan.fallback_reason = f"Framing fell back to a centre crop: {exc}"
        finally:
            segment_path.unlink(missing_ok=True)
        scene.plan = plan
        scene.face_check = check
    store.replace_scenes(clip_id, scenes)


def run_recipe_generate_job(
    job_id: str,
    clip_id: str,
    audio_mode: str = "keep",
    volume_percent: int = 20,
    output_folder: str | None = None,
) -> None:
    """Render the approved timeline into one video.

    Scenes are cached by content, so a second run that only changes the audio
    or the running order re-encodes nothing at all (PRD S28/S29).
    """
    settings = get_settings()
    try:
        job_manager.start(job_id)
        with get_connection() as conn:
            clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            if clip is None:
                raise ValueError(f"Recipe video not found: {clip_id}")
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (clip["project_id"],)).fetchone()

        project_id = clip["project_id"]
        source_video = project["source_video_path"]
        scenes = [scene for scene in store.load_scenes(clip_id) if scene.enabled]
        if not scenes:
            raise ValueError("The timeline is empty. Keep at least one scene before generating the video.")

        clip_dir = settings.clip_dir(project_id, clip_id)
        clip_dir.mkdir(parents=True, exist_ok=True)
        final_path = clip_dir / "video.mp4"

        with _render_slot(job_id):
            scene_paths = []
            for index, scene in enumerate(scenes):
                _raise_if_cancelled(job_id)
                job_manager.update_progress(
                    job_id, 5 + 80 * index / len(scenes), f"Rendering scene {index + 1} of {len(scenes)}"
                )
                plan = scene.plan
                if plan is None:
                    metadata = probe_metadata(source_video)
                    plan = face_check.center_fallback_plan(
                        metadata.width, metadata.height, TARGET_WIDTH, TARGET_HEIGHT
                    )
                scene_path, _rendered = recipe_assemble.ensure_scene_rendered(
                    source_video,
                    scene_dir=settings.recipe_scene_dir(project_id, clip_id, scene.scene_id),
                    start=scene.source_start,
                    end=scene.source_end,
                    plan=plan,
                )
                scene_paths.append(scene_path)

            _raise_if_cancelled(job_id)
            job_manager.update_progress(job_id, 90, "Assembling video")
            recipe_assemble.assemble(
                scene_paths,
                final_path,
                audio_mode=AudioMode(audio_mode),
                volume_percent=volume_percent,
                concat_path=clip_dir / "concat.txt",
            )

        store.set_clip_video(clip_id, str(final_path), sum(scene.duration for scene in scenes))

        if output_folder:
            job_manager.update_progress(job_id, 95, "Copying to output folder")
            with get_connection() as conn:
                refreshed = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            _copy_to_output_folder(refreshed, final_path, None, output_folder)

        job_manager.update_progress(job_id, 100, "Done")
        job_manager.complete(job_id)
    except JobCancelled:
        return
    except Exception as exc:  # noqa: BLE001 -- reported through the job row
        job_manager.fail(job_id, str(exc))
