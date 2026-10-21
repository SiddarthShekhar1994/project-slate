"use client";

import { type FormEvent, useId, useState } from "react";
import { MathText } from "@/components/shared/math/MathText";
import { ApiError, api } from "@/lib/api";
import type { AskAnswer } from "@/lib/types";

type Exchange = { question: string; step: number; answer: AskAnswer | null; error: string | null };

/** Ask a question about the step on screen; the answer is grounded in that step. */
export function AskPanel({ lessonId, step, stepTitle }: { lessonId: string; step: number; stepTitle: string }) {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const id = useId();

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setQuestion("");
    const entry: Exchange = { question: q, step, answer: null, error: null };
    setHistory((h) => [entry, ...h]);
    try {
      const answer = await api.ask(lessonId, step, q);
      setHistory((h) => h.map((e) => (e === entry ? { ...e, answer } : e)));
    } catch (e) {
      const error = e instanceof ApiError ? e.message : "Couldn't get an answer. Try again.";
      setHistory((h) => h.map((x) => (x === entry ? { ...x, error } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={`${id}-title`} className="rounded-[14px] border border-border bg-card p-4 sm:p-5">
      <h2 id={`${id}-title`} className="font-semibold text-text">
        Ask about this step
      </h2>
      <p className="mt-1 text-sm text-text-2">
        Questions are answered in the context of step {step + 1}, {stepTitle.toLowerCase()}.
      </p>
      <form onSubmit={onSubmit} className="mt-3 flex flex-col gap-2 sm:flex-row">
        <label htmlFor={`${id}-q`} className="sr-only">
          Your question
        </label>
        <textarea
          id={`${id}-q`}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              (e.currentTarget.form as HTMLFormElement | null)?.requestSubmit();
            }
          }}
          rows={2}
          maxLength={500}
          placeholder="Why do we keep the inside the same?"
          className="min-h-12 flex-1 resize-y rounded-[10px] border border-border bg-raised px-4 py-3 text-base text-text placeholder:text-muted/70 focus-visible:border-accent-light"
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="min-h-12 rounded-[10px] bg-accent px-5 text-sm font-semibold text-white hover:bg-[#3557f0] disabled:bg-raised disabled:text-muted"
        >
          {busy ? "Thinking…" : "Ask"}
        </button>
      </form>
      <ol className="mt-4 flex flex-col gap-3" aria-live="polite">
        {history.map((entry, i) => (
          <li key={i} className="rounded-[10px] bg-raised px-4 py-3">
            <p className="text-sm font-semibold text-text-2">
              {entry.question} <span className="font-normal text-muted">(step {entry.step + 1})</span>
            </p>
            {entry.answer ? (
              <>
                <MathText as="div" text={entry.answer.answer} className="mt-2 whitespace-pre-line text-sm leading-relaxed text-text" />
                {entry.answer.notes.map((note, j) => (
                  <p key={j} className="mt-2 text-xs text-muted">
                    {note}
                  </p>
                ))}
              </>
            ) : entry.error ? (
              <p role="alert" className="mt-2 text-sm text-warning">
                {entry.error}
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted">Thinking…</p>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
