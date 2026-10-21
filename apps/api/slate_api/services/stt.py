"""Speech to text for spoken questions in the lesson's ask panel.

Uses whichever speech provider is configured, the same accounts as the
narrated voice: OpenAI's transcription endpoint or ElevenLabs' Scribe. Pick
one with ``STT_PROVIDER`` (``openai``, ``elevenlabs`` or ``fake``); by default
it is OpenAI when ``OPENAI_API_KEY`` is set, otherwise ElevenLabs when
``ELEVENLABS_API_KEY`` is set, otherwise none and the ask panel stays typed.

``fake`` returns a fixed question and exists for end-to-end tests, which
record from Chromium's fake microphone.

The transcript is never acted on directly: the student sees it in the
question box and decides whether to ask it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from typing import Protocol

import httpx

TIMEOUT = httpx.Timeout(60.0, connect=10.0)
MAX_AUDIO_BYTES = 10 * 1024 * 1024
AUDIO_TYPES = {
    "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav",
    "audio/x-wav": "wav", "audio/aac": "aac",
}
# Primes the recogniser with the words a calculus student is likely to say.
VOCABULARY = ("A calculus student asks about a derivative: chain rule, product rule, quotient rule, power rule, "
              "implicit differentiation, inner function, outer function, dy/dx, f prime of x, sine, cosine, "
              "tangent, natural log, e to the x, x squared, x cubed.")
FAKE_TRANSCRIPT = "Why do we multiply by the derivative of the inside?"


class STTError(RuntimeError):
    pass


class Transcriber(Protocol):
    name: str

    def transcribe(self, audio: bytes, mime: str) -> str: ...


def _base_mime(mime: str) -> str:
    return (mime or "").split(";")[0].strip().lower()


@dataclass
class OpenAISTT:
    api_key: str
    model: str = "whisper-1"
    http: httpx.Client | None = None
    name: str = "openai"

    def transcribe(self, audio: bytes, mime: str) -> str:
        client = self.http or httpx.Client(timeout=TIMEOUT)
        ext = AUDIO_TYPES.get(_base_mime(mime), "webm")
        r = client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"file": (f"question.{ext}", audio, _base_mime(mime) or "audio/webm")},
            data={"model": self.model, "response_format": "json", "prompt": VOCABULARY},
        )
        if r.status_code != 200:
            raise STTError(f"OpenAI transcription returned {r.status_code}")
        return str(r.json().get("text", "")).strip()


@dataclass
class ElevenLabsSTT:
    api_key: str
    model: str = "scribe_v1"
    http: httpx.Client | None = None
    name: str = "elevenlabs"

    def transcribe(self, audio: bytes, mime: str) -> str:
        client = self.http or httpx.Client(timeout=TIMEOUT)
        ext = AUDIO_TYPES.get(_base_mime(mime), "webm")
        r = client.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": self.api_key},
            files={"file": (f"question.{ext}", audio, _base_mime(mime) or "audio/webm")},
            data={"model_id": self.model, "tag_audio_events": "false"},
        )
        if r.status_code != 200:
            raise STTError(f"ElevenLabs transcription returned {r.status_code}")
        return str(r.json().get("text", "")).strip()


@dataclass
class FakeSTT:
    name: str = "fake"

    def transcribe(self, audio: bytes, mime: str) -> str:
        return FAKE_TRANSCRIPT


@cache
def get_transcriber() -> Transcriber | None:
    name = os.environ.get("STT_PROVIDER", "").lower()
    openai_key = os.environ.get("OPENAI_API_KEY")
    eleven_key = os.environ.get("ELEVENLABS_API_KEY")
    if name == "fake":
        return FakeSTT()
    if name in ("", "openai") and openai_key:
        return OpenAISTT(api_key=openai_key, model=os.environ.get("OPENAI_STT_MODEL") or "whisper-1")
    if name in ("", "elevenlabs") and eleven_key:
        return ElevenLabsSTT(api_key=eleven_key, model=os.environ.get("ELEVENLABS_STT_MODEL") or "scribe_v1")
    return None


def transcribe(audio: bytes, mime: str, transcriber: Transcriber | None = None) -> str:
    """Text of a short recorded question. Raises ``STTError`` with a message safe to show."""
    transcriber = transcriber or get_transcriber()
    if transcriber is None:
        raise STTError("Spoken questions need a speech provider. Type your question instead.")
    if not audio:
        raise STTError("That recording was empty. Try again.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise STTError("That recording is too long. Keep spoken questions under a minute.")
    if _base_mime(mime) not in AUDIO_TYPES:
        raise STTError("Slate can't read that kind of recording.")
    try:
        text = transcriber.transcribe(audio, mime)
    except (httpx.HTTPError, STTError) as exc:
        raise STTError("Couldn't make out that recording. Try again, or type your question.") from exc
    if not text:
        raise STTError("Didn't catch any words. Try again a little closer to the microphone.")
    return text[:500]
