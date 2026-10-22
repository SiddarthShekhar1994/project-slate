"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { MathText } from "@/components/shared/math/MathText";
import { Button, buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { ApiError, api } from "@/lib/api";
import { dueLabel, percent } from "@/lib/format";
import type { ProgressView, RankedMistake, ReviewEntry, SkillProgress } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const STATUS_TEXT: Record<SkillProgress["status"], string> = {
  new: "Not started",
  learning: "Learning",
  practiced: "Practiced",
  mastered: "Mastered",
};

const BAR_COLOR: Record<SkillProgress["status"], string> = {
  new: "bg-border",
  learning: "bg-warning",
  practiced: "bg-accent-light",
  mastered: "bg-success",
};

export function ProgressHome() {
  const router = useRouter();
  const { data, error } = useApi(() => api.progress());
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function go(key: string, start: () => Promise<{ id: string }>) {
    setBusy(key);
    setActionError(null);
    try {
      const sheet = await start();
      router.push(`/practice/${sheet.id}`);
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Couldn't start that. Try again.");
      setBusy(null);
    }
  }

  if (!data) {
    return error ? <p role="alert">{error}</p> : <Spinner label="Loading your progress" />;
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-accent-tint-text">Progress</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">How it&apos;s going</h1>
          <Summary data={data} />
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/progress/exam" className={buttonClasses("primary")}>
            Practice exam
          </Link>
          <Link href="/progress/formulas" className={buttonClasses("secondary")}>
            Formula sheet
          </Link>
        </div>
      </header>

      {actionError && (
        <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
          {actionError}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="flex min-w-0 flex-col gap-6">
          <SkillMap data={data} busy={busy} onPractice={(id) => go(id, () => api.createWorksheet([id]))} />
          <Mistakes mistakes={data.mistakes} />
        </div>
        <ReviewQueuePanel
          due={data.review.due}
          upcoming={data.review.upcoming}
          busy={busy === "review"}
          onStart={() => go("review", () => api.startReview())}
        />
      </div>
    </div>
  );
}

function Summary({ data }: { data: ProgressView }) {
  const { answers, problems_cleared, first_try_rate } = data.summary;
  if (answers === 0) {
    return <p className="mt-2 text-text-2">Answer a few problems and your skill map fills in here.</p>;
  }
  return (
    <p className="mt-2 text-text-2">
      {problems_cleared} {problems_cleared === 1 ? "problem" : "problems"} cleared from {answers}{" "}
      {answers === 1 ? "answer" : "answers"}
      {first_try_rate !== null && <>, {percent(first_try_rate)} right on the first try</>}.
    </p>
  );
}

function SkillMap({
  data,
  busy,
  onPractice,
}: {
  data: ProgressView;
  busy: string | null;
  onPractice: (skillId: string) => void;
}) {
  return (
    <Card aria-labelledby="skills-heading" className="p-4 sm:p-6">
      <h2 id="skills-heading" className="text-lg font-bold">
        Skill map
      </h2>
      {data.courses.map((course) => (
        <div key={course.id} className="mt-4">
          {data.courses.length > 1 && <p className="text-sm font-semibold text-muted">{course.title}</p>}
          {course.units.map((unit) => (
            <section key={unit.id} aria-labelledby={`unit-${unit.id}`} className="mt-2">
              <h3 id={`unit-${unit.id}`} className="text-sm font-semibold tracking-wide text-muted uppercase">
                {unit.title}
              </h3>
              <ul className="mt-2 flex flex-col divide-y divide-border">
                {unit.skills.map((skill) => (
                  <SkillRow
                    key={skill.id}
                    skill={skill}
                    busy={busy === skill.id}
                    disabled={busy !== null}
                    onPractice={() => onPractice(skill.id)}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      ))}
    </Card>
  );
}

function SkillRow({
  skill,
  busy,
  disabled,
  onPractice,
}: {
  skill: SkillProgress;
  busy: boolean;
  disabled: boolean;
  onPractice: () => void;
}) {
  const value = skill.mastery === null ? 0 : Math.round(skill.mastery * 100);
  const details = [
    skill.attempts ? `${skill.attempts} ${skill.attempts === 1 ? "answer" : "answers"}` : null,
    skill.first_try_rate !== null ? `${percent(skill.first_try_rate)} first try` : null,
    skill.due_at ? `review ${dueLabel(skill.due_at).toLowerCase()}` : null,
  ].filter(Boolean);
  return (
    <li className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="font-semibold">{skill.title}</p>
          <p className="text-sm text-text-2">
            {STATUS_TEXT[skill.status]}
            {skill.mastery !== null && <span className="text-muted"> · {value}%</span>}
          </p>
        </div>
        <div
          role="meter"
          aria-label={`${skill.title} mastery`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={value}
          aria-valuetext={skill.mastery === null ? "Not started" : `${value}%, ${STATUS_TEXT[skill.status]}`}
          className="mt-2 h-2 overflow-hidden rounded-full bg-raised"
        >
          <div className={`h-full rounded-full ${BAR_COLOR[skill.status]}`} style={{ width: `${value}%` }} />
        </div>
        {details.length > 0 && <p className="mt-1.5 text-xs text-muted">{details.join(" · ")}</p>}
      </div>
      <div className="flex gap-2">
        {skill.lessons !== false && (
          <Link href={`/lesson?skill=${encodeURIComponent(skill.id)}`} className={buttonClasses("ghost")}>
            Lesson<span className="sr-only">: {skill.title}</span>
          </Link>
        )}
        <Button variant="secondary" onClick={onPractice} disabled={disabled} aria-busy={busy}>
          {busy ? "Building…" : "Practice"}
          <span className="sr-only">: {skill.title}</span>
        </Button>
      </div>
    </li>
  );
}

function Mistakes({ mistakes }: { mistakes: RankedMistake[] }) {
  return (
    <Card aria-labelledby="mistakes-heading" className="p-4 sm:p-6">
      <h2 id="mistakes-heading" className="text-lg font-bold">
        Mistakes you make most
      </h2>
      {mistakes.length === 0 ? (
        <p className="mt-2 text-text-2">No misses tagged yet. When you get one wrong, the kind of slip shows up here.</p>
      ) : (
        <>
          <p className="mt-1 text-sm text-muted">Recent misses count more than old ones.</p>
          <ol className="mt-4 flex flex-col gap-3">
            {mistakes.map((m, i) => (
              <li key={m.tag} className="rounded-[10px] border border-border bg-raised p-4">
                <div className="flex items-start gap-3">
                  <span
                    aria-hidden
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-card text-sm font-bold text-text-2"
                  >
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold">
                      <MathText text={m.label} />
                    </p>
                    <p className="mt-0.5 text-sm text-text-2">
                      {m.count} {m.count === 1 ? "time" : "times"}
                      {m.recent > 0 && m.recent < m.count && <>, {m.recent} in the last two weeks</>} ·{" "}
                      {m.skills.map((s) => s.title).join(", ")}
                    </p>
                    <p className="mt-2 text-sm text-text-2">
                      <MathText text={m.description} />
                    </p>
                    <p className="mt-2 text-sm">
                      <span className="font-semibold text-text-2">Last time: </span>
                      <MathText text={m.example} />
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </Card>
  );
}

function ReviewQueuePanel({
  due,
  upcoming,
  busy,
  onStart,
}: {
  due: ReviewEntry[];
  upcoming: ReviewEntry[];
  busy: boolean;
  onStart: () => void;
}) {
  return (
    <Card as="aside" aria-labelledby="review-heading" className="flex h-fit flex-col gap-4 p-4 sm:p-6">
      <div>
        <h2 id="review-heading" className="text-lg font-bold">
          Review queue
        </h2>
        <p className="mt-1 text-sm text-muted">
          Skills come back on a spaced schedule: sooner after a miss, further apart each time you get them right.
        </p>
      </div>
      {due.length > 0 ? (
        <>
          <ul className="flex flex-col gap-2" aria-label="Due now">
            {due.map((entry) => (
              <ReviewRow key={entry.skill.id} entry={entry} />
            ))}
          </ul>
          <Button onClick={onStart} disabled={busy} aria-busy={busy}>
            {busy ? "Building…" : `Review ${due.length === 1 ? "this skill" : `these ${Math.min(due.length, 6)}`}`}
          </Button>
        </>
      ) : (
        <p className="text-sm text-text-2">
          {upcoming.length > 0 ? "Nothing due right now." : "Clear a problem and its skill joins the queue."}
        </p>
      )}
      {upcoming.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-muted">Coming up this week</h3>
          <ul className="mt-2 flex flex-col gap-2">
            {upcoming.map((entry) => (
              <ReviewRow key={entry.skill.id} entry={entry} />
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function ReviewRow({ entry }: { entry: ReviewEntry }) {
  return (
    <li className="flex items-baseline justify-between gap-3 rounded-[10px] bg-raised px-3 py-2">
      <span className="font-semibold">{entry.skill.title}</span>
      <span className={`text-sm ${entry.overdue_days > 0 ? "text-warning" : "text-text-2"}`}>
        {dueLabel(entry.due_at)}
      </span>
    </li>
  );
}
