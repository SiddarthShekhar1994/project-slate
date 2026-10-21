import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "success";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-[#3557f0] disabled:bg-raised disabled:text-muted",
  secondary: "bg-raised text-text border border-border hover:bg-hover disabled:text-muted",
  ghost: "bg-transparent text-text-2 hover:bg-hover hover:text-text disabled:text-muted",
  success: "bg-success-bg text-success border border-success/40 hover:bg-[#15392f]",
};

export const buttonClasses = (variant: Variant = "primary", extra = "") =>
  [
    "inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-[10px] px-4 text-sm font-semibold",
    "transition-colors disabled:cursor-not-allowed",
    VARIANTS[variant],
    extra,
  ].join(" ");

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant };

export function Button({ variant = "primary", className = "", type = "button", ...rest }: Props) {
  return <button type={type} className={buttonClasses(variant, className)} {...rest} />;
}
