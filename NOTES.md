# Districting experiments — log

Goal: congressional districts at census-block level with equal population
(max-min ≤ 1 person) that minimize total internal border length. Ignores VRA,
communities of interest, county splits (for now).

Pipeline: `python -m districting.cli <STATE>`
- data: TIGER/Line 2020 `tabblock20` (includes PL 94-171 POP20); enacted = TIGER 2024 cd119
- graph: rook adjacency, edge weight = shared border length (m, EPSG:5070)
- METIS / KaHIP initial partition → contiguity repair → balance refinement → border polish
- outputs: `output/<ST>/{map.png, metrics.json, *_assignment.csv, *_districts.geojson}`

## Runs

| name | cmd | check |
|---|---|---|
| ia-v1 | `python -u -m districting.cli IA --seeds 2` | spread reaches ≤1? border km vs enacted; runtime of refine |

ia-v1: killed — Python refinement too slow (~4 moves/s on KaHIP start). Ported refine to C++
(`cpp/refine.cpp`, pybind11, `make`). Multi-source BFS removability + halving population cap
with polish at each level. KaHIP start: 69s -> 0.26s, border 1768 -> 1347 km.

### IA results (C++ refine, 3 seeds each, ~30s total)

| plan | spread | border km | PP mean | split counties |
|---|---|---|---|---|
| metis (seed 2) | 1 | 965.2 | 0.478 | 20 |
| kahip (seed 1) | 1 | 1058.8 | 0.451 | 23 |
| enacted 119th | 94 | 1423.5 | 0.333 | 1 |

Findings:
- KaHIP respects imbalance=0.001 but returns non-contiguous parts; contiguity repair then creates
  ~9% imbalance and balancing degrades border. KaHIP imbalance=0 hangs.
- Raw KaHIP (non-contiguous) cut is ~820 km -> real optimum likely well below 965.
- Seed variance large (METIS 965–1013, KaHIP 1059–1380): more seeds / stronger local search pay.
- Enacted spread 94 may partly be centroid-join error; IA keeps counties whole by law.

Next ideas: many seeds in parallel; perturb+rebalance (iterated local search) in C++;
contiguity-aware KaHIP fix; county-penalty weights; try WI/NC.

### Profiling + speedups (2026-11-10)
- Stage times before: KaHIP STRONG 5.4–6.0 s/seed (dominant), METIS 0.75 s/seed, C++ refine 0.02–0.27 s,
  load zip 1.5 s, dissolve 0.9 s.
- Fixes: KaHIP default mode ECO (~30x faster, same quality); seeds in parallel (`--workers`, default 4 —
  user cap 4 CPUs); reject seeds with >2% deviation after contiguity repair (`--max-start-dev`);
  C++ candidate loop now tries all candidates (was top-256 → balancer got stuck at spread 35,668);
  blocks cached as parquet (1.5 s → 0.6 s).
- Result: 16 seeds in 2.6 s on 4 workers (was ~4 s/seed serial). Whole IA run ~8 s, mostly I/O + plotting.
- More seeds → IA METIS best 947.1 km (was 965.2).

### Target sweep IA (8 seeds/method)
| target | metis spread | metis km | kahip km |
|---|---|---|---|
| 1 | 1 | 947.1 | 1035.6 |
| 10 | 9 | 947.0 | 1035.4 |
| 100 | 46 | 947.0 | 1035.4 |
Exact equality costs ~0.1 km here: METIS start is already ~0.1% off, and balancing uses tiny blocks.
Looser targets only matter if initial partition gets the slack too (METIS ufactor scaled to target).

### Speed round 2 (2026-11-10)
Per-seed IA (k=4): METIS on blocks 690 ms = 97% of seed time; refine 8 ms. At k=40 refine 0.8 s.
perf blocked (perf_event_paranoid=4, needs sudo) — timers used instead.
- METIS ncuts=1: 3.8x faster/call but worse median; ~wash.
- **Coarse start**: METIS on block groups (2,703 nodes) 2 ms, tracts (896) 1 ms; project to blocks,
  repair, block-level refine. Better best plans (tract 922 km, BG 936–942) — more diverse starts.
- Refine then dominated (coarse starts less balanced): added batched moves per scan (skip candidates
  adjacent to a block moved this pass). Polish batching is quality-neutral; balance batching ~3%
  worse median (scatters notches instead of growing compact patches) but 3–22x faster.
  Flag: `--no-batch-balance`.
- Default now `--coarse blockgroup` + batched balance: **96 seeds in 2.1 s on 4 workers**
  (was 16 seeds in 2.6 s). IA best 942.1 km at 48 seeds/method.
- Open: some seeds end at spread 2 (and k=40 at 32–54) — single-move balancer stuck; needs
  chain/path balancing. Tract + sequential balance found 922.4 km (best so far).

| national-v1 | `python -m districting.national run --seeds 8 --workers 4` | all 44 multi-district states; output/national/{summary.csv,national_map.png,timings.json}; check spread>1 in big-k states (balancer stuck), CA/TX memory+time |

- RI enacted spread 1,223 on raw PL data is real: RI reallocates prisoners to home address. Enacted
  spreads are vs unadjusted PL 94-171, so can look >1 in reallocation states (CA, NY, MD, RI, ...).

national-v1 result: 42/44 states ran, ~18 min wall. CA, TX OOM-killed in graph build (~11 GB RSS;
segment arrays for all vertices). HI: no valid plan. summary() crashed on HI (fixed).
| render-v1 | summary + render.render_state for all states + national_map_land.png | check maps look sane |

### Fix round (2026-11-10, user-approved list)
1. Graph build memory: chunked + 64-bit segment hash (~16 B/segment). IA identical graph, 5 s, peak 1.55 GB.
2. ~~Water-only blocks dropped from graph only for MI~~ — MISREAD. User wants all water data in the
   algorithm; water handling is visual only (render.py). DROP_WATER_STATES now empty; national-v2 MI
   ran with water dropped -> rerun MI after v2. (Original text:) Water-only blocks dropped from graph **only for MI** (`--drop-water auto`, DROP_WATER_STATES={"MI"});
   only uninhabited ones (some water blocks have residents). Graph cache `26_land.pkl`.
   MI PP not comparable (shoreline counts as perimeter).
3. coarsen() splits block groups disconnected at block level into separate coarse nodes.
4. Balancing: chain moves (path S->...->T) + pair swaps (net transfer = pop difference) when
   no single move helps. IA graph k=40 spreads 30–54 -> 4–8; k=16 -> 1–2. Exact 1 at high k still open.
5. KaHIP off by default (`--methods metis`).
6. `polished-enacted` plan: enacted + same repair/refine; skipped if repair >2% off (MI: 36.9%,
   UP joined only across Mackinac). IA: 1424 -> 1415 km (layout, not jagged edges, is the cost).
- New `--target-pct` (user: 0.1% of ideal district pop).
| national-v2 | `python -m districting.national run --seeds 8 --workers 4 --target-pct 0.001` | CA/TX finish? spreads <= target? FL vs enacted; seeds rejected count; polished-enacted vs enacted |
| project-v1 | `python -m districting.project output/national` | VEST 2020 pres -> blocks; seats enacted vs metis vs polished; output/national/{projection_summary.txt,projection_by_state.csv,swing_curve.png} |
| project-v2 | rerun of project-v1 (v1: VEST downloads 403 via urllib; now curl) | national seats enacted vs metis |
| project-v3 | rerun (v2: Dataverse file-list call still urllib -> 403; now curl) | national seats |

### Projection results (project-v3, 2020 presidential two-party, VEST -> blocks by pop)
- National: enacted 224D-211R; min-border (metis) 228D-207R; polished-enacted 224D-211R (identical
  to enacted in every state — local polish never flips a seat). LA, HI: no metis plan -> enacted used.
- 24 states change; gross 34 seats move, net only +4 D. R-drawn maps lose R seats (TX +5D, FL +3D,
  OH/NC/WI/TN/SC/UT/MO/OK/GA +1D); D-drawn lose D seats (IL -3, NM/NV/OR/NJ -1).
- VRA caveat: AL -2D, MS -1D — min-border drops the court-ordered Black-opportunity districts.
  AZ -2D (commission map), MN/MI/PA -1D.
- Swing curve: both maps cross 218 at about -1 pt; at +5 pt D swing metis 284 vs enacted 263
  (enacted maps damp D wave gains); at -5 pt 188 vs 191.
