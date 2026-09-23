import type { BadgeTone } from "@/components/ui/badge";
import type { ProjectStatus, TaskPriority } from "./types";

export const PROJECT_STATUS_TONES: Record<ProjectStatus, BadgeTone> = {
  active: "green",
  on_hold: "amber",
  completed: "blue",
  archived: "neutral",
};

export const PRIORITY_TONES: Record<TaskPriority, BadgeTone> = {
  low: "neutral",
  medium: "blue",
  high: "amber",
  urgent: "red",
};
