import type {
  AnswerResponse,
  Catalog,
  Preview,
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

const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

export const api = {
  me: () => request<User>("/auth/me"),
  session: () => request<{ user: User | null }>("/auth/session"),
  signup: (email: string, password: string, display_name: string) =>
    post<User>("/auth/signup", { email, password, display_name }),
  login: (email: string, password: string) => post<User>("/auth/login", { email, password }),
  logout: () => post<void>("/auth/logout"),

  catalog: () => request<Catalog>("/catalog"),
  preview: (text: string, variables: string[], signal?: AbortSignal) =>
    request<Preview>("/math/preview", { method: "POST", body: JSON.stringify({ text, variables }), signal }),

  worksheets: () => request<{ worksheets: WorksheetSummary[] }>("/practice/worksheets"),
  worksheet: (id: string) => request<Worksheet>(`/practice/worksheets/${id}`),
  createWorksheet: (skill_ids: string[], count?: number) =>
    post<Worksheet>("/practice/worksheets", { skill_ids, count }),
  answer: (itemId: string, answer: string, duration_ms?: number) =>
    post<AnswerResponse>(`/practice/items/${itemId}/answer`, { answer, duration_ms }),
  hint: (itemId: string, level: number) => post<{ item: WorksheetItem }>(`/practice/items/${itemId}/hint`, { level }),
  similar: (itemId: string) =>
    post<{ item: WorksheetItem; stats: WorksheetStats }>(`/practice/items/${itemId}/similar`),
};
