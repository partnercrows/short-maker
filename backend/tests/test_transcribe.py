from app.pipeline.transcribe import Segment, TranscriptResult, Word, offset_result


def test_offset_result_shifts_words_and_segments():
    result = TranscriptResult(
        words=[Word(text="hi", start=1.0, end=1.5)],
        segments=[Segment(start=0.5, end=2.0, text="hi there")],
        text="hi there",
    )

    shifted = offset_result(result, 100.0)

    assert shifted.words[0].start == 101.0
    assert shifted.words[0].end == 101.5
    assert shifted.segments[0].start == 100.5
    assert shifted.segments[0].end == 102.0
    assert shifted.text == "hi there"


def test_offset_result_zero_offset_returns_same_object():
    result = TranscriptResult(words=[], segments=[], text="")
    assert offset_result(result, 0) is result
