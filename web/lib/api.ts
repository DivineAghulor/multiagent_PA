import type {
  ApiErrorType,
  DecompositionResult,
  DecompositionSession,
  Habit,
  HabitFrequency,
  HabitLog,
  Health,
  Milestone,
  MilestoneStatus,
  PlanningContext,
  PlanningSession,
  Project,
  ProjectDetail,
  ProjectStatus,
  ReviewDraft,
  Task,
  TaskStatus,
  Week,
  WeeklyGoal,
  WeeklyReview,
} from "./types";

// Reads run in server components and use API_BASE_URL, which stays on the
// server. Writes run in the browser, where only NEXT_PUBLIC_API_BASE_URL
// exists (Next inlines NEXT_PUBLIC_* at build time; the other is undefined).
const BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8000";

/** A failure the API described in its envelope, or the fact it was unreachable. */
export class ApiError extends Error {
  readonly type: ApiErrorType | "unreachable";
  readonly status: number;

  constructor(type: ApiErrorType | "unreachable", message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.type = type;
    this.status = status;
  }

  /** True when the backend itself is down, as opposed to rejecting the request. */
  get isUnreachable(): boolean {
    return this.type === "unreachable";
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

async function parseError(response: Response): Promise<ApiError> {
  let type: ApiErrorType = "internal";
  let message = `Request failed with status ${response.status}`;
  try {
    const body = await response.json();
    if (body?.error) {
      type = body.error.type ?? type;
      message = body.error.message ?? message;
    }
  } catch {
    // A non-JSON body (a proxy error page, say) leaves the defaults above.
  }
  return new ApiError(type, message, response.status);
}

export interface RequestOptions {
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
}

/** Sends one request and returns the raw response once it's known to be OK. */
export async function send(
  method: string,
  path: string,
  { query, body, signal }: RequestOptions = {},
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${withQuery(path, query)}`, {
      method,
      // no-store: this is a single user's live data and every screen should
      // reflect the last write, not a cached render.
      cache: "no-store",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (cause) {
    // An abort is the user's choice, not an outage; let callers see it as-is.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(
      "unreachable",
      `Could not reach the API at ${BASE_URL}. Is it running?`,
      0,
    );
  }
  if (!response.ok) throw await parseError(response);
  return response;
}

async function request<T>(method: string, path: string, options?: RequestOptions): Promise<T> {
  const response = await send(method, path, options);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

function get<T>(path: string, query?: Query): Promise<T> {
  return request<T>("GET", path, { query });
}

export const api = {
  health: () => get<Health>("/api/health"),

  tasks: (query?: {
    status?: TaskStatus;
    project_id?: number;
    milestone_id?: number;
    weekly_goal_id?: number;
  }) => get<Task[]>("/api/tasks", query),

  projects: (query?: { status?: string }) => get<Project[]>("/api/projects", query),
  project: (id: number) => get<ProjectDetail>(`/api/projects/${id}`),

  habits: (query?: { active_only?: boolean }) => get<Habit[]>("/api/habits", query),

  currentWeek: () => get<Week>("/api/weeks/current"),
  week: (weekStart: string) => get<Week>(`/api/weeks/${weekStart}`),

  reviews: (query?: { limit?: number }) => get<WeeklyReview[]>("/api/reviews", query),

  planningContext: (query?: { week_start?: string }) =>
    get<PlanningContext>("/api/planning/context", query),
  planningSession: (id: string) => get<PlanningSession>(`/api/planning/sessions/${id}`),
  decompositionSession: (id: string) =>
    get<DecompositionSession>(`/api/decomposition/sessions/${id}`),
};

export interface TaskEdit {
  title?: string;
  description?: string | null;
  due_date?: string | null;
  project_id?: number | null;
  milestone_id?: number | null;
}

export interface ProjectEdit {
  name?: string;
  description?: string | null;
  status?: ProjectStatus;
  target_date?: string | null;
}

export interface HabitEdit {
  name?: string;
  description?: string | null;
  frequency?: HabitFrequency;
  target_per_period?: number;
  active?: boolean;
}

/**
 * Writes, called from client components. After one succeeds the caller runs
 * `router.refresh()` so the server-rendered screen re-reads the truth rather
 * than the client patching its own copy.
 *
 * Calls marked "model call" spend provider tokens and can take a while; they
 * accept an AbortSignal so the UI can offer a cancel (NFR-1).
 */
export const actions = {
  // Backlog (model call)
  capture: (text: string, signal?: AbortSignal) =>
    request<Task[]>("POST", "/api/backlog/capture", { body: { text }, signal }),

  // Tasks
  updateTask: (id: number, edit: TaskEdit) =>
    request<Task>("PATCH", `/api/tasks/${id}`, { body: edit }),
  rateTask: (id: number, importance: number, urgency: number) =>
    request<Task>("PATCH", `/api/tasks/${id}/priority`, { body: { importance, urgency } }),
  setTaskStatus: (id: number, status: TaskStatus) =>
    request<Task>("PUT", `/api/tasks/${id}/status`, { body: { status } }),
  completeTask: (id: number) => request<Task>("POST", `/api/tasks/${id}/complete`),
  reopenTask: (id: number) => request<Task>("POST", `/api/tasks/${id}/reopen`),
  scheduleTask: (id: number, scheduledFor: string | null) =>
    request<Task>("PUT", `/api/tasks/${id}/schedule`, { body: { scheduled_for: scheduledFor } }),
  deleteTask: (id: number) => request<void>("DELETE", `/api/tasks/${id}`),

  // Projects and milestones
  createProject: (body: { name: string; description?: string | null; target_date?: string | null }) =>
    request<Project>("POST", "/api/projects", { body }),
  updateProject: (id: number, edit: ProjectEdit) =>
    request<Project>("PATCH", `/api/projects/${id}`, { body: edit }),
  archiveProject: (id: number) => request<Project>("POST", `/api/projects/${id}/archive`),
  setMilestoneStatus: (id: number, status: MilestoneStatus) =>
    request<Milestone>("PATCH", `/api/milestones/${id}`, { body: { status } }),

  // Habits
  createHabit: (body: {
    name: string;
    description?: string | null;
    frequency: HabitFrequency;
    target_per_period: number;
  }) => request<Habit>("POST", "/api/habits", { body }),
  updateHabit: (id: number, edit: HabitEdit) =>
    request<Habit>("PATCH", `/api/habits/${id}`, { body: edit }),
  deactivateHabit: (id: number) => request<Habit>("POST", `/api/habits/${id}/deactivate`),
  logHabit: (id: number, date: string) =>
    request<HabitLog>("POST", `/api/habits/${id}/logs`, { body: { date } }),
  unlogHabit: (id: number, date: string) =>
    request<void>("DELETE", `/api/habits/${id}/logs/${date}`),

  // Planning sessions
  startPlanning: (weekStart?: string) =>
    request<PlanningSession>("POST", "/api/planning/sessions", {
      body: weekStart ? { week_start: weekStart } : {},
    }),
  // model call
  planningMessage: (id: string, text: string, signal?: AbortSignal) =>
    request<PlanningSession>("POST", `/api/planning/sessions/${id}/messages`, {
      body: { text },
      signal,
    }),
  /** Without `goals`, confirms the proposal as it stands; with them, only
   * those goals (by index), reworded and re-targeted. */
  confirmPlanning: (
    id: string,
    goals?: { index: number; description: string; target_count: number | null }[],
  ) =>
    request<WeeklyGoal[]>("POST", `/api/planning/sessions/${id}/confirm`, {
      body: goals ? { goals } : {},
    }),
  cancelPlanning: (id: string) => request<void>("DELETE", `/api/planning/sessions/${id}`),

  // Decomposition sessions (turns stream over SSE; see lib/sse.ts)
  startDecomposition: (
    body: { project_id: number } | { name: string; description?: string | null },
  ) => request<DecompositionSession>("POST", "/api/decomposition/sessions", { body }),
  confirmDecomposition: (
    id: string,
    exclude: { milestone_refs: string[]; task_refs: string[] },
  ) =>
    request<DecompositionResult>("POST", `/api/decomposition/sessions/${id}/confirm`, {
      body: {
        exclude_milestone_refs: exclude.milestone_refs,
        exclude_task_refs: exclude.task_refs,
      },
    }),
  cancelDecomposition: (id: string) =>
    request<void>("DELETE", `/api/decomposition/sessions/${id}`),

  // Week review
  // model call; writes nothing
  draftReview: (weekStart: string, signal?: AbortSignal) =>
    request<ReviewDraft>("POST", `/api/weeks/${weekStart}/review/draft`, { signal }),
  saveReview: (weekStart: string, summary: string | null) =>
    request<Week>("POST", `/api/weeks/${weekStart}/review`, { body: { summary } }),
  carryOver: (goalId: number, newWeekStart: string) =>
    request<WeeklyGoal>("POST", `/api/weekly-goals/${goalId}/carry-over`, {
      body: { new_week_start: newWeekStart },
    }),
};
