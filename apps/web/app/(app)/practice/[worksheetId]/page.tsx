import type { Metadata } from "next";
import { Suspense } from "react";
import { PracticeView } from "@/components/practice/PracticeView";
import { Spinner } from "@/components/shared/ui/Spinner";

export const metadata: Metadata = { title: "Practice" };

export default async function WorksheetPage({ params }: PageProps<"/practice/[worksheetId]">) {
  const { worksheetId } = await params;
  return (
    <Suspense fallback={<Spinner label="Loading worksheet" />}>
      <PracticeView worksheetId={worksheetId} />
    </Suspense>
  );
}
