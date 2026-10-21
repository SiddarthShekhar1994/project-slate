"""Answer a student's question about one lesson step.

Claude answers in the context of the step on screen: its narration, what is
on the board so far, the skill's formula, and (when the lesson came from
uploaded sources) the cited source excerpts. The answer comes back as
structured output with every checkable math statement listed separately;
each one is verified with SymPy. If any fails, Claude gets one more try with
the failures named. If the answer still does not check out, or no API key is
configured, the student gets the step's own verified content instead.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from slate_skills import get_skill

from .llm import LLMRefused, LLMUnavailable, get_llm
from .verify.claims import check_claim

SYSTEM = """You are Slate's math tutor, answering a student's question about one step of a narrated calculus lesson.

Answer the question directly in 2 to 5 sentences, in plain, friendly language for a first-year university student.
Stay grounded in the step you are given and the lesson so far. If the question is off topic, say briefly that you can
only help with this lesson and suggest what to ask instead.

Formatting rules:
- Write every piece of math in LaTeX between single dollar signs, like $3x^2\\cos(x^3+1)$. Never write math as plain
  text such as x^2 or sqrt(x).
- Use the same notation the lesson uses.
- No headings, no bullet lists, no markdown other than the dollar-sign math.

Checkable claims: list every mathematical fact your answer asserts that could be checked by a computer algebra
system, such as a derivative or an equality, in the claims field. Write claim expressions in this plain syntax:
^ for powers, * or juxtaposition for products, sqrt(), sin(), cos(), tan(), sec(), exp(), ln(), e and pi.
Use kind "derivative" with of, var and equals for statements like d/dx f = g, and kind "equal" with left, right
and the variables for identities. Every claim must be true; the claims are verified before the student sees your
answer."""


class Claim(BaseModel):
    kind: Literal["derivative", "equal"]
    of: str = ""
    var: str = "x"
    equals: str = ""
    left: str = ""
    right: str = ""
    vars: list[str] = Field(default_factory=lambda: ["x"])


class TutorAnswer(BaseModel):
    answer: str
    claims: list[Claim]


def _claim_dict(claim: Claim) -> dict:
    if claim.kind == "derivative":
        return {"kind": "derivative", "of": claim.of, "var": claim.var, "equals": claim.equals, "vars": claim.vars}
    return {"kind": "equal", "left": claim.left, "right": claim.right, "vars": claim.vars}


def _board_so_far(script: dict, step: int) -> list[str]:
    lines = []
    for s in script["steps"][: step + 1]:
        lines += [a["latex"] for a in s["actions"] if a["type"] == "write"]
    return lines


def _caption(narration: list) -> str:
    return "".join(seg if isinstance(seg, str) else f"${seg['math']}$" for seg in narration)


def context_for(script: dict, step: int) -> str:
    skill = get_skill(script["skillId"])
    current = script["steps"][step]
    parts = [
        f"Lesson: {script['title']} (skill: {skill.title}).",
        f"Formula: ${skill.formula.latex}$. {skill.formula.note}",
        "Steps so far:",
    ]
    for i, s in enumerate(script["steps"][: step + 1]):
        parts.append(f"{i + 1}. {s['title']}: {_caption(s['narration'])}")
    parts.append("Board so far (LaTeX): " + " | ".join(_board_so_far(script, step)))
    parts.append(f"The student is on step {step + 1}: {current['title']}.")
    for source in script.get("sources", []):
        if source.get("excerpt"):
            parts.append(f"From the student's source {source['title']} ({source.get('locator', '')}): {source['excerpt']}")
    return "\n".join(parts)


def fallback_answer(script: dict, step: int) -> str:
    current = script["steps"][step]
    skill = get_skill(script["skillId"])
    return (f"This step, {current['title'].lower()}, says: {_caption(current['narration'])} "
            f"The rule behind it: ${skill.formula.latex}$. {skill.formula.note}")


def answer_question(script: dict, step: int, question: str) -> dict:
    """Returns {answer, verified, notes, source}."""
    llm = get_llm()
    if not llm.available:
        return {"answer": fallback_answer(script, step), "verified": True, "source": "fallback",
                "notes": ["Free-form answers need the Claude API, which isn't set up on this server. "
                          "Here is the step again."]}

    context = context_for(script, step)
    request = f"{context}\n\nThe student asks: {question.strip()}"
    failures: list[str] = []
    for _ in range(2):
        prompt = request
        if failures:
            prompt += ("\n\nYour previous answer stated claims that are false: " + "; ".join(failures)
                       + ". Correct them and answer again.")
        try:
            result = llm.structured(system=SYSTEM, content=prompt, schema=TutorAnswer, effort="medium",
                                    max_tokens=4000)
        except (LLMUnavailable, LLMRefused):
            break
        checks = [check_claim(_claim_dict(c), f"claim {i + 1}") for i, c in enumerate(result.claims)]
        failures = [f"{c.where}: {c.detail}" for c in checks if not c.ok]
        if not failures:
            return {"answer": result.answer, "verified": True, "source": "claude",
                    "notes": [f"{len(checks)} math {'statement' if len(checks) == 1 else 'statements'} checked."]
                    if checks else []}
    return {"answer": fallback_answer(script, step), "verified": True, "source": "fallback",
            "notes": ["I couldn't produce an answer whose math checked out, so here is the step again."]}
