"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { MathText } from "@/components/shared/math/MathText";
import { Tex } from "@/components/shared/math/Tex";
import { Button } from "@/components/shared/ui/Button";
import { Card } from "@/components/shared/ui/Card";
import { Spinner } from "@/components/shared/ui/Spinner";
import { api } from "@/lib/api";
import type { FormulaSheet } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { replaceQuery } from "@/lib/urlState";

/** The formulas for the chosen topics, in the professor's notation. URL: ?skills=a,b */
export function FormulaSheetView() {
  const search = useSearchParams();
  const catalog = useApi(() => api.catalog());
  const skills = useMemo(
    () => catalog.data?.courses.flatMap((c) => c.units.flatMap((u) => u.skills)) ?? [],
    [catalog.data],
  );
  const [chosen, setChosen] = useState<string[] | null>(() => {
    const raw = search?.get("skills");
    return raw ? raw.split(",").filter(Boolean) : null;
  });
  const selected = useMemo(
    () => (chosen ?? skills.map((s) => s.id)).filter((id) => skills.some((s) => s.id === id)),
    [chosen, skills],
  );
  const selectedKey = selected.join(",");
  const [sheet, setSheet] = useState<FormulaSheet | null>(null);

  useEffect(() => {
    if (!catalog.data) return;
    replaceQuery({ skills: chosen ? chosen.join(",") : null });
    if (!selectedKey) return;
    let cancelled = false;
    api
      .formulaSheet(selectedKey.split(","))
      .then((value) => !cancelled && setSheet(value))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [catalog.data, chosen, selectedKey]);

  if (!catalog.data) {
    return catalog.error ? <p role="alert">{catalog.error}</p> : <Spinner label="Loading formulas" />;
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between print:hidden">
        <div>
          <Link href="/progress" className="text-sm font-semibold text-accent-tint-text hover:underline">
            Progress
          </Link>
          <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Formula sheet</h1>
          {sheet?.notation && <p className="mt-2 text-sm text-text-2">Written in your course&apos;s notation: {sheet.notation}.</p>}
        </div>
        <Button variant="secondary" onClick={() => window.print()}>
          Print
        </Button>
      </header>

      <fieldset className="print:hidden">
        <legend className="text-sm font-semibold text-text-2">Topics</legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {skills.map((skill) => {
            const on = selected.includes(skill.id);
            return (
              <label
                key={skill.id}
                className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full border px-3 text-sm ${
                  on ? "border-accent-light bg-accent-tint text-accent-tint-text" : "border-border bg-raised text-text-2"
                }`}
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={(event) =>
                    setChosen(event.target.checked ? [...selected, skill.id] : selected.filter((s) => s !== skill.id))
                  }
                  className="h-4 w-4 accent-[#2748E8]"
                />
                {skill.title}
              </label>
            );
          })}
        </div>
      </fieldset>

      {selected.length === 0 ? (
        <p className="text-text-2">Pick a topic to see its formulas.</p>
      ) : !sheet ? (
        <Spinner label="Loading formulas" />
      ) : (
        sheet.units.map((unit) => (
          <Card key={unit.id} aria-labelledby={`formula-unit-${unit.id}`} className="p-4 sm:p-6 print:border-0 print:p-0">
            <h2 id={`formula-unit-${unit.id}`} className="text-lg font-bold">
              {unit.title}
            </h2>
            <dl className="mt-3 flex flex-col gap-4">
              {unit.entries.map((entry) => (
                <div key={entry.skill.id} className="rounded-[10px] bg-raised p-4 print:bg-transparent">
                  <dt className="font-semibold">{entry.title}</dt>
                  <dd className="mt-2">
                    <Tex latex={entry.latex} display className="text-lg text-text" />
                    {entry.note && (
                      <p className="mt-2 text-sm text-text-2">
                        <MathText text={entry.note} />
                      </p>
                    )}
                    {entry.source && (
                      <p className="mt-2 text-xs text-muted">
                        In your materials: {entry.source.title}, {entry.source.locator}
                      </p>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </Card>
        ))
      )}
    </div>
  );
}
