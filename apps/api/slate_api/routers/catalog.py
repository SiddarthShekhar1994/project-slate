from __future__ import annotations

from fastapi import APIRouter
from slate_skills import courses
from slate_skills.core.types import DIFFICULTY_LABELS

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("")
def catalog() -> dict:
    """Courses, units and skills with their formula sheet entries."""
    return {
        "difficulties": DIFFICULTY_LABELS,
        "courses": [
            {
                "id": course.id,
                "title": course.title,
                "description": course.description,
                "units": [
                    {
                        "id": unit.id,
                        "title": unit.title,
                        "skills": [
                            {
                                "id": skill.id,
                                "slug": skill.slug,
                                "title": skill.title,
                                "summary": skill.summary,
                                "formula": {"title": skill.formula.title, "latex": skill.formula.latex,
                                            "note": skill.formula.note},
                                "difficulties": list(skill.difficulties),
                                "prerequisites": list(skill.prerequisites),
                            }
                            for skill in unit.skills
                        ],
                    }
                    for unit in course.units
                ],
            }
            for course in courses()
        ],
    }
