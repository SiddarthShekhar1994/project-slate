import type { Metadata } from "next";
import { Suspense } from "react";
import { LessonPage } from "@/components/lesson/LessonPage";
import { Spinner } from "@/components/shared/ui/Spinner";

export const metadata: Metadata = { title: "Lesson" };

export default async function Page({ params }: PageProps<"/lesson/[lessonId]">) {
  const { lessonId } = await params;
  return (
    <Suspense fallback={<Spinner label="Loading lesson" />}>
      <LessonPage lessonId={lessonId} />
    </Suspense>
  );
}
