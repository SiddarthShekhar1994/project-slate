import { describe, expect, it } from "vitest";
import { safeNext } from "@/components/auth/AuthForm";

const ORIGIN = "https://slate.example";

describe("safeNext", () => {
  it.each([
    ["/practice/abc?problem=2", "/practice/abc?problem=2"],
    ["/lesson/x?step=3#board", "/lesson/x?step=3#board"],
  ])("keeps same-origin paths: %s", (raw, expected) => {
    expect(safeNext(raw, ORIGIN)).toBe(expected);
  });

  it.each([null, "", "https://evil.com", "//evil.com", "/\\evil.com", "/\\/evil.com", "javascript:alert(1)", "\\\\evil.com"])(
    "rejects %s",
    (raw) => {
      expect(safeNext(raw, ORIGIN)).toBe("/dashboard");
    },
  );
});
