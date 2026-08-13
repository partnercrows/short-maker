import pytest

from app.pipeline.ai_analysis.json_utils import extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_json_wrapped_in_code_fence():
    text = '```json\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}


def test_json_wrapped_in_plain_code_fence():
    text = '```\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}


def test_think_tag_is_stripped():
    text = '<think>let me consider this</think>\n{"a": 1}'
    assert extract_json(text) == {"a": 1}


def test_trailing_comma_is_repaired():
    text = '{"a": 1, "b": [1, 2,],}'
    assert extract_json(text) == {"a": 1, "b": [1, 2]}


def test_leading_and_trailing_commentary_is_ignored():
    text = 'Sure, here is the JSON:\n{"a": 1}\nHope that helps!'
    assert extract_json(text) == {"a": 1}


def test_unparseable_text_raises_value_error():
    with pytest.raises(ValueError):
        extract_json("this is not json at all")
