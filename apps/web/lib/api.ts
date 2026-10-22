import type {
  AnswerKind,
  AnswerResponse,
  AppSettings,
  SettingsChanges,
  AskAnswer,
  LessonSummary,
  LessonView,
  SourceView,
  StepAudio,
  Catalog,
  ExamCreated,
  ExamPace,
  ExamView,
  ExamWeight,
  FormulaSheet,
  MaterialTopic,
  PhotoReading,
  Preview,
  ProgressView,
  ReviewQueue,
  User,
  Worksheet,
  WorksheetItem,
  WorksheetStats,
  WorksheetSummary,
} from "./types";

/** Error from the API with the server's message, safe to show to the student. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Something went wrong. Try again.";
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

/** Multipart POST; the browser sets the boundary, so no Content-Type header here. */
async function send<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`/api${path}`, { method: "POST", body: form, credentials: "same-origin" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Something went wrong. Try again.";
    throw new ApiError(response.status, detail);
  }
  return body as T;
}

const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const api = {
  me: () => request<User>("/auth/me"),
  session: () => request<{ user: User | null; desktop: boolean }>("/auth/session"),
  signup: (email: string, password: string, display_name: string) =>
    post<User>("/auth/signup", { email, password, display_name }),
  login: (email: string, password: string) => post<User>("/auth/login", { email, password }),
  logout: () => post<void>("/auth/logout"),

  catalog: () => request<Catalog>("/catalog"),
  preview: (text: string, variables: string[], signal?: AbortSignal, answerKind: AnswerKind = "expression", units = false) =>
    request<Preview>("/math/preview", {
      method: "POST",
      body: JSON.stringify({ text, variables, answer_kind: answerKind, units }),
      signal,
    }),

  worksheets: () => request<{ worksheets: WorksheetSummary[] }>("/practice/worksheets"),
  worksheet: (id: string) => request<Worksheet>(`/practice/worksheets/${id}`),
  createWorksheet: (skill_ids: string[], count?: number) =>
    post<Worksheet>("/practice/worksheets", { skill_ids, count }),
  answer: (itemId: string, answer: string, duration_ms?: number) =>
    post<AnswerResponse>(`/practice/items/${itemId}/answer`, { answer, duration_ms }),
  hint: (itemId: string, level: number) => post<{ item: WorksheetItem }>(`/practice/items/${itemId}/hint`, { level }),
  similar: (itemId: string) =>
    post<{ item: WorksheetItem; stats: WorksheetStats }>(`/practice/items/${itemId}/similar`),

  lessons: () => request<{ lessons: LessonSummary[] }>("/lessons"),
  lesson: (id: string) => request<LessonView>(`/lessons/${id}`),
  stepAudio: (id: string, step: number, voice: string, signal?: AbortSignal) =>
    request<StepAudio>(`/lessons/${id}/steps/${step}/audio?voice=${encodeURIComponent(voice)}`, { signal }),
  ask: (id: string, step: number, question: string) => post<AskAnswer>(`/lessons/${id}/ask`, { step, question }),
  saveLessonProgress: (id: string, step: number) => post<void>(`/lessons/${id}/progress`, { step }),
  checkpoint: (id: string, step: number, option: string) =>
    post<{ correct: boolean }>(`/lessons/${id}/checkpoint`, { step, option }),
  generateLesson: (skill_id: string) => post<LessonSummary>("/lessons/generate", { skill_id }),

  progress: () => request<ProgressView>("/progress"),
  reviewQueue: () => request<ReviewQueue>("/progress/review"),
  startReview: (skill_ids?: string[]) => post<Worksheet>("/progress/review", { skill_ids: skill_ids ?? null }),
  formulaSheet: (skills: string[]) =>
    request<FormulaSheet>(`/progress/formula-sheet?skills=${encodeURIComponent(skills.join(","))}`),

  examWeights: (skills: string[]) =>
    request<{ weights: ExamWeight[]; minutes: Record<string, number>; study_factor: number }>(
      `/exam/weights?skills=${encodeURIComponent(skills.join(","))}`,
    ),
  createExam: (weights: Record<string, number>, count: number, pace: ExamPace) =>
    post<ExamCreated>("/exam", { weights, count, pace }),
  exam: (id: string) => request<ExamView>(`/exam/${id}`),
  saveExamAnswer: (itemId: string, answer: string) =>
    request<{ id: string; answer: string | null }>(`/exam/items/${itemId}/answer`, {
      method: "PUT",
      body: JSON.stringify({ answer }),
    }),
  finishExam: (id: string) => post<ExamView>(`/exam/${id}/finish`),

  settings: () => request<AppSettings>("/settings"),
  saveSettings: (changes: SettingsChanges) =>
    request<AppSettings>("/settings", { method: "PUT", body: JSON.stringify(changes) }),

  voiceStatus: () => request<{ available: boolean; provider: string | null }>("/voice"),
  transcribe: (audio: Blob) => {
    const form = new FormData();
    const ext = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
    form.append("audio", audio, `question.${ext}`);
    return send<{ text: string }>("/voice/transcribe", form);
  },
  readPhoto: (image: File, variables: string[], prompt: string) => {
    const form = new FormData();
    form.append("image", image);
    form.append("variables", variables.join(","));
    form.append("prompt", prompt.slice(0, 1000));
    return send<PhotoReading>("/math/photo", form);
  },

  sources: () => request<{ sources: SourceView[]; kinds: Record<string, string> }>("/sources"),
  source: (id: string) => request<SourceView>(`/sources/${id}`),
  deleteSource: (id: string) => request<void>(`/sources/${id}`, { method: "DELETE" }),
  reprocessSource: (id: string) => post<SourceView>(`/sources/${id}/reprocess`),
  readSource: (id: string) => post<SourceView>(`/sources/${id}/read`),
  practiceSheet: (id: string) => post<Worksheet>(`/sources/${id}/practice`),
  materialTopics: () => request<{ topics: MaterialTopic[] }>("/materials/topics"),
  uploadSource,
};

/**
 * Upload with progress. fetch() has no upload progress events, so this uses
 * XMLHttpRequest; the session cookie goes along because it is same-origin.
 */
function uploadSource(file: File, kind: string | null, onProgress?: (fraction: number) => void): Promise<SourceView> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    if (kind) form.append("kind", kind);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/sources");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      let body: { detail?: unknown } & Partial<SourceView> = {};
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = {};
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as SourceView);
      else reject(new ApiError(xhr.status, typeof body.detail === "string" ? body.detail : "Upload failed. Try again."));
    };
    xhr.onerror = () => reject(new ApiError(0, "Upload failed. Check your connection and try again."));
    xhr.send(form);
  });
}
