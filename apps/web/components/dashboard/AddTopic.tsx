"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { ApiError, api } from "@/lib/api";
import { topicHref } from "@/lib/topics";
import type { TopicCard, TopicSuggestion } from "@/lib/types";

const MAX_SUGGESTIONS = 10;

/** Type any topic (or pick one) and it gets its own tab with a lesson, problems and worksheets. */
export function AddTopic({
  suggestions,
  claude,
  onAdded,
}: {
  suggestions: TopicSuggestion[];
  claude: boolean;
  onAdded: (topic: TopicCard) => void;
}) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<TopicCard | null>(null);

  async function add(topicName: string) {
    setBusy(topicName);
    setError(null);
    setAdded(null);
    try {
      const topic = await api.addTopic(topicName);
      setAdded(topic);
      setName("");
      onAdded(topic);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't add that topic. Try again.");
    } finally {
      setBusy(null);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (name.trim()) void add(name.trim());
  }

  const writing = added && (added.lesson === "writing" || added.practice === "writing");
  return (
    <section id="add-topic" aria-labelledby="add-topic-heading" className="flex scroll-mt-24 flex-col gap-3">
      <h2 id="add-topic-heading" className="text-lg font-bold">
        Learn a topic
      </h2>
      <Card className="flex flex-1 flex-col gap-4 p-5">
        <form onSubmit={submit} className="flex flex-col gap-2">
          <label htmlFor="topic-name" className="text-sm font-semibold text-text-2">
            What are you working on?
          </label>
          <div className="flex gap-2">
            <input
              id="topic-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              autoComplete="off"
              placeholder="Related rates, L'Hôpital's rule, optimization…"
              className="min-h-11 min-w-0 flex-1 rounded-[10px] border border-border bg-raised px-3 text-text placeholder:text-muted"
            />
            <Button type="submit" disabled={!name.trim() || busy !== null}>
              {busy !== null && busy === name.trim() ? "Adding…" : "Add"}
            </Button>
          </div>
        </form>
        <div aria-live="polite" className="text-sm">
          {error && (
            <p role="alert" className="text-warning">
              {error}
            </p>
          )}
          {added && (
            <p className="text-text-2">
              Added{" "}
              <Link href={topicHref(added.id)} className="font-semibold text-accent-light underline-offset-4 hover:underline">
                {added.title}
              </Link>
              .{" "}
              {writing
                ? "Slate is writing its lesson and problems and checking the math. It takes a minute or two."
                : "Its lesson and problems are ready."}
            </p>
          )}
        </div>
        {suggestions.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-text-2">Or pick one</p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {suggestions.slice(0, MAX_SUGGESTIONS).map((s) => (
                <li key={s.title}>
                  <button
                    type="button"
                    onClick={() => void add(s.title)}
                    disabled={busy !== null}
                    title={s.summary}
                    className="min-h-11 rounded-full border border-border bg-raised px-4 text-sm text-text hover:bg-hover disabled:text-muted"
                  >
                    {busy === s.title ? "Adding…" : s.title}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {!claude && (
          <p className="text-xs text-muted">
            Built-in topics work right away. For anything else Slate needs a Claude API key, which you can add in
            Settings.
          </p>
        )}
      </Card>
    </section>
  );
}
