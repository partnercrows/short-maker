"""Lenient JSON extraction from LLM chat responses.

LLMs routinely wrap JSON in markdown code fences, prepend a "<think>"
reasoning block, or add a stray trailing comma. The idea (not the code)
is borrowed from clipforge's `extract_json`, reimplemented independently
-- see docs/THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import json
import re
from typing import Any

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")


def extract_json(text: str) -> Any:
    """Best-effort JSON parse of an LLM response. Raises ValueError with
    the original text attached if nothing usable is found."""
    candidate = _THINK_TAG_RE.sub("", text).strip()

    fence_match = _CODE_FENCE_RE.search(candidate)
    if fence_match:
        candidate = fence_match.group(1).strip()

    candidate = _isolate_outermost_json(candidate)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        repaired = _TRAILING_COMMA_RE.sub(r"\1", candidate)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Could not parse JSON from model response: {text[:500]!r}") from exc


def _isolate_outermost_json(text: str) -> str:
    start = None
    for i, char in enumerate(text):
        if char in "{[":
            start = i
            break
    if start is None:
        return text

    end = None
    for i in range(len(text) - 1, -1, -1):
        if text[i] in "}]":
            end = i
            break
    if end is None or end <= start:
        return text

    return text[start : end + 1]
