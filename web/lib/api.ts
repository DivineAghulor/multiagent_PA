import type {
  ApiErrorType,
  Habit,
  Health,
  PlanningContext,
  Project,
  ProjectDetail,
  Task,
  TaskStatus,
  Week,
  WeeklyReview,
} from "./types";

// Reads run in server components, so this stays on the server and is never
// bundled into client JS. NEXT_PUBLIC_API_BASE_URL is the browser-visible
// counterpart, for the mutations that arrive in W2.
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

async function get<T>(path: string, query?: Query): Promise<T> {
  let response: Response;
  try {
    // no-store: this is a single user's live data and every screen should
    // reflect the last write, not a cached render.
    response = await fetch(`${BASE_URL}${withQuery(path, query)}`, { cache: "no-store" });
  } catch (cause) {
    throw new ApiError(
      "unreachable",
      `Could not reach the API at ${BASE_URL}. Is it running?`,
      0,
    );
  }

  if (!response.ok) {
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
    throw new ApiError(type, message, response.status);
  }

  return (await response.json()) as T;
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
};
