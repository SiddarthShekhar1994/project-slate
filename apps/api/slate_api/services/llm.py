"""Claude API access. The one place that knows the model, effort and refusal handling.

Every feature that uses Claude (lesson scripts, "ask about this step", hint
wording, "where to look" notes, OCR) goes through :class:`LLM`. Output is always
structured (a Pydantic model), so math the model states arrives as separate,
checkable fields that SymPy verifies before anything reaches a student.

Without ``ANTHROPIC_API_KEY`` the client is ``None`` and :meth:`LLM.available`
is false; callers fall back to the templated text from the skills package.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal, TypeVar

import anthropic
from pydantic import BaseModel

from ..config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Server-side fallback: if a request is declined by a safety classifier, the
# API retries it on a suitable model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(RuntimeError):
    """No API key is configured, or the API could not be reached."""


class LLMRefused(RuntimeError):
    """The model (and its fallbacks) declined the request."""


@dataclass
class LLM:
    client: Any | None
    model: str

    @property
    def available(self) -> bool:
        return self.client is not None

    def structured(self, *, system: str, content: str | list[dict], schema: type[T], effort: Effort = "medium",
                   max_tokens: int = 16000) -> T:
        """One request whose answer is validated against ``schema``.

        The system prompt is marked for caching: it is identical across calls
        of the same kind, while the per-request material goes in ``content``.
        """
        if self.client is None:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
                output_format=schema,
                output_config={"effort": effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as exc:
            raise LLMUnavailable(f"Claude API unavailable: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMRefused("the request was declined")
        if response.parsed_output is None:
            raise LLMUnavailable(f"no structured output (stop reason {response.stop_reason})")
        return response.parsed_output


@cache
def get_llm() -> LLM:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
    return LLM(client=client, model=settings.anthropic_model)
