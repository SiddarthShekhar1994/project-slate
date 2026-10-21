"""Ask Claude for a lesson, check it, retry with the problems, or fall back to the composer."""

from __future__ import annotations

import logging

from ..ingest.notation import NotationProfile, apply_notation
from ..llm import LLMRefused, LLMUnavailable, get_llm
from ..verify.claims import script_is_sound
from . import ChunkRef, GenerationResult
from .compose import compose_script
from .prompt import SYSTEM, build_request
from .schema import Lesson, to_script
from .validate import validate_script

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


def check(script: dict, chunks: list[ChunkRef]) -> list[str]:
    problems = validate_script(script, {c.id for c in chunks})
    ok, results = script_is_sound(script)
    if not ok:
        problems += [f"{r.where}: {r.detail}" for r in results if not r.ok]
    return problems


def _apply_notation(script: dict, notation: NotationProfile | None) -> dict:
    """Belt and braces: rewrite any default notation Claude slipped into."""
    if notation is None:
        return script
    for step in script["steps"]:
        for seg in step["narration"]:
            if isinstance(seg, dict):
                seg["math"] = apply_notation(seg["math"], notation)
        for action in step["actions"]:
            if "latex" in action:
                action["latex"] = apply_notation(action["latex"], notation)
        if "checkpoint" in step:
            for option in step["checkpoint"]["options"]:
                option["latex"] = apply_notation(option["latex"], notation)
    return script


def generate(skill_id: str, chunks: list[ChunkRef], notation: NotationProfile | None, *, llm=None,
             seed: int = 0) -> GenerationResult:
    llm = llm if llm is not None else get_llm()
    feedback: list[str] = []
    attempts = 0
    if llm.available:
        for attempts in range(1, MAX_ATTEMPTS + 1):
            try:
                model = llm.structured(system=SYSTEM, content=build_request(skill_id, chunks, notation, feedback),
                                       schema=Lesson, effort="high", max_tokens=16000)
            except (LLMUnavailable, LLMRefused) as exc:
                log.info("lesson generation fell back to the composer: %s", exc)
                break
            script, problems = to_script(model, chunks, skill_id)
            script = _apply_notation(script, notation)
            problems += check(script, chunks)
            if not problems:
                return GenerationResult(script=script, method="claude", attempts=attempts)
            feedback = problems
            log.info("lesson attempt %d rejected: %s", attempts, problems[:5])
    script = compose_script(skill_id, chunks, notation, seed)
    problems = check(script, chunks)
    if problems:
        raise ValueError(f"composed lesson is not sound: {problems}")
    return GenerationResult(script=script, method="composer", attempts=attempts, problems=feedback)
