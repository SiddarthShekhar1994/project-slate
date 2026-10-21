import type { Metadata } from "next";
import { ExamRunner } from "@/components/progress/ExamRunner";

export const metadata: Metadata = { title: "Practice exam" };

export default async function ExamPage({ params }: PageProps<"/exam/[examId]">) {
  const { examId } = await params;
  return <ExamRunner examId={examId} />;
}
