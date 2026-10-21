"""Placeholder until the skill file is written."""
from .chain_rule import SKILL as _CHAIN
from dataclasses import replace
SKILL = replace(_CHAIN, id="calc1.derivatives.implicit_differentiation", slug="implicit_differentiation")
