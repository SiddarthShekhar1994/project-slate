"""Parse what a student types into a SymPy expression.

This is a small Pratt parser that builds SymPy objects directly. Nothing the
student types is passed to ``eval`` or ``sympy.parse_expr``.

Accepted input, beyond ordinary ``+ - * / ( )``:

* ``^`` or ``**`` for powers, and pasted Unicode superscripts (``x²``, ``x⁻¹``)
* ``sqrt(...)``, ``cbrt(...)``, ``√x``, ``√(x+1)``
* implicit multiplication: ``3x``, ``2(x+1)``, ``x sin(x)``, ``(x+1)(x-1)``
* function application without parentheses: ``sin x``, ``sin 2x``, ``sin x^2``
* powers of trig functions: ``sin^2(x)``, ``sin²x``
* ``e`` for Euler's number, ``pi`` or ``π``, ``ln``/``log`` for the natural log
* Unicode operators pasted from elsewhere: ``×``, ``·``, ``÷``, ``−``
* a leading ``f'(x) =``, ``dy/dx =`` or ``y' =`` is ignored

Decimals become exact rationals (``0.5`` is ``1/2``). Two trees are produced:
``expr`` is evaluated normally for checking, ``display`` keeps the structure the
student typed so their answer can be shown back to them faithfully.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence

import sympy as sp

MAX_INPUT_CHARS = 300
MAX_NODES = 400
MAX_DEPTH = 40
MAX_EXPONENT = 100
MAX_INTEGER = 10**9


class ParseError(ValueError):
    """Raised with a message that is safe and useful to show the student."""


@dataclass(frozen=True)
class Parsed:
    expr: sp.Expr
    display: sp.Expr
    latex: str
    has_decimal: bool
    decimal_places: int


# --- normalisation ------------------------------------------------------------

_SUPERSCRIPTS = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁻": "-", "⁺": "+", "⁽": "(", "⁾": ")", "ⁿ": "n", "ˣ": "x", "ʸ": "y", "ᵗ": "t", "ᐟ": "/",
}
_REPLACEMENTS = {
    "×": "*", "·": "*", "⋅": "*", "∙": "*", "•": "*", "÷": "/", "∕": "/",
    "−": "-", "–": "-", "—": "-", "‐": "-", "‒": "-",
    "π": "pi", "Π": "pi", "√": "sqrt", "∛": "cbrt",
    "½": "(1/2)", "⅓": "(1/3)", "⅔": "(2/3)", "¼": "(1/4)", "¾": "(3/4)",
    "（": "(", "）": ")", " ": " ", " ": " ", "​": "",
}
_LEADING_LHS = re.compile(
    r"""^\s*(?:
        d\s*[a-z]\s*/\s*d\s*[a-z]        # dy/dx
      | [a-zA-Z]\s*'+\s*(?:\(\s*[a-z]\s*\))?   # y', f'(x)
      | [a-zA-Z]\s*\(\s*[a-z]\s*\)       # f(x) when a student restates the function
    )\s*=\s*""",
    re.VERBOSE,
)


def _normalise(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in _SUPERSCRIPTS:
            run = []
            while i < len(text) and text[i] in _SUPERSCRIPTS:
                run.append(_SUPERSCRIPTS[text[i]])
                i += 1
            out.append("^(" + "".join(run) + ")")
            continue
        out.append(_REPLACEMENTS.get(ch, ch))
        i += 1
    s = "".join(out).replace("**", "^")
    return _LEADING_LHS.sub("", s, count=1)


# --- tokenizer ------------------------------------------------------------------

FUNCTIONS: dict[str, Callable[[sp.Expr], sp.Expr]] = {
    "arcsin": sp.asin, "arccos": sp.acos, "arctan": sp.atan,
    "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
    "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
    "sqrt": sp.sqrt, "cbrt": lambda a: sp.Pow(a, sp.Rational(1, 3)),
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "sec": sp.sec, "csc": sp.csc, "cot": sp.cot,
    "exp": sp.exp, "abs": sp.Abs, "ln": sp.log, "log": sp.log,
}
CONSTANTS: dict[str, sp.Expr] = {"pi": sp.pi, "e": sp.E}
_NAMES_BY_LENGTH = sorted([*FUNCTIONS, *CONSTANTS], key=len, reverse=True)


@dataclass(frozen=True)
class Token:
    kind: str  # num, var, const, func, op, lparen, rparen, end
    text: str
    pos: int


_NUMBER = re.compile(r"\d+(?:\.\d*)?|\.\d+")


def _split_name(run: str, pos: int, variables: Sequence[str]) -> list[Token]:
    """Split a run of letters like ``xsinx`` into known names, longest first."""
    tokens: list[Token] = []
    i = 0
    while i < len(run):
        for name in _NAMES_BY_LENGTH:
            if run.startswith(name, i):
                kind = "func" if name in FUNCTIONS else "const"
                tokens.append(Token(kind, name, pos + i))
                i += len(name)
                break
        else:
            ch = run[i]
            if ch in variables:
                tokens.append(Token("var", ch, pos + i))
                i += 1
            else:
                allowed = " and ".join(variables) if variables else "no variables"
                raise ParseError(f"'{ch}' isn't something I recognise here. This answer can use {allowed}.")
    return tokens


def tokenize(text: str, variables: Sequence[str]) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < len(text) and text[i + 1].isdigit()):
            m = _NUMBER.match(text, i)
            assert m is not None
            tokens.append(Token("num", m.group(0), i))
            i = m.end()
            continue
        if ch.isalpha() and ch.isascii():
            j = i
            while j < len(text) and text[j].isalpha() and text[j].isascii():
                j += 1
            tokens.extend(_split_name(text[i:j], i, variables))
            i = j
            continue
        if ch in "+-*/^":
            tokens.append(Token("op", ch, i))
        elif ch in "([{":
            tokens.append(Token("lparen", ch, i))
        elif ch in ")]}":
            tokens.append(Token("rparen", ch, i))
        elif ch == "|":
            raise ParseError("Use abs(...) for absolute value.")
        elif ch == "=":
            raise ParseError("Enter just the expression, without an equals sign.")
        elif ch == ",":
            raise ParseError("Commas aren't needed. For a decimal use a point, like 0.5.")
        else:
            raise ParseError(f"I can't read the character '{ch}'.")
        i += 1
    tokens.append(Token("end", "", len(text)))
    return tokens


# --- parser ---------------------------------------------------------------------
# The AST is a tuple tree; it is folded into SymPy twice (evaluated and as typed).

Node = tuple


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0
        self.nodes = 0

    def peek(self) -> Token:
        return self.tokens[self.i]

    def take(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def node(self, *parts) -> Node:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ParseError("That answer is too long to check.")
        return tuple(parts)

    def expect_rparen(self, opener: Token) -> None:
        tok = self.take()
        if tok.kind != "rparen":
            raise ParseError(f"A bracket opened at position {opener.pos + 1} is never closed.")

    # expr := term (('+'|'-') term)*
    def expr(self, depth: int) -> Node:
        if depth > MAX_DEPTH:
            raise ParseError("That answer is nested too deeply to check.")
        left = self.term(depth)
        while self.peek().kind == "op" and self.peek().text in "+-":
            op = self.take().text
            right = self.term(depth)
            left = self.node("add" if op == "+" else "sub", left, right)
        return left

    # term := unary (('*'|'/'|implicit) unary)*
    def term(self, depth: int) -> Node:
        left = self.unary(depth)
        while True:
            tok = self.peek()
            if tok.kind == "op" and tok.text in "*/":
                self.take()
                right = self.unary(depth)
                left = self.node("mul" if tok.text == "*" else "div", left, right)
            elif tok.kind in ("num", "var", "const", "func", "lparen"):
                if tok.kind == "num" and self.tokens[self.i - 1].kind == "num":
                    raise ParseError("Two numbers in a row. Did you mean to multiply them?")
                right = self.unary(depth, implicit=True)
                left = self.node("mul", left, right)
            else:
                return left

    # unary := ('-'|'+') unary | power
    def unary(self, depth: int, implicit: bool = False) -> Node:
        tok = self.peek()
        if tok.kind == "op" and tok.text in "+-" and not implicit:
            self.take()
            operand = self.unary(depth)
            return self.node("neg", operand) if tok.text == "-" else operand
        return self.power(depth)

    # power := atom ('^' unary)?   (right associative, exponent may be negative)
    def power(self, depth: int) -> Node:
        base = self.atom(depth)
        if self.peek().kind == "op" and self.peek().text == "^":
            self.take()
            if self.peek().kind == "end":
                raise ParseError("The answer ends with ^. What is the exponent?")
            exponent = self.unary(depth + 1)
            return self.node("pow", base, exponent)
        return base

    def atom(self, depth: int) -> Node:
        tok = self.take()
        if tok.kind == "num":
            return self.node("num", tok.text)
        if tok.kind == "var":
            return self.node("var", tok.text)
        if tok.kind == "const":
            return self.node("const", tok.text)
        if tok.kind == "lparen":
            inner = self.expr(depth + 1)
            self.expect_rparen(tok)
            return self.node("group", inner)
        if tok.kind == "func":
            return self.call(tok, depth)
        if tok.kind == "end":
            raise ParseError("The answer seems to stop early. Is something missing at the end?")
        if tok.kind == "rparen":
            raise ParseError(f"There's a closing bracket at position {tok.pos + 1} with nothing to close.")
        raise ParseError(f"I didn't expect '{tok.text}' at position {tok.pos + 1}.")

    def call(self, func: Token, depth: int) -> Node:
        # sin^2(x) and sin²x mean (sin x)^2.
        power: Node | None = None
        if self.peek().kind == "op" and self.peek().text == "^":
            self.take()
            power = self.unary(depth + 1) if self.peek().kind != "lparen" else self.atom(depth + 1)
        if self.peek().kind == "lparen":
            opener = self.take()
            arg = self.expr(depth + 1)
            self.expect_rparen(opener)
        else:
            arg = self.bare_argument(func, depth)
        out = self.node("call", func.text, arg)
        return self.node("pow", out, power) if power is not None else out

    def bare_argument(self, func: Token, depth: int) -> Node:
        """``sin 2x`` is sin(2x); ``sin x cos x`` is sin(x)·cos(x)."""
        tok = self.peek()
        if tok.kind not in ("num", "var", "const", "func"):
            raise ParseError(f"{func.text} needs something to act on, like {func.text}(x).")
        arg = self.power(depth + 1)
        while self.peek().kind in ("num", "var", "const"):
            arg = self.node("mul", arg, self.power(depth + 1))
        return arg


def _number(text: str) -> sp.Rational:
    if "." in text:
        value = sp.Rational(text)
    else:
        value = sp.Integer(text)
    if abs(value) > MAX_INTEGER:
        raise ParseError("That number is too large to check.")
    return value


def _flat_mul(*factors: sp.Expr) -> sp.Expr:
    """Unevaluated product with nested products spliced in, so it prints as typed."""
    args: list[sp.Expr] = []
    for f in factors:
        args.extend(f.args if isinstance(f, sp.Mul) else (f,))
    return sp.Mul(*args, evaluate=False)


def _flat_add(*terms: sp.Expr) -> sp.Expr:
    args: list[sp.Expr] = []
    for t in terms:
        args.extend(t.args if isinstance(t, sp.Add) else (t,))
    return sp.Add(*args, evaluate=False)


def _negate_display(inner: sp.Expr) -> sp.Expr:
    if inner.is_Number:
        return -inner
    return _flat_mul(sp.S.NegativeOne, inner)


def _fold(node: Node, symbols: dict[str, sp.Symbol], evaluate: bool) -> sp.Expr:
    kind = node[0]
    if kind == "num":
        return _number(node[1])
    if kind == "var":
        return symbols[node[1]]
    if kind == "const":
        return CONSTANTS[node[1]]
    if kind == "group":
        return _fold(node[1], symbols, evaluate)
    if kind == "neg":
        inner = _fold(node[1], symbols, evaluate)
        return -inner if evaluate else _negate_display(inner)
    if kind == "call":
        arg = _fold(node[2], symbols, evaluate)
        fn = FUNCTIONS[node[1]]
        if evaluate:
            return fn(arg)
        if node[1] == "sqrt":
            return sp.sqrt(arg, evaluate=False)
        if node[1] == "cbrt":
            return sp.Pow(arg, sp.Rational(1, 3), evaluate=False)
        return fn(arg, evaluate=False)
    a = _fold(node[1], symbols, evaluate)
    b = _fold(node[2], symbols, evaluate)
    if kind == "pow":
        if b.is_Number and abs(b) > MAX_EXPONENT:
            raise ParseError("That exponent is too large to check.")
        if a.is_Number and b.is_Number and a == 0 and b.is_negative:
            raise ParseError("That divides by zero.")
        return sp.Pow(a, b, evaluate=evaluate)
    if kind == "add":
        return a + b if evaluate else _flat_add(a, b)
    if kind == "sub":
        return a - b if evaluate else _flat_add(a, _negate_display(b))
    if kind == "mul":
        return a * b if evaluate else _flat_mul(a, b)
    if kind == "div":
        if b == 0:
            raise ParseError("That divides by zero.")
        if evaluate:
            return a / b
        reciprocal = sp.Pow(b, -1, evaluate=False)
        return reciprocal if a == 1 else _flat_mul(a, reciprocal)
    raise AssertionError(kind)


def parse_answer(text: str, symbols: Sequence[sp.Symbol]) -> Parsed:
    """Parse a student's answer. ``symbols`` are the variables it may use."""
    if text is None or not text.strip():
        raise ParseError("Type an answer first.")
    if len(text) > MAX_INPUT_CHARS:
        raise ParseError("That answer is too long to check.")
    by_name = {s.name: s for s in symbols}
    normalised = _normalise(text)
    tokens = tokenize(normalised, list(by_name))
    parser = _Parser(tokens)
    tree = parser.expr(0)
    trailing = parser.peek()
    if trailing.kind != "end":
        if trailing.kind == "rparen":
            raise ParseError(f"There's a closing bracket at position {trailing.pos + 1} with nothing to close.")
        raise ParseError(f"I couldn't read the answer from position {trailing.pos + 1} on.")

    try:
        expr = _fold(tree, by_name, evaluate=True)
        display = _fold(tree, by_name, evaluate=False)
    except ParseError:
        raise
    except (ZeroDivisionError, OverflowError, RecursionError, MemoryError):
        raise ParseError("I couldn't work with that answer. Check it for typos.") from None

    if expr.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
        raise ParseError("That answer is undefined. Check for a division by zero.")

    decimals = [t.text for t in tokens if t.kind == "num" and "." in t.text]
    places = max((len(d.split(".", 1)[1]) for d in decimals), default=0)
    return Parsed(
        expr=expr,
        display=display,
        latex=to_latex(display),
        has_decimal=bool(decimals),
        decimal_places=places,
    )


def to_latex(expr: sp.Basic) -> str:
    """LaTeX that keeps the order the student typed things in."""
    return sp.latex(expr, ln_notation=True, order="none")
