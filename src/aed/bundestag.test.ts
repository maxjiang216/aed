import { describe, expect, it } from "vitest";
import { imputeRace, sainteLague, sainteLagueWithMinimum, simulate, type SimOptions } from "./bundestag";
import type { HouseFile, Race } from "./types";

const race = (d: number, r: number, extra: Race["c"] = []): Race[] => [
  { c: [["Dem", "Democratic", d, 0], ["Rep", "Republican", r, 0], ...extra], t: d + r + extra.reduce((s, x) => s + x[2], 0) },
];

describe("sainteLague", () => {
  it("matches a hand-worked allocation", () => {
    // quotients A: 26.5, 8.83 ...; B: 18.5, 6.17; C: 9, 3
    expect(sainteLague({ A: 53, B: 37, C: 18 }, 5)).toEqual({ A: 2, B: 2, C: 1 });
  });
  it("with minimums keeps every floor and the total", () => {
    const out = sainteLagueWithMinimum({ A: 90, B: 10 }, { B: 4 }, 10);
    expect(out.B).toBe(4);
    expect(out.A + out.B).toBe(10);
  });
});

describe("imputeRace", () => {
  it("gives the missing major party a quarter of the vote", () => {
    const v = imputeRace({ Democratic: 300 }, 0);
    expect(v.Republican).toBe(100);
  });
  it("leaves contested districts alone", () => {
    const v = { Democratic: 10, Republican: 5 };
    expect(imputeRace(v, 0)).toBe(v);
  });
  it("fills an unopposed seat with no count from the fallback turnout", () => {
    expect(imputeRace({}, 1000, "Republican")).toEqual({ Republican: 750, Democratic: 250 });
  });
});

// State XX: D wins all 4 districts narrowly with 52%; state YY: R wins 2 big.
const file: HouseFile = {
  "XX-01": race(52, 48), "XX-02": race(53, 47), "XX-03": race(51, 49), "XX-04": race(54, 46),
  "YY-01": race(20, 80), "YY-02": race(30, 70),
};
const base: Omit<SimOptions, "rules" | "seatsPerDistrict"> = { threshold: 0.05, directClause: 3, impute: false };

describe("simulate, 2025 rules", () => {
  it("fixes the size and seats only covered district winners, best share first", () => {
    const r = simulate(file, { ...base, rules: "2025", seatsPerDistrict: 1 });
    expect(r.size).toBe(6);
    const lost = r.winners.filter((w) => !w.seated).map((w) => w.id);
    // D: 260 of 600 votes -> 3 seats, split XX 2 / YY 1 (210 vs 50 votes). D won 4 in XX, so
    // its two weakest there (XX-03 51%, XX-01 52%) lose. R: XX 2 / YY 1, won 2 in YY -> YY-02 loses.
    expect(r.parties.find((p) => p.party === "Democratic")!.seats).toBe(3);
    expect(lost).toEqual(["XX-01", "XX-03", "YY-02"]);
  });
  it("seats independents off the top and bars sub-threshold parties", () => {
    const f: HouseFile = { ...file, "ZZ-01": race(10, 10, [["Indy", "Independent", 50, 0], ["Lib", "Libertarian", 1, 0]]) };
    const r = simulate(f, { ...base, rules: "2025", seatsPerDistrict: 10 / 7 });
    expect(r.parties.find((p) => p.party === "Independent")!.seats).toBe(1);
    expect(r.parties.find((p) => p.party === "Libertarian")!.qualified).toBe(false);
    expect(r.size).toBe(10);
  });
});

describe("winners of a party below the threshold", () => {
  const f: HouseFile = { ...file, "ZZ-01": race(1, 1, [["May", "Green", 3, 0]]) };
  it("lose the seat under 2025 rules", () => {
    const r = simulate(f, { ...base, rules: "2025", seatsPerDistrict: 1 });
    expect(r.winners.find((w) => w.id === "ZZ-01")).toMatchObject({ seated: false, lost: "threshold" });
    expect(r.parties.find((p) => p.party === "Green")!.seats).toBe(0);
  });
  it("keep it under 2013 rules", () => {
    const r = simulate(f, { ...base, rules: "2013", seatsPerDistrict: 1 });
    expect(r.winners.find((w) => w.id === "ZZ-01")!.seated).toBe(true);
    expect(r.parties.find((p) => p.party === "Green")!.seats).toBe(1);
  });
});

describe("simulate, 2013 rules", () => {
  it("keeps every winner and grows until proportional", () => {
    const r = simulate(file, { ...base, rules: "2013", seatsPerDistrict: 1 });
    expect(r.winners.every((w) => w.seated)).toBe(true);
    const D = r.parties.find((p) => p.party === "Democratic")!;
    const R = r.parties.find((p) => p.party === "Republican")!;
    expect(r.size).toBeGreaterThan(6);
    expect(D.seats).toBeGreaterThanOrEqual(4);
    expect(Math.abs(D.seats / r.size - 260 / 600)).toBeLessThan(0.1);
    expect(r.states.YY.Republican).toBeGreaterThanOrEqual(2);
    expect(D.seats + R.seats).toBe(r.size);
  });
});
