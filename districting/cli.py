"""Draw equal-population congressional districts that minimise total border length.

Usage:
    python -m districting.cli IA                # METIS + KaHIP, compare to enacted
    python -m districting.cli WI --methods metis --seeds 4
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, evaluate, graph, partition

ROOT = Path(__file__).resolve().parent.parent


DROP_WATER_STATES: set[str] = set()  # water stays in the algorithm; render.py handles visuals


def load_graph(fips: str, blocks, tag: str = ""):
    cache = ROOT / "data" / "graph" / f"{fips}{tag}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    t = time.time()
    g = graph.build_graph(blocks)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(g))
    print(f"graph: {g.n} blocks, {len(g.adjncy)//2} edges, {g.n_virtual} virtual links, "
          f"{time.time()-t:.1f}s")
    return g


_G = _BLOCKS = _K = _TARGET = _MAX_START = None
_CG = _CID = None
_BATCH = True


def _run_seed(job):
    method, seed = job
    t = time.time()
    if _CG is None:  # partition blocks directly
        init = (partition.partition_metis(_G, _K, seed=seed) if method == "metis"
                else partition.partition_kahip(_G, _K, seed=seed))
    else:  # partition coarse graph, project to blocks
        init = (partition.partition_metis(_CG, _K, seed=seed, ufactor=5, ncuts=1) if method == "metis"
                else partition.partition_kahip(_CG, _K, seed=seed, imbalance=0.005))[_CID]
    init = partition.repair_contiguity(_G, init, _K)
    pop = np.bincount(init, weights=_G.pop, minlength=_K)
    ideal = _G.pop.sum() / _K
    dev = np.abs(pop - ideal).max() / ideal
    if dev > _MAX_START:
        return method, seed, None, None, f"start deviation {dev:.1%} after contiguity repair"
    assign = partition.refine(_G, init, _K, target=_TARGET, verbose=False, batch_balance=_BATCH)
    m = evaluate.plan_metrics(_G, _BLOCKS, assign, _K)
    return method, seed, assign, m, f"{time.time()-t:.1f}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state", help="postal code or FIPS, e.g. IA or 19")
    ap.add_argument("--methods", default="metis", help="comma list of metis,kahip")
    ap.add_argument("--seeds", type=int, default=3, help="initial partitions per method; best kept")
    ap.add_argument("--target", type=int, default=1, help="max-min district population")
    ap.add_argument("--target-pct", type=float, default=None,
                    help="spread target as fraction of ideal district pop (e.g. 0.001); overrides --target")
    ap.add_argument("--drop-water", choices=["auto", "yes", "no"], default="auto",
                    help="drop water-only blocks (ALAND20==0) from the graph; auto = only " + ",".join(sorted(DROP_WATER_STATES)))
    ap.add_argument("--no-enacted", action="store_true")
    ap.add_argument("--workers", type=int, default=4, help="parallel seed workers (user cap: 4 CPUs)")
    ap.add_argument("--max-start-dev", type=float, default=0.02,
                    help="reject a seed if, after contiguity repair, max |pop-ideal|/ideal exceeds this")
    ap.add_argument("--coarse", default="blockgroup", choices=["block", "blockgroup", "tract"],
                    help="graph level for the initial METIS/KaHIP partition (refine is always block-level)")
    ap.add_argument("--no-batch-balance", action="store_true",
                    help="one move per scan in balancing: ~3x slower, slightly better median")
    ap.add_argument("--out", default=None, help="output dir (default output/<ST>)")
    args = ap.parse_args()

    fips, abbr, k = data.resolve_state(args.state)
    out = Path(args.out) if args.out else ROOT / "output" / abbr
    out.mkdir(parents=True, exist_ok=True)

    t = time.time()
    blocks = data.load_blocks(fips)
    drop_water = args.drop_water == "yes" or (args.drop_water == "auto" and abbr in DROP_WATER_STATES)
    if drop_water:
        # Drop uninhabited water-only blocks (some water blocks have residents, e.g. houseboats).
        blocks = blocks[(blocks["ALAND20"] > 0) | (blocks["POP20"] > 0)].reset_index(drop=True)
    print(f"{abbr}: {len(blocks)} blocks{' (water blocks dropped)' if drop_water else ''}, "
          f"pop {blocks.POP20.sum():,}, {k} districts ({time.time()-t:.1f}s)")
    g = load_graph(fips, blocks, "_land" if drop_water else "")
    if args.target_pct is not None:
        args.target = max(1, int(args.target_pct * g.pop.sum() / k))
        print(f"target spread: {args.target} ({args.target_pct:.2%} of ideal)")

    # Seeds run in parallel worker processes (fork shares the graph read-only).
    global _G, _BLOCKS, _K, _TARGET, _MAX_START, _CG, _CID, _BATCH
    _G, _BLOCKS, _K, _TARGET, _MAX_START = g, blocks, k, args.target, args.max_start_dev
    _BATCH = not args.no_batch_balance
    if args.coarse != "block":
        _CG, _CID = partition.coarsen(g, blocks.GEOID20.to_numpy(), args.coarse)
        print(f"coarse graph: {args.coarse}, {_CG.n} nodes")
    jobs = [(m, s) for m in args.methods.split(",") for s in range(args.seeds)]
    t = time.time()
    with mp.get_context("fork").Pool(min(args.workers, len(jobs))) as pool:
        results = pool.map(_run_seed, jobs)
    print(f"{len(jobs)} seeds in {time.time()-t:.1f}s on {min(args.workers, len(jobs))} workers")

    plans, metrics = {}, {}
    for method in args.methods.split(","):
        best = None
        for (m_name, seed, assign, m, info) in results:
            if m_name != method:
                continue
            if assign is None:
                print(f"[{method} seed={seed}] rejected: {info}")
                continue
            print(f"[{method} seed={seed}] spread={m['pop_spread']} border={m['internal_border_km']:.1f} km "
                  f"PP={m['polsby_popper_mean']:.3f} ({info})")
            key = (m["pop_spread"] > args.target, m["internal_border_km"])
            if best is None or key < best[0]:
                best = (key, assign, m)
        if best is None:
            print(f"[{method}] no valid plan")
            continue
        _, assign, m = best
        plans[method], metrics[method] = assign, m
        pd.DataFrame({"GEOID20": blocks.GEOID20, "district": assign + 1}).to_csv(
            out / f"{method}_assignment.csv", index=False)

    if not args.no_enacted:
        enacted = evaluate.enacted_assignment(blocks, data.load_enacted(fips))
        plans["enacted (119th)"] = enacted
        metrics["enacted (119th)"] = evaluate.plan_metrics(g, blocks, enacted, k)
        # Enacted map + the same local refinement: how much is layout vs jagged edges?
        # Skipped if contiguity repair unbalances it (e.g. districts joined only by water).
        pe = partition.repair_contiguity(g, enacted, k)
        pe_pop = np.bincount(pe, weights=g.pop, minlength=k)
        pe_dev = np.abs(pe_pop - g.pop.sum() / k).max() / (g.pop.sum() / k)
        if pe_dev <= args.max_start_dev:
            pe = partition.refine(g, pe, k, target=args.target, verbose=False)
            plans["polished-enacted"] = pe
            metrics["polished-enacted"] = evaluate.plan_metrics(g, blocks, pe, k)
            pd.DataFrame({"GEOID20": blocks.GEOID20, "district": pe + 1}).to_csv(
                out / "polished-enacted_assignment.csv", index=False)
        else:
            print(f"polished-enacted skipped: {pe_dev:.1%} deviation after contiguity repair")

    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    shapes = {name: evaluate.dissolve(blocks, a, k) for name, a in plans.items()}
    for name, gdf in shapes.items():
        if name in args.methods.split(","):
            gdf.to_file(out / f"{name}_districts.geojson", driver="GeoJSON")
    evaluate.plot_plans(shapes, metrics, f"{abbr}: {k} districts, min total border, equal population",
                        out / "map.png")

    for m in metrics.values():
        m["target"] = args.target
    print("\nmethod              spread  border_km  PP_mean  split_counties")
    for name, m in metrics.items():
        print(f"{name:18s} {m['pop_spread']:7d} {m['internal_border_km']:10.1f} "
              f"{m['polsby_popper_mean']:8.3f} {m['split_counties']:8d}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
