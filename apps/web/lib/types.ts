import type { LessonScript, WordTiming } from "./lesson/types";

/** Shapes returned by the FastAPI backend. Keep in step with apps/api/slate_api/services/practice.py. */

export type User = { id: string; email: string; display_name: string };

export type Formula = { title: string; latex: string; note: string };

export type SkillSummary = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  formula: Formula;
  difficulties: number[];
  prerequisites: string[];
};

export type Catalog = {
  difficulties: Record<string, string>;
  courses: {
    id: string;
    title: string;
    description: string;
    units: { id: string; title: string; skills: SkillSummary[] }[];
  }[];
};

export type ItemStatus = "up_next" | "retrying" | "cleared" | "cleared_after_retry";

export type Mistake = {
  tag: string;
  label: string;
  category: string;
  step_id: string | null;
  step_title?: string | null;
  where_to_look: string;
};

export type SolutionStep = { id: string; title: string; latex: string };

export type ProblemView = {
  id: string;
  prompt: string;
  variables: string[];
  answer_kind: "expression" | "number";
  is_word: boolean;
  hints: string[];
  solution: SolutionStep[] | null;
  answer_latex: string | null;
};

export type AttemptView = { id: string; status: "correct" | "incorrect"; latex: string; mistake: Mistake | null };

export type WorksheetItem = {
  id: string;
  position: number;
  status: ItemStatus;
  misses: number;
  problems_served: number;
  needs_new_problem: boolean;
  hint_level: number;
  skill: { id: string; title: string };
  difficulty: number;
  difficulty_label: string;
  problem: ProblemView;
  last_attempt: AttemptView | null;
};

export type WorksheetStats = {
  total: number;
  first_try: number;
  after_retry: number;
  retrying: number;
  up_next: number;
  misses: number;
  completed: boolean;
};

export type Worksheet = {
  id: string;
  title: string;
  mode: string;
  skills: { id: string; title: string }[];
  created_at: string;
  completed_at: string | null;
  items: WorksheetItem[];
  stats: WorksheetStats;
};

export type WorksheetSummary = {
  id: string;
  title: string;
  mode: string;
  updated_at: string;
  completed_at: string | null;
  stats: WorksheetStats;
};

export type Grade = {
  status: "correct" | "incorrect" | "invalid";
  latex: string | null;
  message: string | null;
  mistake: Mistake | null;
};

export type AnswerResponse = { grade: Grade; item: WorksheetItem; stats: WorksheetStats };

export type Preview = { ok: boolean; latex: string | null; error: string | null };

// --- lessons -------------------------------------------------------------------

export type MasteryStatus = "new" | "learning" | "practiced" | "mastered";

export type OutlineSkill = { id: string; title: string; mastery: number | null; status: MasteryStatus };

export type LessonSourceView = { id: string; title: string; kind: string; locator: string };

export type Voice = { id: string; label: string };

export type LessonView = {
  id: string;
  script: LessonScript;
  skill: { id: string; title: string };
  outline: { unit: string; skills: OutlineSkill[] };
  sources: LessonSourceView[];
  tts: { available: boolean; provider: string | null; voices: Voice[]; default_voice: string | null };
  resume_step: number;
};

export type LessonSummary = {
  id: string;
  title: string;
  skill: { id: string; title: string };
  kind: "builtin" | "generated";
  steps: number;
  resume_step: number;
  last_opened: string | null;
  sources: number;
};

export type StepAudio =
  | { status: "ok"; url: string; words: WordTiming[]; duration_ms: number }
  | { status: "unavailable"; reason: string };

export type AskAnswer = { answer: string; verified: boolean; notes: string[] };
