import json
from pathlib import Path

import pytest

from slate_api.services.verify.claims import check_checkpoint, check_claim, script_is_sound

BUILTIN = Path(__file__).resolve().parents[2] / "slate_api" / "lessons" / "builtin"


@pytest.mark.parametrize("path", sorted(BUILTIN.glob("*.json")), ids=lambda p: p.name)
def test_builtin_lessons_are_sound(path):
    ok, results = script_is_sound(json.loads(path.read_text()))
    assert ok, [r for r in results if not r.ok]
    assert results, "a lesson should state at least one checkable fact"


def test_true_and_false_claims():
    assert check_claim({"kind": "derivative", "of": "sin(x^3+1)", "var": "x", "equals": "3x^2cos(x^3+1)"}, "s").ok
    bad = check_claim({"kind": "derivative", "of": "sin(x^3+1)", "var": "x", "equals": "cos(x^3+1)"}, "s")
    assert not bad.ok and "false" in bad.detail
    assert check_claim({"kind": "equal", "left": "sec(x)^2", "right": "tan(x)^2 + 1", "vars": ["x"]}, "s").ok
    assert not check_claim({"kind": "derivative", "of": "__import__('os')", "var": "x", "equals": "0"}, "s").ok
    assert not check_claim({"kind": "derivative", "of": "z^2", "var": "x", "equals": "0"}, "s").ok


def _checkpoint(options):
    return {
        "prompt": "?",
        "expect": {"kind": "derivative", "of": "x^3+1", "var": "x", "equals": "3x^2"},
        "options": options,
    }


def test_checkpoint_distractor_that_is_secretly_right_is_caught():
    results = check_checkpoint(_checkpoint([
        {"id": "a", "value": "3x^2", "say": "3 x squared", "correct": True},
        {"id": "b", "value": "3*x*x", "say": "3 x times x", "correct": False},
    ]), "cp")
    assert [r.ok for r in results] == [True, True, False]


def test_checkpoint_needs_one_correct_option():
    results = check_checkpoint(_checkpoint([{"id": "a", "value": "x", "say": "x", "correct": False}]), "cp")
    assert not all(r.ok for r in results)
