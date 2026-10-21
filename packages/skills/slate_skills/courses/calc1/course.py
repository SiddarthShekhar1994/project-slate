"""Single-variable calculus (MATH 30 level)."""

from ...core.types import Course, Unit
from .derivatives import chain_rule, implicit_differentiation, power_rule, product_rule, quotient_rule

DERIVATIVES = Unit(
    id="derivatives",
    title="Derivatives",
    skills=(
        power_rule.SKILL,
        product_rule.SKILL,
        quotient_rule.SKILL,
        chain_rule.SKILL,
        implicit_differentiation.SKILL,
    ),
)

COURSE = Course(
    id="calc1",
    title="Single-variable calculus",
    description="Limits, derivatives and integrals of one-variable functions (MATH 30 level).",
    units=(DERIVATIVES,),
)
