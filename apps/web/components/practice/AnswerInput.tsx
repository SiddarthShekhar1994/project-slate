"use client";

import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { Icon } from "@/components/shared/ui/Icon";
import { ApiError, api } from "@/lib/api";
import type { AnswerKind, Preview } from "@/lib/types";
import { Tex } from "@/components/shared/math/Tex";

type Props = {
  variables: string[];
  answerKind: AnswerKind;
  /** A word problem's number may end with a unit (ft/s); the grader ignores it. */
  units?: boolean;
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
  /** The problem text, so a photo of the work can be read in context. */
  prompt?: string;
};

type Insert = { label: string; aria: string; text: string; caret: number };

const INSERTS: Insert[] = [
  { label: "xⁿ", aria: "Insert power", text: "^", caret: 1 },
  { label: "√", aria: "Insert square root", text: "sqrt()", caret: 5 },
  { label: "( )", aria: "Insert brackets", text: "()", caret: 1 },
  { label: "eˣ", aria: "Insert e to a power", text: "e^()", caret: 3 },
  { label: "ln", aria: "Insert natural log", text: "ln()", caret: 3 },
  { label: "π", aria: "Insert pi", text: "pi", caret: 2 },
];

// Extra keys for answers that aren't a single expression.
const KIND_INSERTS: Partial<Record<AnswerKind, Insert[]>> = {
  limit: [
    { label: "∞", aria: "Insert infinity", text: "oo", caret: 2 },
    { label: "DNE", aria: "Insert does not exist", text: "DNE", caret: 3 },
  ],
  antiderivative: [{ label: "+ C", aria: "Insert plus C", text: " + C", caret: 4 }],
  line: [{ label: "y =", aria: "Insert y equals", text: "y = ", caret: 4 }],
};

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
  units = false,
  disabled,
  busy,
  blocked,
  onSubmit,
  autoFocus,
  initialText = "",
  label = "Your answer",
  submitLabel = "Check answer",
  busyLabel = "Checking…",
  prompt = "",
}: Props) {
  const [text, setText] = useState(initialText);
  const [photo, setPhoto] = useState<{ state: "reading" | "done" | "error"; message: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
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
        .preview(text, variableKey.split(",").filter(Boolean), controller.signal, answerKind, units)
        .then((result) => setPreview({ text, result }))
        .catch(() => undefined);
    }, 220);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [text, variableKey, answerKind, units]);

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

  async function readPhoto(file: File) {
    setPhoto({ state: "reading", message: "Reading your photo…" });
    try {
      const reading = await api.readPhoto(file, variableKey.split(","), prompt);
      setText(reading.text);
      setPhoto({
        state: "done",
        message: reading.error
          ? "Read from your photo, but part of it didn't make sense. Fix it below, then check."
          : "Read from your photo. Make sure it matches what you wrote, then check it.",
      });
      requestAnimationFrame(() => inputRef.current?.focus());
    } catch (e) {
      setPhoto({ state: "error", message: e instanceof ApiError ? e.message : "Couldn't read that photo." });
    }
  }

  const shown = preview && preview.text === text && text.trim() ? preview.result : null;
  const vars = variables.join(" and ");
  const help = {
    number: (
      <>
        Enter a number. Fractions with <Key>/</Key>, roots with <Key>sqrt()</Key> and <Key>e</Key> are fine.
      </>
    ),
    values: (
      <>
        Separate the values with commas, like <Key>-2, 2</Key>. Type <Key>none</Key> if there aren&apos;t any.
      </>
    ),
    limit: (
      <>
        Type a number, <Key>oo</Key> for infinity, <Key>-oo</Key>, or <Key>DNE</Key> if the limit doesn&apos;t
        exist.
      </>
    ),
    line: (
      <>
        Type the line as <Key>y = mx + b</Key>. Point-slope form works too.
      </>
    ),
    antiderivative: (
      <>
        Use {vars}, and end with <Key>+ C</Key>. Type <Key>^</Key> for powers.
      </>
    ),
    expression: (
      <>
        Use {vars}. Type <Key>^</Key> for powers and <Key>sqrt()</Key> for roots. Pasted superscripts work too.
      </>
    ),
  }[answerKind];
  const inserts = [...(KIND_INSERTS[answerKind] ?? []), ...INSERTS];

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
        {inserts.map((item) => (
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
        <button
          type="button"
          disabled={disabled || photo?.state === "reading"}
          onClick={() => fileRef.current?.click()}
          className="inline-flex min-h-11 items-center gap-2 rounded-[10px] border border-border bg-card px-3 text-sm text-text-2 hover:bg-hover hover:text-text disabled:opacity-50"
        >
          <Icon name="camera" size={18} />
          {photo?.state === "reading" ? "Reading…" : "Photo of your work"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void readPhoto(file);
          }}
        />
      </div>
      <p aria-live="polite" className={`text-sm ${photo?.state === "error" ? "text-warning" : "text-text-2"}`}>
        {photo?.message ?? ""}
      </p>
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
