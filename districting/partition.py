"""Partition the block graph into k districts.

Pipeline:
  1. METIS or KaHIP: balanced partition minimising cut weight
     (vertex weight = population, edge weight = shared border length).
  2. Contiguity repair: reattach any stray fragments to a neighbouring district.
  3. Balance refinement: move boundary blocks until max-min district population
     <= target (default 1 person), picking moves with the least added border per unit of
     balance gained, never disconnecting a district.
  4. Border polish: greedy moves that shorten total border without worsening
     the population spread.
"""

from __future__ import annotations

from collections import deque

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components

from .graph import BlockGraph


# ---------------------------------------------------------------- initial ---

COARSE_LEVELS = {"block": 15, "blockgroup": 12, "tract": 11}  # GEOID20 prefix length


def coarsen(g: BlockGraph, geoids: np.ndarray, level: str):
    """Merge blocks into census block groups / tracts. Returns (coarse graph, block->coarse id).

    Partitioning the coarse graph is ~350x faster than the block graph and gives more
    diverse starts; the block-level refine then fixes balance and borders."""
    nchar = COARSE_LEVELS[level]
    _, cid = np.unique(np.asarray([x[:nchar] for x in geoids]), return_inverse=True)
    src = np.repeat(np.arange(g.n), np.diff(g.xadj))
    # Split units that are disconnected at block level (islands, water gaps) into
    # separate coarse nodes, so a contiguous coarse partition is contiguous on blocks.
    inside = cid[src] == cid[g.adjncy]
    within = sparse.coo_matrix((np.ones(inside.sum()), (src[inside], g.adjncy[inside])), shape=(g.n, g.n))
    _, cid = connected_components(within, directed=False)
    nc = int(cid.max()) + 1
    m = sparse.coo_matrix((g.length, (cid[src], cid[g.adjncy])), shape=(nc, nc)).tocsr()
    m.setdiag(0)
    m.eliminate_zeros()
    cg = BlockGraph(m.indptr.astype(np.int64), m.indices.astype(np.int64), m.data.astype(np.float64),
                    np.bincount(cid, weights=g.pop, minlength=nc).astype(np.int64),
                    np.bincount(cid, weights=g.exterior, minlength=nc), 0)
    return cg, cid

def _int_edge_weights(g: BlockGraph) -> np.ndarray:
    return np.maximum(1, np.round(g.length)).astype(np.int64)


def partition_metis(g: BlockGraph, k: int, ufactor: int = 1, seed: int = 0, ncuts: int = 8) -> np.ndarray:
    import pymetis
    opts = pymetis.Options(ufactor=ufactor, contig=True, ncuts=ncuts, seed=seed, niter=50)
    _, parts = pymetis.part_graph(k, xadj=g.xadj, adjncy=g.adjncy, vweights=g.pop,
                                  eweights=_int_edge_weights(g), options=opts)
    return np.asarray(parts, dtype=np.int64)


def partition_kahip(g: BlockGraph, k: int, imbalance: float = 0.001, seed: int = 0, mode: int = 1) -> np.ndarray:
    """mode: 0 FAST, 1 ECO, 2 STRONG. ECO ~30x faster than STRONG on IA, same quality."""
    import kahip
    _, parts = kahip.kaffpa(g.pop.tolist(), g.xadj.tolist(), _int_edge_weights(g).tolist(),
                            g.adjncy.tolist(), k, imbalance, True, seed, mode)
    return np.asarray(parts, dtype=np.int64)


# ------------------------------------------------------------- contiguity ---

def repair_contiguity(g: BlockGraph, assign: np.ndarray, k: int) -> np.ndarray:
    assign = assign.copy()
    m = g.matrix()
    while True:
        moved = False
        for d in range(k):
            idx = np.flatnonzero(assign == d)
            ncomp, lab = connected_components(m[idx][:, idx], directed=False)
            if ncomp == 1:
                continue
            comp_pop = np.bincount(lab, weights=g.pop[idx], minlength=ncomp)
            comp_n = np.bincount(lab, minlength=ncomp)
            keep = np.lexsort((comp_n, comp_pop))[-1]
            for c in range(ncomp):
                if c == keep:
                    continue
                members = idx[lab == c]
                # Neighbouring district with the longest shared border.
                sub = m[members]
                nbr_d = assign[sub.indices]
                w = np.bincount(nbr_d, weights=sub.data, minlength=k)
                w[d] = -1
                assign[members] = int(w.argmax())
                moved = True
        if not moved:
            return assign


# ------------------------------------------------------------ refinement ---

class Refiner:
    """Local search over single-block moves with incremental bookkeeping.

    L[v, d] = border length between block v and district d.
    """

    def __init__(self, g: BlockGraph, assign: np.ndarray, k: int):
        self.g, self.k = g, k
        self.assign = assign.copy()
        src = np.repeat(np.arange(g.n), np.diff(g.xadj))
        self.L = np.zeros((g.n, k), dtype=np.float64)
        np.add.at(self.L, (src, self.assign[g.adjncy]), g.length)
        self.dpop = np.bincount(self.assign, weights=g.pop, minlength=k).astype(np.int64)
        self.ideal = g.pop.sum() / k
        self._update_boundary(np.arange(g.n))

    def _update_boundary(self, nodes: np.ndarray):
        if not hasattr(self, "bmask"):
            self.bmask = np.zeros(self.g.n, dtype=bool)
        own = self.L[nodes, self.assign[nodes]]
        self.bmask[nodes] = self.L[nodes].sum(axis=1) - own > 0

    def spread(self) -> int:
        return int(self.dpop.max() - self.dpop.min())

    def cut_length(self) -> float:
        return float((self.L.sum() - self.L[np.arange(self.g.n), self.assign].sum()) / 2)

    def _removable(self, v: int) -> bool:
        """Would district assign[v] stay connected without v?"""
        g, a = self.g, self.assign
        d = a[v]
        nb = g.neighbors(v)
        same = nb[a[nb] == d]
        if len(same) <= 1:
            return len(same) == 1  # leaf is fine; a lone block would empty its district
        targets = set(same.tolist())
        start = same[0]
        seen = {v, start}
        targets.discard(start)
        q = deque([start])
        while q and targets:
            u = q.popleft()
            for x in g.neighbors(u):
                if x not in seen and a[x] == d:
                    seen.add(x)
                    targets.discard(x)
                    q.append(x)
        return not targets

    def move(self, v: int, b: int):
        g = self.g
        a = self.assign[v]
        nb = g.neighbors(v)
        w = g.length[g.xadj[v]:g.xadj[v + 1]]
        self.L[nb, a] -= w
        self.L[nb, b] += w
        self.assign[v] = b
        self.dpop[a] -= g.pop[v]
        self.dpop[b] += g.pop[v]
        self._update_boundary(np.r_[v, nb])

    def _excl_extremes(self):
        """mx[a, b] / mn[a, b] = max / min population over districts other than a and b."""
        k, d = self.k, self.dpop.astype(np.float64)
        mx = np.full((k, k), -np.inf)
        mn = np.full((k, k), np.inf)
        for a in range(k):
            for b in range(k):
                rest = np.delete(d, [a, b]) if a != b else np.delete(d, [a])
                if len(rest):
                    mx[a, b], mn[a, b] = rest.max(), rest.min()
        return mx, mn

    def _candidates(self, mode: str, spread_cap: int):
        """Return (nodes, targets, score) sorted best-first."""
        g, k = self.g, self.k
        bn = np.flatnonzero(self.bmask)
        if mode == "balance":
            bn = bn[g.pop[bn] > 0]
        if len(bn) == 0:
            return None
        A = self.assign[bn]
        Lb = self.L[bn]
        p = g.pop[bn].astype(np.float64)
        dcut = Lb[np.arange(len(bn)), A][:, None] - Lb  # added border if moved to column d
        valid = Lb > 0
        valid[np.arange(len(bn)), A] = False
        dev = self.dpop - self.ideal
        if mode == "balance":
            gain = 2 * p[:, None] * (dev[A][:, None] - dev[None, :] - p[:, None])
            valid &= gain > 0
            score = np.where(valid, (dcut + 1e-6) / np.where(valid, gain, 1), np.inf)
            # Moves that also shorten the border are always welcome: rank them first.
            score = np.where(valid & (dcut < 0), dcut - 1e12, score)
        else:  # polish: only border-reducing moves that keep spread <= cap
            valid &= dcut < -1e-6
            # Exact new spread: extremes over {A-p, d+p, all other districts}.
            mx, mn = self._excl_extremes()
            new_a = self.dpop[A][:, None] - p[:, None]
            new_b = self.dpop[None, :] + p[:, None]
            hi = np.maximum(np.maximum(new_a, new_b), mx[A])
            lo = np.minimum(np.minimum(new_a, new_b), mn[A])
            valid &= (hi - lo) <= spread_cap
            score = np.where(valid, dcut, np.inf)
        flat = np.flatnonzero(np.isfinite(score))
        if len(flat) == 0:
            return None
        order = flat[np.argsort(score.ravel()[flat])]
        rows, cols = np.divmod(order, k)
        return bn[rows], cols

    def _try_moves(self, nodes, targets, mode: str, spread_cap: int, limit: int = 200) -> bool:
        for v, b in zip(nodes[:limit], targets[:limit]):
            v, b = int(v), int(b)
            a = self.assign[v]
            if mode == "polish":
                newpop = self.dpop.copy()
                newpop[a] -= self.g.pop[v]
                newpop[b] += self.g.pop[v]
                if newpop.max() - newpop.min() > spread_cap:
                    continue
            if self._removable(v):
                self.move(v, b)
                return True
        return False

    def balance(self, target: int = 1, max_iter: int = 200_000, log_every: int = 500) -> None:
        it = 0
        while self.spread() > target and it < max_iter:
            cand = self._candidates("balance", 0)
            if cand is None or not self._try_moves(*cand, "balance", 0):
                print(f"  balance: stuck at spread {self.spread()}")
                break
            it += 1
            if it % log_every == 0:
                print(f"  balance it={it} spread={self.spread()} cut={self.cut_length()/1000:.1f} km")
        print(f"  balance done: {it} moves, spread={self.spread()}")

    def polish(self, spread_cap: int, max_iter: int = 200_000, log_every: int = 2000) -> None:
        it = 0
        start = self.cut_length()
        while it < max_iter:
            cand = self._candidates("polish", spread_cap)
            if cand is None or not self._try_moves(*cand, "polish", spread_cap):
                break
            it += 1
            if it % log_every == 0:
                print(f"  polish it={it} cut={self.cut_length()/1000:.1f} km")
        print(f"  polish done: {it} moves, cut {start/1000:.1f} -> {self.cut_length()/1000:.1f} km")


def refine(g: BlockGraph, assign: np.ndarray, k: int, target: int = 1, polish_rounds: int = 3,
           backend: str = "cpp", verbose: bool = True,
           batch_balance: bool = False) -> np.ndarray:
    if backend == "cpp":
        from . import _refine
        return np.asarray(_refine.refine(g.xadj, g.adjncy, g.length, g.pop, assign, k,
                                         target=target, rounds=polish_rounds, verbose=verbose,
                                         batch_balance=batch_balance))
    r = Refiner(g, assign, k)
    print(f"  start: spread={r.spread()} cut={r.cut_length()/1000:.1f} km")
    r.polish(spread_cap=max(target, r.spread()))
    for _ in range(polish_rounds):
        before = r.cut_length()
        r.balance(target)
        r.polish(spread_cap=max(target, r.spread()))
        if r.spread() <= target and abs(before - r.cut_length()) < 1:
            break
    return r.assign
