import { describe, expect, it } from "vitest";
import { CUTOFFS, PALETTES, TIE, marginColor } from "./colors";
import { bias, fillFor, nationalEnv, outcome, partyHues, pickRace, previousRace } from "./model";
import type { Race, StatewideFile } from "./types";

const al1968: Race = {
  c: [
    ["George Wallace", "American Independent", 691425, 0],
    ["Hubert H. Humphrey", "Democratic", 196579, 0],
    ["Richard Nixon", "Republican", 146923, 0],
    ["Other (combined)", "Other", 14990, 1],
  ],
  t: 1049917,
};

describe("outcome", () => {
  it("margin is (1st - 2nd) / all votes, not a two-party share", () => {
    const o = outcome(al1968)!;
    expect(o.winner[0]).toBe("George Wallace");
    expect(o.margin).toBeCloseTo((691425 - 196579) / 1049917, 10);
  });

  it("third parties shrink the margin", () => {
    const o = outcome({ c: [["A", "Democratic", 45, 0], ["B", "Republican", 40, 0], ["C", "Green", 15, 0]], t: 100 })!;
    expect(o.margin).toBeCloseTo(0.05);
  });

  it("folded minor candidates never place second", () => {
    const o = outcome({ c: [["A", "Republican", 80, 0], ["Others", "Other", 15, 2], ["B", "Democratic", 5, 0]], t: 100 })!;
    expect(o.second?.[0]).toBe("B");
    expect(o.margin).toBeCloseTo(0.75);
  });

  it("an unnamed bloc that may be one candidate can win", () => {
    const o = outcome({ c: [["Other (combined)", "Other", 60, 1], ["A", "Democratic", 40, 0]], t: 100 })!;
    expect(o.winner[3]).toBe(1);
  });
});

describe("marginColor", () => {
  it("hits each stop and interpolates between them", () => {
    const blue = PALETTES.Blue;
    expect(marginColor(0, "Blue")).toBe(TIE);
    expect(marginColor(CUTOFFS[0], "Blue")).toBe(`rgb(${blue[1].join(", ")})`);
    expect(marginColor(CUTOFFS[1], "Blue")).toBe(`rgb(${blue[2].join(", ")})`);
    expect(marginColor(0.5, "Blue")).toBe(`rgb(${blue[3].join(", ")})`);
    const mid = marginColor((CUTOFFS[0] + CUTOFFS[1]) / 2, "Blue");
    expect(mid).toBe(`rgb(${blue[1].map((v, i) => Math.round((v + blue[2][i]) / 2)).join(", ")})`);
  });
});

describe("pickRace", () => {
  const gen: Race = { c: [["A", "Republican", 5, 0]], t: 10 };
  const runoff: Race = { c: [["B", "Democratic", 6, 0]], t: 10, r: 1 };
  const special: Race = { c: [["C", "Democratic", 7, 0]], t: 10, s: 1 };
  it("runoff replaces the first round", () => expect(pickRace([gen, runoff])).toBe(runoff));
  it("regular seat preferred", () => expect(pickRace([special, gen])).toBe(gen));
  it("special only in special mode", () => expect(pickRace([gen], "special")).toBeNull());
  it("falls back to the special when it is the only race", () => expect(pickRace([special])).toBe(special));
});

describe("previousRace", () => {
  const r = (d: number, k?: string): Race => ({ c: [["D", "Democratic", d, 0], ["R", "Republican", 100 - d, 0]], t: 100, k });
  const data: StatewideFile = {
    "2012": { OH: [r(55, "I")] },
    "2016": { OH: [r(40, "III")] },
    "2018": { OH: [r(53, "I")] },
  };
  it("Senate compares with the same class", () => {
    const p = previousRace("senate", data, [2012, 2016, 2018], 2018, "OH", data["2018"].OH[0]);
    expect(p?.year).toBe(2012);
  });
  it("governor compares with the state's last race", () => {
    const p = previousRace("governor", data, [2012, 2016, 2018], 2018, "OH", data["2018"].OH[0]);
    expect(p?.year).toBe(2016);
  });
});

describe("views", () => {
  const env = nationalEnv([al1968]);
  it("bias is zero for the only state", () => expect(bias(al1968, env)).toBeCloseTo(0));
  it("third party gets a third-party hue", () => {
    const hues = partyHues([al1968]);
    expect(hues["American Independent"]).toBe("Yellow");
    const fill = fillFor(al1968, { view: "result", hues, env, prev: null, prevEnv: null });
    expect(fill).toBe(marginColor(0.47, "Yellow"));
  });
});
