/** Small inline icons drawn with strokes so they inherit the text colour. */
const PATHS = {
  library: "M4 5h4v14H4zM10 5h4v14h-4zM16.5 5.5l3.5 1-3.5 13-3.5-1z",
  lesson: "M4 5h16v11H4zM8 20h8M12 16v4",
  practice: "M5 4h10l4 4v12H5zM9 12h6M9 16h4",
  progress: "M5 19V11M12 19V5M19 19v-6",
  check: "M5 12l4 4 10-10",
  retry: "M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4",
  dot: "M12 12h.01",
  play: "M8 5l11 7-11 7z",
  pause: "M8 5h3v14H8zM14 5h3v14h-3z",
  prev: "M18 6l-8 6 8 6zM6 6v12",
  next: "M6 6l8 6-8 6zM18 6v12",
  hint: "M9 18h6M10 21h4M12 3a6 6 0 0 0-3 11v2h6v-2a6 6 0 0 0-3-11z",
  upload: "M12 16V4M7 9l5-5 5 5M5 20h14",
  mic: "M12 4a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v3",
  close: "M6 6l12 12M18 6L6 18",
  arrow: "M5 12h14M13 6l6 6-6 6",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, className = "" }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      aria-hidden
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
