"""Ask Claude for a lesson, check it, retry with the problems, or fall back to the composer."""

from __future__ import annotations

import logging

from slate_skills import get_skill

from .. import sandbox
from ..ingest.notation import NotationProfile, apply_notation
from ..llm import LLMRefused, LLMUnavailable, get_llm
from ..materials.verify import check as check_problem
from ..verify.claims import check_script_payload
from . import ChunkRef, GenerationResult
from .compose import compose_script
from .prompt import SYSTEM, build_request
from .schema import Example, Lesson, example_payload, to_script
from .validate import validate_script

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# SymPy limits and integrals have no cancellation; the checks run where they can be stopped.
SCRIPT_CHECK_TIMEOUT = 90.0
EXAMPLE_CHECK_TIMEOUT = 30.0


def _sandboxed(fn, payload: dict, timeout: float, what: str) -> dict | None:
    try:
        return sandbox.run(fn, payload, timeout=timeout)
    except sandbox.SandboxTimeout:
        log.info("checking %s timed out", what)
    except sandbox.SandboxError as exc:
        log.info("checking %s failed: %s", what, exc)
    return None


def check_example(example: Example) -> tuple[list[str], dict]:
    """Compute the worked example's answer with SymPy and compare it with the lesson's."""
    if example.kind == "other":
        return [], {"kind": "other", "ok": None}
    result = _sandboxed(check_problem, example_payload(example), EXAMPLE_CHECK_TIMEOUT, "the worked example")
    if result is None:
        return ["worked example: SymPy took too long to work it out; pick a simpler example"], {"ok": False}
    record = {"kind": example.kind, "ok": result["ok"], "statement": example.statement,
              "answer": example.answer, "key_latex": result.get("key_latex")}
    if result["ok"]:
        return [], record
    failed = [c for c in result["report"]["checks"] if not c["passed"]]
    detail = failed[0]["detail"] if failed and failed[0].get("detail") else result.get("reason", "")
    return [f"worked example: {detail}"], record


def check(script: dict, chunks: list[ChunkRef], example: Example | None = None) -> tuple[list[str], dict]:
    """Every problem with the lesson, and the verification record to store with it."""
    problems = validate_script(script, {c.id for c in chunks})
    record = _sandboxed(check_script_payload, script, SCRIPT_CHECK_TIMEOUT, "the lesson's claims")
    if record is None:
        record = {"ok": False, "checks": []}
        problems.append("checking the lesson's math took too long; keep each claim to one short step")
    problems += [f"{c['where']}: {c['detail']}" for c in record["checks"] if not c["ok"]]
    if example is not None:
        example_problems, record["example"] = check_example(example)
        problems += example_problems
    record["ok"] = not problems
    return problems, record


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


def can_compose(skill_id: str) -> bool:
    """The composer needs templates: only built-in skills have them."""
    try:
        return bool(get_skill(skill_id).families)
    except KeyError:
        return False


def generate(skill_id: str, chunks: list[ChunkRef], notation: NotationProfile | None, *, llm=None,
             seed: int = 0, examples: list[dict] | None = None) -> GenerationResult:
    llm = llm if llm is not None else get_llm()
    feedback: list[str] = []
    attempts = 0
    if llm.available:
        for attempts in range(1, MAX_ATTEMPTS + 1):
            try:
                model = llm.structured(system=SYSTEM,
                                       content=build_request(skill_id, chunks, notation, feedback, examples),
                                       schema=Lesson, effort="high", max_tokens=20000)
            except (LLMUnavailable, LLMRefused) as exc:
                log.info("lesson generation stopped: %s", exc)
                break
            script, problems = to_script(model, chunks, skill_id)
            script = _apply_notation(script, notation)
            found, record = check(script, chunks, model.example)
            problems += found
            if not problems:
                return GenerationResult(script=script, method="claude", attempts=attempts, record=record)
            feedback = problems
            log.info("lesson attempt %d rejected: %s", attempts, problems[:5])
    if not can_compose(skill_id):
        raise ValueError("no lesson checked out" + (f": {feedback[:3]}" if feedback else ""))
    script = compose_script(skill_id, chunks, notation, seed)
    problems, record = check(script, chunks)
    if problems:
        raise ValueError(f"composed lesson is not sound: {problems}")
    return GenerationResult(script=script, method="composer", attempts=attempts, problems=feedback, record=record)
