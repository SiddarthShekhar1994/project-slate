"""Turn a stored material problem into something practice can serve and grade."""

from __future__ import annotations

from typing import Any

from ..problem_gen import RenderedHints, VerifiedProblem, wrap_material
from ..verify import VerificationReport
from .kinds import GENERIC_SPECS, build


def verified(params: dict[str, Any], report: dict[str, Any], hints: list[str], signature: str, *, skill_id: str,
             origin: str, parent: str | None = None) -> VerifiedProblem:
    """A servable problem from stored ``params`` (which include the key) and its passing report.

    Raises ``TypeError`` if the report says the problem failed its checks.
    """
    built = build(params)
    kind = params["spec"]["kind"]
    nudge, bigger, full = (list(hints) + ["", "", ""])[:3]
    return wrap_material(skill_id, built, VerificationReport.from_dict(report), RenderedHints(nudge, bigger, full),
                         signature, spec=GENERIC_SPECS[kind], origin=origin, parent=parent)
