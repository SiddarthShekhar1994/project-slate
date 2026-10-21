import type { Metadata } from "next";
import { PracticeHome } from "@/components/practice/PracticeHome";

export const metadata: Metadata = { title: "Practice" };

export default function PracticePage() {
  return <PracticeHome />;
}
