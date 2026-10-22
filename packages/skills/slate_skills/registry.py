"""Lookup for courses and skills.

Adding a course means adding a package under ``slate_skills/courses`` that
exposes ``COURSE`` and listing it in ``slate_skills/courses/__init__.py``.
Nothing else in Slate hard-codes course or skill ids.

Skills can also come from outside the package: a topic Slate found in a
student's own materials (related rates, say) is registered at run time with
:func:`register_extra`. :func:`get_skill` finds it like any other skill, but it
belongs to no course, so :func:`courses` and :func:`all_skills` leave it out.
"""

from __future__ import annotations

import importlib
from functools import cache
from typing import Callable

from .core.types import Course, SkillSpec, Unit
from .courses import COURSE_MODULES


@cache
def _index() -> tuple[dict[str, Course], dict[str, SkillSpec], dict[str, tuple[Course, Unit]]]:
    courses: dict[str, Course] = {}
    skills: dict[str, SkillSpec] = {}
    owners: dict[str, tuple[Course, Unit]] = {}
    for module in COURSE_MODULES:
        course: Course = importlib.import_module(module).COURSE
        if course.id in courses:
            raise ValueError(f"duplicate course id {course.id!r}")
        courses[course.id] = course
        for unit in course.units:
            for skill in unit.skills:
                if skill.id in skills:
                    raise ValueError(f"duplicate skill id {skill.id!r}")
                skills[skill.id] = skill
                owners[skill.id] = (course, unit)
    return courses, skills, owners


def courses() -> tuple[Course, ...]:
    return tuple(_index()[0].values())


def get_course(course_id: str) -> Course:
    try:
        return _index()[0][course_id]
    except KeyError:
        raise KeyError(f"unknown course {course_id!r}") from None


def all_skills() -> tuple[SkillSpec, ...]:
    return tuple(_index()[1].values())


_EXTRA: dict[str, SkillSpec] = {}
_RESOLVER: Callable[[str], SkillSpec | None] | None = None


def get_skill(skill_id: str) -> SkillSpec:
    try:
        return _index()[1][skill_id]
    except KeyError:
        pass
    if skill_id in _EXTRA:
        return _EXTRA[skill_id]
    found = _RESOLVER(skill_id) if _RESOLVER is not None else None
    if found is None:
        raise KeyError(f"unknown skill {skill_id!r}")
    _EXTRA[found.id] = found
    return found


def is_builtin(skill_id: str) -> bool:
    """True for a skill that ships in a course, false for one registered at run time."""
    return skill_id in _index()[1]


def register_extra(skill: SkillSpec) -> None:
    """Make a skill defined outside the package resolvable by :func:`get_skill`."""
    if is_builtin(skill.id):
        raise ValueError(f"{skill.id!r} is a built-in skill")
    _EXTRA[skill.id] = skill


def set_extra_resolver(resolver: Callable[[str], SkillSpec | None] | None) -> None:
    """Look up skills registered elsewhere (another server process, say) on first use."""
    global _RESOLVER
    _RESOLVER = resolver


def load_skill_module(skill_id: str) -> SkillSpec:
    """Import one skill file directly by id without loading the whole catalogue."""
    module = importlib.import_module(f"slate_skills.courses.{skill_id}")
    return module.SKILL


def skill_owner(skill_id: str) -> tuple[Course, Unit]:
    get_skill(skill_id)
    return _index()[2][skill_id]
