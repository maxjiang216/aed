import { readFileSync } from "node:fs";
import { beforeAll, expect, test, vi } from "vitest";
import { seatsAt } from "./DistrictsPage";
import { loadNational, loadState, loadSummary, type Summary } from "./data";

// Serve fetch() from disk: site data from public/, us-atlas from node_modules.
beforeAll(() => {
  vi.stubGlobal("fetch", async (url: string) => {
    const path = url.includes("us-atlas") ? `node_modules/us-atlas/${url.split("us-atlas/").pop()!.split("?")[0]}` : `public${url}`;
    const text = readFileSync(path, "utf8");
    return { ok: true, json: async () => JSON.parse(text) };
  });
});

test("national seat totals match the projection notes (228 D shortest-border, 224 D enacted)", async () => {
  const s: Summary = await loadSummary();
  const zero = s.swings.indexOf(0);
  expect(seatsAt(s, "metis", zero)).toEqual({ dem: 228, rep: 207, total: 435 });
  expect(seatsAt(s, "enacted", zero)).toEqual({ dem: 224, rep: 211, total: 435 });
  // Monotone in swing.
  for (let i = 1; i < s.swings.length; i++) expect(seatsAt(s, "metis", i).dem).toBeGreaterThanOrEqual(seatsAt(s, "metis", i - 1).dem);
});

test("every district in the national map has a share and a path", async () => {
  const [s, n] = await Promise.all([loadSummary(), loadNational()]);
  for (const plan of ["metis", "enacted"] as const) {
    for (const d of n.plans[plan]) {
      expect(d.path.length, d.id).toBeGreaterThan(10);
      const proj = s.states[d.st].projection[plan] ?? s.states[d.st].projection.enacted;
      expect(proj!.shares[d.d! - 1], d.id).toBeTypeOf("number");
    }
  }
  // 435 minus 6 at-large states minus Hawaii (2, no shapes) = 427.
  expect(n.plans.enacted.length).toBe(427);
  expect(n.plans.metis.length).toBe(427);
});

test("state view frames both plans", async () => {
  const ia = await loadState("IA");
  expect(ia.plans.metis).toHaveLength(4);
  expect(ia.plans.enacted).toHaveLength(4);
  expect(ia.size[1]).toBeGreaterThan(100);
});
