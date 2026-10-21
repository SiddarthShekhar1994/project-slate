import io
import shutil

import httpx
import pytest
from PIL import Image, ImageDraw

from slate_api.services import photo, stt
from slate_api.services.llm import LLMUnavailable


def mock(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openai_transcription_is_primed_with_calculus_words():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        return httpx.Response(200, json={"text": " Why is it cosine of x cubed? "})

    t = stt.OpenAISTT(api_key="k", http=mock(handler))
    assert stt.transcribe(b"audio", "audio/webm;codecs=opus", t) == "Why is it cosine of x cubed?"
    assert seen["url"].endswith("/v1/audio/transcriptions") and seen["auth"] == "Bearer k"
    assert b"whisper-1" in seen["body"] and b"chain rule" in seen["body"] and b"question.webm" in seen["body"]


def test_elevenlabs_transcription():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["xi-api-key"] == "k"
        assert str(request.url).endswith("/v1/speech-to-text") and b"scribe_v1" in request.content
        return httpx.Response(200, json={"text": "what is the inner function"})

    assert stt.transcribe(b"audio", "audio/mp4", stt.ElevenLabsSTT(api_key="k", http=mock(handler))) == \
        "what is the inner function"


# Named cases: pytest would otherwise name the second case after its 10 MB
# of audio, which floods the test output and breaks on Windows, where the
# name has to fit in an environment variable.
@pytest.mark.parametrize("audio,mime,message", [
    (b"", "audio/webm", "empty"),
    (b"x" * (stt.MAX_AUDIO_BYTES + 1), "audio/webm", "too long"),
    (b"audio", "video/mp4", "kind of recording"),
], ids=["empty", "too-long", "wrong-kind"])
def test_bad_recordings_are_explained(audio, mime, message):
    with pytest.raises(stt.STTError, match=message):
        stt.transcribe(audio, mime, stt.FakeSTT())


def test_provider_failures_and_silence_are_explained():
    failing = stt.OpenAISTT(api_key="k", http=mock(lambda r: httpx.Response(500)))
    with pytest.raises(stt.STTError, match="Couldn't make out"):
        stt.transcribe(b"audio", "audio/webm", failing)
    silent = stt.OpenAISTT(api_key="k", http=mock(lambda r: httpx.Response(200, json={"text": "  "})))
    with pytest.raises(stt.STTError, match="Didn't catch"):
        stt.transcribe(b"audio", "audio/webm", silent)


def test_provider_choice(monkeypatch):
    for key in ("STT_PROVIDER", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    stt.get_transcriber.cache_clear()
    assert stt.get_transcriber() is None
    with pytest.raises(stt.STTError, match="need a speech provider"):
        stt.transcribe(b"audio", "audio/webm")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "e")
    stt.get_transcriber.cache_clear()
    assert stt.get_transcriber().name == "elevenlabs"
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    stt.get_transcriber.cache_clear()
    assert stt.get_transcriber().name == "openai"
    monkeypatch.setenv("STT_PROVIDER", "elevenlabs")
    stt.get_transcriber.cache_clear()
    assert stt.get_transcriber().name == "elevenlabs"
    stt.get_transcriber.cache_clear()


# --- photos -------------------------------------------------------------------------------


def png(text="", size=(400, 120)) -> bytes:
    img = Image.new("RGB", size, "white")
    if text:
        ImageDraw.Draw(img).text((10, 40), text, fill="black")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


class FakeLLM:
    available = True

    def __init__(self, answer="3x^2 cos(x^3+1)", found=True, confidence=0.9):
        self.result = photo.PhotoAnswer(found=found, answer=answer, confidence=confidence)
        self.calls = []

    def structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_photo_answer_is_parsed_like_a_typed_one():
    llm = FakeLLM()
    reading = photo.read_answer(png(), prompt="Differentiate sin(x^3+1).", variables=["x"], llm=llm)
    assert reading.method == "claude" and reading.text == "3x^2 cos(x^3+1)"
    assert "\\cos" in reading.latex and reading.error is None and reading.confidence == 0.9
    # The model sees the image and the problem, and is told not to fix the answer.
    content = llm.calls[0]["content"]
    assert content[0]["type"] == "image" and "Differentiate" in content[1]["text"]
    assert "must stay wrong" in llm.calls[0]["system"]


def test_unparseable_reading_comes_back_for_the_student_to_fix():
    reading = photo.read_answer(png(), variables=["x"], llm=FakeLLM(answer="3x^2 cos(x^3+1"))
    assert reading.latex is None and reading.error and reading.text == "3x^2 cos(x^3+1"


def test_no_answer_in_the_photo():
    with pytest.raises(photo.PhotoError, match="Couldn't find a final answer"):
        photo.read_answer(png(), variables=["x"], llm=FakeLLM(answer="", found=False))


def test_not_an_image():
    with pytest.raises(photo.PhotoError, match="isn't a photo"):
        photo.read_answer(b"%PDF-1.7 nope", variables=["x"], llm=FakeLLM())


def test_large_photos_are_shrunk_before_sending():
    big = png(size=(4000, 3000))
    llm = FakeLLM()
    photo.read_answer(big, variables=["x"], llm=llm)
    import base64

    sent = Image.open(io.BytesIO(base64.b64decode(llm.calls[0]["content"][0]["source"]["data"])))
    assert max(sent.size) == photo.MAX_EDGE


class NoLLM:
    available = False

    def structured(self, **kwargs):
        raise LLMUnavailable("no key")


def test_without_claude_or_tesseract(monkeypatch):
    monkeypatch.setattr(photo, "_with_tesseract", lambda png: None)
    with pytest.raises(photo.PhotoError) as info:
        photo.read_answer(png(), variables=["x"], llm=NoLLM())
    assert info.value.code == 503


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract binary not installed")
def test_tesseract_reads_a_printed_last_line():
    img = Image.new("RGB", (900, 200), "white")
    from PIL import ImageFont

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 48)
    except OSError:
        pytest.skip("no TrueType font for a legible test image")
    ImageDraw.Draw(img).text((20, 60), "y = 6x + 2", fill="black", font=font)
    out = io.BytesIO()
    img.save(out, format="PNG")
    reading = photo.read_answer(out.getvalue(), variables=["x"], llm=NoLLM())
    assert reading.method == "tesseract" and reading.text.replace(" ", "") == "6x+2"
