"""A problem from course materials is used only when SymPy and Claude agree."""

from slate_api.services.materials.verify import check, statement_ok, usable_hints


def test_agreement_is_required():
    spec = {"kind": "derivative", "expr": "x^2 sin(x)"}
    assert check({"spec": spec, "answer": "2x sin(x) + x^2 cos(x)"})["ok"]
    wrong = check({"spec": spec, "answer": "2x cos(x)"})
    assert not wrong["ok"] and "didn't agree" in wrong["reason"]
    assert [c["name"] for c in wrong["report"]["checks"] if not c["passed"]] == ["cross_check"]
    assert not check({"spec": spec, "answer": ""})["ok"]


def test_unreadable_specs_say_why():
    out = check({"spec": {"kind": "derivative", "expr": "x^"}, "answer": "1"})
    assert not out["ok"] and out["reason"].startswith("Slate can't check this one by computer")


def test_word_problems_need_clean_statements():
    spec = {"kind": "related_rates", "relation": "x^2 + y^2 = 25", "variables": "x, y", "values": "x=3, y=4",
            "rates": "x=2", "find": "y"}
    assert not check({"spec": spec, "answer": "-3/2", "statement": "the top falls at dy/dt = ?"})["ok"]
    ok = check({"spec": spec, "answer": "-3/2", "statement": "Find $\\frac{dy}{dt}$ when $x = 3$.", "word": True})
    assert ok["ok"] and ok["prompt"].startswith("Find $")


def test_statements_and_hints():
    assert statement_ok("Find $f'(2)$ for $f(x) = x^2$.")
    assert not statement_ok("Find f'(2) for f(x) = x^2.")
    assert not statement_ok("Unbalanced $x")
    good = ["Look at $u$.", "Then $du$.", "So $u^2$."]
    assert usable_hints("limit", good) == good
    assert usable_hints("limit", ["x^2 here", "b", "c"])[0].startswith("Try substituting")
