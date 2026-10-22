"""Request bodies. Responses are plain dicts built by the services' view helpers."""

from __future__ import annotations

import uuid
from typing import Literal

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
    # How the answer is read: an expression (the default), a number, a line, a list of values, a limit or an
    # antiderivative; see services/materials/answers.py.
    answer_kind: Literal["expression", "number", "line", "values", "limit", "antiderivative"] = "expression"
    units: bool = False  # a word problem's number may end with a unit, like ft/s


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


class TopicIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TopicPracticeIn(BaseModel):
    count: int | None = Field(default=None, ge=1, le=12)
    problem_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=30)


class ExamIn(BaseModel):
    # skill id -> weight; any positive numbers, normalised by the server
    weights: dict[str, float] = Field(min_length=1, max_length=12)
    count: int = Field(default=8, ge=1, le=12)
    pace: str = Field(default="exam", pattern="^(exam|study)$")
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class ExamAnswerIn(BaseModel):
    answer: str = Field(max_length=500)


class ReviewIn(BaseModel):
    # Defaults to every skill that is due.
    skill_ids: list[str] | None = Field(default=None, max_length=8)


class SettingsIn(BaseModel):
    # Omitted fields are left alone; an empty string clears the setting.
    anthropic_api_key: str | None = Field(default=None, max_length=300)
    elevenlabs_api_key: str | None = Field(default=None, max_length=300)
    openai_api_key: str | None = Field(default=None, max_length=300)
    tts_provider: str | None = Field(default=None, max_length=20)
    stt_provider: str | None = Field(default=None, max_length=20)
