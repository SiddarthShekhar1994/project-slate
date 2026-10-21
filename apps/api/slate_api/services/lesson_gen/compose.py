"""Build a sound lesson without an LLM.

The composer takes a verified difficulty-2 problem for the skill and turns its
worked steps into a board lesson: the problem is written first, then one
board step per solution step, with a pause-and-predict checkpoint before the
answer whose distractors are the skill's own mistake patterns. It cites the
student's best matching sources and writes everything in their professor's
notation. Every lesson it produces passes the same checks as Claude's.
"""

from __future__ import annotations

import random
import re

import sympy as sp
from slate_skills import get_skill
from slate_skills.core.text import render, tex

from ..ingest.notation import NotationProfile, apply_notation
from ..problem_gen import generate
from ..tts import spoken_words
from ..verify import constraint_of, equivalent
from . import ChunkRef
from .speech import speak
from .validate import validate_script

MAX_SOURCES = 3


def typed(expr: sp.Expr) -> str:
    """An expression in Slate's answer syntax, readable by the parser."""
    return re.sub(r"\bE\b", "e", sp.sstr(expr).replace("**", "^"))


def _sources(chunks: list[ChunkRef]) -> list[dict]:
    return [
        {"id": c.id, "title": c.source_title, "kind": c.source_kind, "locator": c.locator,
         "excerpt": re.sub(r"\s+", " ", c.text)[:400]}
        for c in chunks[:MAX_SOURCES]
    ]


def latex_say(latex: str) -> str:
    """Rough spoken form for small LaTeX snippets in titles (dy/dx, x = 2)."""
    text = re.sub(r"\\frac\{d([a-z]?)\}\{d([a-z])\}", r" d \1 d \2 ", latex)
    text = text.replace("=", " equals ").replace("'", " prime ")
    text = re.sub(r"\\[a-zA-Z]+|[{}^_]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _segments(text: str) -> list:
    """Prose with $...$ math as narration segments."""
    out: list = []
    for i, part in enumerate(re.split(r"\$([^$]*)\$", text)):
        if not part:
            continue
        out.append({"math": part, "say": latex_say(part)} if i % 2 else part)
    return out


def _step(step_id: str, title: str, before: list, latex: str, say: str, row: int, *, size: str = "md",
          box: str | None = None) -> dict:
    words_before = len(spoken_words(before))
    narration = [*before, {"math": latex, "say": say}, "."]
    actions = [{"type": "write", "id": step_id, "at": {"word": words_before}, "latex": latex, "row": row,
                "size": size, "duration": 1400}]
    if box:
        actions.append({"type": "box", "at": {"word": len(spoken_words(narration)) - 1}, "target": step_id,
                        "color": box})
    return {"id": step_id, "title": title, "narration": narration, "actions": actions}


def compose_script(skill_id: str, chunks: list[ChunkRef], notation: NotationProfile | None, seed: int = 0) -> dict:
    skill = get_skill(skill_id)
    problem = generate(skill_id, 2, seed, word=False)
    built = problem.built
    implicit = built.task == "implicit_differentiate"
    nt = lambda latex: apply_notation(latex, notation)  # noqa: E731

    if implicit:
        statement = tex(built.equation)
        statement_say = speak(built.equation)
    else:
        statement = f"f({tex(built.var)}) = {tex(built.expr)}"
        statement_say = f"f of {built.var.name} equals {speak(built.expr)}"

    sources = _sources(chunks)
    cite = (f" This follows {sources[0]['title']}, {sources[0]['locator']}." if sources else "")
    steps = [{
        **_step("problem", "The problem", ["Here is a problem to work through together: "], nt(statement),
                statement_say, 0, size="lg"),
    }]
    steps[0]["narration"][-1] = "." + cite
    if sources:
        steps[0]["sources"] = [s["id"] for s in sources]

    worked = [s for s in built.steps if s.id != "evaluate"]
    for i, step in enumerate(worked):
        if step.expr is not None:
            before, say = [*_segments(step.title), ": that gives "], speak(step.expr)
        else:
            before, say = [*_segments(step.title), ", as written here"], "on the board"
        steps.append(_step(f"s{i + 1}-{step.id}", step.title, before, nt(step.latex), say, i + 1))

    # Pause and predict before the last worked step: the answer against the skill's real mistakes.
    symbols = built.symbols
    constraint = constraint_of(built)
    options = [{"expr": built.key, "correct": True, "why": "That's the derivative, step by step."}]
    for pattern in skill.mistakes:
        if len(options) == 4:
            break
        try:
            wrong = pattern.buggy(built)
        except Exception:
            continue
        if wrong is None:
            continue
        if any(equivalent(wrong, o["expr"], symbols, constraint=constraint).equal is not False for o in options):
            continue
        if equivalent(wrong, built.key, symbols).equal is not False:
            continue
        options.append({"expr": wrong, "correct": False, "why": render(pattern.note, built)})
    if len(options) >= 2:
        random.Random(seed).shuffle(options)
        if implicit:
            expect = {"kind": "equal", "left": typed(built.key), "right": typed(built.key),
                      "vars": [s.name for s in symbols]}
        else:
            expect = {"kind": "derivative", "of": typed(built.expr), "var": built.var.name, "equals": typed(built.key)}
        steps[-2]["checkpoint"] = {
            "prompt": "Pause and predict: what is the derivative?",
            "expect": expect,
            "options": [
                {"id": chr(97 + i), "latex": nt(tex(o["expr"])), "value": typed(o["expr"]), "say": speak(o["expr"]),
                 "correct": o["correct"], "why": o["why"]}
                for i, o in enumerate(options)
            ],
        }

    answer = nt(tex(built.key))
    answer_label = r"\frac{dy}{dx}" if implicit else f"f'({tex(built.var)})"
    final_say = f"{'d y d x' if implicit else 'f prime of ' + built.var.name} equals {speak(built.key)}"
    steps.append(_step("answer", "The answer", ["So the answer is "], nt(f"{answer_label} = {answer}"), final_say,
                       len(worked) + 1, size="lg", box="mint"))
    if implicit:
        fx, fy = sp.diff(built.expr, built.var), sp.diff(built.expr, built.dependent)
        steps[-1]["claims"] = [{"kind": "equal", "left": typed(-fx / fy), "right": typed(built.key),
                                "vars": [s.name for s in symbols]}]
    else:
        steps[-1]["claims"] = [{"kind": "derivative", "of": typed(built.expr), "var": built.var.name,
                                "equals": typed(built.key)}]

    script = {
        "id": f"composed-{skill.slug}-{problem.signature[:8]}",
        "version": 1,
        "skillId": skill.id,
        "title": f"{skill.title}, worked from your sources" if sources else skill.title,
        "summary": skill.summary,
        "sources": sources,
        "steps": steps,
    }
    problems = validate_script(script, {c.id for c in chunks})
    if problems:
        raise ValueError(f"composed lesson failed validation: {problems}")
    return script
