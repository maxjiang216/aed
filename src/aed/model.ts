import { FIXED_PARTY_HUES, FLIP, Hue, THIRD_PARTY_HUES, TIE, deltaColor, marginColor } from "./colors";
import type { Office, Race, Row, SenateSeat, StatewideFile, View } from "./types";

/** Rows that can win or place second. Folded minor candidates (flag 2) never count. */
export function contenders(race: Race): Row[] {
  return race.c.filter((r) => r[3] !== 2).sort((a, b) => b[2] - a[2]);
}

export interface Outcome {
  winner: Row;
  second: Row | null;
  margin: number; // (1st - 2nd) / all votes cast
  tie: boolean;
}

export function outcome(race: Race): Outcome | null {
  const c = contenders(race);
  if (!c.length || !(race.t > 0)) return null;
  if (race.u) return { winner: c[0], second: null, margin: 1, tie: false };
  const second = c[1] ?? null;
  const diff = c[0][2] - (second ? second[2] : 0);
  return { winner: c[0], second, margin: diff / race.t, tie: diff === 0 };
}

export function partyVotes(race: Race, party: string): number {
  return race.c.reduce((s, r) => (r[1] === party && r[3] === 0 ? s + r[2] : s), 0);
}

/** (D - R) / total */
export function demMargin(race: Race): number | null {
  if (race.u) return null; // unopposed: no vote count to compare
  return race.t > 0 ? (partyVotes(race, "Democratic") - partyVotes(race, "Republican")) / race.t : null;
}

/** Choose the race the map shows for one state-year. Regular mode: regular seat (or the
 *  special if that is all there is); special mode: specials only. A runoff replaces its first round. */
export function pickRace(races: Race[] | undefined, seat: SenateSeat = "regular"): Race | null {
  if (!races?.length) return null;
  let pool = seat === "special" ? races.filter((r) => r.s) : races.filter((r) => !r.s);
  if (!pool.length && seat === "regular") pool = races;
  if (!pool.length) return null;
  return pool.find((r) => r.r) ?? pool[0];
}

export interface Env {
  d: number;
  r: number;
  t: number;
}

export function nationalEnv(races: Iterable<Race>): Env {
  const env = { d: 0, r: 0, t: 0 };
  for (const race of races) {
    env.d += partyVotes(race, "Democratic");
    env.r += partyVotes(race, "Republican");
    env.t += race.t;
  }
  return env;
}

/** (R - D)/T of the race minus the same for the nation. Positive = redder than the nation. */
export function bias(race: Race, env: Env): number | null {
  const dm = demMargin(race);
  if (dm === null || !(env.t > 0)) return null;
  return -dm - (env.r - env.d) / env.t;
}

/** Party -> hue for one year: D blue, R red, unnamed bloc gray, other parties by how many
 *  votes they won while finishing in the top two anywhere. */
export function partyHues(races: Iterable<Race>): Record<string, Hue> {
  const votes: Record<string, number> = {};
  for (const race of races) {
    for (const row of contenders(race).slice(0, 2)) {
      if (row[3] === 0 && !(row[1] in FIXED_PARTY_HUES)) votes[row[1]] = (votes[row[1]] ?? 0) + row[2];
    }
  }
  const hues: Record<string, Hue> = { ...FIXED_PARTY_HUES };
  Object.keys(votes)
    .sort((a, b) => votes[b] - votes[a])
    .forEach((p, i) => (hues[p] = THIRD_PARTY_HUES[Math.min(i, THIRD_PARTY_HUES.length - 1)]));
  return hues;
}

export function hueFor(row: Row, hues: Record<string, Hue>): Hue {
  if (row[3] === 1) return "Gray";
  return hues[row[1]] ?? "Purple";
}

const SENATE_CLASS_FOR_YEAR: Record<number, string> = { 0: "III", 2: "I", 4: "II" };

/** The previous contest for the same seat: last presidential year; for the Senate the same
 *  class (six years back for regular seats); for governors the state's last election. */
export function previousRace(
  office: Office,
  data: StatewideFile,
  years: number[],
  year: number,
  state: string,
  race: Race,
): { race: Race; year: number } | null {
  const earlier = years.filter((y) => y < year).sort((a, b) => b - a);
  if (office === "president") {
    const y = earlier[0];
    const r = y === undefined ? null : pickRace(data[y]?.[state]);
    return r ? { race: r, year: y } : null;
  }
  const cls = office === "senate" ? race.k ?? (race.s ? undefined : SENATE_CLASS_FOR_YEAR[year % 6]) : undefined;
  for (const y of earlier) {
    const races = data[y]?.[state];
    if (!races?.length) continue;
    if (cls) {
      const same = races.filter((r) => r.k === cls);
      if (same.length) return { race: same.find((r) => r.r) ?? same[0], year: y };
      continue;
    }
    const r = pickRace(races);
    if (r) return { race: r, year: y };
  }
  return null;
}

function bucket(party: string): "D" | "R" | "O" {
  return party === "Democratic" ? "D" : party === "Republican" ? "R" : "O";
}

export interface FillContext {
  view: View;
  hues: Record<string, Hue>;
  env: Env;
  prev: Race | null;
  prevEnv: Env | null;
}

/** Map fill for one region. */
export function fillFor(race: Race, ctx: FillContext): string {
  const o = outcome(race);
  if (!o) return TIE;
  switch (ctx.view) {
    case "result":
      return o.tie ? TIE : marginColor(o.margin, hueFor(o.winner, ctx.hues));
    case "bias": {
      const b = bias(race, ctx.env);
      return b === null ? TIE : marginColor(Math.abs(b), b > 0 ? "Red" : "Blue");
    }
    case "flip": {
      const p = ctx.prev && outcome(ctx.prev);
      if (!p || o.tie || p.tie || o.winner[3] !== 0 || p.winner[3] !== 0) return TIE;
      const now = bucket(o.winner[1]);
      const then = bucket(p.winner[1]);
      if (now === "O" || then === "O") {
        return now === then ? marginColor(0.06, hueFor(o.winner, ctx.hues)) : marginColor(0.3, hueFor(o.winner, ctx.hues));
      }
      if (now === then) return now === "D" ? FLIP.holdD : FLIP.holdR;
      return now === "D" ? FLIP.flipD : FLIP.flipR;
    }
    case "shift": {
      const a = demMargin(race);
      const b = ctx.prev ? demMargin(ctx.prev) : null;
      return a === null || b === null ? TIE : deltaColor(a - b, true);
    }
    case "trend": {
      const a = bias(race, ctx.env);
      const b = ctx.prev && ctx.prevEnv ? bias(ctx.prev, ctx.prevEnv) : null;
      return a === null || b === null ? TIE : deltaColor(a - b, false);
    }
  }
}

export function pct(x: number, digits = 1): string {
  return `${(x * 100).toFixed(digits)}%`;
}

/** "D+3.2", "R+0.4", "Wallace+47.1" style label for a margin. */
export function marginLabel(o: Outcome): string {
  if (o.tie) return "Tie";
  const p = o.winner[1];
  const tag = p === "Democratic" ? "D" : p === "Republican" ? "R" : o.winner[3] === 1 ? "Other" : o.winner[0].split(" ").pop();
  return `${tag}+${(o.margin * 100).toFixed(1)}`;
}
