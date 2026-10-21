"""Answer keys for a worksheet, for end-to-end tests only.

    uv run python scripts/e2e_keys.py <worksheet id>

Prints JSON: per item, the typed key and a typed wrong answer. Reads the
database directly; the API never sends keys before a problem is cleared.
"""

import json
import re
import sys

import sympy as sp
from sqlalchemy.orm import Session

from slate_api.db import get_engine
from slate_api.models import Worksheet
from slate_api.services.practice import load_problem


def typed(expr: sp.Expr) -> str:
    return re.sub(r"\bE\b", "e", sp.sstr(expr).replace("**", "^"))


def main(worksheet_id: str) -> None:
    with Session(get_engine()) as db:
        sheet = db.get(Worksheet, worksheet_id)
        out = []
        for item in sheet.items:
            built = load_problem(item.current_problem).built
            out.append({"position": item.position, "key": typed(built.key), "wrong": typed(built.key + 1)})
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1])
