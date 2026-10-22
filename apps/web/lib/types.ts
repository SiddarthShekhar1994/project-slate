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

export type ItemStatus = "up_next" | "retrying" | "cleared" | "cleared_after_retry" | "missed";

export type Mistake = {
  tag: string;
  label: string;
  category: string;
  step_id: string | null;
  step_title?: string | null;
  where_to_look: string;
};

export type SolutionStep = { id: string; title: string; latex: string };

/** How an answer is typed and read; everything but "expression" and "number" comes from course materials. */
export type AnswerKind = "expression" | "number" | "line" | "values" | "limit" | "antiderivative";

export type ProblemView = {
  id: string;
  prompt: string;
  variables: string[];
  answer_kind: AnswerKind;
  is_word: boolean;
  /** The problem's number on the student's sheet, for problems that came from one. */
  label?: string | null;
  hints: string[];
  solution: SolutionStep[] | null;
  answer_latex: string | null;
  source: SourceCitation | null;
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
  /** Study-pace exams only. */
  timer: { ends_at: string; now: string; time_limit_s: number | null } | null;
  /** Made from one uploaded sheet, in the sheet's order. */
  from_sheet?: boolean;
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

/** What Slate read from a photo of the student's work; it only fills the answer box. */
export type PhotoReading = {
  text: string;
  latex: string | null;
  error: string | null;
  confidence: number;
  method: "claude" | "tesseract";
};

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

// --- sources -------------------------------------------------------------------

export type SourceStatus = "processing" | "ready" | "failed";

export type SourceSkill = { id: string; title: string; score: number };

export type SourceChunkView = { id: string; heading: string; locator: string; excerpt: string; skills: SourceSkill[] };

export type SourceView = {
  id: string;
  title: string;
  filename: string;
  kind: string;
  kind_label: string;
  status: SourceStatus;
  error: string | null;
  pages: number | null;
  ocr: string | null;
  size_bytes: number;
  created_at: string;
  file_url: string;
  chunks: number;
  skills: SourceSkill[];
  used_for: { lessons: { id: string; title: string }[]; problems: number };
  reading: SourceReading | null;
  chunk_list?: SourceChunkView[];
};

export type SourceReading = {
  status: "none" | "pending" | "done" | "failed" | "no_key";
  error: string | null;
  problems: number;
  ready: number;
  topics: { id: string | null; title: string; builtin: boolean; problems: number; ready: number }[];
  not_checked: { label: string | null; kind: string; reason: string; statement: string }[];
};

/** Where Slate is with writing a topic's lesson or problems. */
export type BuildState = "done" | "writing" | "failed" | "none" | "needs_key";

export type TopicCard = {
  id: string;
  title: string;
  summary: string;
  builtin: boolean;
  origin: "builtin" | "upload" | "added";
  on_dashboard: boolean;
  mastery: number | null;
  status: MasteryStatus;
  lessons: number;
  problems: number;
  lesson: BuildState;
  lesson_error: string | null;
  practice: BuildState;
  practice_error: string | null;
  sources: { id: string; title: string }[];
};

export type TopicSuggestion = { title: string; summary: string; builtin: boolean };

export type Dashboard = { topics: TopicCard[]; suggestions: TopicSuggestion[]; claude: boolean };

export type TopicProblem = {
  id: string;
  label: string | null;
  statement: string;
  kind: string;
  difficulty: number;
  origin: "sheet" | "variant";
  source: { id: string; title: string } | null;
  status: "ready" | "unchecked" | "unsupported";
  reason: string;
  result: "solved" | "missed" | "new";
};

export type TopicView = Omit<TopicCard, "lessons"> & {
  formula: Formula | null;
  lessons: LessonSummary[];
  problem_list: TopicProblem[];
  worksheets: WorksheetSummary[];
  mistakes: { tag: string; label: string; count: number; example: string }[];
};

export type SourceCitation = { source_id: string; title: string; kind: string; locator: string };

export type SkillProgress = {
  id: string;
  title: string;
  summary: string;
  mastery: number | null;
  status: "new" | "learning" | "practiced" | "mastered";
  attempts: number;
  first_try_rate: number | null;
  last_practiced_at: string | null;
  due_at: string | null;
  prerequisites: string[];
  /** False for topics from the student's uploads, which have practice but no lessons yet. */
  lessons?: boolean;
};

export type CourseProgress = {
  id: string;
  title: string;
  units: { id: string; title: string; skills: SkillProgress[] }[];
};

export type RankedMistake = {
  tag: string;
  label: string;
  description: string;
  category: string;
  category_label: string;
  count: number;
  recent: number;
  score: number;
  last_seen_at: string;
  skills: { id: string; title: string; count: number }[];
  example: string;
};

export type ReviewEntry = {
  skill: { id: string; title: string };
  due_at: string;
  interval_days: number;
  repetitions: number;
  lapses: number;
  last_reviewed_at: string;
  overdue_days: number;
};

export type ReviewQueue = { due: ReviewEntry[]; upcoming: ReviewEntry[] };

export type ProgressView = {
  summary: { answers: number; problems_cleared: number; first_try_rate: number | null };
  courses: CourseProgress[];
  mistakes: RankedMistake[];
  review: ReviewQueue;
};

export type FormulaSheet = {
  units: {
    id: string;
    title: string;
    course: string;
    entries: {
      skill: { id: string; title: string };
      title: string;
      latex: string;
      note: string;
      source: SourceCitation | null;
    }[];
  }[];
  notation: string | null;
};

export type ExamWeight = {
  skill_id: string;
  weight: number;
  source: { title: string; locator: string; line: string } | null;
};

export type ExamPace = "exam" | "study";

export type ExamItem = {
  id: string;
  position: number;
  skill: { id: string; title: string };
  difficulty: number;
  difficulty_label: string;
  problem: { id: string; prompt: string; variables: string[]; answer_kind: AnswerKind; is_word: boolean };
  answer: string | null;
  result: {
    status: "correct" | "incorrect" | "blank";
    attempt: AttemptView | null;
    answer_latex: string;
    solution: SolutionStep[];
  } | null;
};

export type ExamView = {
  id: string;
  title: string;
  pace: ExamPace;
  weights: Record<string, number>;
  time_limit_s: number;
  ends_at: string;
  now: string;
  time_used_s: number | null;
  finished: boolean;
  completed_at: string | null;
  skills: { id: string; title: string }[];
  items: ExamItem[];
  stats: {
    total: number;
    answered: number;
    correct: number | null;
    incorrect: number | null;
    blank: number | null;
    by_skill: { skill: { id: string; title: string }; total: number; correct: number }[] | null;
  };
};

export type ExamCreated =
  | { id: string; pace: "exam"; exam: ExamView }
  | { id: string; pace: "study"; worksheet: Worksheet };

// --- desktop app settings ------------------------------------------------------

export type KeyName = "anthropic_api_key" | "elevenlabs_api_key" | "openai_api_key";

export type AppSettings = {
  keys: Record<KeyName, { set: boolean; hint: string }>;
  tts_provider: "" | "elevenlabs" | "openai";
  stt_provider: "" | "openai" | "elevenlabs";
  active: { claude: boolean; voice: string | null; transcription: string | null };
  data_dir: string;
};

/** Omitted fields stay as they are; an empty string clears a setting. */
export type SettingsChanges = Partial<Record<KeyName | "tts_provider" | "stt_provider", string>>;
