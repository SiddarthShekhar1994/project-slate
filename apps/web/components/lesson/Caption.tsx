"use client";

import { Fragment, useMemo } from "react";
import { Tex } from "@/components/shared/math/Tex";
import { segmentWordRanges } from "@/lib/lesson/timeline";
import type { NarrationSegment } from "@/lib/lesson/types";

/**
 * The caption line under the board. Words already spoken are bright, the rest
 * are dim. Math segments show as KaTeX and light up when the voice reaches them.
 *
 * ``segmentWordRanges`` already accounts for a segment that continues the
 * previous word ("one" + ", the"), so the k-th word of a segment is spoken
 * word ``range.start + k``.
 */
export function Caption({ narration, word }: { narration: NarrationSegment[]; word: number }) {
  const ranges = useMemo(() => segmentWordRanges(narration), [narration]);
  return (
    <p className="text-base leading-relaxed sm:text-lg" aria-hidden>
      {narration.map((seg, i) => {
        const start = ranges[i].start;
        if (typeof seg !== "string") {
          return (
            <span key={i} className={`transition-colors duration-200 ${word >= start ? "text-text" : "text-muted"}`}>
              <Tex latex={seg.math} />
            </span>
          );
        }
        let k = 0;
        return (
          <Fragment key={i}>
            {seg.split(/(\s+)/).map((part, j) => {
              if (!part) return null;
              if (/^\s+$/.test(part)) return <Fragment key={j}>{part}</Fragment>;
              const index = start + k++;
              return (
                <span key={j} className={`transition-colors duration-200 ${word >= index ? "text-text" : "text-muted"}`}>
                  {part}
                </span>
              );
            })}
          </Fragment>
        );
      })}
    </p>
  );
}
