"""The mistake taxonomy shared by every course.

Skill files reference these tags from their :class:`MistakePattern` entries.
The grader in ``apps/api`` stores one tag per wrong answer, and the Progress
page ranks tags by how often they occur, grouped under ``category``.

Generic tags (``sign_error``, ``coefficient_slip``, ``dropped_term``,
``algebra_slip``, ``unclassified``) are detected by the grader itself after the
skill-specific patterns have been tried.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MistakeType:
    tag: str
    label: str
    category: str
    description: str


CATEGORIES: dict[str, str] = {
    "rule": "Rule applied wrong",
    "sign": "Sign errors",
    "algebra": "Algebra slips while simplifying",
    "other": "Other",
}

_TYPES = [
    # Chain rule
    MistakeType("dropped_inner_derivative", "Dropped inner derivative", "rule",
                "Differentiated the outside function but never multiplied by the derivative of the inside."),
    MistakeType("composed_derivatives", "Composed the derivatives", "rule",
                "Plugged the inner derivative into the outer derivative instead of multiplying."),
    MistakeType("wrong_outer_derivative", "Wrong outer derivative", "rule",
                "Used the wrong derivative for the outside function."),
    # Power rule
    MistakeType("power_exponent_not_reduced", "Exponent not reduced", "rule",
                "Brought the power down in front but did not lower the exponent by one."),
    MistakeType("power_coefficient_dropped", "Power not brought down", "rule",
                "Lowered the exponent but did not multiply by the old exponent."),
    MistakeType("negative_exponent_slip", "Negative or fractional exponent slip", "algebra",
                "Subtracted one from a negative or fractional exponent incorrectly."),
    MistakeType("constant_term_kept", "Constant not differentiated to zero", "rule",
                "Left a constant term in the derivative."),
    # Product rule
    MistakeType("product_of_derivatives", "Multiplied the derivatives", "rule",
                "Wrote (fg)' = f'g' instead of f'g + fg'."),
    MistakeType("product_rule_missing_term", "Product rule missing a term", "rule",
                "Kept only one of the two product-rule terms."),
    # Quotient rule
    MistakeType("quotient_numerator_swapped", "Quotient rule terms swapped", "sign",
                "Subtracted in the wrong order in the numerator, which flips the sign."),
    MistakeType("quotient_denominator_not_squared", "Denominator not squared", "rule",
                "Divided by g instead of g squared."),
    MistakeType("quotient_as_derivative_ratio", "Divided the derivatives", "rule",
                "Wrote (f/g)' = f'/g'."),
    MistakeType("quotient_plus_instead_of_minus", "Plus instead of minus in quotient rule", "sign",
                "Added the two numerator terms instead of subtracting."),
    # Implicit differentiation
    MistakeType("implicit_missing_dydx", "Missing dy/dx on y terms", "rule",
                "Differentiated y terms as if y were a constant or as if d/dx of y^n were n y^(n-1) with no dy/dx."),
    MistakeType("implicit_product_rule_missed", "Product rule missed on a mixed term", "rule",
                "Differentiated a term like xy without the product rule."),
    MistakeType("implicit_isolation_error", "Slip while isolating dy/dx", "algebra",
                "Collected or divided the dy/dx terms incorrectly."),
    # Trig and exponential basics that show up inside other rules
    MistakeType("trig_derivative_sign", "Trig derivative sign", "sign",
                "Got the sign of d/dx sin or d/dx cos backwards."),
    MistakeType("exp_log_derivative_error", "Exponential or log derivative error", "rule",
                "Used the wrong derivative for e^x or ln x."),
    # Generic, detected by the grader
    MistakeType("sign_error", "Sign error", "sign",
                "Right structure, but the sign of the answer or of one term is flipped."),
    MistakeType("coefficient_slip", "Coefficient slip", "algebra",
                "Right structure, wrong constant factor."),
    MistakeType("dropped_term", "Dropped a term", "algebra",
                "One term of the derivative is missing."),
    MistakeType("algebra_slip", "Algebra slip while simplifying", "algebra",
                "Set up the derivative correctly but made an arithmetic or algebra slip while simplifying."),
    MistakeType("unclassified", "Other mistake", "other",
                "The answer does not match any known mistake pattern."),
]

MISTAKE_TYPES: dict[str, MistakeType] = {m.tag: m for m in _TYPES}
GENERIC_TAGS = ("sign_error", "coefficient_slip", "dropped_term", "algebra_slip", "unclassified")


def mistake_type(tag: str) -> MistakeType:
    try:
        return MISTAKE_TYPES[tag]
    except KeyError:
        raise KeyError(f"unknown mistake tag {tag!r}") from None
