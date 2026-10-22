"use client";

import { Spinner } from "@/components/shared/ui/Spinner";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useEffect } from "react";
import { useApi } from "@/lib/useApi";
import { ResumeCard } from "./ResumeCard";
import { SourceList } from "./SourceList";
import { UploadZone } from "./UploadZone";

/** Library home: pick up where you left off, add course materials, and see what each was used for. */
export function LibraryHome() {
  const { user } = useSession();
  const recent = useApi(() => api.worksheets());
  const lessons = useApi(() => api.lessons());
  const library = useApi(() => api.sources());
  const sources = library.data?.sources ?? [];
  const processing = sources.some((s) => s.status === "processing" || s.reading?.status === "pending");

  // While anything is still being read, refresh the list every two seconds.
  const setLibrary = library.setData;
  useEffect(() => {
    if (!processing) return;
    const timer = window.setInterval(() => {
      api.sources().then(setLibrary).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [processing, setLibrary]);

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

      {library.data && (
        <>
          <UploadZone
            kinds={library.data.kinds}
            onUploaded={(source) =>
              setLibrary((prev) => (prev ? { ...prev, sources: [source, ...prev.sources] } : prev))
            }
          />
          <section aria-labelledby="sources-heading" className="flex flex-col gap-3">
            <h2 id="sources-heading" className="text-lg font-bold">
              Your sources
            </h2>
            <SourceList
              sources={sources}
              onChange={(next) => setLibrary((prev) => (prev ? { ...prev, sources: next } : prev))}
            />
          </section>
        </>
      )}
      {library.error && <p role="alert" className="text-warning">{library.error}</p>}
    </div>
  );
}
