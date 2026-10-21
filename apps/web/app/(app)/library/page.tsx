import type { Metadata } from "next";
import { LibraryHome } from "@/components/library/LibraryHome";

export const metadata: Metadata = { title: "Library" };

export default function LibraryPage() {
  return <LibraryHome />;
}
