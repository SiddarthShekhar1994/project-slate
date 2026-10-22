"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { MASTERY_BAR, MASTERY_TEXT } from "@/components/dashboard/TopicTile";
import { Tex } from "@/components/shared/math/Tex";
import { Button } from "@/components/shared/ui/Button";
import { Icon } from "@/components/shared/ui/Icon";
import { Spinner } from "@/components/shared/ui/Spinner";
import { ApiError, api } from "@/lib/api";
import { topicHref, useTopics } from "@/lib/topics";
import type { TopicView } from "@/lib/types";
import { replaceQuery } from "@/lib/urlState";
import { LessonTab } from "./LessonTab";
import { ProblemsTab } from "./ProblemsTab";
import { WorksheetsTab } from "./WorksheetsTab";

const TABS = [
  { id: "lesson", label: "Lesson" },
  { id: "problems", label: "Problems" },
  { id: "worksheets", label: "Worksheets" },
] as const;

type Tab = (typeof TABS)[number]["id"];

/** One topic, as its own tab: a lesson that teaches it, its problems, and worksheets. URL: ?tab=&lesson=&step= */
export function TopicPage({ topicId }: { topicId: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const { dashboard, refresh } = useTopics();
  const [view, setView] = useState<TopicView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const tab: Tab = TABS.some((t) => t.id === search?.get("tab")) ? (search?.get("tab") as Tab) : "lesson";

  const show = useCallback(
    (live: () => boolean = () => true) =>
      api
        .topic(topicId)
        .then((value) => {
          if (!live()) return;
          setView(value);
          setError(null);
        })
        .catch((e) => {
          if (live()) setError(e instanceof ApiError ? e.message : "Couldn't load this topic.");
        }),
    [topicId],
  );
  const load = useCallback(() => show(), [show]);

  // Load now, and again whenever the dashboard sees this topic's lesson or problems change.
  const card = dashboard?.topics.find((t) => t.id === topicId);
  const cardKey = card ? [card.title, card.lesson, card.practice, card.lessons, card.problems].join("|") : "";
  useEffect(() => {
    let live = true;
    void show(() => live);
    return () => {
      live = false;
    };
  }, [show, cardKey]);

  async function act(key: string, run: () => Promise<unknown>) {
    setBusy(key);
    setActionError(null);
    try {
      await run();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "That didn't work. Try again.");
    } finally {
      setBusy(null);
    }
  }

  const practice = (key: string, options: { count?: number; problem_ids?: string[] }) =>
    act(key, async () => {
      const sheet = await api.practiceTopic(topicId, options);
      router.push(`/practice/${sheet.id}`);
    });

  const write = (key: string, start: () => Promise<unknown>) =>
    act(key, async () => {
      await start();
      await Promise.all([refresh(), load()]);
    });

  if (!view) {
    return error ? (
      <div className="mx-auto max-w-3xl">
        <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-warning">
          {error}
        </p>
        <Link href="/dashboard" className="mt-4 inline-block text-accent-light underline-offset-4 hover:underline">
          Back to the dashboard
        </Link>
      </div>
    ) : (
      <Spinner label="Loading topic" />
    );
  }

  const value = view.mastery === null ? 0 : Math.round(view.mastery * 100);
  const counts: Partial<Record<Tab, number>> = {
    problems: view.problem_list.filter((p) => p.status === "ready").length || undefined,
    worksheets: view.worksheets.length || undefined,
  };
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <header className="flex flex-col gap-4">
        <nav aria-label="Breadcrumb" className="text-sm">
          <Link href="/dashboard" className="text-accent-tint-text underline-offset-4 hover:underline">
            Dashboard
          </Link>
          <span aria-hidden className="text-muted">
            {" "}
            /{" "}
          </span>
          <span className="text-text-2" aria-current="page">
            {view.title}
          </span>
        </nav>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{view.title}</h1>
            {view.summary && <p className="mt-1 max-w-3xl text-text-2">{view.summary}</p>}
            <p className="mt-2 text-sm text-muted">
              {view.sources.length
                ? `From ${view.sources.map((s) => s.title).join(", ")}`
                : view.builtin
                  ? "Built into Slate"
                  : "Added by you"}
            </p>
            {view.formula && (
              <div className="mt-3 inline-flex max-w-full items-center gap-3 overflow-x-auto rounded-[10px] bg-raised px-3 py-2">
                <span className="text-xs font-semibold text-muted">{view.formula.title}</span>
                <Tex latex={view.formula.latex} />
              </div>
            )}
          </div>
          <div className="flex shrink-0 flex-col gap-3 lg:w-64">
            <div>
              <p className="text-sm text-text-2">
                {MASTERY_TEXT[view.status]}
                {view.mastery !== null && <span className="text-muted"> · {value}%</span>}
              </p>
              <div
                role="meter"
                aria-label={`${view.title} mastery`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={value}
                aria-valuetext={view.mastery === null ? "Not started" : `${value}%, ${MASTERY_TEXT[view.status]}`}
                className="mt-1.5 h-2 overflow-hidden rounded-full bg-raised"
              >
                <div className={`h-full rounded-full ${MASTERY_BAR[view.status]}`} style={{ width: `${value}%` }} />
              </div>
            </div>
            {view.on_dashboard ? (
              <Button
                variant="ghost"
                className="self-start"
                disabled={busy !== null}
                onClick={() => {
                  if (!window.confirm(`Take ${view.title} off your dashboard? Your progress on it stays.`)) return;
                  void act("remove", async () => {
                    await api.removeTopic(topicId);
                    await refresh();
                    router.push("/dashboard");
                  });
                }}
              >
                <Icon name="trash" size={18} />
                Remove from dashboard
              </Button>
            ) : (
              <Button
                className="self-start"
                disabled={busy !== null}
                onClick={() => void write("add", () => api.addTopic(view.title))}
              >
                <Icon name="plus" size={18} />
                Add to your topics
              </Button>
            )}
          </div>
        </div>
      </header>

      <nav aria-label={`${view.title} sections`} className="border-b border-border">
        <ul className="-mb-px flex gap-1 overflow-x-auto">
          {TABS.map((t) => {
            const current = tab === t.id;
            return (
              <li key={t.id}>
                <Link
                  href={topicHref(topicId, t.id)}
                  replace
                  scroll={false}
                  aria-current={current ? "page" : undefined}
                  className={`flex min-h-11 items-center gap-2 border-b-2 px-4 text-sm font-semibold transition-colors ${
                    current ? "border-accent-light text-text" : "border-transparent text-text-2 hover:text-text"
                  }`}
                >
                  {t.label}
                  {counts[t.id] !== undefined && (
                    <span className="rounded-full bg-raised px-2 py-0.5 text-xs text-text-2">{counts[t.id]}</span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {actionError && (
        <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
          {actionError}
        </p>
      )}

      {tab === "lesson" && (
        <LessonTab
          view={view}
          busy={busy === "lesson"}
          onWrite={() =>
            void write("lesson", () => {
              // The new lesson starts at its first step when it arrives.
              replaceQuery({ lesson: null, step: null });
              return api.writeLesson(topicId);
            })
          }
        />
      )}
      {tab === "problems" && (
        <ProblemsTab
          view={view}
          busy={busy}
          claude={dashboard?.claude ?? false}
          onPractice={() => void practice("all", { count: view.builtin ? 8 : Math.min(12, Math.max(view.problems, 1)) })}
          onTry={(id) => void practice(id, { problem_ids: [id] })}
          onWriteMore={() => void write("more", () => api.writeProblems(topicId))}
        />
      )}
      {tab === "worksheets" && <WorksheetsTab view={view} busy={busy} onStart={(count) => void practice("sheet", { count })} />}
    </div>
  );
}
