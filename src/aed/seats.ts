/** Party composition of the House and Senate over time (public/data/congress/seats.json,
 *  built by scripts/ingest/congress_seats.py). */

export type Chamber = "house" | "senate";

export interface SeatsSeries {
  t: string[];
  seats: number[];
  /** Flat [party index, count, party index, count, ...] per change point. */
  n: number[][];
  dc: number[];
  rc: number[];
  /** [+1 arrived | -1 left, name, party index, state] per change point. */
  ev: [number, string, number, string][][];
}

export interface SeatsFile {
  parties: string[];
  source: string;
  built: string;
  house: SeatsSeries;
  senate: SeatsSeries;
}

export interface Change {
  dir: 1 | -1;
  name: string;
  party: string;
  state: string;
}

export interface SeatRow {
  /** Start of this state (ms since epoch, UTC); it holds until the next row's t. */
  t: number;
  date: string;
  seats: number;
  dem: number;
  rep: number;
  other: number;
  vacant: number;
  /** Every party's count, largest first. */
  byParty: [string, number][];
  changes: Change[];
}

/** One row per change point. With `caucus`, independents who caucus with a party count for it. */
export function seatRows(file: SeatsFile, chamber: Chamber, caucus: boolean): SeatRow[] {
  const s = file[chamber];
  return s.t.map((date, i) => {
    const byParty: [string, number][] = [];
    const n = s.n[i];
    for (let j = 0; j < n.length; j += 2) byParty.push([file.parties[n[j]], n[j + 1]]);
    byParty.sort((a, b) => b[1] - a[1]);
    const filled = byParty.reduce((a, [, k]) => a + k, 0);
    const count = (p: string) => byParty.find(([q]) => q === p)?.[1] ?? 0;
    const dem = caucus ? s.dc[i] : count("Democrat");
    const rep = caucus ? s.rc[i] : count("Republican");
    return {
      t: Date.parse(date),
      date,
      seats: s.seats[i],
      dem,
      rep,
      other: filled - dem - rep,
      vacant: Math.max(0, s.seats[i] - filled),
      byParty,
      changes: s.ev[i].map(([dir, name, p, state]) => ({ dir: dir as 1 | -1, name, party: file.parties[p], state })),
    };
  });
}

/** Index of the row in force at time t (rows sorted by t), or -1 before the first. */
export function rowAt(rows: SeatRow[], t: number): number {
  let lo = 0;
  let hi = rows.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].t <= t) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans;
}
