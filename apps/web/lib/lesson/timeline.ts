/**
 * Timing and board state for the lesson player.
 *
 * Everything here is a pure function of (script, step, time). The player
 * never accumulates animation state: it asks "what does the board look like
 * at this instant?" each frame, which makes scrubbing, speed changes and
 * reduced motion straightforward.
 */

import type {
  Anchor,
  BoardAction,
  BoardColor,
  LessonScript,
  LessonStep,
  NarrationSegment,
  WordTiming,
} from "./types";

/** Words per minute used to estimate timings when no voice is playing. */
export const ESTIMATE_WPM = 150;
export const DEFAULT_WRITE_MS = 900;
export const STEP_TAIL_MS = 700;
const WORD_GAP_MS = 40;

export function spokenText(segments: NarrationSegment[]): string {
  return segments
    .map((s) => (typeof s === "string" ? s : s.say))
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}

export function spokenWords(segments: NarrationSegment[]): string[] {
  const text = spokenText(segments);
  return text ? text.split(" ") : [];
}

/**
 * Map each narration segment to the spoken word indices it covers, so the
 * caption can show prose and KaTeX while tracking the voice word by word.
 */
export function segmentWordRanges(segments: NarrationSegment[]): { start: number; end: number }[] {
  const ranges: { start: number; end: number }[] = [];
  let spoken = "";
  for (const seg of segments) {
    const piece = typeof seg === "string" ? seg : seg.say;
    const before = countWords(spoken);
    // "one" + ", the" is spoken as "one," then "the": the segment continues the previous word.
    const joinsPrevious = before > 0 && /\S$/.test(spoken) && /^\S/.test(piece);
    spoken += piece;
    ranges.push({ start: joinsPrevious ? before - 1 : before, end: countWords(spoken) });
  }
  return ranges;
}

function countWords(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

/** Estimated word timings at 1x, weighted by word length and punctuation pauses. */
export function estimateTimings(segments: NarrationSegment[], wpm = ESTIMATE_WPM): WordTiming[] {
  const words = spokenWords(segments);
  const base = 60_000 / wpm;
  let t = 0;
  return words.map((word) => {
    const letters = word.replace(/[^\p{L}\p{N}]/gu, "").length;
    const duration = base * (0.55 + Math.min(letters, 12) * 0.075);
    const pause = /[.!?]$/.test(word) ? 260 : /[,;:]$/.test(word) ? 140 : 0;
    const timing = { text: word, start: t, end: t + duration };
    t += duration + WORD_GAP_MS + pause;
    return timing;
  });
}

export function anchorTime(anchor: Anchor, timings: WordTiming[]): number {
  if ("ms" in anchor) return anchor.ms;
  if (timings.length === 0) return 0;
  const i = Math.max(0, Math.min(anchor.word, timings.length - 1));
  return timings[i].start;
}

function actionEnd(action: BoardAction, timings: WordTiming[]): number {
  const start = anchorTime(action.at, timings);
  return action.type === "write" ? start + (action.duration ?? DEFAULT_WRITE_MS) : start + 300;
}

/** Length of a step at 1x: the narration plus a short tail, or the last action if later. */
export function stepDuration(step: LessonStep, timings: WordTiming[]): number {
  const speech = timings.length ? timings[timings.length - 1].end : 0;
  const actions = step.actions.reduce((m, a) => Math.max(m, actionEnd(a, timings)), 0);
  return Math.max(speech, actions) + STEP_TAIL_MS;
}

/** Index of the word being spoken at ``t`` (-1 before the first word). */
export function currentWord(timings: WordTiming[], t: number): number {
  let lo = 0;
  let hi = timings.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (timings[mid].start <= t) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

export type LineState = {
  id: string;
  latex: string;
  row: number;
  col: number;
  size: "md" | "lg";
  /** 0 to 1: how much of the line the chalk has written. */
  progress: number;
  opacity: number;
  stepIndex: number;
  /** Colour per highlighted part; "" means the whole line. */
  highlights: Record<string, BoardColor>;
  boxes: { part: string; color: BoardColor; progress: number }[];
};

export type LabelState = {
  id: string;
  text: string;
  target: string;
  part: string;
  side: "above" | "below" | "right";
  color: BoardColor;
  progress: number;
};

export type BoardState = { lines: LineState[]; labels: LabelState[] };

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

/**
 * The board after every action of steps before ``stepIndex`` and the actions
 * of ``stepIndex`` that have started by time ``t`` (ms into the step at 1x).
 * With ``reducedMotion`` every started action is shown complete.
 */
export function boardStateAt(
  script: LessonScript,
  stepIndex: number,
  t: number,
  timingsFor: (stepIndex: number) => WordTiming[],
  reducedMotion = false,
): BoardState {
  const lines = new Map<string, LineState>();
  const labels = new Map<string, LabelState>();

  for (let s = 0; s <= stepIndex && s < script.steps.length; s++) {
    const step = script.steps[s];
    const timings = timingsFor(s);
    const now = s < stepIndex ? Number.POSITIVE_INFINITY : t;
    for (const action of step.actions) {
      const start = anchorTime(action.at, timings);
      if (start > now) continue;
      const elapsed = now - start;
      switch (action.type) {
        case "write": {
          const duration = action.duration ?? DEFAULT_WRITE_MS;
          lines.set(action.id, {
            id: action.id,
            latex: action.latex,
            row: action.row,
            col: action.col ?? 0,
            size: action.size ?? "md",
            progress: reducedMotion ? 1 : clamp01(elapsed / duration),
            opacity: 1,
            stepIndex: s,
            highlights: {},
            boxes: [],
          });
          break;
        }
        case "highlight": {
          const line = lines.get(action.target);
          if (line) line.highlights = { ...line.highlights, [action.part ?? ""]: action.color };
          break;
        }
        case "box": {
          const line = lines.get(action.target);
          if (line) {
            const progress = reducedMotion ? 1 : clamp01(elapsed / 500);
            line.boxes = [...line.boxes.filter((b) => b.part !== (action.part ?? "")), { part: action.part ?? "", color: action.color, progress }];
          }
          break;
        }
        case "fade": {
          const line = lines.get(action.target);
          if (line) line.opacity = action.to ?? 0.35;
          const label = labels.get(action.target);
          if (label) labels.delete(action.target);
          break;
        }
        case "label": {
          labels.set(action.id, {
            id: action.id,
            text: action.text,
            target: action.target,
            part: action.part ?? "",
            side: action.side ?? "below",
            color: action.color ?? "chalk",
            progress: reducedMotion ? 1 : clamp01(elapsed / 400),
          });
          break;
        }
      }
    }
  }
  return {
    lines: [...lines.values()].sort((a, b) => a.row - b.row || a.col - b.col),
    labels: [...labels.values()],
  };
}

/** Check a script for references that would silently do nothing. */
export function validateScript(script: LessonScript): string[] {
  const problems: string[] = [];
  const lines = new Set<string>();
  const labels = new Set<string>();
  script.steps.forEach((step, s) => {
    const where = `step ${s + 1} (${step.id})`;
    const words = spokenWords(step.narration).length;
    for (const action of step.actions) {
      if ("word" in action.at && (action.at.word < 0 || action.at.word >= Math.max(words, 1))) {
        problems.push(`${where}: anchor word ${action.at.word} is past the ${words} spoken words`);
      }
      switch (action.type) {
        case "write":
          if (lines.has(action.id)) problems.push(`${where}: line ${action.id} is written twice`);
          lines.add(action.id);
          break;
        case "label":
          if (!lines.has(action.target)) problems.push(`${where}: label ${action.id} targets ${action.target}, not on the board yet`);
          labels.add(action.id);
          break;
        case "fade":
          if (!lines.has(action.target) && !labels.has(action.target)) {
            problems.push(`${where}: fade targets ${action.target}, not on the board yet`);
          }
          break;
        default:
          if (!lines.has(action.target)) {
            problems.push(`${where}: ${action.type} targets ${action.target}, not on the board yet`);
          }
      }
    }
    if (step.checkpoint && step.checkpoint.options.filter((o) => o.correct).length !== 1) {
      problems.push(`${where}: checkpoint needs exactly one correct option`);
    }
  });
  return problems;
}
