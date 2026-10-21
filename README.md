# Slate

Slate is a study app for math courses, built around your own course materials. It's the NotebookLM idea, except the lesson is a narrated chalkboard where the math writes itself step by step, and practice adapts to what you get wrong.

The first course is single-variable calculus (MATH 30 level), starting with the derivative unit: power, product, quotient and chain rules, plus implicit differentiation. Courses are data in `packages/skills`, so adding one doesn't touch the app.

## How it keeps the math right

- Every answer key is checked by SymPy before anyone sees the problem. Templates derive the key by walking the rule's steps. The verifier then recomputes it independently (`sp.diff`, or the implicit function theorem) and must prove the two equal. A `VerifiedProblem` can only be created after that check passes, and the `problems` table has a check constraint that refuses a row whose stored report doesn't say `ok`.
- Answers are compared as math, not strings. Student input goes through a small Pratt parser that builds SymPy objects directly and never calls `eval`. A numeric screen at 30 digits rejects most wrong answers in milliseconds. A symbolic chain then proves the rest: `simplify`, then `fu`, rewrites, and `equals`, with reduction modulo the curve for implicit answers. Answers are compared on the key's real domain, so `cbrt(x^2)` and `x^(2/3)` count as the same function.
- Every wrong answer gets a mistake tag. The tag comes from the skill's own mistake patterns (each computes the exact wrong answer that error produces), then from the expected intermediate steps, then from generic sign, coefficient, dropped-term and algebra-slip checks. Tags are stored per attempt and drive the Progress page.
- Facts the LLM states get checked too. Lesson scripts and tutor answers carry their math as structured claims, which SymPy verifies before they're served. A checkpoint distractor that turns out to be secretly correct is caught.

## Layout

```
apps/
  api/                    FastAPI backend (Python, uv)
    slate_api/
      routers/            auth, catalog, math (input preview), practice, lessons, media
      services/
        verify/           parse.py, equivalence.py, keycheck.py, claims.py
        problem_gen/      engine.py: generate, similar, worksheets
        grading/          grade.py: correctness and mistake tagging
        practice.py       worksheets and the retry loop
        lessons.py        built-in lessons, player views, progress, checkpoints
        ask.py            "ask about this step", with claim checking
        tts.py            ElevenLabs or OpenAI speech with word timings, cached per step
        llm.py            the single Claude API wrapper
        sandbox.py        grading in a killable child process
        storage.py        local disk or S3 for uploads and audio
      models/             SQLAlchemy models; migrations/ holds Alembic revisions
      lessons/builtin/    hand-written lesson scripts (JSON)
    tests/
  web/                    Next.js 16 + TypeScript + Tailwind 4 + KaTeX
    app/                  routes: /library, /lesson/[id], /practice/[id], /progress, /login
    components/           grouped by page, plus shared/board, shared/math, shared/ui
    lib/lesson/           lesson script types and the timeline engine
packages/
  skills/                 one Python module per skill: families, steps, mistakes, hints, formula
scripts/                  check_skill.py, dev-restart.sh, e2e_keys.py
```

## Running it locally

Requirements: Python 3.11+ with [uv](https://docs.astral.sh/uv/), Node 20.9+ with pnpm, and PostgreSQL 16 (or `docker compose up postgres`).

```bash
cp .env.example .env            # then fill in what you want to use
uv sync --all-packages          # Python workspace: apps/api + packages/skills
(cd apps/web && pnpm install)

createdb slate                  # or use docker compose
uv run alembic -c apps/api/alembic.ini upgrade head

uv run uvicorn slate_api.main:app --port 8000      # API
(cd apps/web && pnpm dev --port 3000)              # web, proxies /api to the API
```

Open http://localhost:3000 and create an account.

Without API keys everything still works. Hints, notes and "ask about this step" fall back to the templated text in the skills package, and lessons play with captions on an estimated clock. Set `ANTHROPIC_API_KEY` for Claude-written answers and lessons. Set `ELEVENLABS_API_KEY` or `OPENAI_API_KEY` (with `TTS_PROVIDER`) for the narrated voice.

## Tests

```bash
uv run pytest                                   # verification, generation, grading, API (needs Postgres: slate_test)
uv run python scripts/check_skill.py calc1.derivatives.chain_rule --seeds 100
(cd apps/web && pnpm test)                      # Vitest: KaTeX, timeline engine, captions
(cd apps/web && pnpm e2e)                       # Playwright, desktop and phone
```

The API tests use a database named `slate_test` (`createdb slate_test`). For Playwright in an environment with a preinstalled Chromium, set `PW_CHROMIUM_PATH` instead of running `playwright install`.

## Adding a skill or a course

A skill is one module under `packages/skills/slate_skills/courses/<course>/<unit>/<skill>.py` exporting `SKILL` (see `chain_rule.py`, the reference). It declares:

- families of parameterised problems per difficulty (1 easy to 4 challenge), including word problems
- the worked steps, with checkable values
- the mistake patterns, each returning the exact wrong answer
- the hint ladder and the formula sheet entry
- keywords used to match uploaded sources to the skill

Check it with `scripts/check_skill.py`. To add a course, create a package that defines `COURSE` and list it in `slate_skills/courses/__init__.py`.

## Build status

Built in stages; each ships working before the next starts.

1. Skills package, SymPy verification and generation, with tests. **Done.**
2. Practice page with the retry loop, hint ladder and mistake tagging; local accounts. **Done.**
3. Lesson player with board animation, captions, checkpoints and TTS. **Done.** The built-in chain rule lesson ships now; the ElevenLabs and OpenAI voices are tested against mocked responses, and a silent test voice exercises the audio-driven clock end to end.
4. Source upload and ingestion, then generated lesson scripts cited to sources.
5. Progress page, exam mode, formula sheet, review queue.
6. Voice questions and photo answer input.
