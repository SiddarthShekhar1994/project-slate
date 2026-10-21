"""Text to speech with word timings, cached per step.

The lesson player anchors board actions to word indices in a step's spoken
narration. This module turns that narration into audio plus one timing per
word, in the same word order the player uses:

* **ElevenLabs** (``/with-timestamps``) returns per-character timings for the
  exact text we send, which group into our words directly.
* **OpenAI** speech has no timings, so the audio is transcribed with word
  timestamps and those are aligned back onto our words.

Results are cached in object storage under a hash of provider, model, voice
and text, so each step is synthesised once per voice.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import io
import json
import os
import re
import wave
from dataclasses import asdict, dataclass
from functools import cache
from typing import Any, Protocol

import httpx

from .storage import Storage, get_storage

TIMEOUT = httpx.Timeout(60.0, connect=10.0)


@dataclass(frozen=True)
class WordTiming:
    text: str
    start: float  # ms
    end: float  # ms


@dataclass(frozen=True)
class Speech:
    audio: bytes
    mime: str
    words: list[WordTiming]
    duration_ms: float


@dataclass(frozen=True)
class Voice:
    id: str
    label: str


class TTSError(RuntimeError):
    pass


def spoken_text(narration: list[Any]) -> str:
    """Same rule as the player's ``spokenText``: prose plus each math segment's spoken form."""
    raw = "".join(seg if isinstance(seg, str) else seg["say"] for seg in narration)
    return re.sub(r"\s+", " ", raw).strip()


def spoken_words(narration: list[Any]) -> list[str]:
    text = spoken_text(narration)
    return text.split(" ") if text else []


# --- alignment -----------------------------------------------------------------------


def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def align(ours: list[str], theirs: list[WordTiming]) -> list[WordTiming]:
    """Give each of our words a timing, using the provider's words where they match.

    Matching runs are copied; anything the provider split, merged or spelled
    differently ("3" for "three") is spread evenly over the gap between its
    matched neighbours, weighted by word length.
    """
    if not ours:
        return []
    if not theirs:
        raise TTSError("no word timings to align")
    matcher = difflib.SequenceMatcher(a=[_norm(w) for w in ours], b=[_norm(w.text) for w in theirs], autojunk=False)
    times: list[tuple[float, float] | None] = [None] * len(ours)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            t = theirs[block.b + k]
            times[block.a + k] = (t.start, t.end)

    end_of_audio = theirs[-1].end
    out: list[WordTiming] = []
    i = 0
    while i < len(ours):
        if times[i] is not None:
            start, end = times[i]
            out.append(WordTiming(ours[i], start, end))
            i += 1
            continue
        j = i
        while j < len(ours) and times[j] is None:
            j += 1
        gap_start = out[-1].end if out else 0.0
        gap_end = times[j][0] if j < len(ours) else end_of_audio
        weights = [max(len(w), 1) for w in ours[i:j]]
        total = sum(weights)
        cursor = gap_start
        for k, w in zip(range(i, j), weights):
            span = (gap_end - gap_start) * w / total
            out.append(WordTiming(ours[k], cursor, cursor + span))
            cursor += span
        i = j
    return out


def words_from_characters(text: str, chars: list[str], starts: list[float], ends: list[float]) -> list[WordTiming]:
    """Group ElevenLabs character timings (seconds) into whitespace-separated words (ms)."""
    words: list[WordTiming] = []
    current = ""
    start = end = 0.0
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if current:
                words.append(WordTiming(current, start * 1000, end * 1000))
                current = ""
            continue
        if not current:
            start = s
        current += ch
        end = e
    if current:
        words.append(WordTiming(current, start * 1000, end * 1000))
    return words


# --- providers -------------------------------------------------------------------------


class Provider(Protocol):
    name: str
    model: str

    def voices(self) -> list[Voice]: ...
    def synthesize(self, text: str, voice: str) -> Speech: ...


ELEVENLABS_DEFAULT_VOICES = "Rachel:21m00Tcm4TlvDq8ikWAM,Adam:pNInz6obpgDQGcFmaJgB,Antoni:ErXwobaYiN019PkySvjV"


@dataclass
class ElevenLabs:
    api_key: str
    model: str
    voice_list: str = ELEVENLABS_DEFAULT_VOICES
    http: httpx.Client | None = None
    name: str = "elevenlabs"

    def voices(self) -> list[Voice]:
        out = []
        for item in self.voice_list.split(","):
            label, _, voice_id = item.partition(":")
            if voice_id:
                out.append(Voice(voice_id.strip(), label.strip()))
        return out

    def synthesize(self, text: str, voice: str) -> Speech:
        client = self.http or httpx.Client(timeout=TIMEOUT)
        response = client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": self.api_key},
            json={"text": text, "model_id": self.model},
        )
        if response.status_code != 200:
            raise TTSError(f"ElevenLabs returned {response.status_code}")
        body = response.json()
        alignment = body.get("alignment") or {}
        words = words_from_characters(
            text,
            alignment.get("characters", []),
            alignment.get("character_start_times_seconds", []),
            alignment.get("character_end_times_seconds", []),
        )
        audio = base64.b64decode(body["audio_base64"])
        return Speech(audio=audio, mime="audio/mpeg", words=words, duration_ms=words[-1].end if words else 0.0)


OPENAI_VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer")
TUTOR_STYLE = "Calm, clear and warm, like a patient math tutor at a chalkboard. Unhurried, with short pauses at commas."


@dataclass
class OpenAITTS:
    api_key: str
    model: str
    http: httpx.Client | None = None
    name: str = "openai"

    def voices(self) -> list[Voice]:
        return [Voice(v, v.capitalize()) for v in OPENAI_VOICES]

    def synthesize(self, text: str, voice: str) -> Speech:
        client = self.http or httpx.Client(timeout=TIMEOUT)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        speech = client.post(
            "https://api.openai.com/v1/audio/speech",
            headers=headers,
            json={"model": self.model, "voice": voice, "input": text, "response_format": "mp3",
                  "instructions": TUTOR_STYLE},
        )
        if speech.status_code != 200:
            raise TTSError(f"OpenAI speech returned {speech.status_code}")
        transcript = client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files={"file": ("step.mp3", speech.content, "audio/mpeg")},
            data={"model": "whisper-1", "response_format": "verbose_json", "timestamp_granularities[]": "word"},
        )
        if transcript.status_code != 200:
            raise TTSError(f"OpenAI transcription returned {transcript.status_code}")
        body = transcript.json()
        theirs = [WordTiming(w["word"], w["start"] * 1000, w["end"] * 1000) for w in body.get("words", [])]
        words = align(text.split(" "), theirs)
        duration = float(body.get("duration", 0)) * 1000 or (words[-1].end if words else 0.0)
        return Speech(audio=speech.content, mime="audio/mpeg", words=words, duration_ms=duration)


@dataclass
class Silent:
    """Development and test provider: silent audio with estimated word timings.

    It exercises the audio-driven path of the player (the audio element is the
    clock) without an API key. The estimate matches the player's own
    ``estimateTimings`` closely enough for testing.
    """

    model: str = "silent-1"
    name: str = "silent"

    def voices(self) -> list[Voice]:
        return [Voice("silent", "Silent (testing)")]

    def synthesize(self, text: str, voice: str) -> Speech:
        words: list[WordTiming] = []
        t = 0.0
        base = 60_000 / 150
        for word in text.split(" "):
            letters = len(re.sub(r"[^\w]", "", word))
            duration = base * (0.55 + min(letters, 12) * 0.075)
            pause = 260 if re.search(r"[.!?]$", word) else 140 if re.search(r"[,;:]$", word) else 0
            words.append(WordTiming(word, t, t + duration))
            t += duration + 40 + pause
        rate = 8000
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(1)
            wav.setframerate(rate)
            wav.writeframes(b"\x80" * int(rate * (t + 300) / 1000))
        return Speech(audio=buffer.getvalue(), mime="audio/wav", words=words, duration_ms=t + 300)


EXTENSIONS = {"audio/mpeg": "mp3", "audio/wav": "wav"}


@cache
def get_provider() -> Provider | None:
    name = os.environ.get("TTS_PROVIDER", "elevenlabs").lower()
    if name == "silent":
        return Silent()
    if name == "elevenlabs" and os.environ.get("ELEVENLABS_API_KEY"):
        return ElevenLabs(
            api_key=os.environ["ELEVENLABS_API_KEY"],
            model=os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
            voice_list=os.environ.get("ELEVENLABS_VOICES", ELEVENLABS_DEFAULT_VOICES),
        )
    if name == "openai" and os.environ.get("OPENAI_API_KEY"):
        return OpenAITTS(api_key=os.environ["OPENAI_API_KEY"], model=os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"))
    return None


# --- cached synthesis per step ------------------------------------------------------------


@dataclass(frozen=True)
class StepAudio:
    key: str
    words: list[WordTiming]
    duration_ms: float

    def as_dict(self, url: str) -> dict:
        return {"status": "ok", "url": url, "words": [asdict(w) for w in self.words], "duration_ms": self.duration_ms}


def cache_key(provider: Provider, voice: str, text: str) -> str:
    digest = hashlib.sha256(f"{provider.name}|{provider.model}|{voice}|{text}".encode()).hexdigest()
    return f"tts/{digest[:40]}"


def step_audio(narration: list[Any], voice: str, *, provider: Provider | None = None,
               storage: Storage | None = None) -> StepAudio:
    """Audio and word timings for one step, from cache when possible.

    The returned words line up one-to-one with :func:`spoken_words`, which is
    what the player's word anchors index into.
    """
    provider = provider or get_provider()
    if provider is None:
        raise TTSError("no TTS provider configured")
    if voice not in {v.id for v in provider.voices()}:
        raise TTSError(f"unknown voice {voice!r}")
    storage = storage or get_storage()
    text = spoken_text(narration)
    base = cache_key(provider, voice, text)
    if storage.exists(f"{base}.json"):
        meta = json.loads(storage.get(f"{base}.json"))
        if storage.exists(meta["audio"]):
            return StepAudio(meta["audio"], [WordTiming(**w) for w in meta["words"]], meta["duration_ms"])

    speech = provider.synthesize(text, voice)
    words = align(spoken_words(narration), speech.words)
    audio_key = f"{base}.{EXTENSIONS.get(speech.mime, 'bin')}"
    storage.put(audio_key, speech.audio, speech.mime)
    storage.put(f"{base}.json", json.dumps({"audio": audio_key, "words": [asdict(w) for w in words],
                                            "duration_ms": speech.duration_ms, "text": text, "voice": voice,
                                            "provider": provider.name}).encode(),
                "application/json")
    return StepAudio(audio_key, words, speech.duration_ms)
