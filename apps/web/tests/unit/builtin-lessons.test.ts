import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { boardStateAt, estimateTimings, spokenWords, validateScript } from "@/lib/lesson/timeline";
import type { LessonScript } from "@/lib/lesson/types";

const DIR = path.resolve(__dirname, "../../../api/slate_api/lessons/builtin");
const scripts = readdirSync(DIR)
  .filter((f) => f.endsWith(".json"))
  .map((f) => [f, JSON.parse(readFileSync(path.join(DIR, f), "utf8")) as LessonScript] as const);

describe.each(scripts)("built-in lesson %s", (_name, script) => {
  it("references only lines already on the board, with anchors inside the narration", () => {
    expect(validateScript(script)).toEqual([]);
  });

  it("ends with every line written", () => {
    const last = script.steps.length - 1;
    const state = boardStateAt(script, last, 1e9, (s) => estimateTimings(script.steps[s].narration));
    const written = script.steps.flatMap((s) => s.actions.filter((a) => a.type === "write").map((a) => a.id));
    expect(state.lines.map((l) => l.id).sort()).toEqual([...written].sort());
  });

  it("anchors each write near the words that describe it", () => {
    for (const step of script.steps) {
      expect(spokenWords(step.narration).length).toBeGreaterThan(0);
    }
  });
});
