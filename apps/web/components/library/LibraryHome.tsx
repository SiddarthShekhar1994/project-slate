"use client";

import { Spinner } from "@/components/shared/ui/Spinner";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";
import { ResumeCard } from "./ResumeCard";

/** Library home. Source uploads arrive in stage 4; for now it resumes lessons and practice. */
export function LibraryHome() {
  const { user } = useSession();
  const recent = useApi(() => api.worksheets());
  const lessons = useApi(() => api.lessons());

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8">
      <header>
        <p className="text-sm font-semibold text-accent-tint-text">Library</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
          {user ? `Welcome back, ${user.display_name}` : "Library"}
        </h1>
      </header>

      <section aria-labelledby="pickup-heading">
        <h2 id="pickup-heading" className="sr-only">
          Pick up where you left off
        </h2>
        {!recent.data || !lessons.data ? (
          <Spinner />
        ) : (
          <ResumeCard
            worksheet={recent.data.worksheets.find((w) => !w.completed_at) ?? null}
            lesson={
              lessons.data.lessons
                .filter((l) => l.last_opened && l.resume_step < l.steps - 1)
                .sort((a, b) => Date.parse(b.last_opened ?? "") - Date.parse(a.last_opened ?? ""))[0] ?? null
            }
          />
        )}
      </section>
    </div>
  );
}
