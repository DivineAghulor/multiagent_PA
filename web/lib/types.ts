// Mirrors api/schemas.py. Kept hand-written rather than generated from the
// OpenAPI document: it is small, and a hand-written copy makes a backend shape
// change show up as a TypeScript error here instead of at runtime.

export type TaskStatus =
  | "backlog"
  | "todo"
  | "in_progress"
  | "blocked"
  | "done"
  | "cancelled";

/**
 * Derived from the importance/urgency pair, never set directly (§6.7 SCH-5).
 * Note that "medium" means either "urgent but not important" or "not rated at
 * all" — read the pair to tell those apart.
 */
export type TaskPriority = "low" | "medium" | "high" | "urgent";

export type ProjectStatus = "active" | "on_hold" | "completed" | "archived";
export type MilestoneStatus = "planned" | "in_progress" | "done";
export type HabitFrequency = "daily" | "weekly" | "weekdays" | "custom";
export type WeeklyGoalStatus =
  | "planned"
  | "in_progress"
  | "achieved"
  | "missed"
  | "carried_over";

export interface Task {
  id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  importance: number | null;
  urgency: number | null;
  project_id: number | null;
  milestone_id: number | null;
  weekly_goal_id: number | null;
  due_date: string | null;
  scheduled_for: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Milestone {
  id: number;
  project_id: number;
  name: string;
  description: string | null;
  status: MilestoneStatus;
  due_date: string | null;
  position: number | null;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  status: ProjectStatus;
  target_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  milestones: Milestone[];
  tasks: Task[];
}

export interface Habit {
  id: number;
  name: string;
  description: string | null;
  frequency: HabitFrequency;
  target_per_period: number;
  active: boolean;
}

export interface HabitLog {
  id: number;
  habit_id: number;
  log_date: string;
  completed: boolean;
  note: string | null;
}

export interface WeeklyGoal {
  id: number;
  week_start: string;
  description: string;
  status: WeeklyGoalStatus;
  project_id: number | null;
  habit_id: number | null;
  target_count: number | null;
  reviewed_at: string | null;
  review_notes: string | null;
}

export interface GoalProgress {
  goal: WeeklyGoal;
  kind: "habit" | "tasks" | "qualitative";
  completed: number;
  target: number | null;
  done: string[];
  outstanding: string[];
  status: WeeklyGoalStatus | null;
  achieved: boolean;
  headline: string;
  tasks: Task[];
  habit: Habit | null;
}

export interface WeeklyReview {
  week_start: string;
  summary: string;
  achieved_count: number;
  measurable_count: number;
  unplanned_count: number;
  generated_at: string;
}

export interface Week {
  week_start: string;
  week_end: string;
  goals: GoalProgress[];
  unplanned_done: Task[];
  achieved_count: number;
  measurable_count: number;
  facts: string;
  review: WeeklyReview | null;
}

export interface PlanningContext {
  week_start: string;
  backlog: Task[];
  projects: Project[];
  habits: Habit[];
  existing_goals: WeeklyGoal[];
  rendered: string;
}

export interface Health {
  status: "ok" | "degraded";
  database: boolean;
  provider: string;
  model: string;
  provider_key_configured: boolean;
  tracing: boolean;
  today: string;
}

/** The API's error envelope (api/errors.py). */
export type ApiErrorType =
  | "not_found"
  | "invalid_request"
  | "validation"
  | "session_expired"
  | "provider"
  | "internal";
