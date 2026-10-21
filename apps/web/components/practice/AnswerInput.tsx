"use client";

import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Preview } from "@/lib/types";
import { Tex } from "@/components/shared/math/Tex";

type Props = {
  variables: string[];
  answerKind: "expression" | "number";
  disabled?: boolean;
  busy?: boolean;
  /** Another request is in flight: keep typing allowed but hold submission. */
  blocked?: boolean;
  onSubmit: (text: string) => void;
  /** Focus the field when it appears (a new problem was served). */
  autoFocus?: boolean;
  /** Text to start with, e.g. an exam answer saved earlier. */
  initialText?: string;
  label?: string;
  submitLabel?: string;
  busyLabel?: string;
};

const INSERTS: { label: string; aria: string; text: string; caret: number }[] = [
  { label: "xⁿ", aria: "Insert power", text: "^", caret: 1 },
  { label: "√", aria: "Insert square root", text: "sqrt()", caret: 5 },
  { label: "( )", aria: "Insert brackets", text: "()", caret: 1 },
  { label: "eˣ", aria: "Insert e to a power", text: "e^()", caret: 3 },
  { label: "ln", aria: "Insert natural log", text: "ln()", caret: 3 },
  { label: "π", aria: "Insert pi", text: "pi", caret: 2 },
];

/**
 * Text answer with a live KaTeX preview of how the server reads it.
 *
 * The preview comes from the same parser that grades the answer, so what the
 * student sees is exactly what gets checked (``e^2x`` previews as e²·x).
 */
function Key({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-border bg-raised px-1 font-mono text-[0.85em] text-text-2">{children}</kbd>;
}

export function AnswerInput({
  variables,
  answerKind,
  disabled,
  busy,
  blocked,
  onSubmit,
  autoFocus,
  initialText = "",
  label = "Your answer",
  submitLabel = "Check answer",
  busyLabel = "Checking…",
}: Props) {
  const [text, setText] = useState(initialText);
  // The preview remembers which text it is for, so a stale response never shows.
  const [preview, setPreview] = useState<{ text: string; result: Preview } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const id = useId();
  const helpId = `${id}-help`;
  const previewId = `${id}-preview`;

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  // A new array arrives with every worksheet update; only a change of names matters.
  const variableKey = variables.join(",");
  useEffect(() => {
    if (!text.trim()) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .preview(text, variableKey.split(","), controller.signal)
        .then((result) => setPreview({ text, result }))
        .catch(() => undefined);
    }, 220);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [text, variableKey]);

  function insert(snippet: string, caret: number) {
    const input = inputRef.current;
    if (!input) return;
    const start = input.selectionStart ?? text.length;
    const end = input.selectionEnd ?? text.length;
    const next = text.slice(0, start) + snippet + text.slice(end);
    setText(next);
    requestAnimationFrame(() => {
      input.focus();
      input.setSelectionRange(start + caret, start + caret);
    });
  }

  const shown = preview && preview.text === text && text.trim() ? preview.result : null;
  const vars = variables.join(" and ");
  const help =
    answerKind === "number" ? (
      <>
        Enter a number. Fractions with <Key>/</Key>, roots with <Key>sqrt()</Key> and <Key>e</Key> are fine.
      </>
    ) : (
      <>
        Use {vars}. Type <Key>^</Key> for powers and <Key>sqrt()</Key> for roots. Pasted superscripts work too.
      </>
    );

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (text.trim() && !disabled && !busy && !blocked) onSubmit(text);
      }}
    >
      <label htmlFor={id} className="text-sm font-semibold text-text-2">
        {label}
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          ref={inputRef}
          id={id}
          value={text}
          onChange={(event) => setText(event.target.value)}
          disabled={disabled}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          inputMode="text"
          aria-describedby={`${helpId} ${previewId}`}
          placeholder="Type your answer"
          className="min-h-12 flex-1 rounded-[10px] border border-border bg-raised px-4 font-mono text-base text-text placeholder:text-muted/70 focus-visible:border-accent-light disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={disabled || busy || blocked || !text.trim()}
          className="inline-flex min-h-12 items-center justify-center rounded-[10px] bg-accent px-6 text-sm font-semibold text-white transition-colors hover:bg-[#3557f0] disabled:cursor-not-allowed disabled:bg-raised disabled:text-muted"
        >
          {busy ? busyLabel : submitLabel}
        </button>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Insert symbols">
        {INSERTS.map((item) => (
          <button
            key={item.label}
            type="button"
            aria-label={item.aria}
            disabled={disabled}
            onClick={() => insert(item.text, item.caret)}
            className="min-h-11 min-w-11 rounded-[10px] border border-border bg-card px-3 font-math text-base text-text-2 hover:bg-hover hover:text-text disabled:opacity-50"
          >
            {item.label}
          </button>
        ))}
      </div>
      <p id={helpId} className="text-xs text-muted">
        {help}
      </p>
      <div
        id={previewId}
        className="min-h-12 rounded-[10px] border border-dashed border-border px-4 py-2 text-lg"
        aria-label="How Slate reads your answer"
      >
        {shown?.ok && shown.latex ? (
          <Tex latex={shown.latex} />
        ) : shown && !shown.ok ? (
          <span className="text-sm text-warning">{shown.error}</span>
        ) : (
          <span className="text-sm text-muted">Your answer will appear here as math.</span>
        )}
      </div>
    </form>
  );
}
