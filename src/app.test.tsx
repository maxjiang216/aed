import { readFileSync } from "node:fs";
import { renderToString } from "react-dom/server";
import { feature, mesh } from "topojson-client";
import { describe, expect, it } from "vitest";
import { buildModel } from "./App";
import { Legend } from "./components/Legend";
import { MapView } from "./components/MapView";
import { NationalPanel, RacePanel } from "./components/RacePanel";
import type { Shapes, Shape } from "./geo";
import type { CountyFile, DataIndex, Office, StatewideFile, View } from "./types";

const json = (p: string) => JSON.parse(readFileSync(p, "utf8"));
const index: DataIndex = json("public/data/index.json");

function shapes(level: "state" | "county"): Shapes {
  const topo = json(`node_modules/us-atlas/${level === "state" ? "states" : "counties"}-albers-10m.json`);
  const obj = level === "county" ? topo.objects.counties : topo.objects.states;
  return {
    regions: (feature(topo, obj) as unknown as { features: Shape[] }).features.map((f) => ({ ...f, id: String(f.id) })),
    borders: mesh(topo, topo.objects.states, (a, b) => a !== b),
    outline: mesh(topo, topo.objects.nation),
  };
}
const STATE = shapes("state");
const COUNTY = shapes("county");
const VIEWS: View[] = ["result", "bias", "flip", "shift", "trend"];
const okColor = (c: string) => /^rgb\(\d+, \d+, \d+\)$/.test(c);

describe.each(["president", "senate", "governor"] as Office[])("%s statewide", (office) => {
  const data: StatewideFile = json(`public/data/statewide/${office}.json`);
  const years = index.offices[office].state!;
  it("every year and view yields valid fills and renders", () => {
    for (const year of years) {
      for (const view of VIEWS) {
        const m = buildModel({ office, level: "state", year, view, seat: "regular" }, data, years, null, STATE)!;
        const fills = Object.values(m.fills);
        expect(fills.length, `${office} ${year}`).toBeGreaterThan(0);
        for (const f of fills) expect(okColor(f), `${office} ${year} ${view} ${f}`).toBe(true);
      }
      const m = buildModel({ office, level: "state", year, view: "result", seat: "regular" }, data, years, null, STATE)!;
      renderToString(<NationalPanel sel={{ office, level: "state", year, view: "result", seat: "regular" }} races={m.stateRaces} hues={m.hues} env={m.env} />);
      for (const id of Object.keys(m.fills)) {
        renderToString(<RacePanel title={id} races={m.racesFor(id)} year={year} office={office} hues={m.hues} prev={m.prevFor(id)} pinned onClose={() => {}} />);
      }
      renderToString(<Legend view="result" hues={m.hues} />);
    }
  });
});

describe("spot checks", () => {
  const pres: StatewideFile = json("public/data/statewide/president.json");
  const years = index.offices.president.state!;
  const m = (year: number, view: View = "result") =>
    buildModel({ office: "president", level: "state", year, view, seat: "regular" }, pres, years, null, STATE)!;
  it("1968: Wallace (third party) carries Alabama in a third-party hue", () => {
    const mm = m(1968);
    expect(mm.hues["American Independent"]).toBe("Yellow");
    expect(mm.shown("01")!.c[0][0]).toBe("George Wallace");
  });
  it("2024 flip: Georgia flipped to R", () => {
    expect(m(2024, "flip").fills["13"]).toBe("rgb(191, 29, 41)");
  });
  it("1828: states admitted later have no fill", () => {
    expect(m(1828).fills["06"]).toBeUndefined();
  });
  it("map renders", () => {
    const html = renderToString(<MapView shapes={STATE} fills={m(2020).fills} selected="06" onHover={() => {}} onSelect={() => {}} />);
    expect(html.match(/<path/g)!.length).toBeGreaterThan(50);
  });
});

describe("county", () => {
  const pres: StatewideFile = json("public/data/statewide/president.json");
  const years = index.offices.president.county!;
  it("each county year colors most counties", () => {
    years.forEach((year, i) => {
      const cur: CountyFile = json(`public/data/county/president/${year}.json`);
      const prev: CountyFile | null = i ? json(`public/data/county/president/${years[i - 1]}.json`) : null;
      for (const view of VIEWS) {
        const mm = buildModel({ office: "president", level: "county", year, view, seat: "regular" }, pres, index.offices.president.state!, [cur, prev], COUNTY)!;
        const n = Object.keys(mm.fills).length;
        expect(n, `${year} ${view}`).toBeGreaterThan(3000);
        for (const f of Object.values(mm.fills)) expect(okColor(f)).toBe(true);
      }
    });
  });
});
