# Slate

Slate is a study app for math courses, built around your own course materials. It's the NotebookLM idea, except the lesson is a narrated chalkboard where the math writes itself step by step, and practice adapts to what you get wrong.

The first course is single-variable calculus (MATH 30 level), starting with the derivative unit: power, product, quotient and chain rules, plus implicit differentiation. Courses are data in `packages/skills`, so adding one doesn't touch the app.

Slate runs as a Windows app (one installer, no sign-in, everything stored on your PC) or as a website.

## The Windows app

Download `Slate-Setup-<version>.exe` from the latest successful [Windows app](../../actions/workflows/windows-app.yml) run (under Artifacts), or from Releases once a version is tagged. Run it and pick where to install. Windows SmartScreen may warn that the publisher is unknown, because the installer isn't code-signed yet: choose "More info", then "Run anyway".

Slate opens straight into your Library. Your library, progress and settings live in `%APPDATA%\Slate\data`, and uninstalling keeps them. Everything works offline without any keys. To turn on Claude-written lessons, the narrated voice and spoken questions, paste API keys on the Settings page.

Under the hood the app is the same code as the website. An Electron window (`apps/desktop`) starts the Python backend, packaged with PyInstaller and storing data in SQLite, and the Next.js interface on free ports on 127.0.0.1. Nothing listens on your network. The GitHub Actions workflow builds the installer on Windows, installs it, and drives the installed app through a practice session before keeping it.

To build it yourself on Windows, with uv, Node 24 and pnpm:

```bash
pnpm --dir apps/desktop install
pnpm --dir apps/desktop dist:win      # installer in apps/desktop/dist
pnpm --dir apps/desktop start         # or run it from source, without packaging
```

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
      routers/            auth, catalog, math (preview, photo), practice, lessons, sources, progress, exam,
                          voice, media
      services/
        verify/           parse.py, equivalence.py, keycheck.py, claims.py
        problem_gen/      engine.py: generate, similar, worksheets
        grading/          grade.py: correctness and mistake tagging
        practice.py       worksheets and the retry loop
        review.py         SM-2 spaced repetition on skills: the review queue
        exam.py           timed sets weighted by the syllabus, graded at hand-in
        progress.py       skill map, ranked mistakes, formula sheet
        ingest/           extract (PDF, PPTX, DOCX, images), ocr, chunk, match skills, notation
        lesson_gen/       lesson scripts from sources: Claude with checks, or the composer
        sources.py        uploads, background processing, citations
        lessons.py        built-in and generated lessons, player views, progress, checkpoints
        ask.py            "ask about this step", with claim checking
        tts.py            ElevenLabs or OpenAI speech with word timings, cached per step
        stt.py            spoken questions: OpenAI or ElevenLabs transcription
        photo.py          reads the final answer from a photo of the student's work
        app_settings.py   API keys entered in the Windows app's Settings page
        llm.py            the single Claude API wrapper
        sandbox.py        grading in a killable child process (warm worker pool on Windows)
        storage.py        local disk or S3 for uploads and audio
      models/             SQLAlchemy models (PostgreSQL or SQLite); migrations/ holds Alembic revisions
      desktop.py          the Windows app's backend entry point
      lessons/builtin/    hand-written lesson scripts (JSON)
    tests/
  web/                    Next.js 16 + TypeScript + Tailwind 4 + KaTeX
    app/                  routes: /library, /lesson/[id], /practice/[id], /progress, /progress/exam,
                          /progress/formulas, /exam/[id], /settings, /login
    components/           grouped by page, plus shared/board, shared/math, shared/ui
    lib/lesson/           lesson script types and the timeline engine
    proxy.ts              forwards /api to the backend, at whatever address API_ORIGIN names
  desktop/                the Windows app: Electron shell (main.js), PyInstaller recipe, installer build
packages/
  skills/                 one Python module per skill: families, steps, mistakes, hints, formula
scripts/                  setup.sh, start.sh, check_skill.py, e2e_keys.py, dev-restart.sh (test helper)
```

## Running the website locally

You need:

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs Python for you)
- Node 24 LTS, or Node 22.22.2 or newer, with pnpm 10: run `corepack enable` once (Node 25 and later don't include corepack; use `npm install -g pnpm@10` there)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) for the database, or your own PostgreSQL 16 (see "Without Docker" below)

It runs on macOS and Linux. On Windows, use WSL2: install Ubuntu from the Microsoft Store, turn on WSL integration in Docker Desktop's settings, clone the repo inside your Linux home folder (not under `/mnt/c`), and run every command in the Ubuntu terminal.

```bash
git clone https://github.com/SiddarthShekhar1994/project-slate.git
cd project-slate
scripts/setup.sh     # once: .env, PostgreSQL in Docker, packages, database tables
scripts/start.sh     # API on :8000 and web app on :3000; Ctrl-C stops both
```

Open http://localhost:3000 and create an account. Next time, `scripts/start.sh` is all you need.

### What the scripts do

If you'd rather run the steps yourself:

```bash
cp .env.example .env
docker compose up -d --wait postgres     # role slate/slate, databases slate and slate_test
uv sync --all-packages                   # Python workspace: apps/api + packages/skills
pnpm --dir apps/web install
uv run --env-file .env alembic -c apps/api/alembic.ini upgrade head

uv run --env-file .env uvicorn slate_api.main:app --port 8000    # terminal 1: API
pnpm --dir apps/web dev --port 3000                              # terminal 2: web app
```

The API only reads real environment variables, so `.env` takes effect through `uv run --env-file .env`. A variable already exported in your shell wins over the same one in `.env`. The web app forwards `/api` to http://localhost:8000. If you run the API somewhere else, put `API_ORIGIN=http://localhost:<port>` in `apps/web/.env.local`, because Next.js doesn't read the root `.env`.

### Without Docker

Use PostgreSQL 16 from Homebrew, Postgres.app or `apt`. Create the role and databases that the default `DATABASE_URL` expects, then run `scripts/setup.sh` as usual. On Linux, run the first command as `sudo -u postgres psql -c "..."`.

```bash
psql -d postgres -c "CREATE ROLE slate LOGIN PASSWORD 'slate' CREATEDB"
createdb -h localhost -U slate slate          # password: slate
createdb -h localhost -U slate slate_test
```

Or point `DATABASE_URL` in `.env` at a database you already have. If Docker is installed but you use your own PostgreSQL, stop one of them: both want port 5432.

### API keys (all optional)

Without keys everything still works. Hints, notes and "ask about this step" fall back to the templated text in the skills package. Lessons you generate from your sources are composed from verified problems instead of written by Claude. Lessons play with captions on an estimated clock. Add keys to `.env` and restart:

- `ANTHROPIC_API_KEY`: Claude writes lessons from your sources, answers questions, reads photos and scanned pages.
- `ELEVENLABS_API_KEY` or `OPENAI_API_KEY`: the narrated voice, and spoken questions in the ask panel. With both set, `TTS_PROVIDER` and `STT_PROVIDER` choose.

Without `ANTHROPIC_API_KEY`, images and picture-only pages are read with Tesseract if it's installed (`brew install tesseract`, or `sudo apt install tesseract-ocr` on Linux and WSL). If neither is there, the page is kept but marked as unread.

## Tests

```bash
uv run pytest                                   # verification, generation, grading, API
uv run python scripts/check_skill.py calc1.derivatives.chain_rule --seeds 100
pnpm --dir apps/web test                        # Vitest: KaTeX, timeline engine, captions
pnpm --dir apps/web exec playwright install --with-deps chromium   # once, for the end-to-end tests
pnpm --dir apps/web e2e                         # Playwright, desktop and phone
pnpm --dir apps/desktop test                    # the desktop app, driven through Electron
```

`TEST_DATABASE_URL` can also name a SQLite file, such as `sqlite:////tmp/slate_test.db`; that's how the Windows build runs the suite.

The API tests drop and rebuild the schema of `slate_test`, which Docker creates for you. They never use `DATABASE_URL`. To point them elsewhere, set `TEST_DATABASE_URL` to a database whose name ends in `_test`. The tests also ignore any API keys in your shell, so they never call paid APIs.

The end-to-end tests start the API on port 8000 and the web app on 3000 with a silent test voice and a fake transcriber, so stop `scripts/start.sh` first. If servers are already running on those ports, Playwright reuses them instead. The tests create throwaway accounts in your `slate` database. In an environment with a preinstalled Chromium, set `PW_CHROMIUM_PATH` instead of running `playwright install`.

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
4. Source upload and ingestion, then generated lesson scripts cited to sources. **Done.** Uploads are split into topic-sized chunks, matched to skills and scanned for the professor's notation (prime, Leibniz or operator; ln or log; the letter for the inner function). Claude writes the lesson from the best chunks; every math claim and checkpoint is checked with SymPy, and a lesson that fails three times is replaced by one composed from a verified problem. Practice problems cite the chunk they were matched to.
5. Progress page, exam mode, formula sheet, review queue. **Done.** The skill map shows mastery per skill; mistakes are ranked by a count where each miss weighs half as much for every two weeks of age. Every cleared problem feeds an SM-2 schedule per skill (several in one sitting count as one review), and due skills can be reviewed in one click. Practice exams take topics, weights (read from an uploaded syllabus when it gives percentages) and a pace: exam pace has no hints, one try and grading at hand-in; study pace keeps the practice loop with half as much time again. The formula sheet covers the chosen topics in the professor's notation and prints cleanly.
6. Voice questions and photo answer input. **Done.** The ask panel records a spoken question, transcribes it and puts the text in the box for the student to check before asking. Practice and exam problems take a photo of the student's work: Claude vision copies their final answer exactly (mistakes included, never solved), Tesseract does the same for neat print without an API key, and the reading only fills the answer box. Grading stays symbolic.
