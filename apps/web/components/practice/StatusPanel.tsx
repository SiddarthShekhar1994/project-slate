"use client";

import { StatusPill } from "@/components/shared/ui/StatusPill";
import type { WorksheetItem, WorksheetStats } from "@/lib/types";

type Props = {
  items: WorksheetItem[];
  stats: WorksheetStats;
  selected: number;
  onSelect: (position: number) => void;
};

/** Per-problem status and the running miss count. */
export function StatusPanel({ items, stats, selected, onSelect }: Props) {
  const cleared = stats.first_try + stats.after_retry;
  return (
    <aside aria-label="Worksheet progress" className="flex flex-col gap-4">
      <div>
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-text">Progress</h2>
          <span className="text-sm text-text-2">
            {cleared} of {stats.total} cleared
          </span>
        </div>
        <div
          className="mt-2 h-2 overflow-hidden rounded-full bg-raised"
          role="progressbar"
          aria-label="Problems cleared"
          aria-valuemin={0}
          aria-valuemax={stats.total}
          aria-valuenow={cleared}
        >
          <div
            className="h-full rounded-full bg-success transition-[width] duration-500"
            style={{ width: `${stats.total ? (cleared / stats.total) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* On narrow screens the "All problems" list carries per-problem status. */}
      <ol className="hidden flex-col gap-1 lg:flex">
        {items.map((item) => {
          const active = item.position === selected;
          return (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => onSelect(item.position)}
                aria-current={active ? "step" : undefined}
                className={`flex min-h-11 w-full items-center gap-3 rounded-[10px] px-3 py-2 text-left text-sm transition-colors ${
                  active ? "bg-raised ring-1 ring-accent-light/50" : "hover:bg-hover"
                }`}
              >
                <span className="w-6 shrink-0 font-semibold text-text-2">{item.position + 1}</span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-text">{item.skill.title}</span>
                  <span className="text-xs text-muted">{item.difficulty_label}</span>
                </span>
                <span className="flex flex-col items-end gap-1">
                  <StatusPill status={item.status} />
                  {item.misses > 0 && (
                    <span className="text-xs text-warning">
                      {item.misses} {item.misses === 1 ? "miss" : "misses"}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      <dl className="grid grid-cols-3 gap-2 rounded-[10px] border border-border bg-raised p-3 text-center">
        <div>
          <dt className="text-xs text-muted">First try</dt>
          <dd className="text-lg font-bold text-success">{stats.first_try}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">After retry</dt>
          <dd className="text-lg font-bold text-accent-tint-text">{stats.after_retry}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Misses</dt>
          <dd className="text-lg font-bold text-warning">{stats.misses}</dd>
        </div>
      </dl>
    </aside>
  );
}
