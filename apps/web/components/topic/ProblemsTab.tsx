"use client";

import Link from "next/link";
import { MathText } from "@/components/shared/math/MathText";
import { Button } from "@/components/shared/ui/Button";
import type { TopicProblem, TopicView } from "@/lib/types";
import { Notice } from "./Notice";

export const DIFFICULTY: Record<number, string> = { 1: "Easy", 2: "Medium", 3: "Hard", 4: "Challenge" };

const RESULT: Record<TopicProblem["result"], { label: string; tone: string } | null> = {
  solved: { label: "Solved", tone: "border-success/40 bg-success-bg text-success" },
  missed: { label: "Missed so far", tone: "border-warning/40 bg-warning-bg text-warning" },
  new: null,
};

function ProblemRow({
  problem,
  busy,
  disabled,
  onTry,
}: {
  problem: TopicProblem;
  busy: boolean;
  disabled: boolean;
  onTry: () => void;
}) {
  const result = RESULT[problem.result];
  const where = [
    problem.label ? `Problem ${problem.label}` : null,
    problem.source?.title ?? null,
    DIFFICULTY[problem.difficulty],
    problem.kind,
  ].filter(Boolean);
  return (
    <li className="flex flex-col gap-3 rounded-[14px] border border-border bg-card p-4 sm:flex-row sm:items-start">
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted">{where.join(" · ")}</p>
        <MathText as="p" text={problem.statement} className="mt-1 break-words text-text" />
        {problem.status !== "ready" && (
          <p className="mt-2 text-sm text-muted">{problem.reason || "Slate can't check this one by computer."}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {result && (
          <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${result.tone}`}>{result.label}</span>
        )}
        {problem.status === "ready" && (
          <Button variant="secondary" onClick={onTry} disabled={disabled} aria-busy={busy}>
            {busy ? "Opening…" : problem.result === "new" ? "Try it" : "Try again"}
            <span className="sr-only">: {problem.label ? `problem ${problem.label}` : "this problem"}</span>
          </Button>
        )}
      </div>
    </li>
  );
}

/** The topic's problems: the ones from the student's study guide, then more Slate wrote and checked. */
export function ProblemsTab({
  view,
  busy,
  claude,
  onPractice,
  onTry,
  onWriteMore,
}: {
  view: TopicView;
  busy: string | null;
  claude: boolean;
  onPractice: () => void;
  onTry: (problemId: string) => void;
  onWriteMore: () => void;
}) {
  const sheet = view.problem_list.filter((p) => p.origin === "sheet");
  const more = view.problem_list.filter((p) => p.origin === "variant");
  const canPractice = view.builtin || view.problems > 0;

  const status = (() => {
    if (view.practice === "writing") {
      return (
        <Notice tone="working">
          Slate is writing problems on {view.title.toLowerCase()} and checking every answer with SymPy. They show up
          here as soon as they pass.
        </Notice>
      );
    }
    if (view.practice_error) {
      return (
        <Notice
          tone="warning"
          action={
            claude && (
              <Button variant="secondary" onClick={onWriteMore} disabled={busy !== null}>
                Try again
              </Button>
            )
          }
        >
          {view.practice_error}
        </Notice>
      );
    }
    if (view.practice === "needs_key" && !canPractice) {
      return (
        <Notice>
          Problems on this topic need a Claude API key. Add one in{" "}
          <Link href="/settings" className="font-semibold text-accent-light underline-offset-4 hover:underline">
            Settings
          </Link>
          .
        </Notice>
      );
    }
    return null;
  })();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-2xl text-sm text-text-2">
          {view.builtin
            ? "Slate makes a fresh problem for this topic every time, from easy to hard, and checks each answer key with SymPy."
            : "Every problem here had its answer worked out by SymPy, and Slate only kept the ones that agreed. Miss one and you get a similar problem until it clicks."}
        </p>
        <Button onClick={onPractice} disabled={!canPractice || busy !== null} aria-busy={busy === "all"}>
          {busy === "all" ? "Building…" : "Practice, easy to hard"}
        </Button>
      </div>
      {status}

      {sheet.length > 0 && (
        <section aria-labelledby="sheet-problems" className="flex flex-col gap-3">
          <h2 id="sheet-problems" className="text-base font-bold">
            From your study guide
          </h2>
          <ul className="flex flex-col gap-3">
            {sheet.map((p) => (
              <ProblemRow
                key={p.id}
                problem={p}
                busy={busy === p.id}
                disabled={busy !== null}
                onTry={() => onTry(p.id)}
              />
            ))}
          </ul>
        </section>
      )}

      {more.length > 0 && (
        <section aria-labelledby="more-problems" className="flex flex-col gap-3">
          <h2 id="more-problems" className="text-base font-bold">
            {sheet.length ? "More like these" : "Practice problems"}
          </h2>
          <ul className="flex flex-col gap-3">
            {more.map((p) => (
              <ProblemRow
                key={p.id}
                problem={p}
                busy={busy === p.id}
                disabled={busy !== null}
                onTry={() => onTry(p.id)}
              />
            ))}
          </ul>
        </section>
      )}

      {!view.builtin && claude && view.practice !== "writing" && (
        <div>
          <Button variant="secondary" onClick={onWriteMore} disabled={busy !== null}>
            {busy === "more" ? "Starting…" : "Write more problems"}
          </Button>
        </div>
      )}
    </div>
  );
}
