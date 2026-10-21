"""Structural checks for lesson scripts, mirroring ``validateScript`` in the web app.

A generated script must pass these before its math claims are even checked:
anchors must point at words that are actually spoken, effects must target
lines already on the board, checkpoints need exactly one correct option, and
every cited source must be one the generator was given.
"""

from __future__ import annotations

from typing import Any

from ..tts import spoken_words

ACTIONS = {"write", "label", "highlight", "box", "fade"}
COLORS = {"chalk", "yellow", "mint"}


def _balanced(latex: str) -> bool:
    depth = 0
    escaped = False
    for ch in latex:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def validate_script(script: dict[str, Any], allowed_sources: set[str] | None = None) -> list[str]:
    problems: list[str] = []
    steps = script.get("steps") or []
    if not steps:
        return ["script has no steps"]
    lines: set[str] = set()
    labels: set[str] = set()
    source_ids = {s.get("id") for s in script.get("sources", [])}
    if allowed_sources is not None and not source_ids <= allowed_sources:
        problems.append(f"script cites unknown sources {sorted(source_ids - allowed_sources)}")

    for index, step in enumerate(steps):
        where = f"step {index + 1} ({step.get('id')})"
        words = len(spoken_words(step.get("narration") or []))
        if words == 0:
            problems.append(f"{where}: no narration")
        for action in step.get("actions") or []:
            kind = action.get("type")
            if kind not in ACTIONS:
                problems.append(f"{where}: unknown action {kind!r}")
                continue
            at = action.get("at") or {}
            if "word" in at and not 0 <= int(at["word"]) < max(words, 1):
                problems.append(f"{where}: anchor word {at['word']} is past the {words} spoken words")
            if "color" in action and action["color"] not in COLORS:
                problems.append(f"{where}: unknown colour {action['color']!r}")
            if kind == "write":
                if action.get("id") in lines:
                    problems.append(f"{where}: line {action.get('id')} is written twice")
                lines.add(action.get("id"))
                if not _balanced(action.get("latex", "")):
                    problems.append(f"{where}: unbalanced braces in line {action.get('id')}")
            elif kind == "label":
                if action.get("target") not in lines:
                    problems.append(f"{where}: label {action.get('id')} targets {action.get('target')}, not on the board yet")
                labels.add(action.get("id"))
            elif kind == "fade":
                if action.get("target") not in lines | labels:
                    problems.append(f"{where}: fade targets {action.get('target')}, not on the board yet")
            elif action.get("target") not in lines:
                problems.append(f"{where}: {kind} targets {action.get('target')}, not on the board yet")
        checkpoint = step.get("checkpoint")
        if checkpoint and sum(1 for o in checkpoint.get("options", []) if o.get("correct")) != 1:
            problems.append(f"{where}: checkpoint needs exactly one correct option")
        for ref in step.get("sources") or []:
            if ref not in source_ids:
                problems.append(f"{where}: cites {ref}, which is not in the script's sources")
    return problems
