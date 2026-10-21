import type { Metadata } from "next";
import { Suspense } from "react";
import { FormulaSheetView } from "@/components/progress/FormulaSheetView";
import { Spinner } from "@/components/shared/ui/Spinner";

export const metadata: Metadata = { title: "Formula sheet" };

export default function Page() {
  return (
    <Suspense fallback={<Spinner label="Loading formulas" />}>
      <FormulaSheetView />
    </Suspense>
  );
}
