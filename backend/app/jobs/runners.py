"""Background job bodies: the actual work behind POST /projects/{id}/analyze
and POST /clips/{id}/generate. Each runs in its own daemon thread (started
by the API routers) and drives `job_manager` through the same
queued->running->completed/failed lifecycle every job uses.
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.ai_providers.registry import ProviderConfig
from app.core.clip_export import copy_clip_to_folder
from app.core.config import get_settings
from app.core.ffmpeg_utils import cut_subclip, extract_audio, probe_metadata
from app.core.gpu_pack import download_gpu_pack
from app.core.gpu_utils import ensure_cuda_dlls_on_path
from app.core.system_capabilities import probe_capabilities
from app.db.connection import get_connection
from app.jobs.manager import job_manager
from app.pipeline.ai_analysis.clip_selector import select_clips
from app.pipeline.reframe.models import ReframeMode
from app.pipeline.reframe.modes import resolve as resolve_reframe
from app.pipeline.render import render as render_clip
from app.pipeline.subtitle import build_initial_document, burn_ass_subtitles, load_clip_words
from app.pipeline.subtitle.ass_render import render_ass
from app.pipeline.subtitle.models import load_document, save_document
from app.pipeline.transcribe import TranscriptResult, get_transcriber

TARGET_WIDTH = 720
TARGET_HEIGHT = 1280


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
        (analysis_dir / "transcript.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
        _raise_if_cancelled(job_id)

        job_manager.update_progress(job_id, 60, "Finding best moments (waiting for AI provider)")
        candidates = select_clips(provider, transcript, num_clips, video_duration=project["source_duration"])
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

        job_manager.update_progress(job_id, 15, "Cutting segment")
        cut_subclip(project["source_video_path"], clip["start_time"], clip["duration"], str(subclip_path))
        _raise_if_cancelled(job_id)

        job_manager.update_progress(job_id, 30, "Resolving active speaker crop")
        metadata = probe_metadata(str(subclip_path))
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

        if not rendered_path.exists():
            job_manager.update_progress(job_id, 5, "Rebuilding clip (one-time, no video previously saved)")
            subclip_path = clip_dir / "source_segment.mp4"
            cut_subclip(project["source_video_path"], clip["start_time"], clip["duration"], str(subclip_path))
            _raise_if_cancelled(job_id)
            metadata = probe_metadata(str(subclip_path))
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
