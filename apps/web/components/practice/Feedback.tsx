"use client";

import { Tex } from "@/components/shared/math/Tex";
import { MathText } from "@/components/shared/math/MathText";
import { Icon } from "@/components/shared/ui/Icon";
import type { Grade, SolutionStep } from "@/lib/types";

type Props = {
  grade: Grade | null;
  solution: SolutionStep[] | null;
  onSimilar?: () => void;
  onNext?: () => void;
  busy?: boolean;
};

/** "Dropped inner derivative" reads as "dropped inner derivative" mid-sentence; math is left alone. */
function lowerFirst(text: string): string {
  return text.startsWith("$") ? text : text.charAt(0).toLowerCase() + text.slice(1);
}

/** Result of the last check. Lives in an aria-live region so it is announced. */
export function Feedback({ grade, solution, onSimilar, onNext, busy }: Props) {
  if (!grade) return null;

  if (grade.status === "invalid") {
    return (
      <div className="rounded-[10px] border border-border bg-raised px-4 py-3 text-sm text-text-2">
        <p className="font-semibold text-text">I couldn&apos;t read that yet.</p>
        {grade.message && <MathText as="p" text={grade.message} className="mt-1" />}
        <p className="mt-1 text-muted">This doesn&apos;t count as a miss.</p>
      </div>
    );
  }

  if (grade.status === "correct") {
    return (
      <div className="flex flex-col gap-3 rounded-[10px] border border-success/40 bg-success-bg px-4 py-3">
        <p className="flex items-center gap-2 font-semibold text-success">
          <Icon name="check" size={18} /> Correct
        </p>
        {grade.latex && (
          <p className="text-sm text-text-2">
            You answered <Tex latex={grade.latex} />
          </p>
        )}
        {grade.message && <MathText as="p" text={grade.message} className="text-sm text-text-2" />}
        {solution && (
          <details className="text-sm">
            <summary className="min-h-11 cursor-pointer content-center font-semibold text-text-2">
              See the worked solution
            </summary>
            <ol className="mt-2 flex flex-col gap-2">
              {solution.map((step) => (
                <li key={step.id} className="rounded-lg bg-card px-3 py-2">
                  <p className="text-xs font-semibold text-muted">
                    <MathText text={step.title} />
                  </p>
                  <Tex latex={step.latex} display className="text-text" />
                </li>
              ))}
            </ol>
          </details>
        )}
        {onNext && (
          <button
            type="button"
            onClick={onNext}
            className="inline-flex min-h-11 items-center gap-2 self-start rounded-[10px] bg-accent px-4 text-sm font-semibold text-white hover:bg-[#3557f0]"
          >
            Next problem <Icon name="arrow" size={18} />
          </button>
        )}
      </div>
    );
  }

  const mistake = grade.mistake;
  return (
    <div className="flex flex-col gap-3 rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3">
      <p className="font-semibold text-warning">Not quite</p>
      {grade.latex && (
        <p className="text-sm text-text-2">
          You answered <Tex latex={grade.latex} className="text-text" />
        </p>
      )}
      {mistake && (
        <div className="flex flex-col gap-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-warning/90">
            Where to look{mistake.step_title ? <> · <MathText text={mistake.step_title} /></> : null}
          </p>
          <MathText as="p" text={mistake.where_to_look} className="text-sm leading-relaxed text-text" />
          <MathText as="p" className="text-xs text-muted" text={`Likely mistake: ${lowerFirst(mistake.label)}`} />
        </div>
      )}
      {onSimilar && (
        <button
          type="button"
          onClick={onSimilar}
          disabled={busy}
          className="inline-flex min-h-11 items-center gap-2 self-start rounded-[10px] bg-accent px-4 text-sm font-semibold text-white hover:bg-[#3557f0] disabled:bg-raised disabled:text-muted"
        >
          <Icon name="retry" size={18} /> {busy ? "Making one…" : "Try a similar problem"}
        </button>
      )}
    </div>
  );
}
