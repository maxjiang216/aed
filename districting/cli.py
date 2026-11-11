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
_VOTES = None  # (w, s, lam) for the homogeneity term, or None
_GW = None  # graph the optimiser sees (vote-similarity weights); _G keeps true lengths
_BATCH = True


def _run_seed(job):
    method, seed = job
    t = time.time()
    if _CG is None:  # partition blocks directly
        init = (partition.partition_metis(_GW, _K, seed=seed) if method == "metis"
                else partition.partition_kahip(_GW, _K, seed=seed))
    else:  # partition coarse graph, project to blocks
        init = (partition.partition_metis(_CG, _K, seed=seed, ufactor=5, ncuts=1) if method == "metis"
                else partition.partition_kahip(_CG, _K, seed=seed, imbalance=0.005))[_CID]
    init = partition.repair_contiguity(_G, init, _K)
    pop = np.bincount(init, weights=_G.pop, minlength=_K)
    ideal = _G.pop.sum() / _K
    dev = np.abs(pop - ideal).max() / ideal
    if dev > _MAX_START:
        return method, seed, None, None, f"start deviation {dev:.1%} after contiguity repair"
    assign = partition.refine(_GW, init, _K, target=_TARGET, verbose=False, batch_balance=_BATCH,
                              votes=_VOTES)
    m = evaluate.plan_metrics(_G, _BLOCKS, assign, _K)
    src = np.repeat(np.arange(_GW.n), np.diff(_GW.xadj))
    m["objective"] = float(_GW.length[assign[src] != assign[_GW.adjncy]].sum() / 2000)  # weighted cut, km
    if _VOTES is not None:
        w, sh, lam = _VOTES
        W = np.bincount(assign, weights=w, minlength=_K)
        S = np.bincount(assign, weights=w * sh, minlength=_K)
        Q = np.bincount(assign, weights=w * sh * sh, minlength=_K)
        within = float(np.sum(Q - S * S / np.maximum(W, 1e-12)))
        m["within_ss"] = within
        m["objective"] += lam * within / 1000
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
    ap.add_argument("--vote-alpha", type=float, default=0.0,
                    help="weight borders by vote similarity: length*(1-|share diff|)^alpha (0 = plain min-border)")
    ap.add_argument("--homog-rho", type=float, default=0.0,
                    help="mix in within-district vote variance: J=(1-rho)*border/B0 + rho*W/T (0 = min-border)")
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
    global _G, _BLOCKS, _K, _TARGET, _MAX_START, _CG, _CID, _BATCH, _GW
    _G, _BLOCKS, _K, _TARGET, _MAX_START = g, blocks, k, args.target, args.max_start_dev
    _GW = g
    if args.vote_alpha:
        from . import votes
        share = votes.block_share(g, votes.block_votes(fips, abbr, blocks))
        _GW = votes.similarity_graph(g, share, args.vote_alpha)
        print(f"vote-similarity weights: alpha={args.vote_alpha}, "
              f"optimiser cut weight / true length = {_GW.length.sum() / g.length.sum():.3f}")
    _BATCH = not args.no_batch_balance
    if args.homog_rho:
        global _VOTES
        from . import votes
        v = votes.block_votes(fips, abbr, blocks)
        w = (v["dem"] + v["rep"]).to_numpy()
        sh = votes.block_share(g, v)
        T = float(np.sum(w * (sh - np.sum(w * sh) / w.sum()) ** 2))
        ref = ROOT / "output" / "national" / abbr / "metrics.json"
        B0 = (json.loads(ref.read_text())["metis"]["internal_border_km"] * 1000 if ref.exists()
              else 1.861 * np.sqrt(blocks[["ALAND20", "AWATER20"]].sum().sum() * k) - g.exterior.sum() / 2)
        lam = args.homog_rho / (1 - args.homog_rho) * B0 / T
        _VOTES = (w, sh, lam)
        print(f"homogeneity term: rho={args.homog_rho}, B0={B0/1000:.0f} km, T={T:.0f}, lam={lam:.3g} m per unit SS")
    if args.coarse != "block":
        _CG, _CID = partition.coarsen(_GW, blocks.GEOID20.to_numpy(), args.coarse)
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
            key = (m["pop_spread"] > args.target, m.get("objective", m["internal_border_km"]))
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
        pe = partition.repair_contiguity(_GW, enacted, k)
        pe_pop = np.bincount(pe, weights=g.pop, minlength=k)
        pe_dev = np.abs(pe_pop - g.pop.sum() / k).max() / (g.pop.sum() / k)
        if pe_dev <= args.max_start_dev:
            pe = partition.refine(_GW, pe, k, target=args.target, verbose=False, votes=_VOTES)
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
