"""FastAPI application factory.

    uv run uvicorn slate_api.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from slate_skills import all_skills, skill_owner
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .db import get_engine
from .models import Skill
from .routers import auth, catalog, lessons, math, media, practice
from .services import sandbox
from .services.lessons import sync_builtin_lessons


def sync_skills(db: Session) -> None:
    """Upsert the skills table from the skills package so foreign keys resolve."""
    rows = []
    for position, skill in enumerate(all_skills()):
        course, unit = skill_owner(skill.id)
        rows.append({"id": skill.id, "course_id": course.id, "unit_id": unit.id, "slug": skill.slug,
                     "title": skill.title, "summary": skill.summary, "position": position})
    stmt = insert(Skill).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Skill.id],
        set_={c: stmt.excluded[c] for c in ("course_id", "unit_id", "slug", "title", "summary", "position")},
    )
    db.execute(stmt)
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    sandbox.warm_up()
    with Session(get_engine()) as db:
        sync_skills(db)
        sync_builtin_lessons(db)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Slate API", version="0.1.0", lifespan=lifespan)
    for module in (auth, catalog, lessons, math, media, practice):
        app.include_router(module.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app


app = create_app()
