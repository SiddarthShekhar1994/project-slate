import pytest

from slate_api.services.ingest.extract import ExtractionError, detect_mime, extract
from slate_api.services.ingest.ocr import ocr_image, ocr_pages
from slate_api.services.ingest.types import OcrResult, Page

from . import fixtures as f

PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.parametrize("make, name, mime", [
    (f.calculus_pdf, "w3.pdf", "application/pdf"),
    (f.calculus_pptx, "w3.pptx", PPTX),
    (f.calculus_docx, "notes.docx", DOCX),
    (f.chain_rule_png, "photo.png", "image/png"),
    (f.chain_rule_jpeg, "photo.jpg", "image/jpeg"),
])
def test_detects_by_content(make, name, mime):
    assert detect_mime(make(), name) == mime
    # The extension doesn't matter: a PNG named .pdf is still a PNG.
    assert detect_mime(make(), "renamed.pdf") == mime


def test_rejects_unsupported_and_dangerous_archives():
    assert detect_mime(b"hello", "notes.txt") is None
    assert detect_mime(f.plain_zip(), "x.zip") is None
    assert detect_mime(f.zip_bomb_docx(), "bomb.docx") is None


def test_pdf_pages_headings_and_ocr_flags():
    data = f.calculus_pdf()
    out = extract(data, "application/pdf", "w3.pdf")
    assert [p.label for p in out.pages] == ["p. 1", "p. 2", "p. 3"]
    assert out.pages[0].heading == "The Chain Rule"
    assert "cos" in out.pages[0].text
    assert out.pages[2].needs_ocr and out.pages[2].image


def test_slides_titles_and_picture_only_slide():
    out = extract(f.calculus_pptx(), PPTX, "w3.pptx")
    assert [p.label for p in out.pages][:2] == ["slide 1", "slide 2"]
    assert out.pages[2].heading == "Product rule"
    assert out.pages[-1].needs_ocr


def test_docx_sections():
    out = extract(f.calculus_docx(), DOCX, "notes.docx")
    assert any(p.heading == "The chain rule" for p in out.pages)


@pytest.mark.parametrize("make", [f.encrypted_pdf, f.damaged_pdf, f.blank_pdf])
def test_unreadable_pdfs_explain_themselves(make):
    with pytest.raises(ExtractionError) as err:
        extract(make(), "application/pdf", "x.pdf")
    assert str(err.value)


class FakeLLM:
    available = True

    def __init__(self):
        self.calls = []

    def structured(self, *, system, content, schema, effort, max_tokens):
        self.calls.append(content)
        return schema(text="Chain rule: $\\frac{dy}{dx} = \\frac{dy}{du}\\frac{du}{dx}$", confidence=0.9)


class NoLLM:
    available = False


def test_ocr_prefers_claude_and_sends_the_image():
    llm = FakeLLM()
    result = ocr_image(f.chain_rule_png(), llm=llm)
    assert result.method == "claude" and "$" in result.text
    assert llm.calls[0][0]["type"] == "image"


def test_ocr_falls_back_to_tesseract():
    result = ocr_image(f.chain_rule_png(), llm=NoLLM())
    assert result.method == "tesseract"
    assert "chain rule" in result.text.lower()


def test_ocr_pages_only_touches_pages_that_need_it(monkeypatch):
    from slate_api.services.ingest import ocr

    monkeypatch.setattr(ocr, "ocr_image", lambda image, hint="", llm=None: OcrResult("read", "none", 0.0))
    pages = [Page(1, "p. 1", text="typed"), Page(2, "p. 2", needs_ocr=True, image=b"png")]
    out = ocr_pages(pages)
    assert out[0].text == "typed" and out[0].ocr_method is None
    assert out[1].text == "read" and out[1].image is None
