import { describe, expect, it } from "vitest";
import { rowAt, seatRows, type SeatsFile } from "./seats";

const file: SeatsFile = {
  parties: ["Democrat", "Republican", "Independent"],
  source: "",
  built: "2026-11-10",
  senate: {
    t: ["2001-01-03", "2001-06-06"],
    seats: [100, 100],
    n: [[0, 50, 1, 50], [0, 50, 1, 49, 2, 1]],
    dc: [50, 51],
    rc: [50, 49],
    ev: [[], [[-1, "Jim Jeffords", 1, "VT"], [1, "Jim Jeffords", 2, "VT"]]],
  },
  house: { t: ["2021-01-03"], seats: [435], n: [[0, 222, 1, 211]], dc: [222], rc: [211], ev: [[]] },
};

describe("seatRows", () => {
  it("counts caucusing independents with their party when asked", () => {
    const [, after] = seatRows(file, "senate", true);
    expect([after.dem, after.rep, after.other, after.vacant]).toEqual([51, 49, 0, 0]);
    const [, raw] = seatRows(file, "senate", false);
    expect([raw.dem, raw.rep, raw.other]).toEqual([50, 49, 1]);
    expect(raw.changes.map((c) => c.party)).toEqual(["Republican", "Independent"]);
  });

  it("derives vacancies from seats minus members", () => {
    const [r] = seatRows(file, "house", true);
    expect(r.vacant).toBe(2);
  });
});

describe("rowAt", () => {
  it("finds the row in force at a time", () => {
    const rows = seatRows(file, "senate", true);
    expect(rowAt(rows, Date.parse("2000-01-01"))).toBe(-1);
    expect(rowAt(rows, Date.parse("2001-06-05"))).toBe(0);
    expect(rowAt(rows, Date.parse("2001-06-06"))).toBe(1);
  });
});
