"""Which skills a chunk of course material is about.

Course-agnostic: every skill in the registry is scored with its own
``keywords`` and title, so a new course needs no changes here. A phrase in
the chunk's heading counts three times as much as one in the body, and
repeated mentions have diminishing returns (a slide that says "chain rule"
ten times is not ten times as much about it). Scores are scaled so the
strongest skill in a clearly focused chunk lands near 1.
"""

from __future__ import annotations

import math
import re
from functools import cache

from slate_skills import all_skills

HEADING_WEIGHT = 3.0
FLOOR = 0.15
# Raw score that counts as "clearly about this skill": two body mentions of a
# keyword plus the title once in the heading, roughly.
SATURATION = 4.0


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"[\s\-_]+", " ", text)


@cache
def _patterns() -> dict[str, list[re.Pattern[str]]]:
    out: dict[str, list[re.Pattern[str]]] = {}
    for skill in all_skills():
        phrases = {_norm(skill.title), *(_norm(k) for k in skill.keywords)}
        out[skill.id] = [re.compile(rf"(?<![a-z]){re.escape(p)}(?![a-z])") for p in phrases if len(p) >= 3]
    return out


def _mentions(text: str, patterns: list[re.Pattern[str]]) -> float:
    total = 0.0
    for pattern in patterns:
        count = len(pattern.findall(text))
        if count:
            total += 1 + math.log2(count)  # 1, 2, 2.6, 3, ...
    return total


def match_skills(text: str, heading: str = "") -> dict[str, float]:
    body = _norm(text)
    head = _norm(heading)
    raw: dict[str, float] = {}
    for skill_id, patterns in _patterns().items():
        score = _mentions(body, patterns) + HEADING_WEIGHT * _mentions(head, patterns)
        if score > 0:
            raw[skill_id] = score
    out = {}
    for skill_id, score in raw.items():
        value = round(min(1.0, score / SATURATION), 3)
        if value >= FLOOR:
            out[skill_id] = value
    return out


def top_skill(scores: dict[str, float]) -> tuple[str, float] | None:
    if not scores:
        return None
    skill_id = max(scores, key=lambda k: scores[k])
    return skill_id, scores[skill_id]
