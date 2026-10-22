"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";
import { useTopics } from "@/lib/topics";
import { useApi } from "@/lib/useApi";
import { SourceList } from "./SourceList";
import { UploadZone } from "./UploadZone";

/** Sources: what the student uploaded, the topics Slate found in each, and what each was used for. */
export function LibraryHome() {
  const { refresh } = useTopics();
  const library = useApi(() => api.sources());
  const sources = library.data?.sources ?? [];
  const processing = sources.filter((s) => s.status === "processing" || s.reading?.status === "pending").length;

  // While anything is still being read, refresh the list every two seconds;
  // when a reading finishes, its topics join the sidebar.
  const setLibrary = library.setData;
  useEffect(() => {
    if (!processing) return;
    const timer = window.setInterval(() => {
      api
        .sources()
        .then((next) => {
          setLibrary(next);
          const still = next.sources.filter((s) => s.status === "processing" || s.reading?.status === "pending");
          if (still.length < processing) void refresh();
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [processing, setLibrary, refresh]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8">
      <header>
        <p className="text-sm font-semibold text-accent-tint-text">Sources</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Your course materials</h1>
        <p className="mt-2 max-w-2xl text-text-2">
          Lessons and problems cite these. Slate reads each one for the topics and problems in it, and every topic it
          finds gets a tab of its own.
        </p>
      </header>

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
