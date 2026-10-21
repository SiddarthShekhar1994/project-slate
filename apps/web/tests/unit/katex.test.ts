import { describe, expect, it } from "vitest";
import { renderLatex, splitMath } from "@/lib/katex";

describe("splitMath", () => {
  it("splits inline and display math", () => {
    expect(splitMath("Differentiate $f(x) = x^2$ now.")).toEqual([
      { kind: "text", value: "Differentiate " },
      { kind: "math", value: "f(x) = x^2", display: false },
      { kind: "text", value: " now." },
    ]);
    expect(splitMath("$$a$$ and $b$")).toEqual([
      { kind: "math", value: "a", display: true },
      { kind: "text", value: " and " },
      { kind: "math", value: "b", display: false },
    ]);
  });

  it("keeps escaped and unmatched dollars as text", () => {
    expect(splitMath("costs \\$5")).toEqual([{ kind: "text", value: "costs $5" }]);
    expect(splitMath("a $b")).toEqual([{ kind: "text", value: "a $b" }]);
  });
});

describe("renderLatex", () => {
  it("allows only slate highlight classes through htmlClass", () => {
    const ok = renderLatex("\\htmlClass{slate-yellow}{x^3+1}");
    expect(ok).toContain("slate-yellow");
    // Refused commands are shown as escaped error text, never as attributes.
    const blocked = renderLatex("\\htmlClass{evil onclick}{x}");
    expect(blocked).not.toMatch(/class="[^"]*evil/);
    const href = renderLatex("\\href{javascript:alert(1)}{x}");
    expect(href).not.toMatch(/href="javascript:/);
  });

  it("includes MathML for screen readers", () => {
    expect(renderLatex("x^2")).toContain("<math");
  });

  it("does not throw on bad input", () => {
    expect(() => renderLatex("\\frac{")).not.toThrow();
  });
});
