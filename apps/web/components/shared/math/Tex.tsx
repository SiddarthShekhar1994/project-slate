import { useMemo } from "react";
import { renderLatex } from "@/lib/katex";

type Props = {
  latex: string;
  display?: boolean;
  className?: string;
};

/** Renders LaTeX with KaTeX. Output includes MathML, so screen readers get the math. */
export function Tex({ latex, display = false, className }: Props) {
  const html = useMemo(() => renderLatex(latex, display), [latex, display]);
  const Tag = display ? "div" : "span";
  return <Tag className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}
