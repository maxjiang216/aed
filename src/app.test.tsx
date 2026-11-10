import { readFileSync } from "node:fs";
import { renderToString } from "react-dom/server";
import { geoAlbersUsa, geoBounds, geoPath } from "d3-geo";
import { feature, mesh } from "topojson-client";
import { describe, expect, it } from "vitest";
import { buildModel, redrawnBetween, regionName, type LocalData } from "./App";
import { Legend } from "./components/Legend";
import { MapView } from "./components/MapView";
import { NationalPanel, RacePanel } from "./components/RacePanel";
import { congressFor, type DistrictMeta, type Shapes } from "./geo";
import type { CountyFile, DataIndex, HouseFile, Office, Race, StatewideFile, View } from "./types";

const json = (p: string) => JSON.parse(readFileSync(p, "utf8"));
const index: DataIndex = json("public/data/index.json");

const planar = geoPath();
function shapes(level: "state" | "county"): Shapes {
  const topo = json(`node_modules/us-atlas/${level === "state" ? "states" : "counties"}-albers-10m.json`);
  const obj = level === "county" ? topo.objects.counties : topo.objects.states;
  const fs = (feature(topo, obj) as unknown as { features: { id: string; properties: { name: string } }[] }).features;
  return {
    regions: fs.map((f) => ({ id: String(f.id), name: f.properties.name, d: planar(f as never) ?? "" })),
    borders: planar(mesh(topo, topo.objects.states, (a, b) => a !== b)) ?? "",
    outline: planar(mesh(topo, topo.objects.nation)) ?? "",
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
      renderToString(<NationalPanel sel={{ office, level: "state", year, view: "result", seat: "regular" }} races={m.allRaces} hues={m.hues} env={m.env} />);
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
      const wrap = (f: CountyFile) => Object.fromEntries(Object.entries(f).map(([k, r]) => [k, [r]]));
      const local: LocalData = { cur: wrap(cur), prev: prev && wrap(prev), prevYear: i ? years[i - 1] : null };
      for (const view of VIEWS) {
        const mm = buildModel({ office: "president", level: "county", year, view, seat: "regular" }, pres, index.offices.president.state!, local, COUNTY)!;
        const n = Object.keys(mm.fills).length;
        expect(n, `${year} ${view}`).toBeGreaterThan(3000);
        for (const f of Object.values(mm.fills)) expect(okColor(f)).toBe(true);
      }
    });
  });
});

describe("house districts", () => {
  const meta: DistrictMeta = json("public/data/house/shapes/meta.json");
  const albers = geoAlbersUsa().scale(1300).translate([487.5, 305]);
  const projected = geoPath(albers);
  const districtShapes = (c: number): Shapes => {
    const topo = json(`public/data/house/shapes/${meta.congressFile[c]}`);
    const fs = (feature(topo, topo.objects.districts) as unknown as { features: { properties: { id: string } }[] }).features;
    return { regions: fs.map((f) => ({ id: f.properties.id, name: f.properties.id, d: projected(f as never) ?? "" })), borders: "", outline: "" };
  };
  /** Fake results: party by district number parity, margin from the number. */
  const fake = (ids: string[], seed: number): HouseFile =>
    Object.fromEntries(ids.map((id, i) => {
      const dem = (i + seed) % 2 === 0;
      const w = 50 + ((i * 7 + seed) % 30);
      const race: Race = { c: [["W", dem ? "Democratic" : "Republican", w, 0], ["L", dem ? "Republican" : "Democratic", 100 - w, 0]], t: 100 };
      return [id, i % 50 === 0 ? [{ c: [["U", "Democratic", 1, 0]], t: 1, u: 1 }] : [race]];
    }));

  it("every Congress 95-119 has 435 districts that project inside the map", () => {
    for (let c = 95; c <= 119; c++) {
      const s = districtShapes(c);
      expect(s.regions.length, `congress ${c}`).toBe(435);
      for (const r of s.regions) expect(r.d.length, r.id).toBeGreaterThan(10);
    }
  });

  it("district outlines line up with the us-atlas state shapes", () => {
    // Bounding box of all projected districts vs the pre-projected states.
    const topo = json(`public/data/house/shapes/${meta.congressFile[119]}`);
    const box = projected.bounds(feature(topo, topo.objects.districts) as never);
    const st = json("node_modules/us-atlas/states-albers-10m.json");
    const sbox = planar.bounds(feature(st, st.objects.states) as never);
    for (let k = 0; k < 2; k++) for (let j = 0; j < 2; j++) expect(Math.abs(box[k][j] - sbox[k][j])).toBeLessThan(6);
    expect(geoBounds(feature(topo, topo.objects.districts) as never)[0][1]).toBeGreaterThan(17);
  });

  it("builds a district model for every view, greys out redrawn states", () => {
    const shapes = districtShapes(congressFor(2022));
    const ids = shapes.regions.map((r) => r.id);
    const local: LocalData = {
      cur: fake(ids, 0), prev: fake(ids, 1), prevYear: 2020, redrawn: redrawnBetween(meta, 2020, 2022),
    };
    expect(local.redrawn!.has("TX")).toBe(true);
    for (const view of VIEWS) {
      const m = buildModel({ office: "house", level: "district", year: 2022, view, seat: "regular" }, null, [], local, shapes)!;
      expect(Object.keys(m.fills).length).toBe(435);
      for (const f of Object.values(m.fills)) expect(okColor(f)).toBe(true);
      if (view === "flip") expect(m.prevFor("TX-02")).toBeNull();
    }
    const m = buildModel({ office: "house", level: "district", year: 2022, view: "result", seat: "regular" }, null, [], local, shapes)!;
    expect(m.noteFor("TX-02")).toMatch(/changed/);
    renderToString(<NationalPanel sel={{ office: "house", level: "district", year: 2022, view: "result", seat: "regular" }} races={m.allRaces} hues={m.hues} env={m.env} />);
    renderToString(<RacePanel title={regionName("WY-AL", null)} races={m.racesFor(ids[0])} year={2022} office="house" hues={m.hues} prev={null} note={m.noteFor("TX-02")} pinned onClose={() => {}} />);
    expect(regionName("CA-12", null)).toBe("California's 12th");
    expect(regionName("WY-AL", null)).toBe("Wyoming at-large");
  });

  it("2018 only flags Pennsylvania as redrawn", () => {
    expect([...redrawnBetween(meta, 2016, 2018)]).toEqual(["PA"]);
  });
});
