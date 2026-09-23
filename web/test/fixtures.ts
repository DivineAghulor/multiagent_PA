import type { Draft, Task } from "@/lib/types";

export function task(overrides: Partial<Task> = {}): Task {
  return {
    id: 1,
    title: "Fix login bug",
    description: null,
    status: "backlog",
    priority: "medium",
    importance: null,
    urgency: null,
    project_id: null,
    milestone_id: null,
    weekly_goal_id: null,
    due_date: null,
    scheduled_for: null,
    completed_at: null,
    created_at: "2026-09-16T10:00:00+00:00",
    updated_at: "2026-09-16T10:00:00+00:00",
    ...overrides,
  };
}

export function draft(overrides: Partial<Draft> = {}): Draft {
  return {
    project_name: "Website",
    project_description: null,
    project_id: 7,
    milestones: [
      {
        ref: "M1",
        name: "Design approved",
        description: null,
        due_date: null,
        existing_id: 11,
        existing_task_titles: ["Draft wireframes"],
        tasks: [{ ref: "T3", title: "Write copy", description: null, existing_task_id: 42 }],
      },
      {
        ref: "M2",
        name: "Launched",
        description: "Live on the domain",
        due_date: "2026-11-01",
        existing_id: null,
        existing_task_titles: [],
        tasks: [
          { ref: "T4", title: "Point DNS", description: null, existing_task_id: null },
          { ref: "T5", title: "Announce", description: null, existing_task_id: null },
        ],
      },
    ],
    eligible_tasks: [],
    new_task_count: 2,
    ...overrides,
  };
}
