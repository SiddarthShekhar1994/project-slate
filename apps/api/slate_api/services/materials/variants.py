"""Similar problems for practice, written by Claude and checked like a sheet's.

A miss in practice asks for a new problem of the same kind. For a built-in
skill Slate's templates make one; for a topic from the student's materials
(related rates, limits) Claude writes problems in the same structured form as
a sheet's, and each goes through ``verify.py`` before it can be served.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .read import SYSTEM, ProblemOut

MAX_VARIANTS = 8

VARIANT_SYSTEM = SYSTEM + """

# Writing practice problems
Instead of reading material, you are now writing new practice problems for one topic, in exactly the format above. Each problem must be self-contained, have a single clean answer that you work out carefully, and use different numbers and functions from the examples and from each other. Keep them at the examples' difficulty. Use the same kinds as the examples (when there are no examples, pick the kinds that fit the topic), never kind "other". Leave label empty and set chunk to 0."""


PLAN_SYSTEM = VARIANT_SYSTEM + """

# A topic the student named
The student typed the name of a topic they want to learn. Give its title as a calculus course would write it, a one-sentence summary for the student, and practice problems that test the topic itself, from easy to hard: about a third each at difficulty 1, 2 and 3. Pick the kinds that fit: for L'Hopital's rule, limits of the form 0/0 or infinity/infinity; for optimization, extremum word problems; for the Mean Value Theorem, solve problems for c. Set is_math to false, with no problems, if what they typed isn't a math topic."""


class VariantSet(BaseModel):
    problems: list[ProblemOut]


class TopicPlan(BaseModel):
    is_math: bool = Field(description="True if this is a math topic you can teach")
    title: str = Field(description="The topic as a calculus course titles it, e.g. L'Hopital's rule")
    summary: str = Field(description="One sentence on what the topic covers, for the student")
    problems: list[ProblemOut]


def write_variants(llm, *, topic: str, summary: str, examples: list[dict], count: int,
                   spread: bool = False) -> list[ProblemOut]:
    """``count`` new problems on ``topic`` like ``examples`` (each with statement, kind, spec and answer).

    With ``spread`` they run from easy to hard instead of matching the examples' difficulty."""
    count = max(1, min(count, MAX_VARIANTS))
    lines = [f"Topic: {topic}." + (f" {summary}" if summary else ""), f"Write {count} new problems."]
    if spread:
        lines.append("Spread them from easy to hard: about a third each at difficulty 1, 2 and 3.")
    if examples:
        lines.append("Examples from the student's material:")
        for ex in examples:
            lines.append(f"- kind {ex['kind']}: {ex['statement']} (answer: {ex['answer']})")
    result = llm.structured(system=VARIANT_SYSTEM, content="\n".join(lines), schema=VariantSet, effort="medium",
                            max_tokens=16000)
    return [p for p in result.problems if p.kind != "other"][:count]


def plan_topic(llm, *, name: str, count: int) -> TopicPlan:
    """A title, summary and ``count`` practice problems for a topic the student typed in."""
    count = max(1, min(count, MAX_VARIANTS))
    plan = llm.structured(system=PLAN_SYSTEM, content=f"The topic the student typed: {name}\nWrite {count} problems.",
                          schema=TopicPlan, effort="medium", max_tokens=16000)
    plan.problems = [p for p in plan.problems if p.kind != "other"][:count] if plan.is_math else []
    return plan
