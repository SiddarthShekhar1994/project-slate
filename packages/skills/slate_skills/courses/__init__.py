"""Every course Slate ships.

Each entry is the module that defines ``COURSE``. Modules are imported lazily
by :mod:`slate_skills.registry`, so importing one skill file never pulls in the
rest of the catalogue. Skill ids mirror module paths: the skill
``calc1.derivatives.chain_rule`` lives in
``slate_skills/courses/calc1/derivatives/chain_rule.py``.
"""

COURSE_MODULES = ("slate_skills.courses.calc1.course",)
