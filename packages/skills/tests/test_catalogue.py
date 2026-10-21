import json
from random import Random

import pytest

from slate_skills import all_skills, courses, get_course, get_skill, load_skill_module, skill_owner
from slate_skills.core.mistakes import CATEGORIES, MISTAKE_TYPES
from slate_skills.core.text import placeholders

SKILLS = all_skills()
SKILL_IDS = [s.id for s in SKILLS]


def test_calc1_has_the_derivative_unit():
    course = get_course("calc1")
    unit = course.units[0]
    assert unit.id == "derivatives"
    assert [s.slug for s in unit.skills] == [
        "power_rule", "product_rule", "quotient_rule", "chain_rule", "implicit_differentiation",
    ]


def test_ids_are_unique_and_mirror_module_paths():
    assert len(SKILL_IDS) == len(set(SKILL_IDS))
    for skill in SKILLS:
        course, unit = skill_owner(skill.id)
        assert skill.id == f"{course.id}.{unit.id}.{skill.slug}"
        assert load_skill_module(skill.id) is skill


def test_every_course_is_reachable():
    assert {c.id for c in courses()} == {"calc1"}
    with pytest.raises(KeyError):
        get_skill("calc1.derivatives.nope")


def test_mistake_categories_are_known():
    assert all(m.category in CATEGORIES for m in MISTAKE_TYPES.values())


@pytest.mark.parametrize("skill_id", SKILL_IDS)
def test_skill_spec_is_complete(skill_id):
    skill = get_skill(skill_id)
    assert skill.title and skill.summary
    assert skill.formula.title and skill.formula.latex
    assert skill.keywords, "ingestion needs keywords to match sources to this skill"
    for prereq in skill.prerequisites:
        get_skill(prereq)

    ids = [f.id for f in skill.families]
    assert len(ids) == len(set(ids))
    assert skill.difficulties == (1, 2, 3, 4)
    for difficulty in (1, 2, 3, 4):
        assert len(skill.families_at(difficulty)) >= 2, f"difficulty {difficulty} needs two families"
    assert any(f.word for f in skill.families), "needs a word problem family"

    assert skill.mistakes
    assert any(m.signature for m in skill.mistakes)
    for m in skill.mistakes:
        assert m.tag in MISTAKE_TYPES, m.tag
        assert m.note and "—" not in m.note
        for name in placeholders(m.note):
            assert name  # placeholders are resolved per problem by the verifier's text check


@pytest.mark.parametrize("skill_id", SKILL_IDS)
def test_families_sample_deterministically_and_build_consistently(skill_id):
    skill = get_skill(skill_id)
    for fam in skill.families:
        for seed in range(5):
            params = fam.sample(Random(seed))
            assert params == fam.sample(Random(seed))
            json.dumps(params)
            snapshot = json.dumps(params, sort_keys=True)
            try:
                built = fam.build(params)
            except ValueError:
                continue
            assert json.dumps(params, sort_keys=True) == snapshot, "build must not mutate params"
            assert built.family == fam.id
            assert built.difficulty == fam.difficulty
            assert built.task == skill.task
            assert (built.word is not None) == fam.word
            assert built.steps and all(s.title for s in built.steps)
