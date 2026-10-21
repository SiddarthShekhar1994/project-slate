// @vitest-environment node
import { describe, expect, it } from "vitest";
import { safeNext } from "@/components/auth/AuthForm";

// The login page computes its redirect while rendering on the server, where
// there is no window.
describe("safeNext during server rendering", () => {
  it("works without a window", () => {
    expect(typeof window).toBe("undefined");
    expect(safeNext("/practice/abc?problem=2")).toBe("/practice/abc?problem=2");
    expect(safeNext("//evil.com")).toBe("/library");
    expect(safeNext(null)).toBe("/library");
  });
});
