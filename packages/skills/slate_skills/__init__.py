"""Slate skill definitions, one Python module per skill, grouped by course and unit."""

from .registry import (
    all_skills,
    courses,
    get_course,
    get_skill,
    is_builtin,
    load_skill_module,
    register_extra,
    set_extra_resolver,
    skill_owner,
)

__all__ = ["all_skills", "courses", "get_course", "get_skill", "is_builtin", "load_skill_module", "register_extra",
           "set_extra_resolver", "skill_owner"]
