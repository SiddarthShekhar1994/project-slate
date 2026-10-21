"use client";

import Link from "next/link";
import { useState } from "react";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { api } from "@/lib/api";
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
              {source.skills.length ? (
                source.skills.slice(0, 5).map((skill) => (
                  <span key={skill.id} className="rounded-full bg-raised px-2.5 py-0.5 text-xs text-text-2">
                    {skill.title}
                  </span>
                ))
              ) : (
                <span className="text-text-2">No derivative topics found</span>
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
