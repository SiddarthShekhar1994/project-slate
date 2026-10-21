import pytest
from slate_skills import all_skills, get_skill

from slate_api.services.problem_gen import engine
from slate_api.services.problem_gen import (
    GenerationError,
    VerifiedProblem,
    build_worksheet,
    generate,
    plan_difficulties,
    rebuild,
    similar,
)
from slate_api.services.verify import Check, VerificationReport

CHAIN = "calc1.derivatives.chain_rule"
SKILL_IDS = [s.id for s in all_skills()]


def test_same_seed_same_problem():
    a = generate(CHAIN, 2, 1234)
    b = generate(CHAIN, 2, 1234)
    assert a.signature == b.signature
    assert a.built.prompt == b.built.prompt


def test_different_seeds_vary():
    signatures = {generate(CHAIN, 2, seed).signature for seed in range(12)}
    assert len(signatures) >= 10


@pytest.mark.parametrize("skill_id", SKILL_IDS)
def test_every_skill_and_difficulty_generates_verified_problems(skill_id):
    skill = get_skill(skill_id)
    assert skill.difficulties == (1, 2, 3, 4)
    for difficulty in skill.difficulties:
        for seed in range(4):
            problem = generate(skill_id, difficulty, seed)
            assert problem.report.ok
            assert problem.skill_id == skill_id
            assert problem.difficulty == difficulty
            assert problem.built.difficulty == difficulty
            assert problem.hints.nudge and problem.hints.bigger and problem.hints.full_step


@pytest.mark.parametrize("skill_id", SKILL_IDS)
def test_similar_problem_is_new_but_same_skill_and_difficulty(skill_id):
    original = generate(skill_id, 2, 99)
    seen = {original.signature}
    current = original
    for attempt in range(5):
        nxt = similar(current, attempt=attempt, exclude=seen)
        assert nxt.skill_id == original.skill_id
        assert nxt.difficulty == original.difficulty
        assert nxt.signature not in seen, "similar() repeated a problem"
        assert nxt.built.expr != current.built.expr or nxt.built.at != current.built.at
        assert nxt.parent_signature == current.signature
        assert get_skill(skill_id).family(nxt.family).word == get_skill(skill_id).family(original.family).word
        seen.add(nxt.signature)
        current = nxt


def test_similar_keeps_word_problems_as_word_problems():
    word = generate(CHAIN, 2, 5, word=True)
    assert get_skill(CHAIN).family(word.family).word
    assert get_skill(CHAIN).family(similar(word).family).word


def test_excluded_signatures_are_never_returned():
    first = generate(CHAIN, 1, 7, family="linear_power")
    for seed in range(10):
        assert generate(CHAIN, 1, seed, family="linear_power", exclude={first.signature}).signature != first.signature


def test_verified_problem_cannot_be_forged():
    real = generate(CHAIN, 1, 1)
    with pytest.raises(TypeError):
        VerifiedProblem(
            skill_id=real.skill_id, family=real.family, difficulty=1, seed=1, built=real.built,
            report=real.report, hints=real.hints, signature=real.signature,
        )


def test_failed_verification_never_escapes(monkeypatch):
    failing = VerificationReport(ok=False, oracle="sympy.diff", method="x", checks=(Check("oracle", False, "no"),))
    monkeypatch.setattr(engine, "verify_built", lambda skill, built: failing)
    with pytest.raises(GenerationError):
        generate(CHAIN, 1, 3, max_attempts=5)


def test_rebuild_from_stored_params():
    problem = generate(CHAIN, 3, 21)
    again = rebuild(problem.skill_id, problem.family, problem.params, problem.seed)
    assert again.signature == problem.signature
    assert again.built.key == problem.built.key


@pytest.mark.parametrize("count", [1, 2, 4, 6, 9])
def test_plan_is_easy_to_hard(count):
    plan = plan_difficulties(get_skill(CHAIN), count)
    assert len(plan) == count
    assert plan == sorted(plan)
    assert plan[0] == 1
    if count >= 4:
        assert plan[-1] == 4


def test_worksheet_is_ordered_distinct_and_has_a_story_problem():
    sheet = build_worksheet([CHAIN], 6, seed=42)
    difficulties = [p.difficulty for p in sheet]
    assert difficulties == sorted(difficulties)
    assert len({p.signature for p in sheet}) == len(sheet)
    assert any(get_skill(CHAIN).family(p.family).word for p in sheet)
    # Variety: no family twice while others at the same difficulty are unused.
    assert len({p.family for p in sheet}) == len(sheet)


def test_worksheet_across_skills():
    skills = SKILL_IDS[:3]
    sheet = build_worksheet(skills, 9, seed=3)
    assert {p.skill_id for p in sheet} == set(skills)
    assert [p.difficulty for p in sheet] == sorted(p.difficulty for p in sheet)
