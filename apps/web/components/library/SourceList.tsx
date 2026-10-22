"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { MathText } from "@/components/shared/math/MathText";
import { buttonClasses } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { SourceView } from "@/lib/types";

const size = (bytes: number) =>
  bytes > 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} KB`;

type Props = {
  sources: SourceView[];
  onChange: (sources: SourceView[]) => void;
};

/** Every uploaded source with what Slate found in it and what it was used for. */
export function SourceList({ sources, onChange }: Props) {
  if (sources.length === 0) {
    return (
      <p className="rounded-[14px] border border-border bg-card px-5 py-4 text-sm text-text-2">
        No sources yet. Once you add materials, lessons follow your professor&apos;s notation and practice problems
        point back to the slides they come from.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {sources.map((source) => (
        <li key={source.id}>
          <SourceCard
            source={source}
            onReplace={(next) => onChange(sources.map((s) => (s.id === next.id ? next : s)))}
            onDelete={() => onChange(sources.filter((s) => s.id !== source.id))}
          />
        </li>
      ))}
    </ul>
  );
}

function SourceCard({ source, onReplace, onDelete }: {
  source: SourceView;
  onReplace: (s: SourceView) => void;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const { lessons, problems } = source.used_for;
  const reading = source.reading;
  const found = reading?.status === "done" && reading.topics.length > 0;

  return (
    <Card as="article" aria-labelledby={`source-${source.id}`} className="flex flex-col gap-3 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id={`source-${source.id}`} className="truncate font-semibold text-text">
            {source.title}
          </h3>
          <p className="text-xs text-muted">
            {source.kind_label}
            {source.pages ? ` · ${source.pages} ${source.pages === 1 ? "page" : "pages"}` : ""} · {size(source.size_bytes)}
            {source.ocr ? ` · read with ${source.ocr === "claude" ? "Claude vision" : source.ocr}` : ""}
          </p>
        </div>
        {source.status === "processing" && <Spinner label="Reading" />}
        {source.status === "ready" && (
          <span className="rounded-full border border-success/40 bg-success-bg px-2.5 py-0.5 text-xs font-semibold text-success">
            Ready
          </span>
        )}
        {source.status === "failed" && (
          <span className="rounded-full border border-warning/40 bg-warning-bg px-2.5 py-0.5 text-xs font-semibold text-warning">
            Couldn&apos;t read
          </span>
        )}
      </div>

      {source.status === "failed" && source.error && <p className="text-sm text-warning">{source.error}</p>}

      {source.status === "ready" && (
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted">Covers</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {found ? (
                reading.topics.map((topic) => (
                  <span key={topic.id ?? topic.title} className="rounded-full bg-raised px-2.5 py-0.5 text-xs text-text-2">
                    {topic.title}
                    {topic.problems > 0 && <span className="text-muted"> · {topic.problems}</span>}
                  </span>
                ))
              ) : source.skills.length ? (
                source.skills.slice(0, 5).map((skill) => (
                  <span key={skill.id} className="rounded-full bg-raised px-2.5 py-0.5 text-xs text-text-2">
                    {skill.title}
                  </span>
                ))
              ) : reading?.status === "pending" ? (
                <span className="text-text-2">Reading the problems…</span>
              ) : (
                <span className="text-text-2">No topics found yet</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted">Used for</dt>
            <dd className="mt-1 text-text-2">
              {lessons.length === 0 && problems === 0 ? (
                "Not used yet"
              ) : (
                <>
                  {lessons.map((l, i) => (
                    <span key={l.id}>
                      {i > 0 ? ", " : ""}
                      <Link href={`/lesson/${l.id}`} className="text-accent-light underline-offset-4 hover:underline">
                        {l.title}
                      </Link>
                    </span>
                  ))}
                  {lessons.length > 0 && problems > 0 ? "; " : ""}
                  {problems > 0 ? `${problems} practice ${problems === 1 ? "problem" : "problems"}` : ""}
                </>
              )}
            </dd>
          </div>
        </dl>
      )}

      {source.status === "ready" && reading && <ReadingPanel source={source} onReplace={onReplace} />}

      <div className="flex flex-wrap gap-2">
        <a
          href={source.file_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-11 items-center rounded-[10px] px-3 text-sm font-semibold text-text-2 hover:bg-hover hover:text-text"
        >
          Open file
        </a>
        {source.status === "failed" && (
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              onReplace(await api.reprocessSource(source.id));
              setBusy(false);
            }}
            className="min-h-11 rounded-[10px] px-3 text-sm font-semibold text-accent-tint-text hover:bg-accent-tint"
          >
            Try again
          </button>
        )}
        {confirming ? (
          <span className="flex flex-wrap items-center gap-2 text-sm text-text-2">
            Remove this source?
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                await api.deleteSource(source.id);
                onDelete();
              }}
              className="min-h-11 rounded-[10px] bg-warning-bg px-3 font-semibold text-warning hover:bg-[#4a2d16]"
            >
              Remove
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="min-h-11 rounded-[10px] px-3 font-semibold text-text-2 hover:bg-hover"
            >
              Keep
            </button>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="min-h-11 rounded-[10px] px-3 text-sm font-semibold text-text-2 hover:bg-hover hover:text-text"
          >
            Remove
          </button>
        )}
      </div>
    </Card>
  );
}

/** What Slate made of the problems on a source, and the way into practicing them. */
function ReadingPanel({ source, onReplace }: { source: SourceView; onReplace: (s: SourceView) => void }) {
  const router = useRouter();
  const { desktop } = useSession();
  const [busy, setBusy] = useState<"practice" | "read" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reading = source.reading!;

  async function practice() {
    setBusy("practice");
    setError(null);
    try {
      const sheet = await api.practiceSheet(source.id);
      router.push(`/practice/${sheet.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't build the worksheet.");
      setBusy(null);
    }
  }

  async function readAgain() {
    setBusy("read");
    setError(null);
    try {
      onReplace(await api.readSource(source.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't start reading.");
    }
    setBusy(null);
  }

  if (reading.status === "pending") {
    return (
      <p className="flex items-center gap-2 text-sm text-text-2">
        <Spinner label="Reading the problems" />
        Claude is reading the problems. Slate checks each answer as it goes; this takes a minute or two.
      </p>
    );
  }
  if (reading.status === "no_key") {
    return (
      <p className="text-sm text-text-2">
        Slate needs a Claude API key to read the problems on this sheet.{" "}
        {desktop ? (
          <Link href="/settings" className="text-accent-light underline-offset-4 hover:underline">
            Add one in Settings
          </Link>
        ) : (
          "Set ANTHROPIC_API_KEY for the API"
        )}
        , then come back here.
      </p>
    );
  }
  if (reading.status === "failed") {
    return (
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <p className="text-warning">{reading.error ?? "Slate couldn't read the problems."}</p>
        <button type="button" className={buttonClasses("secondary")} disabled={busy !== null} onClick={readAgain}>
          {busy === "read" ? "Starting…" : "Read it again"}
        </button>
      </div>
    );
  }
  if (reading.status !== "done") return null;

  return (
    <div className="flex flex-col gap-3 rounded-[10px] bg-raised/60 px-4 py-3 text-sm">
      {reading.problems === 0 ? (
        <p className="text-text-2">No problems on this one, just topics.</p>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-text-2">
            {reading.ready === reading.problems
              ? `Slate can grade all ${reading.problems} problems on it.`
              : `Slate can grade ${reading.ready} of the ${reading.problems} problems on it.`}
          </p>
          {reading.ready > 0 && (
            <button type="button" className={buttonClasses("primary")} disabled={busy !== null} onClick={practice}>
              {busy === "practice" ? "Building…" : "Practice this sheet"}
            </button>
          )}
        </div>
      )}
      {reading.not_checked.length > 0 && (
        <details>
          <summary className="min-h-11 cursor-pointer content-center font-semibold text-text-2">
            Not graded by Slate ({reading.not_checked.length})
          </summary>
          <ul className="mt-2 flex flex-col gap-2">
            {reading.not_checked.map((problem, i) => (
              <li key={`${problem.label ?? ""}-${i}`} className="rounded-lg bg-card px-3 py-2">
                <p className="text-xs font-semibold text-muted">
                  {problem.label ? `Problem ${problem.label}` : "Problem"} · {problem.kind}
                </p>
                {problem.statement && <MathText as="p" text={problem.statement} className="mt-1 text-text" />}
                <p className="mt-1 text-text-2">{problem.reason}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
      {error && <p role="alert" className="text-warning">{error}</p>}
    </div>
  );
}
