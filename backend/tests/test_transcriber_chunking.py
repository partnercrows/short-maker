from unittest.mock import MagicMock, patch


class _FakeWord:
    def __init__(self, word, start, end):
        self.word = word
        self.start = start
        self.end = end


class _FakeSegment:
    def __init__(self, start, end, text, words):
        self.start = start
        self.end = end
        self.text = text
        self.words = words


def _make_transcriber():
    with patch("app.pipeline.transcribe.WhisperModel"):
        from app.pipeline.transcribe import Transcriber

        return Transcriber()


def test_transcribe_splits_long_audio_and_offsets_each_chunk(monkeypatch):
    transcriber = _make_transcriber()

    def fake_model_transcribe(path, word_timestamps=True):
        words = [_FakeWord("w", 0.0, 5.0)]
        segment = _FakeSegment(0.0, 5.0, "w", words)
        return iter([segment]), MagicMock(duration=5.0)

    transcriber._model.transcribe.side_effect = fake_model_transcribe

    slice_calls = []

    def fake_slice_audio(audio_path, start, duration, output_path):
        slice_calls.append((start, duration))
        open(output_path, "w").close()

    monkeypatch.setattr("app.pipeline.transcribe.probe_duration", lambda path: 1300.0)
    monkeypatch.setattr("app.pipeline.transcribe.slice_audio", fake_slice_audio)

    progress_values = []
    result = transcriber.transcribe("fake.wav", on_progress=progress_values.append)

    # 600s chunks over a 1300s file: [0, 600), [600, 1200), [1200, 1300)
    assert slice_calls == [(0.0, 600.0), (600.0, 600.0), (1200.0, 100.0)]

    # Each chunk's (locally-zeroed) word timestamp comes back shifted by that chunk's start.
    assert [w.start for w in result.words] == [0.0, 600.0, 1200.0]
    assert [s.start for s in result.segments] == [0.0, 600.0, 1200.0]

    assert len(progress_values) == 3
    assert progress_values == sorted(progress_values)
    assert all(0.0 <= p <= 1.0 for p in progress_values)


def test_transcribe_does_not_chunk_short_audio(monkeypatch):
    transcriber = _make_transcriber()

    def fake_model_transcribe(path, word_timestamps=True):
        segment = _FakeSegment(0.0, 10.0, "hi", [_FakeWord("hi", 0.0, 10.0)])
        return iter([segment]), MagicMock(duration=10.0)

    transcriber._model.transcribe.side_effect = fake_model_transcribe
    monkeypatch.setattr("app.pipeline.transcribe.probe_duration", lambda path: 10.0)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("slice_audio should not be called for audio shorter than the chunk size")

    monkeypatch.setattr("app.pipeline.transcribe.slice_audio", fail_if_called)

    result = transcriber.transcribe("fake.wav")
    assert result.words[0].start == 0.0
