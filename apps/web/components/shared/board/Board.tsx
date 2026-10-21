"use client";

import { type CSSProperties, useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { BoardState, LineState } from "@/lib/lesson/timeline";
import type { BoardColor } from "@/lib/lesson/types";
import { renderLatex } from "@/lib/katex";

const COLOR_VAR: Record<BoardColor, string> = {
  chalk: "var(--chalk)",
  yellow: "var(--yellow)",
  mint: "var(--mint)",
};

type Rect = { x: number; y: number; w: number; h: number };

const lineDomId = (boardId: string, lineId: string) => `${boardId}-line-${lineId}`;

/**
 * The chalkboard. It renders a :type:`BoardState` and nothing else: no
 * timers, no animation state. Write progress becomes a left-to-right clip,
 * highlights become scoped colour rules, and boxes and labels are measured
 * from the KaTeX parts they point at.
 */
export function Board({ state, boardId = "board", label }: { state: BoardState; boardId?: string; label: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [rects, setRects] = useState<Record<string, Rect>>({});

  const rowCount = Math.max(4, ...state.lines.map((l) => l.row + 1));

  // A line runs until the next line in its row starts, so lines never overlap.
  const spanEnd = useMemo(() => {
    const ends: Record<string, number> = {};
    for (const line of state.lines) {
      const next = state.lines
        .filter((o) => o.row === line.row && o.col > line.col)
        .reduce((m, o) => Math.min(m, o.col), 12);
      ends[line.id] = next;
    }
    return ends;
  }, [state.lines]);

  // Colour rules for highlighted parts, scoped to each line.
  const styleRules = useMemo(() => {
    const rules: string[] = [];
    for (const line of state.lines) {
      for (const [part, color] of Object.entries(line.highlights)) {
        const scope = `#${CSS.escape(lineDomId(boardId, line.id))}`;
        const target = part ? `${scope} .slate-part-${part}` : scope;
        rules.push(`${target}{color:${COLOR_VAR[color]};text-shadow:0 0 18px color-mix(in srgb, ${COLOR_VAR[color]} 35%, transparent)}`);
      }
    }
    return rules.join("\n");
  }, [state.lines, boardId]);

  // Which line parts need measuring: box targets and label anchors.
  const measureKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const line of state.lines) for (const box of line.boxes) keys.add(`${line.id}|${box.part}`);
    for (const lbl of state.labels) keys.add(`${lbl.target}|${lbl.part}`);
    return [...keys].sort();
  }, [state.lines, state.labels]);
  const layoutKey = state.lines.map((l) => `${l.id}:${l.latex}:${l.row}:${l.col}:${l.size}`).join(";");

  const measure = useCallback(() => {
    const root = container.current;
    if (!root) return;
    const origin = root.getBoundingClientRect();
    const next: Record<string, Rect> = {};
    for (const key of measureKeys) {
      const [lineId, part] = key.split("|");
      const el = document.getElementById(lineDomId(boardId, lineId));
      if (!el) continue;
      const targets = part ? [...el.querySelectorAll(`.slate-part-${part}`)] : [el.querySelector(".katex") ?? el];
      if (!targets.length) continue;
      const boxes = targets.map((t) => t.getBoundingClientRect());
      const left = Math.min(...boxes.map((b) => b.left));
      const top = Math.min(...boxes.map((b) => b.top));
      const right = Math.max(...boxes.map((b) => b.right));
      const bottom = Math.max(...boxes.map((b) => b.bottom));
      next[key] = { x: left - origin.left, y: top - origin.top, w: right - left, h: bottom - top };
    }
    setRects((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
  }, [measureKeys, boardId]);

  useLayoutEffect(() => {
    measure();
    const root = container.current;
    if (!root || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => measure());
    observer.observe(root);
    return () => observer.disconnect();
    // layoutKey changes when lines move or change size.
  }, [measure, layoutKey]);

  return (
    <div
      ref={container}
      role="region"
      aria-label={label}
      className="relative w-full overflow-hidden rounded-[14px] border border-[#1d3a31] bg-board px-4 py-5 text-chalk shadow-[inset_0_0_60px_rgba(0,0,0,0.35)] sm:px-8 sm:py-7"
      style={{
        backgroundImage:
          "radial-gradient(120% 90% at 20% 10%, rgba(255,255,255,0.045), transparent 60%), radial-gradient(90% 80% at 85% 90%, rgba(0,0,0,0.25), transparent 65%)",
      }}
    >
      {styleRules && <style>{styleRules}</style>}
      <div
        className="grid gap-y-3 sm:gap-y-4"
        style={{ gridTemplateColumns: "repeat(12, minmax(0, 1fr))", gridTemplateRows: `repeat(${rowCount}, minmax(2.75rem, auto))` }}
      >
        {state.lines.map((line) => (
          <BoardLine key={line.id} line={line} end={spanEnd[line.id]} domId={lineDomId(boardId, line.id)} />
        ))}
      </div>

      <svg aria-hidden className="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
        {state.lines.flatMap((line) =>
          line.boxes.map((box) => {
            const r = rects[`${line.id}|${box.part}`];
            if (!r) return null;
            const pad = 6;
            const w = r.w + pad * 2;
            const h = r.h + pad * 2;
            const perimeter = 2 * (w + h);
            return (
              <rect
                key={`${line.id}-${box.part}`}
                x={r.x - pad}
                y={r.y - pad}
                width={w}
                height={h}
                rx={8}
                fill="none"
                stroke={COLOR_VAR[box.color]}
                strokeWidth={2.2}
                strokeLinecap="round"
                strokeDasharray={perimeter}
                strokeDashoffset={perimeter * (1 - box.progress)}
                style={{ opacity: line.opacity, filter: "url(#chalk-rough)" }}
              />
            );
          }),
        )}
        <defs>
          <filter id="chalk-rough">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="1" result="noise" />
            <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.4" />
          </filter>
        </defs>
      </svg>

      {state.labels.map((lbl) => {
        const r = rects[`${lbl.target}|${lbl.part}`];
        if (!r) return null;
        const style: CSSProperties =
          lbl.side === "right"
            ? { left: r.x + r.w + 14, top: r.y + r.h / 2, transform: "translateY(-50%)" }
            : lbl.side === "above"
              ? { left: r.x + r.w / 2, top: r.y - 6, transform: "translate(-50%, -100%)" }
              : { left: r.x + r.w / 2, top: r.y + r.h + 4, transform: "translateX(-50%)" };
        return (
          <span
            key={lbl.id}
            aria-hidden
            className="pointer-events-none absolute whitespace-nowrap font-hand text-xl leading-none sm:text-2xl"
            style={{ ...style, color: COLOR_VAR[lbl.color], opacity: lbl.progress }}
          >
            {lbl.text}
          </span>
        );
      })}
    </div>
  );
}

function BoardLine({ line, end, domId }: { line: LineState; end: number; domId: string }) {
  const html = useMemo(() => renderLatex(line.latex, false), [line.latex]);
  const done = line.progress >= 1;
  return (
    <div
      id={domId}
      aria-hidden={!done}
      className={`min-w-0 self-center transition-opacity duration-500 ${line.size === "lg" ? "text-2xl sm:text-[2rem]" : "text-lg sm:text-2xl"}`}
      style={{
        gridRow: line.row + 1,
        gridColumn: `${line.col + 1} / ${end + 1}`,
        opacity: line.opacity,
        clipPath: done ? undefined : `inset(-20% ${(1 - line.progress) * 100}% -20% 0)`,
      }}
    >
      <span className="board-math inline-block max-w-full overflow-x-auto" dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
}
