"""Speech-to-text via faster-whisper (PRD S19): word + segment timestamps.

Model size defaults to "base" (multilingual -- the Step 2 test content is
Indonesian) on CPU with int8 quantization, matching the CPU-only decision
already made for this machine in Step 2. `get_transcriber()` caches the
loaded model process-wide since loading it is the expensive part, not
running it.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel
from pydantic import BaseModel

from app.core.ffmpeg_utils import probe_duration, slice_audio

# faster-whisper's CPU feature extractor computes the log-mel spectrogram for
# the *entire* input in one array (see faster_whisper/feature_extractor.py's
# hand-rolled `stft()` -- it isn't chunked or streamed). A 77-minute file
# needs a ~1.4 GiB single contiguous complex128 allocation for that, which
# fails outright on a memory-constrained machine ("Unable to allocate ... for
# an array with shape (1, 465571, 201)"). Splitting first keeps every
# allocation to a size that's fine even under memory pressure, at the cost of
# a (usually imperceptible) decoder context reset at each chunk boundary.
_CHUNK_SECONDS = 600.0


class Word(BaseModel):
    text: str
    start: float
    end: float


class Segment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptResult(BaseModel):
    words: list[Word]
    segments: list[Segment]
    text: str


def offset_result(result: TranscriptResult, offset: float) -> TranscriptResult:
    """Shift every timestamp in a transcript by `offset` seconds -- used to
    stitch a chunk's transcript back into the full audio's timeline."""
    if offset == 0:
        return result
    return TranscriptResult(
        words=[Word(text=w.text, start=w.start + offset, end=w.end + offset) for w in result.words],
        segments=[Segment(start=s.start + offset, end=s.end + offset, text=s.text) for s in result.segments],
        text=result.text,
    )


class Transcriber:
    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8") -> None:
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: str, on_progress: Callable[[float], None] | None = None) -> TranscriptResult:
        """`on_progress` (if given) is called with a 0..1 fraction of audio
        duration transcribed so far -- faster-whisper's segment generator
        only reports what it just finished, not a percentage, so this
        turns "current_step: Transcribing" into something a job consumer
        can show real progress and an ETA for, instead of a flat number."""
        total_duration = probe_duration(audio_path)
        if total_duration <= _CHUNK_SECONDS:
            return self._transcribe_one(audio_path, duration=total_duration, on_progress=on_progress)

        all_words: list[Word] = []
        all_segments: list[Segment] = []
        text_parts: list[str] = []
        with tempfile.TemporaryDirectory(prefix="short-maker-transcribe-") as tmp_dir:
            offset = 0.0
            while offset < total_duration:
                chunk_duration = min(_CHUNK_SECONDS, total_duration - offset)
                chunk_path = str(Path(tmp_dir) / f"chunk_{int(offset)}.wav")
                slice_audio(audio_path, offset, chunk_duration, chunk_path)

                def chunk_progress(fraction: float, _offset: float = offset, _chunk_duration: float = chunk_duration) -> None:
                    if on_progress:
                        on_progress(min(1.0, (_offset + fraction * _chunk_duration) / total_duration))

                chunk_result = self._transcribe_one(chunk_path, duration=chunk_duration, on_progress=chunk_progress)
                shifted = offset_result(chunk_result, offset)
                all_words.extend(shifted.words)
                all_segments.extend(shifted.segments)
                if shifted.text:
                    text_parts.append(shifted.text)

                offset += chunk_duration

        return TranscriptResult(words=all_words, segments=all_segments, text=" ".join(text_parts))

    def _transcribe_one(
        self, audio_path: str, *, duration: float, on_progress: Callable[[float], None] | None
    ) -> TranscriptResult:
        segments_iter, _info = self._model.transcribe(audio_path, word_timestamps=True)

        words: list[Word] = []
        segments: list[Segment] = []
        text_parts: list[str] = []

        for segment in segments_iter:
            segment_text = segment.text.strip()
            segments.append(Segment(start=segment.start, end=segment.end, text=segment_text))
            text_parts.append(segment_text)
            for word in segment.words or []:
                words.append(Word(text=word.word.strip(), start=word.start, end=word.end))
            if on_progress and duration > 0:
                on_progress(min(1.0, segment.end / duration))

        return TranscriptResult(words=words, segments=segments, text=" ".join(text_parts))


@lru_cache
def get_transcriber(device: str = "cpu", compute_type: str = "int8") -> Transcriber:
    return Transcriber(device=device, compute_type=compute_type)
