"""LaTeX formatting and ``[[placeholder]]`` rendering for skill text.

Placeholders:

``[[name]]``          LaTeX of ``built.snippets[name]`` or ``built.parts[name]``
``[[name:yellow]]``   the same, wrapped in the yellow board highlight
``[[name:mint]]``     the same, wrapped in the mint board highlight
``[[step:id]]``       the ``latex`` of the step with that id
``[[key]]``           the answer key
``[[expr]]``          the expression being differentiated

Highlights become ``\\htmlClass{slate-yellow}{...}``. The web app renders KaTeX
with ``trust`` limited to ``\\htmlClass`` and maps the classes to theme tokens,
so colours stay in one place.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import sympy as sp

if TYPE_CHECKING:
    from .types import Built

COLORS = ("yellow", "mint")

_PLACEHOLDER = re.compile(r"\[\[([a-zA-Z_][\w]*)(?::([a-zA-Z_][\w]*))?\]\]")


def tex(expr: sp.Basic) -> str:
    """LaTeX for an expression the way Slate shows it (``ln``, not ``log``)."""
    return sp.latex(expr, ln_notation=True)


def highlight(latex: str, color: str) -> str:
    if color not in COLORS:
        raise ValueError(f"unknown highlight colour {color!r}; use one of {COLORS}")
    return rf"\htmlClass{{slate-{color}}}{{{latex}}}"


def tex_compose(outer: sp.Expr, u: sp.Symbol, inner: sp.Expr, *, inner_color: str | None = None,
                outer_color: str | None = None) -> str:
    """LaTeX for ``outer(inner)`` with the inner part optionally highlighted.

    ``outer`` is written in terms of the placeholder symbol ``u``. Rendering
    substitutes a unique marker symbol and splices the inner LaTeX in, so
    SymPy never re-simplifies the composition.
    """
    marker = sp.Symbol("SLATEINNERMARKER")
    outer_tex = tex(outer.subs(u, marker))
    inner_tex = tex(inner)
    if inner_color:
        inner_tex = highlight(inner_tex, inner_color)
    out = outer_tex.replace("SLATEINNERMARKER", inner_tex)
    if outer_color:
        out = highlight(out, outer_color)
    return out


def render(template: str, built: Built) -> str:
    """Fill ``[[...]]`` placeholders in a note or hint template."""

    def lookup(name: str) -> str:
        if name == "key":
            return tex(built.key)
        if name == "expr":
            return tex(built.expr)
        if name in built.snippets:
            return built.snippets[name]
        if name in built.parts:
            return tex(built.parts[name])
        raise KeyError(f"template references unknown part {name!r} (family {built.family})")

    def step_latex(step_id: str) -> str:
        for step in built.steps:
            if step.id == step_id:
                return step.latex
        raise KeyError(f"template references unknown step {step_id!r} (family {built.family})")

    def sub(match: re.Match[str]) -> str:
        name, modifier = match.group(1), match.group(2)
        # [[step:id]] was already replaced, so a modifier here must be a colour.
        if modifier and modifier not in COLORS:
            raise KeyError(f"unknown modifier {modifier!r} in [[{name}:{modifier}]]")
        out = lookup(name)
        return highlight(out, modifier) if modifier else out

    def sub_step(match: re.Match[str]) -> str:
        return step_latex(match.group(1))

    text = re.sub(r"\[\[step:([a-zA-Z_][\w]*)\]\]", sub_step, template)
    return _PLACEHOLDER.sub(sub, text)


def placeholders(template: str) -> list[str]:
    """Names referenced by a template (``step:<id>`` for steps)."""
    names = [f"step:{m}" for m in re.findall(r"\[\[step:([a-zA-Z_][\w]*)\]\]", template)]
    stripped = re.sub(r"\[\[step:[a-zA-Z_][\w]*\]\]", "", template)
    names += [m.group(1) for m in _PLACEHOLDER.finditer(stripped)]
    return names
