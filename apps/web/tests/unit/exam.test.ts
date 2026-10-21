import { describe, expect, it } from "vitest";
import { allocate, planDifficulties, timeLimitSeconds } from "@/lib/exam";
import { clock, dueLabel, minutesText } from "@/lib/format";

// The same cases as apps/api/tests/test_review_and_exam_rules.py, so the
// builder's preview can't drift from the exam the server builds.
describe("allocate", () => {
  it("follows the weights", () => {
    expect(allocate({ a: 50, b: 30, c: 20 }, 10)).toEqual({ a: 5, b: 3, c: 2 });
    expect(allocate({ a: 50, b: 30, c: 20 }, 8)).toEqual({ a: 4, b: 2, c: 2 });
  });
  it("gives every topic a problem when it can", () => {
    const out = allocate({ a: 95, b: 5 }, 6);
    expect(out.b).toBe(1);
    expect(out.a + out.b).toBe(6);
  });
  it("lets the heaviest topics win when problems are short", () => {
    expect(allocate({ a: 10, b: 60, c: 30 }, 2)).toEqual({ a: 0, b: 1, c: 1 });
    expect(allocate({ a: 0, b: 10 }, 3)).toEqual({ a: 0, b: 3 });
  });
});

describe("planDifficulties", () => {
  it("runs easy to hard like the server", () => {
    expect(planDifficulties([1, 2, 3, 4], 1)).toEqual([1]);
    expect(planDifficulties([1, 2, 3, 4], 2)).toEqual([1, 4]);
    expect(planDifficulties([1, 2, 3, 4], 3)).toEqual([1, 3, 4]);
    expect(planDifficulties([1, 2, 3, 4], 6)).toEqual([1, 1, 2, 3, 3, 4]);
    // Python rounds halves to even: 2.5 -> 2.
    expect(planDifficulties([1, 2, 3, 4, 5, 6], 3)).toEqual([1, 3, 6]);
  });
});

describe("timeLimitSeconds", () => {
  const minutes = { "1": 2, "2": 3, "3": 5, "4": 7 };
  it("adds minutes per difficulty and stretches study pace", () => {
    expect(timeLimitSeconds([1, 2, 3, 4], "exam", minutes, 1.5)).toBe(17 * 60);
    expect(timeLimitSeconds([1, 2, 3, 4], "study", minutes, 1.5)).toBe(26 * 60);
  });
});

describe("format", () => {
  const now = new Date(2026, 9, 21, 12, 0);
  it("labels due dates", () => {
    expect(dueLabel(new Date(2026, 9, 21, 11, 0).toISOString(), now)).toBe("Due now");
    expect(dueLabel(new Date(2026, 9, 19, 9, 0).toISOString(), now)).toBe("Overdue by 2 days");
    expect(dueLabel(new Date(2026, 9, 21, 18, 0).toISOString(), now)).toBe("Due today");
    expect(dueLabel(new Date(2026, 9, 22, 8, 0).toISOString(), now)).toBe("Due tomorrow");
    expect(dueLabel(new Date(2026, 9, 26, 8, 0).toISOString(), now)).toBe("Due in 5 days");
  });
  it("formats clocks and minutes", () => {
    expect(clock(245)).toBe("4:05");
    expect(clock(3729)).toBe("1:02:09");
    expect(clock(-3)).toBe("0:00");
    expect(minutesText(17 * 60)).toBe("17 minutes");
    expect(minutesText(65 * 60)).toBe("1 hour 5 minutes");
  });
});
