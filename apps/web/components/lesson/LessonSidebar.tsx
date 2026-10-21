import Link from "next/link";
import type { LessonView, MasteryStatus } from "@/lib/types";

const STATUS: Record<MasteryStatus, { label: string; dot: string }> = {
  new: { label: "Not started", dot: "bg-raised border border-border" },
  learning: { label: "Learning", dot: "bg-warning" },
  practiced: { label: "Practiced", dot: "bg-accent-light" },
  mastered: { label: "Mastered", dot: "bg-success" },
};

/** Unit outline with mastery per skill, and the sources this lesson was built from. */
export function LessonSidebar({ lesson }: { lesson: LessonView }) {
  return (
    <aside className="flex flex-col gap-6" aria-label="Lesson context">
      <section aria-labelledby="outline-heading">
        <h2 id="outline-heading" className="text-xs font-semibold uppercase tracking-wide text-muted">
          {lesson.outline.unit}
        </h2>
        <ol className="mt-2 flex flex-col gap-1">
          {lesson.outline.skills.map((skill) => {
            const status = STATUS[skill.status];
            const current = skill.id === lesson.skill.id;
            return (
              <li key={skill.id}>
                <Link
                  href={`/lesson?skill=${encodeURIComponent(skill.id)}`}
                  aria-current={current ? "page" : undefined}
                  className={`flex min-h-11 items-center gap-3 rounded-[10px] px-3 py-2 text-sm ${
                    current ? "bg-accent-tint text-accent-tint-text" : "text-text-2 hover:bg-hover hover:text-text"
                  }`}
                >
                  <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${status.dot}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold">{skill.title}</span>
                    <span className="block text-xs text-muted">
                      {status.label}
                      {skill.mastery !== null ? ` · ${Math.round(skill.mastery * 100)}%` : ""}
                    </span>
                  </span>
                </Link>
                {skill.mastery !== null && (
                  <span aria-hidden className="mx-3 mt-1 block h-1 overflow-hidden rounded-full bg-raised">
                    <span className="block h-full rounded-full bg-success" style={{ width: `${skill.mastery * 100}%` }} />
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-labelledby="sources-heading">
        <h2 id="sources-heading" className="text-xs font-semibold uppercase tracking-wide text-muted">
          Built from
        </h2>
        {lesson.sources.length === 0 ? (
          <p className="mt-2 text-sm text-text-2">
            Slate&apos;s built-in lesson. Upload your course materials in the{" "}
            <Link href="/library" className="text-accent-light underline-offset-4 hover:underline">
              library
            </Link>{" "}
            to get one in your professor&apos;s notation.
          </p>
        ) : (
          <ul className="mt-2 flex flex-col gap-2">
            {lesson.sources.map((source) => (
              <li key={source.id} className="rounded-[10px] border border-border bg-card px-3 py-2 text-sm">
                <p className="font-semibold text-text">{source.title}</p>
                <p className="text-xs text-muted">
                  {source.kind} · {source.locator}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
