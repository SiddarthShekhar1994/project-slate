"use client";

import { MathText } from "@/components/shared/math/MathText";
import { Icon } from "@/components/shared/ui/Icon";

const LEVELS = ["Nudge", "Bigger hint", "Full step"] as const;

type Props = {
  hints: string[];
  level: number;
  disabled?: boolean;
  busy?: boolean;
  onReveal: (level: number) => void;
};

/** Three hints that open in order: a nudge, a bigger hint, then the full step. */
export function HintLadder({ hints, level, disabled, busy, onReveal }: Props) {
  const next = level + 1;
  return (
    <section aria-label="Hints" className="flex flex-col gap-3">
      {hints.length > 0 && (
        <ol className="flex flex-col gap-2">
          {hints.map((hint, i) => (
            <li key={i} className="rounded-[10px] border border-accent-light/25 bg-accent-tint px-4 py-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-accent-tint-text">{LEVELS[i]}</p>
              <MathText as="p" text={hint} className="text-sm leading-relaxed text-text" />
            </li>
          ))}
        </ol>
      )}
      {next <= 3 && (
        <button
          type="button"
          onClick={() => onReveal(next)}
          disabled={disabled || busy}
          className="inline-flex min-h-11 items-center gap-2 self-start rounded-[10px] px-3 text-sm font-semibold text-accent-tint-text hover:bg-accent-tint disabled:opacity-50"
        >
          <Icon name="hint" size={18} />
          {level === 0 ? "Show a hint" : `Show ${LEVELS[next - 1].toLowerCase()}`}
          <span className="text-xs font-normal text-muted">
            ({next} of 3)
          </span>
        </button>
      )}
    </section>
  );
}
