import base64
import json

import httpx
import pytest

from slate_api.services.storage import LocalStorage
from slate_api.services.tts import (
    ElevenLabs,
    Silent,
    OpenAITTS,
    TTSError,
    WordTiming,
    align,
    spoken_text,
    spoken_words,
    step_audio,
    words_from_characters,
)

NARRATION = ["Let ", {"math": "u = x^3 + 1", "say": "u equal x cubed plus one"}, ", the inside."]


def test_spoken_text_matches_the_player():
    assert spoken_text(NARRATION) == "Let u equal x cubed plus one, the inside."
    assert spoken_words(NARRATION) == ["Let", "u", "equal", "x", "cubed", "plus", "one,", "the", "inside."]


def test_characters_group_into_words():
    text = "Hi there."
    chars = list(text)
    starts = [i * 0.1 for i in range(len(chars))]
    ends = [s + 0.08 for s in starts]
    words = words_from_characters(text, chars, starts, ends)
    assert [w.text for w in words] == ["Hi", "there."]
    assert words[0].start == 0 and words[1].start == pytest.approx(300)


def test_align_copies_matches_and_spreads_gaps():
    ours = ["The", "derivative", "is", "three", "x", "squared."]
    theirs = [WordTiming("the", 0, 100), WordTiming("derivative", 120, 500), WordTiming("is", 520, 600),
              WordTiming("3x", 620, 900), WordTiming("squared", 920, 1300)]
    out = align(ours, theirs)
    assert [w.text for w in out] == ours
    assert out[1].start == 120
    # "three x" were heard as "3x": spread across the gap before "squared".
    assert 600 <= out[3].start < out[4].start < out[5].start == 920
    assert all(a.end <= b.start + 1e-6 for a, b in zip(out, out[1:]))


def _eleven_transport(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        text = body["text"]
        chars = list(text)
        starts = [i * 0.05 for i in range(len(chars))]
        return httpx.Response(200, json={
            "audio_base64": base64.b64encode(b"ID3fake").decode(),
            "alignment": {"characters": chars, "character_start_times_seconds": starts,
                          "character_end_times_seconds": [s + 0.04 for s in starts]},
        })
    return httpx.MockTransport(handler)


def test_elevenlabs_step_audio_is_cached(tmp_path):
    calls = []
    provider = ElevenLabs(api_key="k", model="m", http=httpx.Client(transport=_eleven_transport(calls)))
    storage = LocalStorage(tmp_path)
    voice = provider.voices()[0].id
    first = step_audio(NARRATION, voice, provider=provider, storage=storage)
    assert [w.text for w in first.words] == spoken_words(NARRATION)
    assert storage.get(first.key) == b"ID3fake"
    assert calls[0].headers["xi-api-key"] == "k"
    second = step_audio(NARRATION, voice, provider=provider, storage=storage)
    assert len(calls) == 1, "second request should come from the cache"
    assert second.words == first.words


def test_openai_audio_is_aligned_from_transcription(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/audio/speech"):
            assert json.loads(request.content)["voice"] == "nova"
            return httpx.Response(200, content=b"mp3bytes")
        words = [{"word": w, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, w in
                 enumerate(["Let", "u", "equal", "x", "cubed", "plus", "one", "the", "inside"])]
        return httpx.Response(200, json={"words": words, "duration": 2.9})

    provider = OpenAITTS(api_key="k", model="gpt-4o-mini-tts", http=httpx.Client(transport=httpx.MockTransport(handler)))
    audio = step_audio(NARRATION, "nova", provider=provider, storage=LocalStorage(tmp_path))
    assert [w.text for w in audio.words] == spoken_words(NARRATION)
    assert audio.words[6].start == pytest.approx(1800)
    assert audio.duration_ms == pytest.approx(2900)


def test_unknown_voice_and_provider_errors(tmp_path):
    provider = ElevenLabs(api_key="k", model="m",
                          http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(TTSError):
        step_audio(NARRATION, "not-a-voice", provider=provider, storage=LocalStorage(tmp_path))
    with pytest.raises(TTSError):
        step_audio(NARRATION, provider.voices()[0].id, provider=provider, storage=LocalStorage(tmp_path))


def test_silent_provider_gives_playable_wav_and_aligned_words(tmp_path):
    audio = step_audio(NARRATION, "silent", provider=Silent(), storage=LocalStorage(tmp_path))
    data = LocalStorage(tmp_path).get(audio.key)
    assert audio.key.endswith(".wav") and data[:4] == b"RIFF"
    assert [w.text for w in audio.words] == spoken_words(NARRATION)
    assert audio.duration_ms > audio.words[-1].end
