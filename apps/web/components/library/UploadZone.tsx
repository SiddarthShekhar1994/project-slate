"use client";

import { type DragEvent, useId, useRef, useState } from "react";
import { Icon } from "@/components/shared/ui/Icon";
import { ApiError, api } from "@/lib/api";
import type { SourceView } from "@/lib/types";

const ACCEPT = ".pdf,.pptx,.docx,.png,.jpg,.jpeg,.webp,application/pdf,image/*";

type Upload = { name: string; progress: number; error: string | null };

/**
 * Drop files here or choose them with the button. The drop area is only a
 * convenience for mice; the button and its file picker work by keyboard.
 */
export function UploadZone({
  kinds,
  onUploaded,
  title = "Add course materials",
  blurb = "Drop lecture slides, textbook chapters, your syllabus, past exams or photos of notes here.",
}: {
  kinds: Record<string, string>;
  onUploaded: (s: SourceView) => void;
  title?: string;
  blurb?: string;
}) {
  const [kind, setKind] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const id = useId();

  async function send(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      setUploads((u) => [...u, { name: file.name, progress: 0, error: null }]);
      const update = (patch: Partial<Upload>) =>
        setUploads((u) => u.map((x) => (x.name === file.name ? { ...x, ...patch } : x)));
      try {
        const source = await api.uploadSource(file, kind || null, (progress) => update({ progress }));
        setUploads((u) => u.filter((x) => x.name !== file.name));
        onUploaded(source);
      } catch (e) {
        update({ error: e instanceof ApiError ? e.message : "Upload failed." });
      }
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) void send(event.dataTransfer.files);
  }

  return (
    <section aria-labelledby={`${id}-title`} className="flex flex-col gap-3">
      <h2 id={`${id}-title`} className="text-lg font-bold">
        {title}
      </h2>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center gap-3 rounded-[14px] border-2 border-dashed px-6 py-8 text-center transition-colors ${
          dragging ? "border-accent-light bg-accent-tint" : "border-border bg-card"
        }`}
      >
        <Icon name="upload" size={28} className="text-accent-light" />
        <p className="text-text">{blurb}</p>
        <p className="text-sm text-muted">PDF, PowerPoint (.pptx), Word (.docx), PNG or JPEG, up to 50 MB each.</p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <label className="flex items-center gap-2 text-sm text-text-2">
            Type
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="min-h-11 rounded-[10px] border border-border bg-raised px-3 text-sm text-text"
            >
              <option value="">Guess from the file</option>
              {Object.entries(kinds).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => input.current?.click()}
            className="min-h-11 rounded-[10px] bg-accent px-5 text-sm font-semibold text-white hover:bg-[#3557f0]"
          >
            Choose files
          </button>
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPT}
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(e) => {
              if (e.target.files?.length) void send(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
      </div>
      <ul aria-live="polite" className="flex flex-col gap-2">
        {uploads.map((u) => (
          <li key={u.name} className="rounded-[10px] border border-border bg-card px-4 py-3 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="truncate text-text">{u.name}</span>
              {u.error ? (
                <span className="text-warning">{u.error}</span>
              ) : (
                <span className="text-muted">Uploading {Math.round(u.progress * 100)}%</span>
              )}
            </div>
            {!u.error && (
              <span aria-hidden className="mt-2 block h-1.5 overflow-hidden rounded-full bg-raised">
                <span className="block h-full rounded-full bg-accent-light" style={{ width: `${u.progress * 100}%` }} />
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
