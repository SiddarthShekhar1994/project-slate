"use client";

import { useSearchParams } from "next/navigation";
import { Spinner } from "@/components/shared/ui/Spinner";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { LessonPlayer, SPEEDS } from "./LessonPlayer";
import { LessonSidebar } from "./LessonSidebar";

export function LessonPage({ lessonId }: { lessonId: string }) {
  const search = useSearchParams();
  const { data: lesson, error } = useApi(() => api.lesson(lessonId), [lessonId]);

  if (error) {
    return (
      <p role="alert" className="rounded-[10px] border border-warning/40 bg-warning-bg px-4 py-3 text-warning">
        {error}
      </p>
    );
  }
  if (!lesson) return <Spinner label="Loading lesson" />;

  const stepParam = Number(search?.get("step"));
  const speedParam = Number(search?.get("speed"));
  const initialStep = Number.isInteger(stepParam) && stepParam >= 1 ? stepParam - 1 : lesson.resume_step;
  const initialSpeed = (SPEEDS as readonly number[]).includes(speedParam) ? speedParam : 1;
  const voiceParam = search?.get("voice");
  const initialVoice = voiceParam && lesson.tts.voices.some((v) => v.id === voiceParam) ? voiceParam : null;

  return (
    <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
      <div className="order-2 lg:order-1">
        <LessonSidebar lesson={lesson} />
      </div>
      <div className="order-1 flex min-w-0 flex-col gap-4 lg:order-2">
        <header>
          <p className="text-sm font-semibold text-accent-tint-text">Lesson · {lesson.skill.title}</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">{lesson.script.title}</h1>
          <p className="mt-1 text-sm text-text-2">{lesson.script.summary}</p>
        </header>
        <LessonPlayer
          lesson={lesson}
          initialStep={Math.min(initialStep, lesson.script.steps.length - 1)}
          initialSpeed={initialSpeed}
          initialVoice={initialVoice}
          initialCaptions={search?.get("cc") !== "0"}
        />
      </div>
    </div>
  );
}
