/** Small text formatters shared by the progress and exam pages. */

export function percent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

const DAY = 24 * 60 * 60 * 1000;

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** "Due now", "Overdue by 2 days", "Due tomorrow", "Due in 5 days", "Due Nov 3". */
export function dueLabel(iso: string, now: Date = new Date()): string {
  const due = new Date(iso);
  const days = Math.round((startOfDay(due) - startOfDay(now)) / DAY);
  if (due.getTime() <= now.getTime()) {
    return days <= -1 ? `Overdue by ${-days} ${days === -1 ? "day" : "days"}` : "Due now";
  }
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days < 7) return `Due in ${days} days`;
  return `Due ${due.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
}

/** Seconds as a clock: "4:05", "1:02:09". */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${rest}` : `${m}:${rest}`;
}

/** Seconds in words for screen readers and summaries: "12 minutes", "1 hour 5 minutes". */
export function minutesText(seconds: number): string {
  const total = Math.max(1, Math.round(seconds / 60));
  const h = Math.floor(total / 60);
  const m = total % 60;
  const parts = [];
  if (h) parts.push(`${h} ${h === 1 ? "hour" : "hours"}`);
  if (m || !h) parts.push(`${m} ${m === 1 ? "minute" : "minutes"}`);
  return parts.join(" ");
}
