"""Speech-to-text via faster-whisper (PRD S19): word + segment timestamps.

Model size defaults to "base" (multilingual -- the Step 2 test content is
Indonesian) on CPU with int8 quantization, matching the CPU-only decision
already made for this machine in Step 2. `get_transcriber()` caches the
loaded model process-wide since loading it is the expensive part, not
running it.
"""

from __future__ import annotations

from functools import lru_cache

from faster_whisper import WhisperModel
from pydantic import BaseModel


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


class Transcriber:
    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8") -> None:
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: str) -> TranscriptResult:
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

        return TranscriptResult(words=words, segments=segments, text=" ".join(text_parts))


@lru_cache
def get_transcriber() -> Transcriber:
    return Transcriber()
