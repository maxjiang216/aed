/** "What if this election used Bundestag rules": a mixed-member proportional re-count of one
 *  single-member-district election (U.S. House, Canadian House of Commons). Every district keeps
 *  its winner as a constituency candidate; the district votes, summed per party, stand in for
 *  the second (list) vote, which these voters never cast. States/provinces play the Länder.
 *
 *  Two rule sets:
 *  - "2025": the 2023 reform as used in 2025 (fixed size; constituency winners are seated only
 *    while their party's list share covers them, best first-vote share first; the 3-constituency
 *    clause restored by the Constitutional Court in 2024).
 *  - "2013": the 2013-2017 rules (overhang seats kept, every party's overhang compensated by
 *    growing the house until the national split is proportional again).
 */
import { outcome, pickRace } from "./model";
import type { HouseFile, Race } from "./types";

export type RuleSet = "2025" | "2013";

export interface SimOptions {
  rules: RuleSet;
  /** Seats per district. 2025: fixes the total. 2013: the base size before overhang and
   *  leveling seats. Germany: 630 / 299 (2025), 598 / 299 = 2 (2013). */
  seatsPerDistrict: number;
  /** National list-vote threshold (0.05 in Germany). */
  threshold: number;
  /** Constituency wins that qualify a party regardless of the threshold (3 in Germany; 0 = off). */
  directClause: number;
  /** Fill in votes for the major party missing from a district (see imputeRace). */
  impute: boolean;
}

export const DEFAULTS: Record<RuleSet, Omit<SimOptions, "rules" | "impute">> = {
  "2025": { seatsPerDistrict: 630 / 299, threshold: 0.05, directClause: 3 },
  "2013": { seatsPerDistrict: 2, threshold: 0.05, directClause: 3 },
};

export const sizeFor = (options: SimOptions, districts: number) => Math.round(options.seatsPerDistrict * districts);

/** Ballot lines that are not parties and so cannot run a list. */
const NON_PARTY = new Set([
  "Other", "Independent", "Unenrolled", "No Political Party", "Nominated By Petition",
  "Nonpartisan", "Unaffiliated", "Write-in", "No Party Affiliation", "No Affiliation",
]);
export const isParty = (label: string) => !NON_PARTY.has(label);

export interface Winner {
  id: string;
  state: string;
  name: string;
  party: string;
  /** Winner's share of all votes in the district (the first-vote ranking key). */
  share: number;
  /** Seated under the simulated rules. */
  seated: boolean;
  /** Why not: the party's list share in the state ran out, or the party missed the threshold. */
  lost?: "uncovered" | "threshold";
}

export interface PartyResult {
  party: string;
  votes: number;
  share: number;
  qualified: boolean;
  /** Districts won (the actual House result). */
  won: number;
  /** Constituency winners seated. */
  direct: number;
  /** Seats from the list. */
  list: number;
  seats: number;
}

export interface SimResult {
  options: SimOptions;
  size: number;
  totalVotes: number;
  parties: PartyResult[];
  /** state -> party -> seats */
  states: Record<string, Record<string, number>>;
  winners: Winner[];
  /** Districts whose votes were imputed. */
  imputed: string[];
}

interface District {
  id: string;
  state: string;
  votes: Record<string, number>; // party -> list votes
  winner: Omit<Winner, "seated" | "lost"> | null;
}

const MAJOR = ["Democratic", "Republican"];

/** A district without a candidate from one major party gets one at 25% of the vote
 *  (the present party's votes are scaled to 75%). Unopposed seats without a count get the
 *  state's mean contested turnout at the same 75/25 split. */
export function imputeRace(
  votes: Record<string, number>,
  fallbackTurnout: number,
  unopposedParty?: string,
): Record<string, number> {
  if (unopposedParty) {
    if (!MAJOR.includes(unopposedParty)) return { [unopposedParty]: fallbackTurnout };
    const other = MAJOR.find((p) => p !== unopposedParty)!;
    return { [unopposedParty]: 0.75 * fallbackTurnout, [other]: 0.25 * fallbackTurnout };
  }
  const have = MAJOR.filter((p) => (votes[p] ?? 0) > 0);
  if (have.length !== 1) return votes;
  const [present] = have;
  const missing = MAJOR.find((p) => p !== present)!;
  const out = { ...votes };
  out[missing] = (out[present] ?? 0) / 3; // present : missing = 75 : 25
  return out;
}

function districtsFrom(file: HouseFile, impute: boolean): { districts: District[]; imputed: string[] } {
  const districts: District[] = [];
  const raw: { id: string; race: Race }[] = [];
  for (const [id, races] of Object.entries(file)) {
    const race = pickRace(races);
    if (race) raw.push({ id, race });
  }
  // Mean contested turnout per state, for unopposed seats with no count.
  const turnout: Record<string, number[]> = {};
  for (const { id, race } of raw) {
    if (!race.u && race.t > 0) (turnout[id.slice(0, 2)] ??= []).push(race.t);
  }
  const all = Object.values(turnout).flat();
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  const imputed: string[] = [];

  for (const { id, race } of raw) {
    const state = id.slice(0, 2);
    let votes: Record<string, number> = {};
    for (const [, party, v, flag] of race.c) {
      if (flag !== 0 || !isParty(party) || race.u) continue;
      votes[party] = (votes[party] ?? 0) + v;
    }
    const o = outcome(race);
    let winner: District["winner"] = null;
    if (o) {
      const [name, party] = o.winner;
      const own = race.c.filter((r) => r[0] === name).reduce((s, r) => s + r[2], 0);
      winner = { id, state, name, party, share: race.u ? 1 : own / race.t };
      if (race.u) votes = { [party]: 0 };
    }
    if (impute) {
      const before = votes;
      votes = imputeRace(
        votes,
        turnout[state] ? mean(turnout[state]) : mean(all),
        race.u && winner ? winner.party : undefined,
      );
      if (votes !== before) imputed.push(id);
    }
    districts.push({ id, state, votes, winner });
  }
  return { districts, imputed };
}

/** Sainte-Laguë / Schepers: n seats by highest averages with divisors 0.5, 1.5, 2.5, ... */
export function sainteLague(votes: Record<string, number>, n: number): Record<string, number> {
  const keys = Object.keys(votes).filter((k) => votes[k] > 0);
  const seats: Record<string, number> = Object.fromEntries(Object.keys(votes).map((k) => [k, 0]));
  for (let i = 0; i < n && keys.length; i++) {
    let best = keys[0];
    let bestQ = -1;
    for (const k of keys) {
      const q = votes[k] / (seats[k] + 0.5);
      if (q > bestQ) [best, bestQ] = [k, q];
    }
    seats[best]++;
  }
  return seats;
}

/** Divisor method with standard rounding where each key gets at least min[k]: find the
 *  divisor D with sum(max(min, round(v / D))) = n. Used for the 2013 distribution to states. */
export function sainteLagueWithMinimum(
  votes: Record<string, number>,
  min: Record<string, number>,
  n: number,
): Record<string, number> {
  const keys = Object.keys(votes);
  const alloc = (d: number) =>
    Object.fromEntries(keys.map((k) => [k, Math.max(min[k] ?? 0, Math.round(votes[k] / d))]));
  const sum = (a: Record<string, number>) => Object.values(a).reduce((x, y) => x + y, 0);
  const floor = keys.reduce((s, k) => s + (min[k] ?? 0), 0);
  if (n <= floor) return Object.fromEntries(keys.map((k) => [k, min[k] ?? 0]));
  // Seats fall as the divisor grows; bisect for a divisor that hits n exactly, then fix
  // any tie (several keys on a .5 boundary) by highest-average steps.
  let lo = 1e-9;
  let hi = keys.reduce((s, k) => s + votes[k], 0) * 2 + 1;
  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2;
    if (sum(alloc(mid)) > n) lo = mid;
    else hi = mid;
  }
  const out = alloc(hi);
  while (sum(out) < n) {
    let best = keys[0];
    let bestQ = -1;
    for (const k of keys) {
      const q = votes[k] / (out[k] + 0.5);
      if (q > bestQ) [best, bestQ] = [k, q];
    }
    out[best]++;
  }
  return out;
}

export function simulate(file: HouseFile, options: SimOptions): SimResult {
  const { districts, imputed } = districtsFrom(file, options.impute);

  const natVotes: Record<string, number> = {};
  const stateVotes: Record<string, Record<string, number>> = {};
  const won: Record<string, number> = {};
  const directBy: Record<string, Record<string, number>> = {}; // party -> state -> wins
  for (const d of districts) {
    for (const [p, v] of Object.entries(d.votes)) {
      natVotes[p] = (natVotes[p] ?? 0) + v;
      (stateVotes[d.state] ??= {})[p] = (stateVotes[d.state][p] ?? 0) + v;
    }
    if (d.winner) {
      const p = d.winner.party;
      won[p] = (won[p] ?? 0) + 1;
      if (isParty(p)) ((directBy[p] ??= {})[d.state] = (directBy[p][d.state] ?? 0) + 1);
    }
  }
  const totalVotes = Object.values(natVotes).reduce((a, b) => a + b, 0);
  const qualified = Object.keys(natVotes).filter(
    (p) =>
      natVotes[p] / totalVotes >= options.threshold ||
      (options.directClause > 0 && (won[p] ?? 0) >= options.directClause),
  );
  const qualVotes = Object.fromEntries(qualified.map((p) => [p, natVotes[p]]));
  // Constituency winners outside the qualifying parties. Independents always sit, and their
  // seats come off the top. Winners for a party that missed the threshold sat under the 2013
  // rules; since 2023 they get nothing (their party takes no part in the seat distribution).
  const unqualified = districts.filter((d) => d.winner && !qualified.includes(d.winner.party));
  const freeWinners =
    options.rules === "2025" ? unqualified.filter((d) => !isParty(d.winner!.party)) : unqualified;
  const shutOut = unqualified.filter((d) => !freeWinners.includes(d));
  const states = [...new Set(districts.map((d) => d.state))].sort();
  const stateVotesOf = (p: string) => Object.fromEntries(states.map((s) => [s, stateVotes[s]?.[p] ?? 0]));

  let partySeats: Record<string, number>;
  let byState: Record<string, Record<string, number>>; // party -> state -> seats

  if (options.rules === "2025") {
    partySeats = sainteLague(qualVotes, Math.max(0, sizeFor(options, districts.length) - freeWinners.length));
    byState = Object.fromEntries(qualified.map((p) => [p, sainteLague(stateVotesOf(p), partySeats[p])]));
  } else {
    // 1. Base seats per state in proportion to population: districts are apportioned by
    //    population, so a state's base is its district share of the base size.
    const districtCount: Record<string, number> = {};
    for (const d of districts) districtCount[d.state] = (districtCount[d.state] ?? 0) + 1;
    const base = sainteLague(districtCount, Math.max(0, sizeFor(options, districts.length) - freeWinners.length));
    // 2. Each party's minimum: per state, the larger of its state contingent and its wins.
    const minimum: Record<string, number> = Object.fromEntries(qualified.map((p) => [p, 0]));
    for (const s of states) {
      const contingent = sainteLague(
        Object.fromEntries(qualified.map((p) => [p, stateVotes[s]?.[p] ?? 0])),
        base[s] ?? 0,
      );
      for (const p of qualified) minimum[p] += Math.max(contingent[p], directBy[p]?.[s] ?? 0);
    }
    // 3. Grow the house until the national split gives every party its minimum.
    let n = Math.max(0, sizeFor(options, districts.length) - freeWinners.length);
    partySeats = sainteLague(qualVotes, n);
    while (qualified.some((p) => partySeats[p] < minimum[p])) partySeats = sainteLague(qualVotes, ++n);
    // 4. Each party's seats to its state lists, never below its wins there.
    byState = Object.fromEntries(
      qualified.map((p) => [p, sainteLagueWithMinimum(stateVotesOf(p), directBy[p] ?? {}, partySeats[p])]),
    );
  }

  // Seat constituency winners in order of first-vote share while list seats cover them.
  const winners: Winner[] = [];
  for (const d of freeWinners) winners.push({ ...d.winner!, seated: true });
  for (const d of shutOut) winners.push({ ...d.winner!, seated: false, lost: "threshold" });
  const groups: Record<string, Omit<Winner, "seated" | "lost">[]> = {};
  for (const d of districts) {
    if (d.winner && qualified.includes(d.winner.party)) (groups[`${d.winner.party}|${d.state}`] ??= []).push(d.winner);
  }
  const direct: Record<string, number> = {};
  for (const [key, ws] of Object.entries(groups)) {
    const [p, s] = key.split("|");
    const cap = byState[p]?.[s] ?? 0;
    ws.sort((a, b) => b.share - a.share);
    ws.forEach((w, i) => winners.push(i < cap ? { ...w, seated: true } : { ...w, seated: false, lost: "uncovered" }));
    direct[p] = (direct[p] ?? 0) + Math.min(cap, ws.length);
  }
  winners.sort((a, b) => a.id.localeCompare(b.id));

  const parties: PartyResult[] = Object.keys({ ...natVotes, ...won })
    .map((party) => {
      const q = qualified.includes(party);
      const free = freeWinners.filter((d) => d.winner!.party === party).length;
      const seats = (q ? partySeats[party] : 0) + free;
      const dir = (direct[party] ?? 0) + free;
      return {
        party,
        votes: natVotes[party] ?? 0,
        share: (natVotes[party] ?? 0) / totalVotes,
        qualified: q,
        won: won[party] ?? 0,
        direct: dir,
        list: seats - dir,
        seats,
      };
    })
    .sort((a, b) => b.seats - a.seats || b.votes - a.votes);

  const statesOut: Record<string, Record<string, number>> = {};
  for (const s of states) statesOut[s] = {};
  for (const p of qualified) for (const s of states) if (byState[p][s]) statesOut[s][p] = byState[p][s];
  for (const d of freeWinners) statesOut[d.state][d.winner!.party] = (statesOut[d.state][d.winner!.party] ?? 0) + 1;

  return {
    options,
    size: parties.reduce((s, p) => s + p.seats, 0),
    totalVotes,
    parties,
    states: statesOut,
    winners,
    imputed,
  };
}
