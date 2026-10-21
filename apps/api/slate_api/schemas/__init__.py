"""Request bodies. Responses are plain dicts built by the services' view helpers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SignupIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)
    display_name: str = Field(default="", max_length=80)


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class PreviewIn(BaseModel):
    text: str = Field(max_length=500)
    variables: list[str] = Field(default_factory=lambda: ["x"], max_length=3)


class WorksheetIn(BaseModel):
    skill_ids: list[str] = Field(min_length=1, max_length=8)
    count: int | None = Field(default=None, ge=1, le=12)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class AnswerIn(BaseModel):
    answer: str = Field(max_length=500)
    duration_ms: int | None = Field(default=None, ge=0, le=24 * 3600 * 1000)


class HintIn(BaseModel):
    level: int = Field(ge=1, le=3)


class StepIn(BaseModel):
    step: int = Field(ge=0, le=500)


class AskIn(BaseModel):
    step: int = Field(ge=0, le=500)
    question: str = Field(min_length=1, max_length=500)


class CheckpointIn(BaseModel):
    step: int = Field(ge=0, le=500)
    option: str = Field(min_length=1, max_length=20)


class GenerateLessonIn(BaseModel):
    skill_id: str = Field(min_length=1, max_length=120)
