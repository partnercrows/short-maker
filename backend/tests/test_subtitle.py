from app.pipeline.subtitle import group_into_lines, lines_to_srt, slice_words
from app.pipeline.transcribe import Word


def _word(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def test_slice_words_filters_and_shifts_timestamps():
    words = [_word("a", 10.0, 10.5), _word("b", 12.0, 12.5), _word("c", 20.0, 20.5)]
    sliced = slice_words(words, clip_start=10.0, clip_end=15.0)
    assert [w.text for w in sliced] == ["a", "b"]
    assert sliced[0].start == 0.0
    assert sliced[1].start == 2.0


def test_group_into_lines_respects_word_count():
    words = [_word(str(i), i, i + 0.5) for i in range(10)]
    lines = group_into_lines(words, max_words_per_line=4, max_line_duration=999.0)
    assert [len(line.text.split()) for line in lines] == [4, 4, 2]


def test_group_into_lines_respects_max_duration():
    words = [_word("a", 0.0, 0.5), _word("b", 3.0, 3.5), _word("c", 6.0, 6.5)]
    lines = group_into_lines(words, max_words_per_line=99, max_line_duration=4.0)
    # "c" starts far enough after "a" that including it would exceed max_line_duration
    assert len(lines) == 2
    assert lines[0].text == "a b"
    assert lines[1].text == "c"


def test_lines_to_srt_format():
    from app.pipeline.subtitle import SubtitleLine

    srt = lines_to_srt([SubtitleLine(start=0.0, end=1.5, text="hello")])
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nhello")
