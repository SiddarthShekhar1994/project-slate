import Link from "next/link";
import { buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { topicHref } from "@/lib/topics";
import type { BuildState, MasteryStatus, TopicCard } from "@/lib/types";

export const MASTERY_TEXT: Record<MasteryStatus, string> = {
  new: "Not started",
  learning: "Learning",
  practiced: "Practiced",
  mastered: "Mastered",
};

export const MASTERY_BAR: Record<MasteryStatus, string> = {
  new: "bg-border",
  learning: "bg-warning",
  practiced: "bg-accent-light",
  mastered: "bg-success",
};

const LESSON_TEXT: Record<BuildState, string> = {
  done: "Lesson ready",
  writing: "Writing the lesson…",
  failed: "Lesson didn't work out",
  none: "No lesson yet",
  needs_key: "Lesson needs a Claude key",
};

export function practiceText(topic: Pick<TopicCard, "builtin" | "problems" | "practice">): string {
  if (topic.practice === "writing") return topic.problems ? "Writing more problems…" : "Writing problems…";
  if (topic.builtin) return "Endless problems";
  if (topic.problems > 0) return `${topic.problems} checked ${topic.problems === 1 ? "problem" : "problems"}`;
  return {
    done: "No problems Slate can check",
    writing: "Writing problems…",
    failed: "Problems didn't work out",
    none: "No problems yet",
    needs_key: "Problems need a Claude key",
  }[topic.practice];
}

function Chip({ state, children }: { state: BuildState | "ready"; children: string }) {
  const tone =
    state === "writing"
      ? "border-accent-light/40 bg-accent-tint text-accent-tint-text"
      : state === "failed"
        ? "border-warning/40 bg-warning-bg text-warning"
        : state === "done" || state === "ready"
          ? "border-success/40 bg-success-bg text-success"
          : "border-border bg-raised text-text-2";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${tone}`}>
      {state === "writing" && (
        <span
          aria-hidden
          className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none"
        />
      )}
      {children}
    </span>
  );
}

/** One topic on the dashboard: how far along the student is, and what Slate has ready for it. */
export function TopicTile({ topic }: { topic: TopicCard }) {
  const value = topic.mastery === null ? 0 : Math.round(topic.mastery * 100);
  const practiceState =
    topic.practice !== "writing" && (topic.builtin || topic.problems > 0) ? "ready" : topic.practice;
  const lessonText = topic.lesson === "writing" && topic.lessons > 0 ? "Writing a new lesson…" : LESSON_TEXT[topic.lesson];
  const headingId = `topic-${topic.id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  return (
    <Card as="article" aria-labelledby={headingId} className="flex h-full flex-col gap-3 p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 id={headingId} className="text-base font-bold text-text">
          <Link href={topicHref(topic.id)} className="underline-offset-4 hover:underline">
            {topic.title}
          </Link>
        </h3>
        <span className="shrink-0 text-xs text-muted">
          {MASTERY_TEXT[topic.status]}
          {topic.mastery !== null && ` · ${value}%`}
        </span>
      </div>
      {topic.summary && <p className="line-clamp-2 text-sm text-text-2">{topic.summary}</p>}
      <div className="flex flex-wrap gap-2">
        <Chip state={topic.lesson}>{lessonText}</Chip>
        <Chip state={practiceState}>{practiceText(topic)}</Chip>
      </div>
      <div
        role="meter"
        aria-label={`${topic.title} mastery`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-valuetext={topic.mastery === null ? "Not started" : `${value}%, ${MASTERY_TEXT[topic.status]}`}
        className="h-1.5 overflow-hidden rounded-full bg-raised"
      >
        <div className={`h-full rounded-full ${MASTERY_BAR[topic.status]}`} style={{ width: `${value}%` }} />
      </div>
      {topic.sources.length > 0 ? (
        <p className="text-xs text-muted">From {topic.sources.map((s) => s.title).join(", ")}</p>
      ) : (
        <p className="text-xs text-muted">{topic.builtin ? "Built into Slate" : "Added by you"}</p>
      )}
      <div className="mt-auto flex flex-wrap gap-2 pt-1">
        <Link href={topicHref(topic.id, "lesson")} className={buttonClasses("secondary")}>
          Lesson<span className="sr-only">: {topic.title}</span>
        </Link>
        <Link href={topicHref(topic.id, "problems")} className={buttonClasses("ghost")}>
          Problems<span className="sr-only">: {topic.title}</span>
        </Link>
        <Link href={topicHref(topic.id, "worksheets")} className={buttonClasses("ghost")}>
          Worksheets<span className="sr-only">: {topic.title}</span>
        </Link>
      </div>
    </Card>
  );
}
