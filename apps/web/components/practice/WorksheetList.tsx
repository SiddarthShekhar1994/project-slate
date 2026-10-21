import Link from "next/link";
import type { WorksheetSummary } from "@/lib/types";

const when = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export function WorksheetList({ worksheets }: { worksheets: WorksheetSummary[] }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {worksheets.map((w) => {
        const cleared = w.stats.first_try + w.stats.after_retry;
        return (
          <li key={w.id}>
            <Link
              href={`/practice/${w.id}`}
              className="flex min-h-11 flex-col gap-2 rounded-[14px] border border-border bg-card p-4 transition-colors hover:bg-hover"
            >
              <span className="flex items-center justify-between gap-2">
                <span className="truncate font-semibold text-text">{w.title}</span>
                <span className="shrink-0 text-xs text-muted">{when(w.updated_at)}</span>
              </span>
              <span className="text-sm text-text-2">
                {w.completed_at ? "Complete" : `${cleared} of ${w.stats.total} cleared`}
                {w.stats.misses > 0 ? `, ${w.stats.misses} ${w.stats.misses === 1 ? "miss" : "misses"}` : ""}
              </span>
              <span aria-hidden className="h-1.5 overflow-hidden rounded-full bg-raised">
                <span
                  className="block h-full rounded-full bg-success"
                  style={{ width: `${w.stats.total ? (cleared / w.stats.total) * 100 : 0}%` }}
                />
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
