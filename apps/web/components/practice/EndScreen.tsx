"use client";

import Link from "next/link";
import { buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import type { Worksheet } from "@/lib/types";

type Props = { worksheet: Worksheet; onRestart: () => void; restarting?: boolean };

/** Shown when every problem on the worksheet is cleared. */
export function EndScreen({ worksheet, onRestart, restarting }: Props) {
  const { stats } = worksheet;
  const missed = worksheet.items.filter((i) => i.misses > 0);
  return (
    <Card className="flex flex-col gap-6 p-6 sm:p-8">
      <div>
        <p className="text-sm font-semibold text-success">Worksheet complete</p>
        <h2 className="mt-1 text-2xl font-bold text-text">{worksheet.title}</h2>
        <p className="mt-2 text-text-2">
          {stats.misses === 0
            ? "Every problem right on the first try."
            : `You worked through ${stats.misses} ${stats.misses === 1 ? "miss" : "misses"} and cleared every problem.`}
        </p>
      </div>
      <dl className="grid grid-cols-3 gap-3">
        {[
          ["First try", stats.first_try, "text-success"],
          ["Cleared after retry", stats.after_retry, "text-accent-tint-text"],
          ["Misses", stats.misses, "text-warning"],
        ].map(([label, value, color]) => (
          <div key={label as string} className="rounded-[10px] border border-border bg-raised p-4">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className={`mt-1 text-3xl font-bold ${color}`}>{value}</dd>
          </div>
        ))}
      </dl>
      {missed.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-text">Where the misses were</h3>
          <ul className="mt-2 flex flex-col gap-1 text-sm text-text-2">
            {missed.map((item) => (
              <li key={item.id}>
                Problem {item.position + 1}, {item.skill.title.toLowerCase()} ({item.difficulty_label.toLowerCase()}):{" "}
                {item.misses} {item.misses === 1 ? "miss" : "misses"}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <button type="button" className={buttonClasses("primary")} onClick={onRestart} disabled={restarting}>
          {restarting ? "Building…" : "New worksheet on these skills"}
        </button>
        <Link href="/progress" className={buttonClasses("secondary")}>
          See progress
        </Link>
      </div>
    </Card>
  );
}
