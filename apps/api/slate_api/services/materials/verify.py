"""Check a problem read from course materials before anyone practices it.

The problem arrives as Claude read it: a spec (the mathematics, structured),
the problem's own wording, Claude's answer, hints and worked steps. It is
ready for practice only if every check passes:

``spec``         the spec reads with Slate's parser and describes a problem SymPy can answer
``oracle``       SymPy computed the answer key from the spec
``cross_check``  Claude's answer equals SymPy's key, judged exactly as a student's answer is
``finite``       the key is a real number, a real expression, or (for limits) oo, -oo or DNE
``size``         the key is small enough to read and type
``text``         the prompt has its math between dollar signs

A problem that fails is kept, marked ``unchecked``, so the student still sees
it in the sheet's list with the reason, but Slate never grades it.

:func:`check` runs inside the grading sandbox: SymPy can take a long time on
some limits and integrals, and the sandbox kills it at the time limit.
"""

from __future__ import annotations

from typing import Any

import sympy as sp

from ..verify import Check, ParseError, VerificationReport
from ..verify.keycheck import plain_text_math
from .answers import matches, read_answer
from .kinds import DNE, KIND_INFO, SpecError, build, finite_real, key_latex, signature

MAX_KEY_OPS = 120
MAX_PROMPT_CHARS = 1500


def statement_ok(text: str) -> bool:
    """Prompt-ready text: math between dollar signs, balanced, not too long."""
    return (bool(text.strip()) and len(text) <= MAX_PROMPT_CHARS and text.count("$") % 2 == 0
            and plain_text_math(text) is None)


def usable_hints(kind: str, hints: list[str] | None) -> list[str]:
    """Claude's three hints if they're presentable, otherwise the kind's own."""
    hints = [h.strip() for h in (hints or []) if isinstance(h, str) and h.strip()]
    if len(hints) >= 3 and all(statement_ok(h) for h in hints[:3]):
        return hints[:3]
    return list(KIND_INFO[kind].hints)


def _finite(key: Any, answer: str) -> bool:
    if answer == "values":
        return all(finite_real(v) for v in key)
    if answer == "limit":
        return key in (sp.oo, -sp.oo, DNE) or finite_real(key)
    if answer == "number":
        return finite_real(key)
    return isinstance(key, sp.Expr) and not key.has(sp.zoo, sp.nan, sp.oo, -sp.oo)


def _size(key: Any) -> bool:
    items = list(key) if isinstance(key, sp.FiniteSet) else [key]
    return all(sp.count_ops(v) <= MAX_KEY_OPS for v in items if isinstance(v, sp.Basic))


def _failed(name: str, detail: str, reason: str) -> dict:
    report = VerificationReport(False, "none", "none", (Check(name, False, detail),))
    return {"ok": False, "report": report.as_dict(), "reason": reason, "params": None}


def check(payload: dict) -> dict:
    """Build and check one problem. ``payload``: spec, answer (Claude's), statement, word, steps, difficulty.

    Returns ``ok``, ``params`` (with the key), ``prompt``, ``key_latex``,
    ``answer`` (the answer kind), ``signature``, ``report`` and ``reason``.
    """
    spec = dict(payload.get("spec") or {})
    params = {
        "spec": spec,
        "statement": str(payload.get("statement") or ""),
        "word": bool(payload.get("word")),
        "steps": [s for s in payload.get("steps") or [] if isinstance(s, dict)],
        "difficulty": min(4, max(1, int(payload.get("difficulty") or 2))),
    }
    try:
        built = build(params, statement_ok=statement_ok)
    except SpecError as exc:
        return _failed("spec", str(exc), f"Slate can't check this one by computer: {exc}.")
    except (ValueError, TypeError, NotImplementedError, AttributeError, RecursionError, ZeroDivisionError) as exc:
        return _failed("oracle", f"{type(exc).__name__}: {exc}", "SymPy couldn't work this one out.")

    answer = built.params["answer"]
    checks = [Check("spec", True), Check("oracle", True, f"key from SymPy for {spec.get('kind')}")]
    claimed = str(payload.get("answer") or "").strip()
    try:
        method = matches(built, read_answer(built, claimed)) if claimed else None
        detail = method or f"Claude's answer {claimed!r} differs from SymPy's {key_latex(built.key)!r}"
    except (ParseError, ValueError, TypeError, NotImplementedError) as exc:
        method, detail = None, f"couldn't read Claude's answer {claimed!r}: {exc}"
    checks.append(Check("cross_check", method is not None, detail))
    checks.append(Check("finite", _finite(built.key, answer)))
    checks.append(Check("size", _size(built.key)))
    checks.append(Check("text", statement_ok(built.prompt), "" if statement_ok(built.prompt) else "prompt"))
    ok = all(c.passed for c in checks)
    report = VerificationReport(ok, "sympy", method or "none", tuple(checks))
    reason = ""
    if not ok:
        failed = report.failures[0].name
        reason = {
            "cross_check": "Slate's answer and Claude's reading of the problem didn't agree, so Slate won't grade it.",
            "finite": "The answer isn't a real number Slate can check.",
            "size": "The answer is too long to type comfortably.",
            "text": "The problem's wording couldn't be shown cleanly.",
        }.get(failed, "Slate couldn't check this one.")
    return {
        "ok": ok,
        "params": built.params,
        "prompt": built.prompt,
        "key_latex": key_latex(built.key),
        "answer": answer,
        "signature": signature(spec, built.params["key"]),
        "report": report.as_dict(),
        "reason": reason,
    }
