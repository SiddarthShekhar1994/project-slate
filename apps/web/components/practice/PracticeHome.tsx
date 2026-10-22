"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Tex } from "@/components/shared/math/Tex";
import { buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { ApiError, api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { WorksheetList } from "./WorksheetList";

export function PracticeHome() {
  const router = useRouter();
  const catalog = useApi(() => api.catalog());
  const recent = useApi(() => api.worksheets());
  const materials = useApi(() => api.materialTopics());
  const topics = materials.data?.topics ?? [];
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start(key: string, skillIds: string[]) {
    setStarting(key);
    setError(null);
    try {
      const sheet = await api.createWorksheet(skillIds);
      router.push(`/practice/${sheet.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't build a worksheet.");
      setStarting(null);
    }
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8">
      <header>
        <p className="text-sm font-semibold text-accent-tint-text">Practice</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Pick a skill to practice</h1>
        <p className="mt-2 max-w-2xl text-text-2">
          Each worksheet runs easy to hard. Every answer key is checked by a computer algebra system before you see
          the problem, and a miss gets you a fresh problem of the same kind.
        </p>
      </header>

      {error && (
        <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
          {error}
        </p>
      )}

      {recent.data && recent.data.worksheets.length > 0 && (
        <section aria-labelledby="recent-heading" className="flex flex-col gap-3">
          <h2 id="recent-heading" className="text-lg font-bold">
            Recent worksheets
          </h2>
          <WorksheetList worksheets={recent.data.worksheets.slice(0, 4)} />
        </section>
      )}

      {topics.length > 0 && (
        <section aria-labelledby="materials-heading" className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="materials-heading" className="text-lg font-bold">
                From your materials
              </h2>
              <p className="mt-1 max-w-2xl text-sm text-text-2">
                Topics Slate found in your uploads. Problems come from your sheets, plus similar ones Claude writes
                and Slate checks the same way.
              </p>
            </div>
            {topics.length > 1 && (
              <button
                type="button"
                className={buttonClasses("secondary")}
                disabled={starting !== null}
                onClick={() => start("materials", topics.slice(0, 8).map((t) => t.id))}
              >
                {starting === "materials" ? "Building…" : "Mixed practice: your topics"}
              </button>
            )}
          </div>
          <ul className="grid gap-3 sm:grid-cols-2">
            {topics.map((topic) => (
              <li key={topic.id}>
                <Card className="flex h-full flex-col gap-3 p-5">
                  <div>
                    <h3 className="font-bold text-text">{topic.title}</h3>
                    {topic.summary && <p className="mt-1 text-sm text-text-2">{topic.summary}</p>}
                    <p className="mt-1 text-xs text-muted">
                      {topic.problems} checked {topic.problems === 1 ? "problem" : "problems"}
                      {topic.sources.length > 0 ? ` · from ${topic.sources.join(", ")}` : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    className={buttonClasses("primary", "mt-auto self-start")}
                    disabled={starting !== null}
                    onClick={() => start(topic.id, [topic.id])}
                    aria-label={`Practice ${topic.title.toLowerCase()}`}
                  >
                    {starting === topic.id ? "Building…" : "Practice"}
                  </button>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!catalog.data ? (
        catalog.error ? <p role="alert">{catalog.error}</p> : <Spinner label="Loading skills" />
      ) : (
        catalog.data.courses.map((course) => (
          <section key={course.id} aria-labelledby={`course-${course.id}`} className="flex flex-col gap-4">
            <h2 id={`course-${course.id}`} className="text-lg font-bold">
              {course.title}
            </h2>
            {course.units.map((unit) => (
              <div key={unit.id} className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-base font-semibold text-text-2">{unit.title}</h3>
                  <button
                    type="button"
                    className={buttonClasses("secondary")}
                    disabled={starting !== null}
                    onClick={() => start(unit.id, unit.skills.map((s) => s.id))}
                  >
                    {starting === unit.id ? "Building…" : `Mixed practice: ${unit.title.toLowerCase()}`}
                  </button>
                </div>
                <ul className="grid gap-3 sm:grid-cols-2">
                  {unit.skills.map((skill) => (
                    <li key={skill.id}>
                      <Card className="flex h-full flex-col gap-3 p-5">
                        <div>
                          <h4 className="font-bold text-text">{skill.title}</h4>
                          <p className="mt-1 text-sm text-text-2">{skill.summary}</p>
                        </div>
                        <div className="overflow-x-auto rounded-lg bg-raised px-3 py-2 text-text">
                          <Tex latex={skill.formula.latex} />
                        </div>
                        <button
                          type="button"
                          className={buttonClasses("primary", "mt-auto self-start")}
                          disabled={starting !== null}
                          onClick={() => start(skill.id, [skill.id])}
                          aria-label={`Practice ${skill.title.toLowerCase()}`}
                        >
                          {starting === skill.id ? "Building…" : "Practice"}
                        </button>
                      </Card>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        ))
      )}
      <p className="text-sm text-muted">
        Looking for your history? <Link href="/progress" className="text-accent-light underline-offset-4 hover:underline">See progress</Link>.
      </p>
    </div>
  );
}
