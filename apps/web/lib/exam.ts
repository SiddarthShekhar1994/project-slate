/**
 * The exam builder's preview: how many problems each topic gets and how long
 * the set will run. These mirror the server's rules (services/exam.py
 * ``allocate`` and problem_gen ``plan_difficulties``) so the numbers shown
 * before starting match the exam that gets built.
 */

/** Python's round(): halves go to the even neighbour. */
function roundHalfEven(value: number): number {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (Math.abs(diff - 0.5) > 1e-9) return Math.round(value);
  return floor % 2 === 0 ? floor : floor + 1;
}

/** Largest remainder; every weighted topic gets one problem when there are enough to go round. */
export function allocate(weights: Record<string, number>, count: number): Record<string, number> {
  const ids = Object.keys(weights);
  const positive = ids.filter((id) => weights[id] > 0);
  const out: Record<string, number> = Object.fromEntries(ids.map((id) => [id, 0]));
  if (positive.length === 0 || count <= 0) return out;
  const total = positive.reduce((sum, id) => sum + weights[id], 0);
  const exact = Object.fromEntries(positive.map((id) => [id, (count * weights[id]) / total]));
  for (const id of positive) out[id] = Math.floor(exact[id]);
  const order = [...positive].sort((a, b) => {
    const byRemainder = exact[b] - out[b] - (exact[a] - out[a]);
    return byRemainder !== 0 ? byRemainder : weights[b] - weights[a];
  });
  let left = count - positive.reduce((sum, id) => sum + out[id], 0);
  for (const id of order) {
    if (left <= 0) break;
    out[id] += 1;
    left -= 1;
  }
  if (count >= positive.length) {
    for (const id of positive.filter((p) => out[p] === 0)) {
      const donor = ids.reduce((best, k) =>
        out[k] > out[best] || (out[k] === out[best] && -weights[k] > -weights[best]) ? k : best,
      );
      out[donor] -= 1;
      out[id] = 1;
    }
  }
  return out;
}

/** Spread ``count`` problems over a skill's difficulty levels, easy to hard. */
export function planDifficulties(levels: number[], count: number): number[] {
  if (count <= 0 || levels.length === 0) return [];
  if (count <= levels.length) {
    const step = (levels.length - 1) / Math.max(count - 1, 1);
    return Array.from({ length: count }, (_, i) => levels[roundHalfEven(i * step)]);
  }
  return Array.from(
    { length: count },
    (_, i) => levels[Math.min(levels.length - 1, Math.floor((i * levels.length) / count))],
  );
}

export function timeLimitSeconds(
  difficulties: number[],
  pace: "exam" | "study",
  minutes: Record<string, number>,
  studyFactor: number,
): number {
  let total = difficulties.reduce((sum, d) => sum + (minutes[String(d)] ?? 0), 0);
  if (pace === "study") total *= studyFactor;
  return Math.ceil(total - 1e-9) * 60;
}
