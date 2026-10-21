"""Problem generation: parameterised templates per skill, verified by SymPy before use."""

from .engine import (
    GenerationError,
    RenderedHints,
    VerifiedProblem,
    build_worksheet,
    derive_seed,
    generate,
    plan_difficulties,
    problem_signature,
    rebuild,
    similar,
    verify_and_wrap,
)

__all__ = [
    "GenerationError", "RenderedHints", "VerifiedProblem", "build_worksheet", "derive_seed", "generate",
    "plan_difficulties", "problem_signature", "rebuild", "similar", "verify_and_wrap",
]
