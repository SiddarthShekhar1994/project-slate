import Link from "next/link";
import { buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import type { LessonSummary, WorksheetSummary } from "@/lib/types";

type Props = { worksheet: WorksheetSummary | null; lesson: LessonSummary | null };

/** "Pick up where you left off": whichever of the open worksheet or lesson was touched last. */
export function ResumeCard({ worksheet, lesson }: Props) {
  const lessonTime = lesson?.last_opened ? Date.parse(lesson.last_opened) : 0;
  const sheetTime = worksheet ? Date.parse(worksheet.updated_at) : 0;

  if (lesson && lessonTime >= sheetTime) {
    return (
      <Card className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-accent-tint-text">Pick up where you left off</p>
          <p className="mt-1 text-xl font-bold text-text">{lesson.title}</p>
          <p className="mt-1 text-sm text-text-2">
            Lesson, step {lesson.resume_step + 1} of {lesson.steps}
          </p>
        </div>
        <Link href={`/lesson/${lesson.id}?step=${lesson.resume_step + 1}`} className={buttonClasses("primary")}>
          Resume lesson
        </Link>
      </Card>
    );
  }
  if (worksheet) {
    const cleared = worksheet.stats.first_try + worksheet.stats.after_retry;
    return (
      <Card className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-accent-tint-text">Pick up where you left off</p>
          <p className="mt-1 text-xl font-bold text-text">{worksheet.title}</p>
          <p className="mt-1 text-sm text-text-2">
            {cleared} of {worksheet.stats.total} cleared
            {worksheet.stats.retrying ? `, ${worksheet.stats.retrying} retrying` : ""}
          </p>
        </div>
        <Link href={`/practice/${worksheet.id}`} className={buttonClasses("primary")}>
          Continue practice
        </Link>
      </Card>
    );
  }
  return (
    <Card className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-semibold text-accent-tint-text">Start studying</p>
        <p className="mt-1 text-text-2">Nothing in progress. Watch a lesson, or pick a skill and work a worksheet.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href="/lesson" className={buttonClasses("secondary")}>
          Lessons
        </Link>
        <Link href="/practice" className={buttonClasses("primary")}>
          Practice
        </Link>
      </div>
    </Card>
  );
}
