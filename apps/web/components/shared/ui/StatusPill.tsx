import type { ItemStatus } from "@/lib/types";

export const STATUS_LABELS: Record<ItemStatus, string> = {
  up_next: "Up next",
  retrying: "Retrying",
  cleared: "Cleared",
  cleared_after_retry: "Cleared after retry",
};

const STYLES: Record<ItemStatus, string> = {
  up_next: "bg-raised text-text-2 border-border",
  retrying: "bg-warning-bg text-warning border-warning/40",
  cleared: "bg-success-bg text-success border-success/40",
  cleared_after_retry: "bg-accent-tint text-accent-tint-text border-accent-light/40",
};

export function StatusPill({ status, className = "" }: { status: ItemStatus; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ${STYLES[status]} ${className}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}
