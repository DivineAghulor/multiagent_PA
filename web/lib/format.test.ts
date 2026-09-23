import { describe, expect, it } from "vitest";
import { addDays, mondayOf } from "@/lib/format";

describe("date arithmetic", () => {
  it("runs east of UTC, where the old bug showed", () => {
    expect(new Date("2026-09-14T00:00:00").getTimezoneOffset()).toBeLessThan(0);
  });

  it("addDays keeps the calendar date", () => {
    expect(addDays("2026-09-14", 0)).toBe("2026-09-14");
    expect(addDays("2026-09-14", 7)).toBe("2026-09-21");
    expect(addDays("2026-09-14", -7)).toBe("2026-09-07");
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
  });

  it("mondayOf finds the week's Monday", () => {
    expect(mondayOf("2026-09-14")).toBe("2026-09-14"); // Monday
    expect(mondayOf("2026-09-17")).toBe("2026-09-14"); // Thursday
    expect(mondayOf("2026-09-20")).toBe("2026-09-14"); // Sunday
  });
});
