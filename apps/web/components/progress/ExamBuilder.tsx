"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useMemo, useState } from "react";
import { Button, buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { ApiError, api } from "@/lib/api";
import { allocate, planDifficulties, timeLimitSeconds } from "@/lib/exam";
import { minutesText } from "@/lib/format";
import { useTopics } from "@/lib/topics";
import type { ExamPace, ExamWeight, TopicCard } from "@/lib/types";
import { replaceQuery } from "@/lib/urlState";

const COUNTS = [4, 6, 8, 10, 12];
// Problems on a topic run easy, medium, hard.
const LEVELS = [1, 2, 3];

/** A topic can be on the exam once Slate has problems for it. */
const examinable = (topic: TopicCard) => topic.builtin || topic.problems > 0;

/** Pick topics, weight them like the syllabus, choose a pace, start a timed set. URL: ?skills=&pace=&count= */
export function ExamBuilder() {
  const router = useRouter();
  const search = useSearchParams();
  const { dashboard, error: loadError } = useTopics();
  const skills = useMemo(() => (dashboard?.topics ?? []).filter(examinable), [dashboard]);

  const [chosen, setChosen] = useState<string[] | null>(() => {
    const raw = search?.get("skills");
    return raw ? raw.split(",").filter(Boolean) : null;
  });
  const [pace, setPace] = useState<ExamPace>(() => (search?.get("pace") === "study" ? "study" : "exam"));
  const [count, setCount] = useState(() => {
    const n = Number(search?.get("count"));
    return COUNTS.includes(n) ? n : 8;
  });
  const [defaults, setDefaults] = useState<{
    weights: ExamWeight[];
    minutes: Record<string, number>;
    study_factor: number;
  } | null>(null);
  const [edited, setEdited] = useState<Record<string, number>>({});
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Everything is chosen until the student says otherwise.
  const selected = useMemo(() => {
    const known = new Set(skills.map((s) => s.id));
    return (chosen ?? skills.map((s) => s.id)).filter((id) => known.has(id));
  }, [chosen, skills]);
  const selectedKey = selected.join(",");

  useEffect(() => {
    if (!selectedKey) return;
    let cancelled = false;
    api
      .examWeights(selectedKey.split(","))
      .then((value) => !cancelled && setDefaults(value))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [selectedKey]);

  useEffect(() => {
    if (!dashboard) return;
    replaceQuery({ skills: chosen ? chosen.join(",") : null, pace, count: String(count) });
  }, [dashboard, chosen, pace, count]);

  const weights: Record<string, number> = Object.fromEntries(
    selected.map((id) => [id, edited[id] ?? defaults?.weights.find((w) => w.skill_id === id)?.weight ?? 1]),
  );
  const counts = allocate(weights, count);
  const difficulties = selected.flatMap((id) => planDifficulties(LEVELS, counts[id] ?? 0));
  const fromSyllabus = defaults?.weights.filter((w) => w.source) ?? [];

  function toggle(id: string, on: boolean) {
    setChosen(on ? [...selected, id] : selected.filter((s) => s !== id));
  }

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const created = await api.createExam(weights, count, pace);
      router.push(created.pace === "exam" ? `/exam/${created.id}` : `/practice/${created.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't build the exam. Try again.");
      setStarting(false);
    }
  }

  if (!dashboard) {
    return loadError ? <p role="alert">{loadError}</p> : <Spinner label="Loading topics" />;
  }
  const waiting = dashboard.topics.filter((t) => !examinable(t));

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header>
        <Link href="/progress" className="text-sm font-semibold text-accent-tint-text hover:underline">
          Progress
        </Link>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Practice exam</h1>
        <p className="mt-2 text-text-2">
          A timed set over the topics you pick, weighted the way your exam will be. Every answer key is checked by
          a computer algebra system first.
        </p>
      </header>

      {error && (
        <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
          {error}
        </p>
      )}

      <Card className="p-4 sm:p-6">
        <fieldset>
          <legend className="text-lg font-bold">Topics and weights</legend>
          <p className="mt-1 text-sm text-muted">
            {fromSyllabus.length > 0
              ? "Weights start from your syllabus. Change any of them; they're scaled to fit."
              : "Weights start equal. Upload your syllabus and Slate uses its percentages. They're scaled to fit."}
          </p>
          {skills.length === 0 ? (
            <p className="mt-4 text-sm text-text-2">
              Add a topic or upload a study guide on the{" "}
              <Link href="/dashboard" className="text-accent-light underline-offset-4 hover:underline">
                dashboard
              </Link>{" "}
              first. Its topics can then go on a practice exam.
            </p>
          ) : (
            <ul className="mt-4 flex flex-col gap-2">
              {skills.map((skill) => (
                <TopicRow
                  key={skill.id}
                  skill={skill}
                  checked={selected.includes(skill.id)}
                  weight={weights[skill.id]}
                  problems={counts[skill.id] ?? 0}
                  source={defaults?.weights.find((w) => w.skill_id === skill.id)?.source ?? null}
                  onToggle={(on) => toggle(skill.id, on)}
                  onWeight={(value) => setEdited({ ...edited, [skill.id]: value })}
                />
              ))}
            </ul>
          )}
          {waiting.length > 0 && (
            <p className="mt-3 text-xs text-muted">
              Not yet: {waiting.map((t) => t.title).join(", ")}. Slate has no checked problems for{" "}
              {waiting.length === 1 ? "it" : "them"} yet.
            </p>
          )}
        </fieldset>
      </Card>

      <Card className="flex flex-col gap-5 p-4 sm:p-6">
        <div>
          <label htmlFor="exam-count" className="text-lg font-bold">
            Problems
          </label>
          <select
            id="exam-count"
            value={count}
            onChange={(event) => setCount(Number(event.target.value))}
            className="mt-2 block min-h-11 rounded-[10px] border border-border bg-raised px-3 text-text"
          >
            {COUNTS.map((n) => (
              <option key={n} value={n}>
                {n} problems
              </option>
            ))}
          </select>
        </div>

        <fieldset>
          <legend className="text-lg font-bold">Pace</legend>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {(["exam", "study"] as const).map((value) => {
              const seconds = defaults
                ? timeLimitSeconds(difficulties, value, defaults.minutes, defaults.study_factor)
                : null;
              return (
                <label
                  key={value}
                  className={`flex min-h-11 cursor-pointer gap-3 rounded-[10px] border p-4 ${
                    pace === value ? "border-accent-light bg-accent-tint" : "border-border bg-raised hover:bg-hover"
                  }`}
                >
                  <input
                    type="radio"
                    name="pace"
                    value={value}
                    checked={pace === value}
                    onChange={() => setPace(value)}
                    className="mt-1 h-4 w-4 accent-[#2748E8]"
                  />
                  <span>
                    <span className="block font-semibold">{value === "exam" ? "Exam pace" : "Study pace"}</span>
                    <span className="mt-1 block text-sm text-text-2">
                      {value === "exam"
                        ? "One try at each problem, no hints, graded when you hand in."
                        : "Hints and similar problems after a miss, with half as much time again."}
                    </span>
                    {seconds !== null && selected.length > 0 && (
                      <span className="mt-1 block text-sm font-semibold text-text">{minutesText(seconds)}</span>
                    )}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <div className="flex flex-wrap gap-3">
          <Button onClick={start} disabled={starting || selected.length === 0} aria-busy={starting}>
            {starting ? "Building your exam…" : "Start the exam"}
          </Button>
          <Link
            href={`/progress/formulas?skills=${encodeURIComponent(selected.join(","))}`}
            className={buttonClasses("secondary")}
          >
            Formula sheet for these topics
          </Link>
        </div>
        {selected.length === 0 && <p className="text-sm text-warning">Pick at least one topic.</p>}
      </Card>
    </div>
  );
}

function TopicRow({
  skill,
  checked,
  weight,
  problems,
  source,
  onToggle,
  onWeight,
}: {
  skill: Pick<TopicCard, "id" | "title">;
  checked: boolean;
  weight: number | undefined;
  problems: number;
  source: ExamWeight["source"];
  onToggle: (on: boolean) => void;
  onWeight: (value: number) => void;
}) {
  const id = useId();
  return (
    <li className="flex flex-col gap-2 rounded-[10px] bg-raised px-3 py-2 sm:flex-row sm:items-center">
      <label htmlFor={`${id}-on`} className="flex min-h-11 flex-1 cursor-pointer items-center gap-3">
        <input
          id={`${id}-on`}
          type="checkbox"
          checked={checked}
          onChange={(event) => onToggle(event.target.checked)}
          className="h-5 w-5 accent-[#2748E8]"
        />
        <span>
          <span className="font-semibold">{skill.title}</span>
          {checked && source && (
            <span className="block text-xs text-muted">
              {source.title}, {source.locator}
            </span>
          )}
        </span>
      </label>
      {checked && (
        <div className="flex items-center gap-3 pl-8 sm:pl-0">
          <label htmlFor={`${id}-weight`} className="sr-only">
            Weight for {skill.title}, percent
          </label>
          <input
            id={`${id}-weight`}
            type="number"
            inputMode="decimal"
            min={0}
            max={100}
            step={1}
            value={weight ?? ""}
            onChange={(event) => onWeight(Math.max(0, Math.min(100, Number(event.target.value) || 0)))}
            className="min-h-11 w-20 rounded-[10px] border border-border bg-card px-3 text-right text-text"
          />
          <span className="text-sm text-muted" aria-hidden>
            %
          </span>
          <span className="w-24 text-sm text-text-2" aria-live="polite">
            {problems} {problems === 1 ? "problem" : "problems"}
          </span>
        </div>
      )}
    </li>
  );
}
