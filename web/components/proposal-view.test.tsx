import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ProposalView, Warnings, editsFor } from "@/components/proposal-view";
import type { Proposal } from "@/lib/types";

describe("ProposalView (FR-8)", () => {
  it("renders goals as structure: links, targets and tasks", () => {
    render(
      <ProposalView
        proposal={{
          reply: "Here's the week.",
          goals: [
            {
              description: "Ship pricing",
              project_id: 1,
              project_name: "Website",
              habit_id: null,
              habit_name: null,
              target_count: 1,
              tasks: [
                { id: 5, title: "Update pricing copy" },
                { id: 6, title: "Add FAQ" },
              ],
            },
            {
              description: "Gym",
              project_id: null,
              project_name: null,
              habit_id: 2,
              habit_name: "Gym",
              target_count: 3,
              tasks: [],
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("1. Ship pricing")).toBeTruthy();
    expect(screen.getByText("project: Website")).toBeTruthy();
    expect(screen.getByText("target 1 of 2")).toBeTruthy();
    expect(screen.getByText("· Update pricing copy")).toBeTruthy();
    expect(screen.getByText("habit: Gym")).toBeTruthy();
    expect(screen.getByText("target 3×")).toBeTruthy();
  });

  it("says so when the model proposed no goals", () => {
    render(<ProposalView proposal={{ reply: "What matters most?", goals: [] }} />);
    expect(screen.getByText(/No goals proposed yet/)).toBeTruthy();
  });
});

describe("Warnings (S-6)", () => {
  it("lists every correction", () => {
    render(<Warnings warnings={["'Ship pricing': task 999 is not in the unassigned backlog, removed"]} />);
    expect(screen.getByText(/task 999/)).toBeTruthy();
  });

  it("renders nothing without warnings", () => {
    const { container } = render(<Warnings warnings={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("ProposalView editing", () => {
  const proposal: Proposal = {
    reply: "ok",
    goals: [
      {
        description: "Ship pricing",
        project_id: 1,
        project_name: "Website",
        habit_id: null,
        habit_name: null,
        target_count: null,
        tasks: [
          { id: 5, title: "Update pricing copy" },
          { id: 6, title: "Add FAQ" },
        ],
      },
    ],
  };

  it("starts with every goal included as proposed", () => {
    expect(editsFor(proposal)).toEqual([{ include: true, description: "Ship pricing", target: null }]);
    expect(editsFor(null)).toEqual([]);
  });

  it("reports unticking, rewording and re-targeting, capping the target at the task count", () => {
    const onEdit = vi.fn();
    render(<ProposalView proposal={proposal} edits={editsFor(proposal)} onEdit={onEdit} />);

    fireEvent.click(screen.getByRole("checkbox", { name: "Include goal 1" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Goal 1" }), { target: { value: "Ship it" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Target for goal 1" }), { target: { value: "9" } });

    expect(onEdit.mock.calls).toEqual([
      [0, { include: false, description: "Ship pricing", target: null }],
      [0, { include: true, description: "Ship it", target: null }],
      [0, { include: true, description: "Ship pricing", target: 2 }],
    ]);
  });
});

