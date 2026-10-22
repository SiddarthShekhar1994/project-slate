export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-muted">
      <span
        aria-hidden
        className="h-4 w-4 animate-spin rounded-full border-2 border-border border-t-accent-light motion-reduce:animate-none"
      />
      {label}
    </span>
  );
}

/** Just the spinning ring, for places where the words around it say what's happening. */
export function SpinnerIcon({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-accent-light motion-reduce:animate-none ${className}`}
    />
  );
}
