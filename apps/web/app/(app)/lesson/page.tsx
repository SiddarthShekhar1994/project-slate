import type { Metadata } from "next";
import { Suspense } from "react";
import { LessonList } from "@/components/lesson/LessonList";

export const metadata: Metadata = { title: "Lessons" };

export default function Page() {
  return (
    <Suspense>
      <LessonList />
    </Suspense>
  );
}
