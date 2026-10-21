/**
 * Lesson script format, shared by the hand-written scripts, the generator in
 * apps/api (services/lesson_gen) and the player.
 *
 * A lesson is a list of steps. Each step has narration (what the voice says),
 * a list of timed board actions, and optionally a "pause and predict"
 * checkpoint at its end. Actions are anchored to word indices in the spoken
 * narration, so the same script plays in sync with any voice: word
 * timestamps from the TTS provider (or an estimate when the voice is off) turn
 * anchors into milliseconds.
 */

export type BoardColor = "chalk" | "yellow" | "mint";

/** A point in a step: the start of a spoken word, or a fixed offset. */
export type Anchor = { word: number } | { ms: number };

/** Narration is prose plus math. Math has a spoken form for the voice. */
export type NarrationSegment = string | { math: string; say: string };

export type WriteAction = {
  type: "write";
  id: string;
  at: Anchor;
  latex: string;
  row: number;
  /** Indent in board columns (0 to 11). */
  col?: number;
  size?: "md" | "lg";
  /** How long the chalk takes to write it, in ms at 1x. */
  duration?: number;
};

/** Handwritten note in Caveat next to something already on the board. */
export type LabelAction = {
  type: "label";
  id: string;
  at: Anchor;
  text: string;
  target: string;
  part?: string;
  side?: "above" | "below" | "right";
  color?: BoardColor;
};

/** Colour a written line or a named part of it (\htmlClass{slate-part-NAME}{...}). */
export type HighlightAction = { type: "highlight"; at: Anchor; target: string; part?: string; color: BoardColor };

/** Draw a box around a line or part. */
export type BoxAction = { type: "box"; at: Anchor; target: string; part?: string; color: BoardColor };

/** Dim something that is no longer the focus. */
export type FadeAction = { type: "fade"; at: Anchor; target: string; to?: number };

export type BoardAction = WriteAction | LabelAction | HighlightAction | BoxAction | FadeAction;

/**
 * A math fact a step states, in Slate's answer syntax, so the backend can
 * check it with SymPy before the lesson is served.
 */
export type Claim =
  | { kind: "derivative"; of: string; var: string; equals: string }
  | { kind: "equal"; left: string; right: string; vars: string[] };

/**
 * ``value`` is the option in answer syntax; the verifier proves the correct one
 * and refutes the rest. ``say`` is how a screen reader reads it, since a
 * button's name is not computed from the KaTeX inside it.
 */
export type CheckpointOption = { id: string; latex: string; value: string; say: string; correct: boolean; why: string };

/** "Pause and predict": asked at the end of the step, before the next step is revealed. */
export type Checkpoint = { prompt: string; options: CheckpointOption[]; expect: Claim };

export type LessonStep = {
  id: string;
  title: string;
  narration: NarrationSegment[];
  actions: BoardAction[];
  checkpoint?: Checkpoint;
  claims?: Claim[];
  sources?: string[];
};

export type LessonSource = { id: string; title: string; locator: string };

export type LessonScript = {
  id: string;
  version: 1;
  skillId: string;
  title: string;
  summary: string;
  sources: LessonSource[];
  steps: LessonStep[];
};

/** Start and end of each spoken word, in ms from the start of the step at 1x. */
export type WordTiming = { text: string; start: number; end: number };
