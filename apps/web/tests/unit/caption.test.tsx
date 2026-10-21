import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Caption } from "@/components/lesson/Caption";
import type { NarrationSegment } from "@/lib/lesson/types";

const NARRATION: NarrationSegment[] = ["Let ", { math: "u = x^3 + 1", say: "u equal x cubed plus one" }, ", the inside."];

describe("Caption", () => {
  it("brightens words as they are spoken", () => {
    const { container, rerender } = render(<Caption narration={NARRATION} word={0} />);
    expect(screen.getByText("Let")).toHaveClass("text-text");
    expect(screen.getByText("the")).toHaveClass("text-muted");
    expect(container.querySelector(".katex")?.closest("span.transition-colors")).toHaveClass("text-muted");

    rerender(<Caption narration={NARRATION} word={7} />);
    expect(screen.getByText("the")).toHaveClass("text-text");
    expect(screen.getByText("inside.")).toHaveClass("text-muted");
    expect(container.querySelector(".katex")?.closest("span.transition-colors")).toHaveClass("text-text");
  });

  it("renders math with KaTeX, not as plain text", () => {
    const { container } = render(<Caption narration={NARRATION} word={9} />);
    expect(container.querySelector(".katex")).not.toBeNull();
    // The visible layer is typeset; the TeX source only lives in the hidden MathML annotation.
    expect(container.querySelector(".katex-html")?.textContent).not.toContain("^");
  });
});
