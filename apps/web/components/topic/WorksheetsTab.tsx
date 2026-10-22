"use client";

import { useState } from "react";
import { MathText } from "@/components/shared/math/MathText";
import { WorksheetList } from "@/components/practice/WorksheetList";
import { Button } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import type { TopicView } from "@/lib/types";

const LENGTHS = [5, 8, 12] as const;

/** Worksheets on this topic: start a new one, pick up an old one, and see what keeps tripping you up. */
export function WorksheetsTab({
  view,
  busy,
  onStart,
}: {
  view: TopicView;
  busy: string | null;
  onStart: (count: number) => void;
}) {
  const [count, setCount] = useState<number>(8);
  const canPractice = view.builtin || view.problems > 0;
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
      <div className="flex min-w-0 flex-col gap-6">
        <Card className="flex flex-col gap-4 p-5">
          <div>
            <h2 className="text-base font-bold">New worksheet</h2>
            <p className="mt-1 text-sm text-text-2">
              Problems run easy to hard. Miss one and you get a fresh problem of the same kind until you get one right.
            </p>
          </div>
          <fieldset className="flex flex-wrap items-center gap-2">
            <legend className="mb-2 text-sm font-semibold text-text-2">How many problems?</legend>
            {LENGTHS.map((n) => (
              <label
                key={n}
                className={`flex min-h-11 min-w-16 cursor-pointer items-center justify-center rounded-[10px] border px-4 text-sm font-semibold has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent-light ${
                  count === n ? "border-accent-light bg-accent-tint text-accent-tint-text" : "border-border bg-raised text-text"
                }`}
              >
                <input
                  type="radio"
                  name="worksheet-length"
                  value={n}
                  checked={count === n}
                  onChange={() => setCount(n)}
                  className="sr-only"
                />
                {n}
              </label>
            ))}
          </fieldset>
          <div>
            <Button onClick={() => onStart(count)} disabled={!canPractice || busy !== null} aria-busy={busy === "sheet"}>
              {busy === "sheet" ? "Building…" : "Start the worksheet"}
            </Button>
            {!canPractice && (
              <p className="mt-2 text-sm text-muted">There are no checked problems on this topic yet.</p>
            )}
          </div>
        </Card>

        <section aria-labelledby="past-worksheets" className="flex flex-col gap-3">
          <h2 id="past-worksheets" className="text-base font-bold">
            Your worksheets
          </h2>
          {view.worksheets.length ? (
            <WorksheetList worksheets={view.worksheets} />
          ) : (
            <p className="text-sm text-text-2">None yet. Your first one shows up here.</p>
          )}
        </section>
      </div>

      <Card as="aside" aria-labelledby="topic-mistakes" className="h-fit p-5">
        <h2 id="topic-mistakes" className="text-base font-bold">
          What trips you up here
        </h2>
        {view.mistakes.length ? (
          <ul className="mt-3 flex flex-col gap-3">
            {view.mistakes.map((m) => (
              <li key={m.tag} className="text-sm">
                <p className="font-semibold text-text">
                  {m.label} <span className="font-normal text-muted">({m.count})</span>
                </p>
                {m.example && <MathText as="p" text={m.example} className="mt-1 text-text-2" />}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-text-2">Nothing yet. Slate notes the kind of slip behind each miss.</p>
        )}
      </Card>
    </div>
  );
}
