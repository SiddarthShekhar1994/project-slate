"""Generate problems that are verified before anyone can see them.

The only way to obtain a :class:`VerifiedProblem` is through this module, and
it is constructed only after :func:`verify_built` passes. Routers and the
database layer deal exclusively in ``VerifiedProblem`` objects, so an
unverified key has no path to a student.

Seeds are explicit everywhere: the same skill, difficulty and seed always give
the same problem, and child seeds for "similar problem" are derived from the
parent's seed so retries are reproducible too.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from random import Random
from typing import Iterable, Sequence

import sympy as sp
from slate_skills import get_skill
from slate_skills.core.text import render
from slate_skills.core.types import Built, Family, SkillSpec

from ..verify import VerificationReport, verify_built

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 60
_MINT = object()  # only this module holds it; see VerifiedProblem.__post_init__


class GenerationError(RuntimeError):
    """No verified problem could be produced within the attempt budget."""


@dataclass(frozen=True)
class RenderedHints:
    nudge: str
    bigger: str
    full_step: str

    def level(self, n: int) -> str:
        return (self.nudge, self.bigger, self.full_step)[n - 1]


@dataclass(frozen=True)
class VerifiedProblem:
    skill_id: str
    family: str
    difficulty: int
    seed: int
    built: Built
    report: VerificationReport
    hints: RenderedHints
    signature: str
    origin: str = "template"
    parent_signature: str | None = None
    _mint: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._mint is not _MINT:
            raise TypeError("VerifiedProblem is created only by problem_gen after verification")
        if not self.report.ok:
            raise TypeError("refusing to wrap a problem whose verification failed")

    @property
    def skill(self) -> SkillSpec:
        return get_skill(self.skill_id)

    @property
    def params(self) -> dict:
        return dict(self.built.params)


def derive_seed(seed: int, salt: str | int) -> int:
    digest = hashlib.sha256(f"{seed}:{salt}".encode()).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def problem_signature(skill_id: str, built: Built) -> str:
    """Identity of a problem's mathematics, independent of its wording."""
    at = "" if not built.at else sp.srepr(sorted((str(k), sp.srepr(v)) for k, v in built.at.items()))
    raw = f"{skill_id}|{sp.srepr(built.expr)}|{at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _render_hints(skill: SkillSpec, built: Built) -> RenderedHints:
    ladder = skill.hint_ladder(built)
    return RenderedHints(
        nudge=render(ladder.nudge, built),
        bigger=render(ladder.bigger, built),
        full_step=render(ladder.full_step, built),
    )


def _wrap(skill: SkillSpec, built: Built, seed: int, report: VerificationReport, *, origin: str,
          parent: str | None) -> VerifiedProblem:
    return VerifiedProblem(
        skill_id=skill.id,
        family=built.family,
        difficulty=built.difficulty,
        seed=seed,
        built=built,
        report=report,
        hints=_render_hints(skill, built),
        signature=problem_signature(skill.id, built),
        origin=origin,
        parent_signature=parent,
        _mint=_MINT,
    )


def verify_and_wrap(skill: SkillSpec, built: Built, seed: int, *, origin: str = "template",
                    parent: str | None = None) -> VerifiedProblem | None:
    """Verify ``built``; return a servable problem or ``None`` if any check fails."""
    report = verify_built(skill, built)
    if not report.ok:
        log.info("rejected %s/%s seed=%s: %s", skill.id, built.family, seed,
                 "; ".join(f"{c.name}: {c.detail}" for c in report.failures))
        return None
    return _wrap(skill, built, seed, report, origin=origin, parent=parent)


def _candidate_families(skill: SkillSpec, difficulty: int, family: str | None, word: bool | None) -> list[Family]:
    if family is not None:
        fam = skill.family(family)
        if fam.difficulty != difficulty:
            raise ValueError(f"family {family} is difficulty {fam.difficulty}, not {difficulty}")
        return [fam]
    fams = list(skill.families_at(difficulty, word=word))
    if not fams:
        raise ValueError(f"{skill.id} has no families at difficulty {difficulty} (word={word})")
    return fams


def generate(skill_id: str, difficulty: int, seed: int, *, family: str | None = None,
             word: bool | None = None, exclude: Iterable[str] = (), parent: str | None = None,
             avoid_families: Iterable[str] = (), max_attempts: int = MAX_ATTEMPTS) -> VerifiedProblem:
    """A verified problem for ``skill_id`` at ``difficulty``.

    ``exclude`` holds signatures the student has already seen; they are never
    returned again. ``avoid_families`` steers towards families not used yet
    (for variety on a worksheet) when others exist. Samples that fail to build
    or verify are discarded and resampled; if the budget runs out,
    :class:`GenerationError` is raised rather than ever returning an
    unverified problem.
    """
    skill = get_skill(skill_id)
    families = _candidate_families(skill, difficulty, family, word)
    fresh = [f for f in families if f.id not in set(avoid_families)]
    if fresh:
        families = fresh
    seen = set(exclude)
    rng = Random(seed)
    for attempt in range(max_attempts):
        fam = families[rng.randrange(len(families))]
        sample_seed = derive_seed(seed, attempt)
        try:
            built = fam.build(fam.sample(Random(sample_seed)))
        except ValueError:
            continue
        if problem_signature(skill.id, built) in seen:
            continue
        problem = verify_and_wrap(skill, built, sample_seed, parent=parent)
        if problem is not None:
            return problem
    raise GenerationError(f"no verified {skill_id} problem at difficulty {difficulty} after {max_attempts} tries")


def rebuild(skill_id: str, family: str, params: dict, seed: int, *, origin: str = "template",
            parent: str | None = None) -> VerifiedProblem:
    """Rebuild a stored problem from its params and verify it again."""
    skill = get_skill(skill_id)
    built = skill.family(family).build(dict(params))
    problem = verify_and_wrap(skill, built, seed, origin=origin, parent=parent)
    if problem is None:
        raise GenerationError(f"stored problem {skill_id}/{family} no longer verifies")
    return problem


def restore(skill_id: str, family: str, params: dict, seed: int, report: VerificationReport, signature: str, *,
            origin: str = "template", parent: str | None = None) -> VerifiedProblem:
    """Rebuild a problem that was verified when it was stored.

    ``build`` is pure, so the same params give the same problem. If the
    signature no longer matches (the template changed since), the problem is
    verified again from scratch instead of trusting the old report.
    """
    skill = get_skill(skill_id)
    built = skill.family(family).build(dict(params))
    if problem_signature(skill.id, built) != signature or not report.ok:
        return rebuild(skill_id, family, params, seed, origin=origin, parent=parent)
    return _wrap(skill, built, seed, report, origin=origin, parent=parent)


def similar(problem: VerifiedProblem, *, attempt: int = 0, exclude: Iterable[str] = (),
            same_family: bool = True) -> VerifiedProblem:
    """A new problem of the same skill and difficulty with different mathematics.

    The new problem never has the parent's signature (or any in ``exclude``),
    so it is a fresh problem rather than a reworded copy. It stays in the
    parent's family when it can, falling back to a sibling family of the same
    difficulty and the same word or non-word kind.
    """
    excluded = {problem.signature, *exclude}
    seed = derive_seed(problem.seed, f"similar:{attempt}")
    skill = problem.skill
    word = skill.family(problem.family).word
    if same_family:
        try:
            return generate(problem.skill_id, problem.difficulty, seed, family=problem.family,
                            exclude=excluded, parent=problem.signature)
        except GenerationError:
            pass
    return generate(problem.skill_id, problem.difficulty, seed, word=word, exclude=excluded,
                    parent=problem.signature)


def plan_difficulties(skill: SkillSpec, count: int) -> list[int]:
    """Spread ``count`` problems over the skill's difficulties, easy to hard."""
    levels = list(skill.difficulties)
    if count <= 0:
        return []
    if count <= len(levels):
        # Evenly pick levels, always including the easiest.
        step = (len(levels) - 1) / max(count - 1, 1)
        return [levels[round(i * step)] for i in range(count)]
    out = []
    for i in range(count):
        out.append(levels[min(len(levels) - 1, i * len(levels) // count)])
    return out


def build_worksheet(skill_ids: Sequence[str], count: int, seed: int, *,
                    include_word: bool = True) -> list[VerifiedProblem]:
    """A worksheet ordered easy to hard, spread across ``skill_ids``.

    Every problem is distinct. When ``include_word`` is set and a skill has
    word families, one slot at medium difficulty or above becomes a word problem.
    """
    if not skill_ids:
        raise ValueError("a worksheet needs at least one skill")
    slots: list[tuple[int, str]] = []
    per_skill = [count // len(skill_ids) + (1 if i < count % len(skill_ids) else 0) for i in range(len(skill_ids))]
    for skill_id, n in zip(skill_ids, per_skill):
        skill = get_skill(skill_id)
        slots += [(d, skill_id) for d in plan_difficulties(skill, n)]
    slots.sort(key=lambda s: (s[0], skill_ids.index(s[1])))

    # One story problem, in the latest eligible slot so it sits near the end.
    word_slot = None
    if include_word:
        for i, (difficulty, skill_id) in enumerate(slots):
            if difficulty >= 2 and get_skill(skill_id).families_at(difficulty, word=True):
                word_slot = i

    problems: list[VerifiedProblem] = []
    seen: set[str] = set()
    used_families: set[str] = set()
    for i, (difficulty, skill_id) in enumerate(slots):
        word = True if i == word_slot else False
        skill = get_skill(skill_id)
        if word is False and not skill.families_at(difficulty, word=False):
            word = None
        problem = generate(skill_id, difficulty, derive_seed(seed, f"slot:{i}"), word=word, exclude=seen,
                           avoid_families=used_families)
        seen.add(problem.signature)
        used_families.add(problem.family)
        problems.append(problem)
    return problems
