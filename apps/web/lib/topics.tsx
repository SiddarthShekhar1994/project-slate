"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "./api";
import type { Dashboard, TopicCard } from "./types";

type TopicsState = {
  dashboard: Dashboard | null;
  error: string | null;
  refresh: () => Promise<void>;
};

const TopicsContext = createContext<TopicsState>({ dashboard: null, error: null, refresh: async () => undefined });

const POLL_MS = 4000;

export const isWriting = (topic: TopicCard) => topic.lesson === "writing" || topic.practice === "writing";

/**
 * The student's topics, shared by the sidebar and the pages. While Slate is
 * writing a lesson or problems in the background it checks back every few
 * seconds, so a topic's tab fills in on its own.
 */
export function TopicsProvider({ children }: { children: ReactNode }) {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const show = useCallback((next: Promise<Dashboard>, live: () => boolean = () => true) => {
    return next
      .then((value) => {
        if (!live()) return;
        setDashboard(value);
        setError(null);
      })
      .catch((e) => {
        if (live()) setError(e instanceof ApiError ? e.message : "Couldn't load your topics.");
      });
  }, []);
  const refresh = useCallback(() => show(api.topics()), [show]);

  useEffect(() => {
    let live = true;
    void show(api.topics(), () => live);
    return () => {
      live = false;
    };
  }, [show]);

  const writing = dashboard?.topics.some(isWriting) ?? false;
  useEffect(() => {
    if (!writing) return;
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [writing, refresh]);

  const value = useMemo(() => ({ dashboard, error, refresh }), [dashboard, error, refresh]);
  return <TopicsContext.Provider value={value}>{children}</TopicsContext.Provider>;
}

export const useTopics = () => useContext(TopicsContext);

export const topicHref = (id: string, tab?: "lesson" | "problems" | "worksheets") =>
  `/topics/${encodeURIComponent(id)}${tab ? `?tab=${tab}` : ""}`;
