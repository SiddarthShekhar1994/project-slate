"use client";

import Link from "next/link";
import { buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

/** Library home. Source uploads arrive in stage 4; for now it resumes practice. */
export function LibraryHome() {
  const { user } = useSession();
  const recent = useApi(() => api.worksheets());
  const open = recent.data?.worksheets.find((w) => !w.completed_at);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-8">
      <header>
        <p className="text-sm font-semibold text-accent-tint-text">Library</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">
          {user ? `Welcome back, ${user.display_name}` : "Library"}
        </h1>
      </header>

      <section aria-labelledby="pickup-heading">
        <h2 id="pickup-heading" className="sr-only">
          Pick up where you left off
        </h2>
        {!recent.data ? (
          <Spinner />
        ) : open ? (
          <Card className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-accent-tint-text">Pick up where you left off</p>
              <p className="mt-1 text-xl font-bold text-text">{open.title}</p>
              <p className="mt-1 text-sm text-text-2">
                {open.stats.first_try + open.stats.after_retry} of {open.stats.total} cleared
                {open.stats.retrying ? `, ${open.stats.retrying} retrying` : ""}
              </p>
            </div>
            <Link href={`/practice/${open.id}`} className={buttonClasses("primary")}>
              Continue
            </Link>
          </Card>
        ) : (
          <Card className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-accent-tint-text">Start studying</p>
              <p className="mt-1 text-text-2">Nothing in progress. Pick a skill and work a worksheet, easy to hard.</p>
            </div>
            <Link href="/practice" className={buttonClasses("primary")}>
              Choose a skill
            </Link>
          </Card>
        )}
      </section>
    </div>
  );
}
