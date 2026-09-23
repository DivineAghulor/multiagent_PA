import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HabitDays } from "@/components/week-controls";
import { actions } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...real,
    actions: { ...real.actions, logHabit: vi.fn(), unlogHabit: vi.fn() },
  };
});

const MONDAY = "2026-09-14";
const WEDNESDAY = "2026-09-16";

/** The day button at an offset from Monday. */
function day(offset: number) {
  return screen.getAllByRole("button")[offset] as HTMLButtonElement;
}

describe("HabitDays (FR-16/17)", () => {
  it("shows seven days with logged ones pressed and future ones disabled", () => {
    render(<HabitDays habitId={3} weekStart={MONDAY} logged={[MONDAY]} today={WEDNESDAY} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(7);
    expect(buttons[0].getAttribute("aria-pressed")).toBe("true");
    expect(buttons[1].getAttribute("aria-pressed")).toBe("false");
    expect(buttons.map((b) => (b as HTMLButtonElement).disabled)).toEqual([
      false, false, false, true, true, true, true,
    ]);
  });

  it("ticking an unlogged day logs it", async () => {
    vi.mocked(actions.logHabit).mockResolvedValue({
      id: 1, habit_id: 3, log_date: WEDNESDAY, completed: true, note: null,
    });
    render(<HabitDays habitId={3} weekStart={MONDAY} logged={[]} today={WEDNESDAY} />);

    fireEvent.click(day(2));

    await waitFor(() => expect(actions.logHabit).toHaveBeenCalledWith(3, WEDNESDAY));
    expect(actions.unlogHabit).not.toHaveBeenCalled();
  });

  it("unticking a logged day removes the log", async () => {
    vi.mocked(actions.unlogHabit).mockResolvedValue(undefined);
    render(<HabitDays habitId={3} weekStart={MONDAY} logged={[MONDAY]} today={WEDNESDAY} />);

    fireEvent.click(day(0));

    await waitFor(() => expect(actions.unlogHabit).toHaveBeenCalledWith(3, MONDAY));
  });

  it("with no known today, no day is disabled", () => {
    render(<HabitDays habitId={3} weekStart={MONDAY} logged={[]} today={null} />);
    expect(screen.getAllByRole("button").every((b) => !(b as HTMLButtonElement).disabled)).toBe(true);
  });
});
