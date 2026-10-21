"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { ApiError, api } from "@/lib/api";
import { useApi } from "@/lib/useApi";

/** Lessons by skill. ``?skill=`` jumps straight into that skill's lesson. */
export function LessonList() {
  const router = useRouter();
  const search = useSearchParams();
  const { data, error } = useApi(() => api.lessons());
  const library = useApi(() => api.sources());
  const wanted = search?.get("skill");
  const [generating, setGenerating] = useState<string | null>(null);
  const [genError, setGenError] = useState<string | null>(null);

  // Skills the student's ready sources cover, strongest first, one entry each.
  const covered = new Map<string, { title: string; score: number }>();
  for (const source of library.data?.sources ?? []) {
    if (source.status !== "ready") continue;
    for (const skill of source.skills) {
      const seen = covered.get(skill.id);
      if (!seen || seen.score < skill.score) covered.set(skill.id, { title: skill.title, score: skill.score });
    }
  }

  async function generate(skillId: string) {
    setGenerating(skillId);
    setGenError(null);
    try {
      const lesson = await api.generateLesson(skillId);
      router.push(`/lesson/${lesson.id}`);
    } catch (e) {
      setGenError(e instanceof ApiError ? e.message : "Couldn't write that lesson. Try again.");
      setGenerating(null);
    }
  }

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

      {covered.size > 0 && (
        <section aria-labelledby="from-sources" className="flex flex-col gap-3 rounded-[14px] border border-accent-light/30 bg-accent-tint p-5">
          <div>
            <h2 id="from-sources" className="font-bold text-text">
              From your sources
            </h2>
            <p className="mt-1 text-sm text-text-2">
              Slate writes the lesson from your materials, in your professor&apos;s notation, and cites the slides it
              used. Every step&apos;s math is checked before you see it.
            </p>
          </div>
          <ul className="flex flex-wrap gap-2">
            {[...covered.entries()]
              .sort((a, b) => b[1].score - a[1].score)
              .map(([skillId, skill]) => (
                <li key={skillId}>
                  <button
                    type="button"
                    disabled={generating !== null}
                    onClick={() => generate(skillId)}
                    className="min-h-11 rounded-[10px] bg-accent px-4 text-sm font-semibold text-white hover:bg-[#3557f0] disabled:bg-raised disabled:text-muted"
                  >
                    {generating === skillId ? "Writing the lesson…" : `${skill.title} lesson`}
                  </button>
                </li>
              ))}
          </ul>
          <div aria-live="polite">
            {generating && (
              <p className="text-sm text-text-2">This can take up to a minute while each step is checked.</p>
            )}
            {genError && (
              <p role="alert" className="text-sm text-warning">
                {genError}
              </p>
            )}
          </div>
        </section>
      )}
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
