import katex from "katex";

/**
 * KaTeX options used everywhere. `trust` is limited to \htmlClass so skill text
 * can colour parts with the board palette; nothing else that emits raw HTML
 * (\href, \url, \htmlData, \includegraphics) is allowed.
 */
export const KATEX_OPTIONS: katex.KatexOptions = {
  throwOnError: false,
  output: "htmlAndMathml",
  strict: "ignore",
  trust: (context) => context.command === "\\htmlClass" && /^slate-[a-z-]+$/.test(String(context.class ?? "")),
};

export function renderLatex(latex: string, displayMode = false): string {
  return katex.renderToString(latex, { ...KATEX_OPTIONS, displayMode });
}

export type Segment = { kind: "text"; value: string } | { kind: "math"; value: string; display: boolean };

/**
 * Split text with inline `$...$` and display `$$...$$` math into segments.
 * A backslash-escaped dollar (`\$`) stays literal text.
 */
export function splitMath(text: string): Segment[] {
  const segments: Segment[] = [];
  let buffer = "";
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch === "\\" && text[i + 1] === "$") {
      buffer += "$";
      i += 2;
      continue;
    }
    if (ch === "$") {
      const display = text[i + 1] === "$";
      const open = display ? 2 : 1;
      const close = text.indexOf(display ? "$$" : "$", i + open);
      if (close === -1) {
        buffer += text.slice(i);
        break;
      }
      if (buffer) segments.push({ kind: "text", value: buffer });
      buffer = "";
      segments.push({ kind: "math", value: text.slice(i + open, close), display });
      i = close + open;
      continue;
    }
    buffer += ch;
    i += 1;
  }
  if (buffer) segments.push({ kind: "text", value: buffer });
  return segments;
}
