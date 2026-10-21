import type { Metadata } from "next";
import { ProgressHome } from "@/components/progress/ProgressHome";

export const metadata: Metadata = { title: "Progress" };

export default function Page() {
  return <ProgressHome />;
}
