"""Build the block adjacency graph, weighted by shared border length (meters).

TIGER blocks are topologically consistent: two neighbouring blocks share the
exact same edge vertices. So we split every polygon ring into segments, match
identical segments across blocks, and sum their projected lengths per block
pair. Segments that appear only once lie on the state's outer boundary.
Point-only contact (queen adjacency) is ignored on purpose: districts touching
at a corner are not contiguous.
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import shapely
from pyproj import Transformer
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

EQUAL_AREA_CRS = "EPSG:5070"  # CONUS Albers, meters


@dataclass
class BlockGraph:
    xadj: np.ndarray        # CSR row pointers, len n+1
    adjncy: np.ndarray      # CSR column indices
    length: np.ndarray      # shared border length (m) per CSR entry; 0 for virtual links
    pop: np.ndarray         # population per node
    exterior: np.ndarray    # state-boundary length (m) per node
    n_virtual: int          # virtual edges added to connect islands

    @property
    def n(self) -> int:
        return len(self.pop)

    def neighbors(self, v: int) -> np.ndarray:
        return self.adjncy[self.xadj[v]:self.xadj[v + 1]]

    def matrix(self) -> sparse.csr_matrix:
        return sparse.csr_matrix((self.length, self.adjncy, self.xadj), shape=(self.n, self.n))


def _segments(geoms: np.ndarray):
    """Return (block index, start xy, end xy) for every ring segment."""
    parts, part_block = shapely.get_parts(geoms, return_index=True)
    rings, ring_part = shapely.get_rings(parts, return_index=True)
    coords, coord_ring = shapely.get_coordinates(rings, return_index=True)
    same_ring = coord_ring[:-1] == coord_ring[1:]
    a, b = coords[:-1][same_ring], coords[1:][same_ring]
    block = part_block[ring_part[coord_ring[:-1][same_ring]]]
    return block, a, b


_M1 = np.uint64(0x9E3779B97F4A7C15)
_M2 = np.uint64(0xBF58476D1CE4E5B9)
_M3 = np.uint64(0x94D049BB133111EB)


def _mix(h: np.ndarray, x: np.ndarray) -> np.ndarray:
    """splitmix64-style combine (wrapping uint64 arithmetic)."""
    h = (h ^ x.astype(np.uint64)) * _M1
    h ^= h >> np.uint64(31)
    h *= _M2
    h ^= h >> np.uint64(29)
    return h * _M3


def _segment_chunk(geoms, block_offset, tr):
    """Hash, block index, length (m) for every ring segment in a chunk of blocks."""
    block, a, b = _segments(geoms)
    ka = np.round(a * 1e7).astype(np.int64)  # 1e-7 deg ~ 1 cm; exact for TIGER topology
    kb = np.round(b * 1e7).astype(np.int64)
    swap = (ka[:, 0] > kb[:, 0]) | ((ka[:, 0] == kb[:, 0]) & (ka[:, 1] > kb[:, 1]))
    lo = np.where(swap[:, None], kb, ka)
    hi = np.where(swap[:, None], ka, kb)
    keep = (lo != hi).any(axis=1)  # drop zero-length segments
    lo, hi, block, a, b = lo[keep], hi[keep], block[keep], a[keep], b[keep]
    h = np.full(len(lo), 0x243F6A8885A308D3, dtype=np.uint64)
    for col in (lo[:, 0], lo[:, 1], hi[:, 0], hi[:, 1]):
        h = _mix(h, col)
    ax, ay = tr.transform(a[:, 0], a[:, 1])
    bx, by = tr.transform(b[:, 0], b[:, 1])
    return h, (block + block_offset).astype(np.int32), np.hypot(ax - bx, ay - by).astype(np.float32)


def build_graph(blocks: gpd.GeoDataFrame, chunk: int = 20_000) -> BlockGraph:
    """Rook adjacency weighted by shared border length.

    Memory-lean: blocks are processed in chunks, keeping only a 64-bit hash of each
    orientation-free segment (+ block id + length): ~16 B/segment instead of >100 B.
    Collision odds for 1e8 segments ~ 3e-4 (a collision would only fake one tiny edge)."""
    n = len(blocks)
    tr = Transformer.from_crs(blocks.crs, EQUAL_AREA_CRS, always_xy=True)
    geoms = blocks.geometry.values
    hs, bs, ls = [], [], []
    for start in range(0, n, chunk):
        h, bl, ln = _segment_chunk(geoms[start:start + chunk], start, tr)
        hs.append(h); bs.append(bl); ls.append(ln)
    h = np.concatenate(hs); del hs
    blk = np.concatenate(bs); del bs
    ln = np.concatenate(ls); del ls

    order = np.argsort(h, kind="stable")
    h, blk, ln = h[order], blk[order], ln[order]
    del order
    new_run = np.r_[True, h[1:] != h[:-1]]
    del h
    run_id = np.cumsum(new_run) - 1
    run_size = np.bincount(run_id)
    size = run_size[run_id]
    del run_id

    if (run_size > 2).any():
        print(f"warning: {(run_size > 2).sum()} segments shared by >2 blocks (ignored)")

    exterior = np.bincount(blk[size == 1], weights=ln[size == 1], minlength=n)

    # Pairs: first and second member of each size-2 run.
    starts = np.flatnonzero(new_run & (size == 2))
    u, v, w = blk[starts].astype(np.int64), blk[starts + 1].astype(np.int64), ln[starts].astype(np.float64)
    diff = u != v  # same block on both sides = internal ring artefact
    u, v, w = u[diff], v[diff], w[diff]

    adj = sparse.coo_matrix((np.r_[w, w], (np.r_[u, v], np.r_[v, u])), shape=(n, n)).tocsr()
    adj.sum_duplicates()

    # Connect islands / disconnected pieces to the nearest block elsewhere so
    # the graph is connected (needed for contiguous partitions).
    adj, n_virtual = _connect_components(adj, blocks)

    pop = blocks["POP20"].to_numpy(np.int64)
    return BlockGraph(adj.indptr.astype(np.int64), adj.indices.astype(np.int64),
                      adj.data.astype(np.float64), pop, exterior, n_virtual)


def _connect_components(adj: sparse.csr_matrix, blocks: gpd.GeoDataFrame):
    ncomp, label = connected_components(adj, directed=False)
    if ncomp == 1:
        return adj, 0
    pts = shapely.get_coordinates(
        blocks.to_crs(EQUAL_AREA_CRS).geometry.representative_point().values)
    main = np.bincount(label).argmax()
    tree = cKDTree(pts[label == main])
    main_idx = np.flatnonzero(label == main)
    rows, cols = [], []
    for c in range(ncomp):
        if c == main:
            continue
        members = np.flatnonzero(label == c)
        d, j = tree.query(pts[members])
        i = d.argmin()
        rows.append(members[i]); cols.append(main_idx[j[i]])
    # Virtual edges get a tiny positive weight so they exist in CSR but count ~0 border.
    eps = 1e-3
    extra = sparse.coo_matrix((np.full(2 * len(rows), eps), (rows + cols, cols + rows)), shape=adj.shape)
    out = (adj + extra).tocsr()
    return out, len(rows)
