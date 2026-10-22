"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { LessonPlayer, SPEEDS } from "@/components/lesson/LessonPlayer";
import { Button } from "@/components/shared/ui/Button";
import { Spinner } from "@/components/shared/ui/Spinner";
import { api } from "@/lib/api";
import type { LessonSummary, TopicView } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { Notice } from "./Notice";

function lessonLabel(lesson: LessonSummary) {
  return lesson.kind === "builtin" ? `${lesson.title} (Slate's lesson)` : lesson.title;
}

/** The topic's lesson, played right here: the board, the voice, the checkpoints. */
export function LessonTab({
  view,
  busy,
  onWrite,
}: {
  view: TopicView;
  busy: boolean;
  onWrite: () => void;
}) {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const lessons = view.lessons;
  const current = lessons.find((l) => l.id === search?.get("lesson")) ?? lessons[0] ?? null;
  const { data: lesson, error } = useApi(
    () => (current ? api.lesson(current.id) : Promise.resolve(null)),
    [current?.id],
  );

  const status = (() => {
    if (view.lesson === "writing") {
      return (
        <Notice tone="working">
          Slate is writing {lessons.length ? "a new" : "the"} lesson on {view.title.toLowerCase()}. Every step&apos;s
          math is checked by SymPy before you see it, so this takes a minute or two. It appears here when it&apos;s ready.
        </Notice>
      );
    }
    if (view.lesson_error) {
      // A first lesson that didn't work out, or a new one (the old lesson still plays below).
      return (
        <Notice
          tone="warning"
          action={
            <Button variant="secondary" onClick={onWrite} disabled={busy}>
              Try again
            </Button>
          }
        >
          {lessons.length ? `The new lesson didn't work out. ${view.lesson_error}` : view.lesson_error}
        </Notice>
      );
    }
    if (lessons.length) return null;
    if (view.lesson === "needs_key") {
      return (
        <Notice>
          A lesson on this topic needs a Claude API key. Add one in{" "}
          <Link href="/settings" className="font-semibold text-accent-light underline-offset-4 hover:underline">
            Settings
          </Link>{" "}
          and Slate writes it, checked by SymPy.
        </Notice>
      );
    }
    return (
      <Notice
        action={
          <Button onClick={onWrite} disabled={busy}>
            {busy ? "Starting…" : "Write the lesson"}
          </Button>
        }
      >
        No lesson on {view.title.toLowerCase()} yet.
      </Notice>
    );
  })();

  if (!current) return status;

  const stepParam = Number(search?.get("step"));
  const speedParam = Number(search?.get("speed"));
  const voiceParam = search?.get("voice");
  return (
    <div className="flex flex-col gap-4">
      {status}
      {!lesson ? (
        error ? (
          <p role="alert" className="text-warning">
            {error}
          </p>
        ) : (
          <Spinner label="Loading the lesson" />
        )
      ) : (
        <>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-xl font-bold text-text">{lesson.script.title}</h2>
              {lesson.script.summary && <p className="mt-1 text-sm text-text-2">{lesson.script.summary}</p>}
            </div>
            {lessons.length > 1 && (
              <label className="flex items-center gap-2 text-sm text-text-2">
                Lesson
                <select
                  value={current.id}
                  onChange={(e) => {
                    const params = new URLSearchParams(search?.toString() ?? "");
                    params.set("lesson", e.target.value);
                    params.delete("step");
                    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
                  }}
                  className="min-h-11 max-w-64 rounded-[10px] border border-border bg-raised px-3 text-sm text-text"
                >
                  {lessons.map((l, i) => (
                    <option key={l.id} value={l.id}>
                      {lessonLabel(l)}
                      {l.kind === "generated" && i === 0 ? " (newest)" : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <LessonPlayer
            key={lesson.id}
            lesson={lesson}
            initialStep={Math.min(
              Number.isInteger(stepParam) && stepParam >= 1 ? stepParam - 1 : lesson.resume_step,
              lesson.script.steps.length - 1,
            )}
            initialSpeed={(SPEEDS as readonly number[]).includes(speedParam) ? speedParam : 1}
            initialVoice={voiceParam && lesson.tts.voices.some((v) => v.id === voiceParam) ? voiceParam : null}
            initialCaptions={search?.get("cc") !== "0"}
          />
          <div className="flex flex-col gap-3 text-sm text-text-2 sm:flex-row sm:items-center sm:justify-between">
            <p>
              {lesson.sources.length
                ? `Built from ${lesson.sources.map((s) => `${s.title} (${s.locator})`).join(", ")}.`
                : "Slate's lesson. Upload your notes or a study guide on this topic for one in your professor's style."}{" "}
              <Link
                href={`/lesson/${lesson.id}`}
                className="font-semibold text-accent-light underline-offset-4 hover:underline"
              >
                Open it full size
              </Link>
            </p>
            {view.lesson !== "writing" && view.lesson !== "needs_key" && (
              <Button variant="ghost" onClick={onWrite} disabled={busy}>
                {busy ? "Starting…" : "Write a new lesson"}
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
