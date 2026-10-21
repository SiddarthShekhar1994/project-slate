"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { MathText } from "@/components/shared/math/MathText";
import { Spinner } from "@/components/shared/ui/Spinner";
import { STATUS_LABELS, StatusPill } from "@/components/shared/ui/StatusPill";
import { ApiError, api } from "@/lib/api";
import { replaceQuery } from "@/lib/urlState";
import type { Grade, Worksheet, WorksheetItem, WorksheetStats } from "@/lib/types";
import { clock } from "@/lib/format";
import { useCountdown } from "@/lib/useCountdown";
import { EndScreen } from "./EndScreen";
import { ProblemCard } from "./ProblemCard";
import { StatusPanel } from "./StatusPanel";

type Busy = "answer" | "hint" | "similar" | null;

function firstOpen(items: WorksheetItem[]): number {
  const open = items.find((i) => i.status !== "cleared" && i.status !== "cleared_after_retry");
  return open ? open.position : 0;
}

/**
 * A worksheet ordered easy to hard. The selected problem lives in the URL
 * (``?problem=3``) so reloads and shared links land on the same problem.
 */
export function PracticeView({ worksheetId }: { worksheetId: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const [sheet, setSheet] = useState<Worksheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [restarting, setRestarting] = useState(false);
  const [grades, setGrades] = useState<Record<string, Grade>>({});
  const shownAt = useRef<Record<string, number>>({});
  const [landing, setLanding] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .worksheet(worksheetId)
      .then((data) => {
        if (cancelled) return;
        setSheet(data);
        setLanding((current) => current ?? firstOpen(data.items));
      })
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : "Couldn't load this worksheet."));
    return () => {
      cancelled = true;
    };
  }, [worksheetId]);

  // ``landing`` is the first open problem when the sheet loaded. It is captured
  // once so that clearing a problem doesn't yank the view to the next one
  // before the student has read the feedback.

  const requested = Number(search?.get("problem"));
  const validRequest = !!sheet && Number.isInteger(requested) && requested >= 1 && requested <= sheet.items.length;
  const selected = validRequest ? requested - 1 : (landing ?? 0);

  // A shallow URL update: Next keeps useSearchParams in sync with
  // history.replaceState, so switching problems needs no server round trip.
  const select = useCallback((position: number) => {
    replaceQuery({ problem: String(position + 1) });
  }, []);

  // Keep the URL in step with what is on screen.
  useEffect(() => {
    if (sheet && landing !== null && !validRequest) select(landing);
  }, [sheet, landing, validRequest, select]);

  const item = sheet?.items[selected];
  useEffect(() => {
    if (item && !shownAt.current[item.problem.id]) shownAt.current[item.problem.id] = Date.now();
  }, [item]);

  function replaceItem(next: WorksheetItem, stats?: WorksheetStats) {
    setSheet((prev) => {
      if (!prev) return prev;
      const items = prev.items.map((i) => (i.id === next.id ? next : i));
      const done = items.every((i) => i.status === "cleared" || i.status === "cleared_after_retry");
      return {
        ...prev,
        items,
        stats: stats ?? prev.stats,
        completed_at: done ? (prev.completed_at ?? new Date().toISOString()) : prev.completed_at,
      };
    });
  }

  // One request at a time per worksheet: a late hint response must never
  // overwrite the item returned by a newer answer.
  const inFlight = useRef(false);
  async function run<T>(kind: Busy, task: () => Promise<T>): Promise<T | undefined> {
    if (inFlight.current) return undefined;
    inFlight.current = true;
    setBusy(kind);
    setError(null);
    try {
      return await task();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      return undefined;
    } finally {
      inFlight.current = false;
      setBusy(null);
    }
  }

  if (error && !sheet) {
    return (
      <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-warning">
        {error}
      </p>
    );
  }
  if (!sheet || !item) return <Spinner label="Loading worksheet" />;

  const onAnswer = (text: string) =>
    run("answer", async () => {
      const started = shownAt.current[item.problem.id];
      const result = await api.answer(item.id, text, started ? Date.now() - started : undefined);
      setGrades((g) => ({ ...g, [item.problem.id]: result.grade }));
      replaceItem(result.item, result.stats);
    });

  const onHint = (level: number) =>
    run("hint", async () => {
      const result = await api.hint(item.id, level);
      replaceItem(result.item);
    });

  const onSimilar = () =>
    run("similar", async () => {
      const result = await api.similar(item.id);
      replaceItem(result.item, result.stats);
    });

  const nextOpen = sheet.items.find(
    (i) => i.position > selected && i.status !== "cleared" && i.status !== "cleared_after_retry",
  ) ?? sheet.items.find((i) => i.status !== "cleared" && i.status !== "cleared_after_retry");

  const onRestart = async () => {
    setRestarting(true);
    try {
      const fresh = await api.createWorksheet(sheet.skills.map((s) => s.id));
      router.push(`/practice/${fresh.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't build a new worksheet.");
      setRestarting(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold text-accent-tint-text">{KICKERS[sheet.mode] ?? "Practice"}</p>
          {sheet.timer && !sheet.completed_at && <StudyTimer endsAt={sheet.timer.ends_at} now={sheet.timer.now} />}
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-text sm:text-3xl">{sheet.title}</h1>
        <p className="text-sm text-text-2">
          {sheet.stats.total} problems, easy to hard. Miss one and you get a fresh problem of the same kind until it
          clicks.
        </p>
      </header>

      {error && (
        <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
          {error}
        </p>
      )}

      {sheet.completed_at && <EndScreen worksheet={sheet} onRestart={onRestart} restarting={restarting} />}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px] xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-3">
          <ProblemCard
            key={item.id}
            item={item}
            total={sheet.items.length}
            grade={grades[item.problem.id] ?? null}
            busy={busy}
            onAnswer={onAnswer}
            onHint={onHint}
            onSimilar={onSimilar}
            onNext={nextOpen && nextOpen.position !== selected ? () => select(nextOpen.position) : null}
          />

          <h2 className="mt-4 text-sm font-semibold text-text-2">All problems</h2>
          <ol className="flex flex-col gap-2">
            {sheet.items.map((other) => (
              <li key={other.id}>
                <button
                  type="button"
                  onClick={() => select(other.position)}
                  aria-current={other.position === selected ? "step" : undefined}
                  aria-label={`Problem ${other.position + 1}, ${other.skill.title.toLowerCase()}, ${other.difficulty_label.toLowerCase()}: ${STATUS_LABELS[other.status].toLowerCase()}${other.misses ? `, ${other.misses} ${other.misses === 1 ? "miss" : "misses"}` : ""}`}
                  className={`flex min-h-12 w-full items-center gap-3 rounded-[10px] border px-4 py-2 text-left transition-colors ${
                    other.position === selected
                      ? "border-accent-light/50 bg-raised"
                      : "border-border bg-card hover:bg-hover"
                  }`}
                >
                  <span className="w-5 shrink-0 text-sm font-semibold text-muted">{other.position + 1}</span>
                  <MathText text={other.problem.prompt} className="line-clamp-1 min-w-0 flex-1 text-sm text-text-2" />
                  <span className="flex shrink-0 flex-col items-end gap-0.5">
                    <StatusPill status={other.status} />
                    {other.misses > 0 && (
                      <span className="text-xs text-warning lg:hidden">
                        {other.misses} {other.misses === 1 ? "miss" : "misses"}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>

        <div className="lg:sticky lg:top-8 lg:self-start">
          <StatusPanel items={sheet.items} stats={sheet.stats} selected={selected} onSelect={select} />
        </div>
      </div>
    </div>
  );
}

const KICKERS: Record<string, string> = { practice: "Practice", review: "Review", exam: "Practice exam" };

/** Study pace keeps the clock in view but never takes the problem away. */
function StudyTimer({ endsAt, now }: { endsAt: string; now: string }) {
  const left = useCountdown(endsAt, now);
  if (left === null) return null;
  return (
    <p className="text-sm text-text-2">
      {left > 0 ? (
        <>
          <span className="sr-only">Time left: </span>
          <span role="timer" className="font-mono text-base font-bold text-text tabular-nums">
            {clock(left)}
          </span>{" "}
          left
        </>
      ) : (
        <span className="font-semibold text-warning">Time&apos;s up. Finish at your own pace.</span>
      )}
    </p>
  );
}
