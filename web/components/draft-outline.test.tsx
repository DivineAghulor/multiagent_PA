import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DraftOutline } from "@/components/draft-outline";
import { draft } from "@/test/fixtures";

const none = { milestones: new Set<string>(), tasks: new Set<string>() };

describe("DraftOutline (FR-13)", () => {
  it("marks existing and new items and shows what's already in the DB", () => {
    render(<DraftOutline draft={draft()} excluded={none} onToggle={() => {}} />);

    expect(screen.getByText("existing")).toBeTruthy();
    expect(screen.getByText("new")).toBeTruthy();
    expect(screen.getByText(/Draft wireframes/).textContent).toContain("already in project");
    expect(screen.getByText("attach existing")).toBeTruthy();
  });

  it("offers an include box for new milestones but not existing ones", () => {
    render(<DraftOutline draft={draft()} excluded={none} onToggle={() => {}} />);

    expect(screen.queryByRole("checkbox", { name: "Include milestone Design approved" })).toBeNull();
    expect(screen.getByRole("checkbox", { name: "Include milestone Launched" })).toBeTruthy();
  });

  it("reports toggles by ref", () => {
    const onToggle = vi.fn();
    render(<DraftOutline draft={draft()} excluded={none} onToggle={onToggle} />);

    fireEvent.click(screen.getByRole("checkbox", { name: "Include milestone Launched" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Include task Point DNS" }));

    expect(onToggle.mock.calls).toEqual([
      ["milestones", "M2"],
      ["tasks", "T4"],
    ]);
  });

  it("an excluded milestone takes its tasks with it", () => {
    render(
      <DraftOutline
        draft={draft()}
        excluded={{ milestones: new Set(["M2"]), tasks: new Set() }}
        onToggle={() => {}}
      />,
    );
    const dns = screen.getByRole("checkbox", { name: "Include task Point DNS" }) as HTMLInputElement;
    expect(dns.checked).toBe(false);
    expect(dns.disabled).toBe(true);
  });

  it("warns about a new milestone with no tasks", () => {
    const d = draft();
    d.milestones[1].tasks = [];
    render(<DraftOutline draft={d} excluded={none} onToggle={() => {}} />);
    expect(screen.getByText(/needs at least one/)).toBeTruthy();
  });
});
