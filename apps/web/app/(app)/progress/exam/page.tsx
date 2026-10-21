import type { Metadata } from "next";
import { Suspense } from "react";
import { ExamBuilder } from "@/components/progress/ExamBuilder";
import { Spinner } from "@/components/shared/ui/Spinner";

export const metadata: Metadata = { title: "Practice exam" };

export default function Page() {
  return (
    <Suspense fallback={<Spinner label="Loading topics" />}>
      <ExamBuilder />
    </Suspense>
  );
}
