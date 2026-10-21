"use client";

import { MathText } from "@/components/shared/math/MathText";
import { Card } from "@/components/shared/ui/Card";
import { StatusPill } from "@/components/shared/ui/StatusPill";
import type { Grade, WorksheetItem } from "@/lib/types";
import { AnswerInput } from "./AnswerInput";
import { Feedback } from "./Feedback";
import { HintLadder } from "./HintLadder";

type Props = {
  item: WorksheetItem;
  total: number;
  grade: Grade | null;
  busy: "answer" | "hint" | "similar" | null;
  onAnswer: (text: string) => void;
  onHint: (level: number) => void;
  onSimilar: () => void;
  onNext: (() => void) | null;
};

/** The problem being worked on: prompt, answer box, hints and feedback. */
export function ProblemCard({ item, total, grade, busy, onAnswer, onHint, onSimilar, onNext }: Props) {
  const cleared = item.status === "cleared" || item.status === "cleared_after_retry";
  const locked = cleared || item.needs_new_problem;
  // After reloading the page the last graded attempt stands in for a fresh grade.
  const shown: Grade | null =
    grade ??
    (item.last_attempt
      ? { status: item.last_attempt.status, latex: item.last_attempt.latex, message: null, mistake: item.last_attempt.mistake }
      : null);

  return (
    <Card as="article" aria-labelledby={`problem-${item.id}`} className="flex flex-col gap-5 p-5 sm:p-6">
      <header className="flex flex-wrap items-center gap-2">
        <h2 id={`problem-${item.id}`} className="text-sm font-semibold text-text-2">
          Problem {item.position + 1} of {total}
        </h2>
        <span className="rounded-full bg-raised px-2.5 py-0.5 text-xs font-semibold text-text-2">
          {item.difficulty_label}
        </span>
        <span className="rounded-full bg-raised px-2.5 py-0.5 text-xs text-muted">{item.skill.title}</span>
        {item.problems_served > 1 && (
          <span className="text-xs text-muted">Similar problem {item.problems_served - 1}</span>
        )}
        <StatusPill status={item.status} className="ml-auto" />
      </header>

      <MathText as="p" text={item.problem.prompt} className="text-lg leading-relaxed text-text sm:text-xl" />
      {item.problem.source && (
        <p className="-mt-3 text-xs text-muted">
          Practice for {item.problem.source.title}, {item.problem.source.locator}
        </p>
      )}

      {!locked && (
        <AnswerInput
          key={item.problem.id}
          variables={item.problem.variables}
          answerKind={item.problem.answer_kind}
          busy={busy === "answer"}
          blocked={busy !== null}
          onSubmit={onAnswer}
          autoFocus={item.problems_served > 1}
        />
      )}

      <div aria-live="polite" aria-atomic="true">
        <Feedback
          grade={shown}
          solution={item.problem.solution}
          onSimilar={item.needs_new_problem ? onSimilar : undefined}
          onNext={cleared && onNext ? onNext : undefined}
          busy={busy === "similar"}
        />
      </div>

      {!cleared && !item.needs_new_problem && (
        <HintLadder
          hints={item.problem.hints}
          level={item.hint_level}
          busy={busy === "hint"}
          disabled={busy !== null && busy !== "hint"}
          onReveal={onHint}
        />
      )}
    </Card>
  );
}
