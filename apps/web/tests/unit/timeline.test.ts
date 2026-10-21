import { describe, expect, it } from "vitest";
import {
  anchorTime,
  boardStateAt,
  currentWord,
  estimateTimings,
  segmentWordRanges,
  spokenWords,
  stepDuration,
  validateScript,
} from "@/lib/lesson/timeline";
import type { LessonScript, NarrationSegment } from "@/lib/lesson/types";

const NARRATION: NarrationSegment[] = [
  "Let ",
  { math: "u = x^3 + 1", say: "u equal x cubed plus one" },
  ", the inside.",
];

const SCRIPT: LessonScript = {
  id: "t",
  version: 1,
  skillId: "calc1.derivatives.chain_rule",
  title: "Test",
  summary: "",
  sources: [],
  steps: [
    {
      id: "a",
      title: "Write it",
      narration: ["We start with this function."],
      actions: [{ type: "write", id: "f", at: { word: 0 }, latex: "f(x)", row: 0, duration: 1000 }],
    },
    {
      id: "b",
      title: "Mark the inside",
      narration: NARRATION,
      actions: [
        { type: "highlight", at: { word: 1 }, target: "f", part: "inner", color: "yellow" },
        { type: "box", at: { word: 4 }, target: "f", color: "mint" },
        { type: "write", id: "g", at: { word: 6 }, latex: "g", row: 1 },
        { type: "fade", at: { ms: 9000 }, target: "f" },
      ],
    },
  ],
};

const timings = (s: number) => estimateTimings(SCRIPT.steps[s].narration);

describe("narration", () => {
  it("speaks math by its spoken form", () => {
    expect(spokenWords(NARRATION)).toEqual(["Let", "u", "equal", "x", "cubed", "plus", "one,", "the", "inside."]);
  });

  it("maps segments to the words they cover, joining split words", () => {
    expect(segmentWordRanges(NARRATION)).toEqual([
      { start: 0, end: 1 },
      { start: 1, end: 7 },
      { start: 6, end: 9 },
    ]);
  });

  it("estimates increasing timings", () => {
    const t = estimateTimings(NARRATION);
    expect(t).toHaveLength(9);
    for (let i = 1; i < t.length; i++) expect(t[i].start).toBeGreaterThan(t[i - 1].end);
  });
});

describe("timing", () => {
  it("resolves anchors", () => {
    const t = timings(1);
    expect(anchorTime({ word: 2 }, t)).toBe(t[2].start);
    expect(anchorTime({ ms: 1234 }, t)).toBe(1234);
    expect(anchorTime({ word: 99 }, t)).toBe(t[t.length - 1].start);
  });

  it("finds the current word", () => {
    const t = timings(1);
    expect(currentWord(t, -1)).toBe(-1);
    expect(currentWord(t, t[3].start + 1)).toBe(3);
    expect(currentWord(t, 1e9)).toBe(t.length - 1);
  });

  it("covers speech and the last action", () => {
    const t = timings(1);
    expect(stepDuration(SCRIPT.steps[1], t)).toBeGreaterThanOrEqual(9300);
  });
});

describe("boardStateAt", () => {
  it("writes progressively within a step", () => {
    const half = boardStateAt(SCRIPT, 0, 500, timings);
    expect(half.lines[0].progress).toBeCloseTo(0.5);
    expect(boardStateAt(SCRIPT, 0, 5000, timings).lines[0].progress).toBe(1);
  });

  it("shows earlier steps complete and applies actions as their words arrive", () => {
    const t = timings(1);
    const before = boardStateAt(SCRIPT, 1, 0, timings);
    expect(before.lines.map((l) => l.id)).toEqual(["f"]);
    expect(before.lines[0].progress).toBe(1);
    expect(before.lines[0].highlights).toEqual({});

    const mid = boardStateAt(SCRIPT, 1, t[4].start + 10, timings);
    expect(mid.lines[0].highlights).toEqual({ inner: "yellow" });
    expect(mid.lines[0].boxes[0].progress).toBeLessThan(1);

    const end = boardStateAt(SCRIPT, 1, 10_000, timings);
    expect(end.lines.map((l) => l.id)).toEqual(["f", "g"]);
    expect(end.lines[0].opacity).toBeLessThan(1);
  });

  it("is idempotent for scrubbing backwards", () => {
    const late = boardStateAt(SCRIPT, 1, 10_000, timings);
    const early = boardStateAt(SCRIPT, 1, 0, timings);
    expect(boardStateAt(SCRIPT, 1, 0, timings)).toEqual(early);
    expect(late).not.toEqual(early);
  });

  it("completes animations at once with reduced motion", () => {
    const state = boardStateAt(SCRIPT, 0, 10, timings, true);
    expect(state.lines[0].progress).toBe(1);
  });
});

describe("validateScript", () => {
  it("accepts a sound script", () => {
    expect(validateScript(SCRIPT)).toEqual([]);
  });

  it("reports targets that are not written yet and bad anchors", () => {
    const broken: LessonScript = {
      ...SCRIPT,
      steps: [
        {
          id: "x",
          title: "x",
          narration: ["one two"],
          actions: [
            { type: "highlight", at: { word: 0 }, target: "nope", color: "mint" },
            { type: "write", id: "w", at: { word: 5 }, latex: "w", row: 0 },
          ],
          checkpoint: {
            prompt: "?",
            options: [{ id: "a", latex: "1", value: "1", say: "one", correct: false, why: "" }],
            expect: { kind: "equal", left: "1", right: "1", vars: [] },
          },
        },
      ],
    };
    const problems = validateScript(broken);
    expect(problems).toHaveLength(3);
  });
});
