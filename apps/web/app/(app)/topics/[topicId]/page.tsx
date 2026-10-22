import type { Metadata } from "next";
import { Suspense } from "react";
import { TopicPage } from "@/components/topic/TopicPage";
import { Spinner } from "@/components/shared/ui/Spinner";

export const metadata: Metadata = { title: "Topic" };

export default async function Page({ params }: PageProps<"/topics/[topicId]">) {
  const { topicId } = await params;
  return (
    <Suspense fallback={<Spinner label="Loading topic" />}>
      <TopicPage topicId={decodeURIComponent(topicId)} />
    </Suspense>
  );
}
