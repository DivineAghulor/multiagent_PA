import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RatingQueue } from "@/components/rating";
import { actions } from "@/lib/api";
import { task } from "@/test/fixtures";

vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return { ...real, actions: { ...real.actions, rateTask: vi.fn() } };
});

const rateTask = vi.mocked(actions.rateTask);

function card(title: string) {
  return screen.getByText(title).closest("li") as HTMLElement;
}

describe("RatingQueue (FR-2)", () => {
  it("saves a rating and drops the task from the queue", async () => {
    const first = task({ id: 1, title: "Fix login bug" });
    rateTask.mockResolvedValue({ ...first, importance: 4, urgency: 3, priority: "urgent" });
    render(<RatingQueue tasks={[first, task({ id: 2, title: "Email Sam" })]} />);

    const row = within(card("Fix login bug"));
    fireEvent.click(row.getByRole("radio", { name: "Importance 4" }));
    fireEvent.click(row.getByRole("radio", { name: "Urgency 3" }));
    fireEvent.click(row.getByRole("button", { name: "Save rating" }));

    await waitFor(() => expect(screen.queryByText("Fix login bug")).toBeNull());
    expect(rateTask).toHaveBeenCalledWith(1, 4, 3);
    expect(screen.getByText("Email Sam")).toBeTruthy();
  });

  it("can't save until both axes are chosen", () => {
    render(<RatingQueue tasks={[task()]} />);
    const save = screen.getByRole("button", { name: "Save rating" }) as HTMLButtonElement;

    expect(save.disabled).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: "Importance 2" }));
    expect(save.disabled).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: "Urgency 1" }));
    expect(save.disabled).toBe(false);
  });

  it("skipping leaves the task unrated and makes no call", () => {
    const onEmpty = vi.fn();
    render(<RatingQueue tasks={[task()]} onEmpty={onEmpty} />);

    fireEvent.click(screen.getByRole("button", { name: "Skip" }));

    expect(rateTask).not.toHaveBeenCalled();
    expect(onEmpty).toHaveBeenCalledOnce();
    expect(screen.queryByText("Fix login bug")).toBeNull();
  });

  it("keeps the task queued and shows the error when saving fails", async () => {
    const { ApiError } = await import("@/lib/api");
    rateTask.mockRejectedValue(new ApiError("validation", "importance: must be 1-4", 422));
    render(<RatingQueue tasks={[task()]} />);

    fireEvent.click(screen.getByRole("radio", { name: "Importance 4" }));
    fireEvent.click(screen.getByRole("radio", { name: "Urgency 4" }));
    fireEvent.click(screen.getByRole("button", { name: "Save rating" }));

    expect((await screen.findByRole("alert")).textContent).toContain("must be 1-4");
    expect(screen.getByText("Fix login bug")).toBeTruthy();
  });
});
