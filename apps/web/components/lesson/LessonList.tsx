"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";

/** Lessons by skill. ``?skill=`` jumps straight into that skill's lesson. */
export function LessonList() {
  const router = useRouter();
  const search = useSearchParams();
  const { data, error } = useApi(() => api.lessons());
  const wanted = search?.get("skill");

  useEffect(() => {
    if (!data || !wanted) return;
    const match = data.lessons.find((l) => l.skill.id === wanted);
    if (match) router.replace(`/lesson/${match.id}`);
  }, [data, wanted, router]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <header>
        <p className="text-sm font-semibold text-accent-tint-text">Lessons</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Watch it worked on the board</h1>
        <p className="mt-2 max-w-2xl text-text-2">
          Each lesson writes the math step by step, narrated, and stops now and then to let you predict the next move.
        </p>
      </header>
      {error && <p role="alert" className="text-warning">{error}</p>}
      {!data ? (
        <Spinner label="Loading lessons" />
      ) : data.lessons.length === 0 ? (
        <p className="text-text-2">No lessons yet.</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {data.lessons.map((lesson) => (
            <li key={lesson.id}>
              <Card className="flex h-full flex-col gap-3 p-5">
                <div>
                  <p className="text-xs font-semibold text-muted">{lesson.skill.title}</p>
                  <h2 className="mt-1 font-bold text-text">{lesson.title}</h2>
                  <p className="mt-1 text-sm text-text-2">
                    {lesson.steps} steps · {lesson.kind === "builtin" ? "built-in" : `from ${lesson.sources} of your sources`}
                  </p>
                </div>
                <Link href={`/lesson/${lesson.id}`} className={buttonClasses("primary", "mt-auto self-start")}>
                  {lesson.resume_step > 0 ? `Resume at step ${lesson.resume_step + 1}` : "Start lesson"}
                </Link>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
