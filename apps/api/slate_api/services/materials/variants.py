"""Similar problems for practice, written by Claude and checked like a sheet's.

A miss in practice asks for a new problem of the same kind. For a built-in
skill Slate's templates make one; for a topic from the student's materials
(related rates, limits) Claude writes problems in the same structured form as
a sheet's, and each goes through ``verify.py`` before it can be served.
"""

from __future__ import annotations

from pydantic import BaseModel

from .read import SYSTEM, ProblemOut

MAX_VARIANTS = 8

VARIANT_SYSTEM = SYSTEM + """

# Writing practice problems
Instead of reading material, you are now writing new practice problems for one topic, in exactly the format above. Each problem must be self-contained, have a single clean answer that you work out carefully, and use different numbers and functions from the examples and from each other. Keep them at the examples' difficulty. Use the same kinds as the examples (when there are no examples, pick the kinds that fit the topic), never kind "other". Leave label empty and set chunk to 0."""


class VariantSet(BaseModel):
    problems: list[ProblemOut]


def write_variants(llm, *, topic: str, summary: str, examples: list[dict], count: int) -> list[ProblemOut]:
    """``count`` new problems on ``topic`` like ``examples`` (each with statement, kind, spec and answer)."""
    count = max(1, min(count, MAX_VARIANTS))
    lines = [f"Topic: {topic}." + (f" {summary}" if summary else ""), f"Write {count} new problems."]
    if examples:
        lines.append("Examples from the student's material:")
        for ex in examples:
            lines.append(f"- kind {ex['kind']}: {ex['statement']} (answer: {ex['answer']})")
    result = llm.structured(system=VARIANT_SYSTEM, content="\n".join(lines), schema=VariantSet, effort="medium",
                            max_tokens=16000)
    return [p for p in result.problems if p.kind != "other"][:count]
