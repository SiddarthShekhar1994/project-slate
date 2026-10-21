"""Generate many problems for one skill and report verification results.

    uv run python scripts/check_skill.py calc1.derivatives.chain_rule --seeds 40 --show 2

Prints, per family: pass rate, time per problem, failing checks, and a few
sample prompts with keys and mistake answers so a human can eyeball them.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from random import Random

import sympy as sp
from slate_api.services.verify import verify_built
from slate_skills import load_skill_module
from slate_skills.core.text import render


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("skill_id")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--show", type=int, default=1, help="sample problems to print per family")
    args = ap.parse_args()

    skill = load_skill_module(args.skill_id)
    total_bad = 0
    for fam in skill.families:
        fails: Counter[str] = Counter()
        build_errors = 0
        t0 = time.time()
        shown = 0
        for seed in range(args.seeds):
            try:
                built = fam.build(fam.sample(Random(seed)))
            except ValueError:
                build_errors += 1
                continue
            report = verify_built(skill, built)
            if not report.ok:
                for c in report.failures:
                    fails[f"{c.name}: {c.detail[:120]}"] += 1
            if shown < args.show:
                shown += 1
                print(f"  [{fam.id} d{fam.difficulty} seed {seed}] {built.prompt}")
                print(f"      key: {sp.sstr(built.key)}")
                for m in skill.mistakes:
                    wrong = m.buggy(built)
                    if wrong is not None:
                        print(f"      {m.tag}@{m.step}: {sp.sstr(wrong)}")
                ladder = skill.hint_ladder(built)
                print(f"      hint 2: {render(ladder.bigger, built)[:160]}")
        ms = (time.time() - t0) / args.seeds * 1000
        bad = sum(fails.values())
        total_bad += bad
        status = "OK " if not fails else "BAD"
        print(f"{status} {fam.id:24} d{fam.difficulty} {ms:7.0f} ms/problem  rejected_builds={build_errors}"
              f"  failing_checks={dict(fails) if fails else 0}")
    raise SystemExit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
