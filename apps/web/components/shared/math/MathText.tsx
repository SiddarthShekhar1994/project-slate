import { Fragment, useMemo } from "react";
import { splitMath } from "@/lib/katex";
import { Tex } from "./Tex";

type Props = {
  text: string;
  className?: string;
  as?: "p" | "span" | "div";
};

/** Prose with inline `$...$` math, as written by skill files and the API. */
export function MathText({ text, className, as: Tag = "span" }: Props) {
  const segments = useMemo(() => splitMath(text), [text]);
  return (
    <Tag className={className}>
      {segments.map((segment, i) =>
        segment.kind === "text" ? (
          <Fragment key={i}>{segment.value}</Fragment>
        ) : (
          <Tex key={i} latex={segment.value} display={segment.display} />
        ),
      )}
    </Tag>
  );
}
