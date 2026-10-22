"use client";

import { useEffect } from "react";
import { ResumeCard } from "@/components/library/ResumeCard";
import { UploadZone } from "@/components/library/UploadZone";
import { Card } from "@/components/shared/ui/Card";
import { Spinner, SpinnerIcon } from "@/components/shared/ui/Spinner";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useTopics } from "@/lib/topics";
import type { SourceView } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { AddTopic } from "./AddTopic";
import { TopicTile } from "./TopicTile";

const isReading = (s: SourceView) => s.status === "processing" || s.reading?.status === "pending";

/**
 * The dashboard: upload a study guide or type a topic, and every topic gets
 * its own lesson, problems and worksheets.
 */
export function DashboardHome() {
  const { user } = useSession();
  const { dashboard, error, refresh } = useTopics();
  const recent = useApi(() => api.worksheets());
  const lessons = useApi(() => api.lessons());
  const library = useApi(() => api.sources());
  const reading = (library.data?.sources ?? []).filter(isReading);

  // While an upload is being read, check back every two seconds. When one
  // finishes, its topics appear (and Slate starts writing their lessons).
  const setLibrary = library.setData;
  const readingCount = reading.length;
  useEffect(() => {
    if (!readingCount) return;
    const timer = window.setInterval(() => {
      api
        .sources()
        .then((next) => {
          setLibrary(next);
          if (next.sources.filter(isReading).length < readingCount) void refresh();
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [readingCount, setLibrary, refresh]);

  const topics = dashboard?.topics ?? [];
  const openSheet = recent.data?.worksheets.find((w) => !w.completed_at) ?? null;
  const openLesson =
    lessons.data?.lessons
      .filter((l) => l.last_opened && l.resume_step < l.steps - 1)
      .sort((a, b) => Date.parse(b.last_opened ?? "") - Date.parse(a.last_opened ?? ""))[0] ?? null;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8">
      <header>
        <p className="text-sm font-semibold text-accent-tint-text">Dashboard</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
          {user ? `Welcome back, ${user.display_name}` : "Dashboard"}
        </h1>
        <p className="mt-2 max-w-2xl text-text-2">
          Every topic you&apos;re studying gets its own lesson, problems and worksheets. Upload a study guide and Slate
          finds the topics in it, or type in whatever you&apos;re stuck on.
        </p>
      </header>

      {(openSheet || openLesson) && <ResumeCard worksheet={openSheet} lesson={openLesson} />}

      <div className="grid gap-6 lg:grid-cols-2">
        <AddTopic
          suggestions={dashboard?.suggestions ?? []}
          claude={dashboard?.claude ?? false}
          onAdded={() => void refresh()}
        />
        {library.data && (
          <UploadZone
            kinds={library.data.kinds}
            title="Upload a study guide"
            blurb="A review sheet, past exam, slides or notes. Slate finds every topic in it and builds a lesson, problems and worksheets for each."
            onUploaded={(source) =>
              setLibrary((prev) => (prev ? { ...prev, sources: [source, ...prev.sources] } : prev))
            }
          />
        )}
      </div>

      {reading.length > 0 && (
        <Card className="flex items-center gap-3 px-5 py-4" aria-live="polite">
          <SpinnerIcon />
          <p className="text-sm text-text-2">
            Reading {reading.map((s) => s.title).join(", ")}. Its topics show up here when Slate has gone through
            every problem.
          </p>
        </Card>
      )}

      <section aria-labelledby="topics-heading" className="flex flex-col gap-4">
        <h2 id="topics-heading" className="text-lg font-bold">
          Your topics
        </h2>
        {!dashboard ? (
          error ? (
            <p role="alert" className="text-warning">
              {error}
            </p>
          ) : (
            <Spinner label="Loading your topics" />
          )
        ) : topics.length === 0 ? (
          <Card className="px-5 py-6 text-text-2">
            No topics yet. Upload a study guide above, or type a topic you want to learn.
          </Card>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {topics.map((topic) => (
              <li key={topic.id}>
                <TopicTile topic={topic} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
