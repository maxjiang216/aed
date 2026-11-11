#!/usr/bin/env node
/**
 * Districting results -> website data in <repo>/public/districting/.
 *
 *   summary.json          per-state metrics + 2020-presidential projections, citizen apportionment
 *   national.json         TopoJSON, objects {metis, enacted}: every multi-district state, coarse
 *   states/<ST>.json      TopoJSON, objects {metis, enacted}: one state, finer
 *
 * Reads output/national/<ST>/{metrics,projection}.json + *_districts_land.geojson and
 * output/citizen/*.csv (run `python -m districting.national run`, `... project`,
 * `... citizen_apportion` first). Usage: node web/export.mjs
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import mapshaper from "mapshaper";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROJECT = join(HERE, "..");
const SITE = join(PROJECT, "..", "..");
const NATIONAL = join(PROJECT, "output", "national");
const CITIZEN = join(PROJECT, "output", "citizen");
const OUT = join(SITE, "public", "districting");
const PLANS = ["metis", "enacted"];
// Same grid as districting/project.py SWINGS: -10..+10 pts of D two-party share, 0.5 pt steps.
const SWINGS = Array.from({ length: 41 }, (_, i) => Math.round((-0.1 + i * 0.005) * 1000) / 1000);
const AT_LARGE = ["AK", "DE", "ND", "SD", "VT", "WY"];

const json = (p) => JSON.parse(readFileSync(p, "utf8"));
const r = (x, n = 1) => (x == null ? null : Math.round(x * 10 ** n) / 10 ** n);

function csv(p) {
  const [head, ...rows] = readFileSync(p, "utf8").trim().split("\n").map((l) => l.split(","));
  return rows.map((row) => Object.fromEntries(head.map((h, i) => [h, isNaN(+row[i]) ? row[i] : +row[i]])));
}

/** GeoJSON districts with state + projected D share attached. */
function districts(st, plan, proj) {
  const f = join(NATIONAL, st, `${plan}_districts_land.geojson`);
  if (!existsSync(f)) return null;
  const g = json(f);
  delete g.crs;
  const share = proj?.[plan]?.district_dem_share ?? [];
  g.features = g.features.map((ft) => ({
    type: "Feature",
    geometry: ft.geometry,
    properties: { st, d: ft.properties.district, dem: share[ft.properties.district - 1] ?? null },
  }));
  return g;
}

async function topo(layers, simplify, out) {
  const input = {};
  const cmds = [];
  for (const [name, fc] of Object.entries(layers)) {
    input[`${name}.json`] = fc;
    cmds.push(`-i ${name}.json name=${name}`);
  }
  const names = Object.keys(layers).join(",");
  cmds.push(`-simplify ${simplify} weighted keep-shapes target=${names}`);
  cmds.push(`-o format=topojson quantization=100000 target=${names} combine-layers out.json`);
  const res = await mapshaper.applyCommands(cmds.join(" "), input);
  writeFileSync(out, res["out.json"]);
  return res["out.json"].length;
}

const states = {};
const all = { metis: [], enacted: [] };
mkdirSync(join(OUT, "states"), { recursive: true });

for (const st of readdirSync(NATIONAL).filter((d) => /^[A-Z]{2}$/.test(d)).sort()) {
  const dir = join(NATIONAL, st);
  const metrics = json(join(dir, "metrics.json"));
  const proj = existsSync(join(dir, "projection.json")) ? json(join(dir, "projection.json")) : null;
  const enactedKey = Object.keys(metrics).find((k) => k.startsWith("enacted"));
  const m = (k) =>
    metrics[k] && {
      spread: metrics[k].pop_spread,
      maxDevPct: r(metrics[k].max_dev_pct, 3),
      borderKm: r(metrics[k].internal_border_km),
      ppMean: r(metrics[k].polsby_popper_mean, 3),
      splitCounties: metrics[k].split_counties,
    };
  const p = (k) =>
    proj?.[k] && {
      dem: proj[k].dem_seats,
      rep: proj[k].rep_seats,
      statewideDem: proj[k].statewide_dem,
      efficiencyGap: proj[k].efficiency_gap,
      competitive: proj[k].competitive_seats,
      shares: proj[k].district_dem_share,
      swing: proj[k].swing_dem_seats,
    };
  states[st] = {
    seats: metrics[enactedKey].districts,
    metrics: { metis: m("metis"), enacted: m(enactedKey) },
    projection: { metis: p("metis"), enacted: p("enacted") },
  };

  const layers = {};
  for (const plan of PLANS) {
    const g = districts(st, plan, proj);
    if (g) {
      layers[plan] = g;
      all[plan].push(...g.features);
    }
  }
  if (!Object.keys(layers).length) {
    console.log(`${st}  no district shapes`);
    continue;
  }
  const size = await topo(layers, "4%", join(OUT, "states", `${st}.json`));
  console.log(`${st}  ${Object.keys(layers).join("+")}  ${(size / 1024).toFixed(0)} KB`);
}

// Single-district states: 2020 presidential two-party D share from the AED data.
const pres = json(join(SITE, "public", "data", "statewide", "president.json"))["2020"];
const atLarge = {};
for (const st of AT_LARGE) {
  const c = pres[st][0].c; // [[name, party, votes, ...]]
  const d = c.find((x) => x[1] === "Democratic")[2];
  const rep = c.find((x) => x[1] === "Republican")[2];
  atLarge[st] = r(d / (d + rep), 4);
}

const fc = (features) => ({ type: "FeatureCollection", features });
const size = await topo({ metis: fc(all.metis), enacted: fc(all.enacted) }, "0.6%", join(OUT, "national.json"));
console.log(`national  ${(size / 1024).toFixed(0)} KB`);

const summary = {
  generated: new Date().toISOString().slice(0, 10),
  swings: SWINGS,
  states,
  atLarge,
  citizen: { states: csv(join(CITIZEN, "states.csv")), elections: csv(join(CITIZEN, "elections.csv")) },
};
writeFileSync(join(OUT, "summary.json"), JSON.stringify(summary));
console.log(`summary  ${(JSON.stringify(summary).length / 1024).toFixed(0)} KB`);
