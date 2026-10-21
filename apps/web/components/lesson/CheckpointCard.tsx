"use client";

import { useEffect, useRef, useState } from "react";
import { MathText } from "@/components/shared/math/MathText";
import { Tex } from "@/components/shared/math/Tex";
import { Icon } from "@/components/shared/ui/Icon";
import { api } from "@/lib/api";
import type { Checkpoint } from "@/lib/lesson/types";

type Props = { lessonId: string; step: number; checkpoint: Checkpoint; onContinue: () => void };

/** "Pause and predict": playback stops and waits for a choice before the next step. */
export function CheckpointCard({ lessonId, step, checkpoint, onContinue }: Props) {
  const [chosen, setChosen] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const option = checkpoint.options.find((o) => o.id === chosen);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  function choose(id: string) {
    if (chosen) return;
    setChosen(id);
    void api.checkpoint(lessonId, step, id).catch(() => undefined);
  }

  return (
    <section
      aria-labelledby={`checkpoint-${step}`}
      className="flex flex-col gap-4 rounded-[14px] border border-accent-light/40 bg-accent-tint p-5"
    >
      <h2 id={`checkpoint-${step}`} ref={heading} tabIndex={-1} className="text-sm font-semibold uppercase tracking-wide text-accent-tint-text">
        Pause and predict
      </h2>
      <MathText as="p" text={checkpoint.prompt} className="text-lg text-text" />
      <div role="group" aria-label="Choices" className="grid gap-2 sm:grid-cols-2">
        {checkpoint.options.map((o, index) => {
          const state = !chosen ? "idle" : o.correct ? "right" : o.id === chosen ? "wrong" : "idle";
          return (
            <button
              key={o.id}
              type="button"
              onClick={() => choose(o.id)}
              aria-disabled={chosen !== null}
              aria-pressed={o.id === chosen}
              aria-label={`Choice ${String.fromCharCode(65 + index)}: ${o.say}`}
              className={`flex min-h-14 items-center justify-between gap-3 rounded-[10px] border px-4 py-3 text-left text-lg transition-colors ${
                state === "right"
                  ? "border-success/60 bg-success-bg text-text"
                  : state === "wrong"
                    ? "border-warning/60 bg-warning-bg text-text"
                    : "border-border bg-card text-text hover:bg-hover"
              } ${chosen ? "cursor-default" : ""}`}
            >
              <Tex latex={o.latex} />
              {state === "right" && <Icon name="check" className="text-success" />}
              {state === "wrong" && <Icon name="close" className="text-warning" />}
            </button>
          );
        })}
      </div>
      <div aria-live="polite">
        {option && (
          <div className="flex flex-col gap-3">
            <p className={`font-semibold ${option.correct ? "text-success" : "text-warning"}`}>
              {option.correct ? "Right." : "Not quite."}
            </p>
            <MathText as="p" text={option.why} className="text-sm text-text-2" />
            {!option.correct && (
              <MathText
                as="p"
                className="text-sm text-text-2"
                text={`The answer is $${checkpoint.options.find((o) => o.correct)?.latex ?? ""}$.`}
              />
            )}
            <button
              type="button"
              onClick={onContinue}
              className="inline-flex min-h-11 items-center gap-2 self-start rounded-[10px] bg-accent px-4 text-sm font-semibold text-white hover:bg-[#3557f0]"
            >
              Continue the lesson <Icon name="arrow" size={18} />
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
