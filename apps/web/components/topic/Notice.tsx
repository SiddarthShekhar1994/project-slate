import type { ReactNode } from "react";
import { SpinnerIcon } from "@/components/shared/ui/Spinner";

type Tone = "info" | "working" | "warning";

const TONES: Record<Tone, string> = {
  info: "border-border bg-card text-text-2",
  working: "border-accent-light/40 bg-accent-tint text-accent-tint-text",
  warning: "border-warning/40 bg-warning-bg text-warning",
};

/** A status line on a topic's page: what Slate is writing, what went wrong, what to do next. */
export function Notice({ tone = "info", children, action }: { tone?: Tone; children: ReactNode; action?: ReactNode }) {
  return (
    <div
      role={tone === "warning" ? "alert" : "status"}
      className={`flex flex-col gap-3 rounded-[14px] border px-5 py-4 text-sm sm:flex-row sm:items-center sm:justify-between ${TONES[tone]}`}
    >
      <div className="flex items-start gap-3">
        {tone === "working" && <SpinnerIcon className="mt-0.5" />}
        <div>{children}</div>
      </div>
      {action}
    </div>
  );
}
