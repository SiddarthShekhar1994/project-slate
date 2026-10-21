import type { HTMLAttributes } from "react";

type Props = HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "article" | "aside" };

export function Card({ as: Tag = "section", className = "", ...rest }: Props) {
  return <Tag className={`rounded-[14px] border border-border bg-card ${className}`} {...rest} />;
}
