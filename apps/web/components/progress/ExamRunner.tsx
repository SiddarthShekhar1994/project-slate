"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AnswerInput } from "@/components/practice/AnswerInput";
import { MathText } from "@/components/shared/math/MathText";
import { Tex } from "@/components/shared/math/Tex";
import { Button, buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { ApiError, api } from "@/lib/api";
import { clock, minutesText } from "@/lib/format";
import type { ExamItem, ExamView } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useCountdown } from "@/lib/useCountdown";

const WARNINGS = [300, 60];

export function ExamRunner({ examId }: { examId: string }) {
  const { data, error, setData } = useApi(() => api.exam(examId), [examId]);
  if (!data) return error ? <p role="alert">{error}</p> : <Spinner label="Loading your exam" />;
  return data.finished ? <ExamResults exam={data} /> : <ExamInProgress exam={data} onUpdate={setData} />;
}

function ExamInProgress({ exam, onUpdate }: { exam: ExamView; onUpdate: (exam: ExamView) => void }) {
  const left = useCountdown(exam.ends_at, exam.now);
  const [answers, setAnswers] = useState<Record<string, string | null>>(() =>
    Object.fromEntries(exam.items.map((i) => [i.id, i.answer])),
  );
  const [saving, setSaving] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirming, setConfirming] = useState(false);
  const [handingIn, setHandingIn] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const warned = useRef(new Set<number>());

  async function handIn() {
    setHandingIn(true);
    try {
      onUpdate(await api.finishExam(exam.id));
      window.scrollTo({ top: 0 });
    } catch {
      setHandingIn(false);
    }
  }

  useEffect(() => {
    if (left === null) return;
    for (const mark of WARNINGS) {
      if (left <= mark && left > 0 && !warned.current.has(mark)) {
        warned.current.add(mark);
        setAnnouncement(`${minutesText(mark)} left.`);
      }
    }
    if (left === 0 && !handingIn) {
      setAnnouncement("Time is up. Handing in your exam.");
      void handIn();
    }
    // handIn is stable enough for this purpose; it only reads exam.id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left]);

  async function save(item: ExamItem, text: string) {
    setSaving(item.id);
    setErrors((prev) => {
      const next = { ...prev };
      delete next[item.id];
      return next;
    });
    try {
      const saved = await api.saveExamAnswer(item.id, text);
      setAnswers((prev) => ({ ...prev, [item.id]: saved.answer }));
      setAnnouncement(`Answer to problem ${item.position + 1} saved.`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        onUpdate(await api.exam(exam.id));
        return;
      }
      setErrors((prev) => ({
        ...prev,
        [item.id]: e instanceof ApiError ? e.message : "Couldn't save that. Try again.",
      }));
    } finally {
      setSaving(null);
    }
  }

  const answered = exam.items.filter((i) => answers[i.id]).length;
  const blank = exam.items.length - answered;
  const low = left !== null && left <= 60;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header className="sticky top-0 z-10 -mx-4 flex flex-wrap items-center justify-between gap-3 border-b border-border bg-page/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-b-[14px] sm:border-x">
        <div>
          <h1 className="text-lg font-bold">{exam.title}</h1>
          <p className="text-sm text-text-2">
            {answered} of {exam.items.length} answered
          </p>
        </div>
        <div className="flex items-center gap-3">
          <p
            role="timer"
            aria-label="Time left"
            className={`font-mono text-xl font-bold tabular-nums ${low ? "text-warning" : "text-text"}`}
          >
            {left === null ? "" : clock(left)}
          </p>
          {!confirming ? (
            <Button onClick={() => (blank > 0 ? setConfirming(true) : void handIn())} disabled={handingIn}>
              {handingIn ? "Grading…" : "Hand in"}
            </Button>
          ) : (
            <span className="flex flex-wrap items-center gap-2">
              <Button onClick={handIn} disabled={handingIn} aria-busy={handingIn}>
                {handingIn ? "Grading…" : `Hand in with ${blank} blank`}
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)} disabled={handingIn}>
                Keep working
              </Button>
            </span>
          )}
        </div>
      </header>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>

      <p className="text-sm text-text-2">
        One try at each problem and no hints. Save an answer to keep it; you can change it until you hand in. Nothing
        is graded before then. The exam hands itself in when the time runs out.
      </p>

      <nav aria-label="Problems" className="flex flex-wrap gap-2">
        {exam.items.map((item) => (
          <a
            key={item.id}
            href={`#problem-${item.position + 1}`}
            className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-[10px] border text-sm font-semibold ${
              answers[item.id]
                ? "border-accent-light bg-accent-tint text-accent-tint-text"
                : "border-border bg-raised text-text-2 hover:bg-hover"
            }`}
          >
            {item.position + 1}
            <span className="sr-only">{answers[item.id] ? ", answered" : ", blank"}</span>
          </a>
        ))}
      </nav>

      <ol className="flex flex-col gap-4">
        {exam.items.map((item) => (
          <li key={item.id} id={`problem-${item.position + 1}`} className="scroll-mt-24">
            <Card as="article" aria-labelledby={`problem-${item.id}-title`} className="flex flex-col gap-4 p-4 sm:p-6">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 id={`problem-${item.id}-title`} className="font-bold">
                  Problem {item.position + 1}
                </h2>
                <p className="text-xs text-muted">
                  {item.skill.title} · {item.difficulty_label}
                </p>
              </div>
              <p className="text-lg leading-relaxed">
                <MathText text={item.problem.prompt} />
              </p>
              <AnswerInput
                variables={item.problem.variables}
                answerKind={item.problem.answer_kind}
                initialText={answers[item.id] ?? ""}
                busy={saving === item.id}
                blocked={saving !== null && saving !== item.id}
                disabled={handingIn}
                submitLabel={answers[item.id] ? "Update answer" : "Save answer"}
                busyLabel="Saving…"
                label={`Your answer to problem ${item.position + 1}`}
                onSubmit={(text) => save(item, text)}
              />
              {errors[item.id] ? (
                <p role="alert" className="text-sm text-warning">
                  {errors[item.id]}
                </p>
              ) : (
                answers[item.id] && <p className="text-sm text-success">Saved.</p>
              )}
            </Card>
          </li>
        ))}
      </ol>
    </div>
  );
}

const RESULT_TEXT = { correct: "Right", incorrect: "Not quite", blank: "Left blank" } as const;
const RESULT_STYLE = {
  correct: "bg-success-bg text-success border-success/40",
  incorrect: "bg-warning-bg text-warning border-warning/40",
  blank: "bg-raised text-text-2 border-border",
} as const;

function ExamResults({ exam }: { exam: ExamView }) {
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { correct, total, by_skill } = exam.stats;
  const missedSkills = Array.from(
    new Set(exam.items.filter((i) => i.result?.status !== "correct").map((i) => i.skill.id)),
  );

  async function practiceMissed() {
    setStarting(true);
    setError(null);
    try {
      const sheet = await api.createWorksheet(missedSkills);
      router.push(`/practice/${sheet.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't build a worksheet.");
      setStarting(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <Link href="/progress" className="text-sm font-semibold text-accent-tint-text hover:underline">
          Progress
        </Link>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
          {correct} of {total} right
        </h1>
        <p className="mt-2 text-text-2">
          {exam.time_used_s !== null && <>Handed in after {minutesText(exam.time_used_s)} of {minutesText(exam.time_limit_s)}. </>}
          {exam.stats.blank ? `${exam.stats.blank} left blank. ` : ""}
          Every topic here is now on your review schedule.
        </p>
      </header>

      {error && (
        <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
          {error}
        </p>
      )}

      {by_skill && (
        <Card aria-labelledby="by-topic" className="p-4 sm:p-6">
          <h2 id="by-topic" className="text-lg font-bold">
            By topic
          </h2>
          <ul className="mt-3 flex flex-col gap-2">
            {by_skill.map((row) => (
              <li key={row.skill.id} className="flex items-baseline justify-between gap-3 rounded-[10px] bg-raised px-3 py-2">
                <span className="font-semibold">{row.skill.title}</span>
                <span className="text-sm text-text-2">
                  {row.correct} of {row.total}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap gap-3">
            {missedSkills.length > 0 && (
              <Button onClick={practiceMissed} disabled={starting} aria-busy={starting}>
                {starting ? "Building…" : "Practice what you missed"}
              </Button>
            )}
            <Link href="/progress/exam" className={buttonClasses("secondary")}>
              Another exam
            </Link>
          </div>
        </Card>
      )}

      <ol className="flex flex-col gap-4">
        {exam.items.map((item) => (
          <li key={item.id}>
            <ResultCard item={item} />
          </li>
        ))}
      </ol>
    </div>
  );
}

function ResultCard({ item }: { item: ExamItem }) {
  const result = item.result;
  if (!result) return null;
  const mistake = result.attempt?.mistake;
  return (
    <Card as="article" aria-labelledby={`result-${item.id}`} className="flex flex-col gap-3 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={`result-${item.id}`} className="font-bold">
          Problem {item.position + 1}
          <span className="font-normal text-muted"> · {item.skill.title}</span>
        </h2>
        <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${RESULT_STYLE[result.status]}`}>
          {RESULT_TEXT[result.status]}
        </span>
      </div>
      <p className="leading-relaxed">
        <MathText text={item.problem.prompt} />
      </p>
      {result.attempt?.latex && (
        <p className="text-sm text-text-2">
          You answered <Tex latex={result.attempt.latex} />
        </p>
      )}
      {result.status !== "correct" && (
        <p className="text-sm text-text-2">
          The answer is <Tex latex={result.answer_latex} />
        </p>
      )}
      {mistake && (
        <div className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-sm">
          <p className="font-semibold text-warning">
            <MathText text={mistake.label} />
          </p>
          <p className="mt-1 text-text-2">
            <span className="font-semibold">Where to look: </span>
            <MathText text={mistake.where_to_look} />
          </p>
        </div>
      )}
      <details className="text-sm">
        <summary className="min-h-11 cursor-pointer content-center font-semibold text-text-2">Worked solution</summary>
        <ol className="mt-2 flex flex-col gap-2">
          {result.solution.map((step) => (
            <li key={step.id} className="rounded-lg bg-raised px-3 py-2">
              <p className="text-xs font-semibold text-muted">
                <MathText text={step.title} />
              </p>
              <Tex latex={step.latex} display className="text-text" />
            </li>
          ))}
        </ol>
      </details>
    </Card>
  );
}
