// Local-search refinement for equal-population, min-border districting.
//
// Graph: CSR (xadj, adjncy) with per-entry border length; node weight = population.
// Moves single boundary blocks between adjacent districts, never disconnecting
// the source district.
//
//   balance(): drive max-min district population down to `target`, choosing
//              moves with the least added border per unit of squared-deviation gain.
//   polish():  greedy border-reducing moves that keep spread <= cap.
//
// Exposed to Python via pybind11 as districting._refine.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

namespace py = pybind11;
using i64 = int64_t;

struct Candidate {
    double score;
    int v, b;
    bool operator<(const Candidate& o) const { return score < o.score; }
};

class Refiner {
public:
    Refiner(py::array_t<i64, py::array::c_style | py::array::forcecast> xadj,
            py::array_t<i64, py::array::c_style | py::array::forcecast> adjncy,
            py::array_t<double, py::array::c_style | py::array::forcecast> length,
            py::array_t<i64, py::array::c_style | py::array::forcecast> pop,
            py::array_t<i64, py::array::c_style | py::array::forcecast> assign, int k)
        : k_(k) {
        n_ = static_cast<int>(pop.size());
        xadj_.assign(xadj.data(), xadj.data() + xadj.size());
        adjncy_.assign(adjncy.data(), adjncy.data() + adjncy.size());
        len_.assign(length.data(), length.data() + length.size());
        pop_.assign(pop.data(), pop.data() + pop.size());
        assign_.resize(n_);
        dpop_.assign(k_, 0);
        for (int v = 0; v < n_; ++v) {
            assign_[v] = static_cast<int>(assign.data()[v]);
            dpop_[assign_[v]] += pop_[v];
            total_ += pop_[v];
        }
        ideal_ = static_cast<double>(total_) / k_;
        acc_.assign(k_, 0.0);
        acc_seen_.assign(k_, 0);
        seen_.assign(n_, 0);
        owner_.assign(n_, 0);
        dirty_.assign(n_, 0);
        bpos_.assign(n_, -1);
        for (int v = 0; v < n_; ++v) update_boundary(v);
    }

    i64 spread() const {
        auto [mn, mx] = std::minmax_element(dpop_.begin(), dpop_.end());
        return *mx - *mn;
    }

    double cut_length() const {
        double s = 0;
        for (int v = 0; v < n_; ++v)
            for (i64 e = xadj_[v]; e < xadj_[v + 1]; ++e)
                if (assign_[adjncy_[e]] != assign_[v]) s += len_[e];
        return s / 2;
    }

    py::array_t<i64> assignment() const {
        py::array_t<i64> out(n_);
        auto* p = out.mutable_data();
        for (int v = 0; v < n_; ++v) p[v] = assign_[v];
        return out;
    }

    py::array_t<i64> district_pop() const {
        py::array_t<i64> out(k_);
        std::copy(dpop_.begin(), dpop_.end(), out.mutable_data());
        return out;
    }

    int balance(i64 target, int max_iter, bool verbose) {
        int it = 0;
        balance_target_ = target;
        while (spread() > target && it < max_iter) {
            int m = step(/*polish=*/false, 0);
            if (m == 0) {
                // No single move helps: swap a block pair between neighbours (net
                // transfer = difference of their populations), else use a path.
                if (swap_move() || chain_move()) {
                    ++chains_;
                    ++it;
                    continue;
                }
                if (verbose) py::print("  balance: stuck at spread", spread());
                break;
            }
            it += m;
            if (verbose && it % 5000 == 0)
                py::print("  balance it=", it, "spread=", spread(), "cut_km=", cut_length() / 1000);
        }
        if (verbose) py::print("  balance done:", it, "moves, spread =", spread());
        return it;
    }

    int polish(i64 cap, int max_iter, bool verbose) {
        double start = verbose ? cut_length() : 0;
        int it = 0;
        int m;
        while (it < max_iter && (m = step(/*polish=*/true, cap)) > 0) it += m;
        if (verbose)
            py::print("  polish done:", it, "moves, cut_km", start / 1000, "->", cut_length() / 1000);
        return it;
    }

    int chains() const { return chains_; }

    // Pair swap between adjacent districts S (heavier) and D: move v (S->D) and
    // u (D->S). Net transfer delta = pop[v] - pop[u] improves sum of squares iff
    // 0 < delta < dpop[S] - dpop[D]. Best gain first, ties by added border.
    bool swap_move() {
        const size_t kk = static_cast<size_t>(k_) * k_;
        if (buckets_.size() != kk) buckets_.assign(kk, {});
        for (auto& b : buckets_) b.clear();
        for (int v : blist_) {
            neighbor_lengths(v);
            const int a = assign_[v];
            for (int d : touched_)
                if (d != a) buckets_[static_cast<size_t>(a) * k_ + d].push_back({v, acc_[a] - acc_[d]});
        }
        struct Swap {
            double gain, dcut;
            int v, u, S, D;
        };
        std::vector<Swap> swaps;
        for (int S = 0; S < k_; ++S)
            for (int D = 0; D < k_; ++D) {
                const i64 gap = dpop_[S] - dpop_[D];
                if (S == D || gap < 2) continue;
                const auto& out = buckets_[static_cast<size_t>(S) * k_ + D];
                const auto& in = buckets_[static_cast<size_t>(D) * k_ + S];
                if (out.empty() || in.empty()) continue;
                Swap best{-1, 0, -1, -1, S, D};
                for (const auto& [v, dv] : out)
                    for (const auto& [u, du] : in) {
                        const i64 delta = pop_[v] - pop_[u];
                        if (delta <= 0 || delta >= gap) continue;
                        const double gain = 2.0 * delta * (gap - delta);
                        const double dc = dv + du;
                        if (gain > best.gain || (gain == best.gain && dc < best.dcut))
                            best = {gain, dc, v, u, S, D};
                    }
                if (best.v >= 0) swaps.push_back(best);
            }
        std::sort(swaps.begin(), swaps.end(), [](const Swap& x, const Swap& y) {
            return x.gain != y.gain ? x.gain > y.gain : x.dcut < y.dcut;
        });
        for (const Swap& w : swaps) {
            if (!removable(w.v)) continue;
            move(w.v, w.D);
            if (assign_[w.u] == w.D && removable(w.u)) {
                move(w.u, w.S);
                ++swaps_;
                return true;
            }
            move(w.v, w.S);  // undo
        }
        return false;
    }

    int swaps() const { return swaps_; }

    // Path balancing. Find a shortest path S -> ... -> T in the district adjacency
    // graph from an over-populated to an under-populated district, then move one
    // boundary block across each hop, each sized as close as possible to what the
    // previous hop delivered. Accept if the sum of squared deviations drops,
    // otherwise undo the whole chain.
    bool chain_move() {
        std::vector<char> adj(static_cast<size_t>(k_) * k_, 0);
        for (int v : blist_)
            for (i64 e = xadj_[v]; e < xadj_[v + 1]; ++e) {
                int d = assign_[adjncy_[e]];
                if (d != assign_[v]) adj[static_cast<size_t>(assign_[v]) * k_ + d] = 1;
            }
        std::vector<int> by_pop(k_);
        for (int i = 0; i < k_; ++i) by_pop[i] = i;
        std::sort(by_pop.begin(), by_pop.end(), [&](int a, int b) { return dpop_[a] > dpop_[b]; });
        const int tries = std::min(k_, 4);
        std::vector<int> parent(k_);
        for (int si = 0; si < tries; ++si) {
            const int S = by_pop[si];
            if (dpop_[S] <= ideal_) break;
            std::fill(parent.begin(), parent.end(), -2);
            parent[S] = -1;
            std::vector<int> q{S};
            for (size_t qi = 0; qi < q.size(); ++qi)
                for (int d = 0; d < k_; ++d)
                    if (adj[static_cast<size_t>(q[qi]) * k_ + d] && parent[d] == -2) {
                        parent[d] = q[qi];
                        q.push_back(d);
                    }
            for (int ti = 0; ti < tries; ++ti) {
                const int T = by_pop[k_ - 1 - ti];
                if (dpop_[T] >= ideal_ || parent[T] == -2) continue;
                std::vector<int> path;
                for (int d = T; d != -1; d = parent[d]) path.push_back(d);
                std::reverse(path.begin(), path.end());
                const i64 want = std::max<i64>(1, (dpop_[S] - dpop_[T]) / 2);
                if (try_path(path, want)) return true;
            }
        }
        return false;
    }

    void move(int v, int b) {
        int a = assign_[v];
        assign_[v] = b;
        dpop_[a] -= pop_[v];
        dpop_[b] += pop_[v];
        update_boundary(v);
        for (i64 e = xadj_[v]; e < xadj_[v + 1]; ++e) update_boundary(static_cast<int>(adjncy_[e]));
    }

    // Would district assign[v] stay connected without v?
    // Runs one BFS per same-district neighbour of v, round-robin, merging searches
    // that meet (union-find). Returns false as soon as some merged group exhausts
    // (it is cut off), true once all groups merge. Cost ~ size of the smaller side.
    bool removable(int v) {
        const int d = assign_[v];
        ++stamp_;
        seen_[v] = stamp_;
        tgt_.clear();
        for (i64 e = xadj_[v]; e < xadj_[v + 1]; ++e) {
            int u = static_cast<int>(adjncy_[e]);
            if (assign_[u] != d || seen_[u] == stamp_) continue;
            seen_[u] = stamp_;
            owner_[u] = static_cast<int>(tgt_.size());
            tgt_.push_back(u);
        }
        const int nt = static_cast<int>(tgt_.size());
        if (nt == 0) return false;  // v is its whole district
        if (nt == 1) return true;
        if (static_cast<int>(qs_.size()) < nt) qs_.resize(nt);
        uf_.resize(nt);
        heads_.assign(nt, 0);
        for (int i = 0; i < nt; ++i) {
            qs_[i].clear();
            qs_[i].push_back(tgt_[i]);
            uf_[i] = i;
        }
        int groups = nt;
        while (true) {
            for (int i = 0; i < nt; ++i) {
                if (heads_[i] >= qs_[i].size()) continue;
                int u = qs_[i][heads_[i]++];
                for (i64 e = xadj_[u]; e < xadj_[u + 1]; ++e) {
                    int x = static_cast<int>(adjncy_[e]);
                    if (assign_[x] != d) continue;
                    if (seen_[x] != stamp_) {
                        seen_[x] = stamp_;
                        owner_[x] = i;
                        qs_[i].push_back(x);
                    } else if (x != v) {
                        int ra = find(i), rb = find(owner_[x]);
                        if (ra != rb) {
                            uf_[ra] = rb;
                            if (--groups == 1) return true;
                        }
                    }
                }
                if (heads_[i] >= qs_[i].size()) {
                    // Search i exhausted: if its whole group is exhausted, it's cut off.
                    int r = find(i);
                    bool alive = false;
                    for (int j = 0; j < nt && !alive; ++j)
                        if (find(j) == r && heads_[j] < qs_[j].size()) alive = true;
                    if (!alive) return false;
                }
            }
        }
    }

private:
    int chains_ = 0, swaps_ = 0;
    std::vector<std::vector<std::pair<int, double>>> buckets_;
    std::vector<std::pair<int, int>> undo_;
    struct Pick {
        double score;
        int v;
        bool operator<(const Pick& o) const { return score < o.score; }
    };
    std::vector<Pick> picks_;

    double sumsq() const {
        double s = 0;
        for (int d = 0; d < k_; ++d) s += (dpop_[d] - ideal_) * (dpop_[d] - ideal_);
        return s;
    }

    bool try_path(const std::vector<int>& path, i64 want) {
        const double before = sumsq();
        undo_.clear();
        i64 carry = want;
        for (size_t i = 0; i + 1 < path.size(); ++i) {
            const int a = path[i], b = path[i + 1];
            picks_.clear();
            for (int v : blist_) {
                if (assign_[v] != a || pop_[v] == 0) continue;
                neighbor_lengths(v);
                if (acc_seen_[b] != acc_stamp_) continue;
                const double dcut = acc_[a] - acc_[b];
                const double miss = static_cast<double>(std::llabs(pop_[v] - carry)) + (pop_[v] > carry ? 0.5 : 0);
                picks_.push_back({miss * 1e7 + dcut, v});
            }
            std::sort(picks_.begin(), picks_.end());
            int chosen = -1;
            for (size_t j = 0; j < picks_.size() && j < 512; ++j)
                if (removable(picks_[j].v)) { chosen = picks_[j].v; break; }
            if (chosen < 0) break;
            move(chosen, b);
            undo_.push_back({chosen, a});
            carry = pop_[chosen];
        }
        if (undo_.size() + 1 == path.size() && sumsq() < before - 1e-9) return true;
        for (auto it = undo_.rbegin(); it != undo_.rend(); ++it) move(it->first, it->second);
        undo_.clear();
        return false;
    }

    int n_, k_;
    i64 total_ = 0;
    double ideal_;
    std::vector<i64> xadj_, adjncy_, pop_, dpop_;
    std::vector<double> len_;
    std::vector<int> assign_;
    // boundary set: blist_ holds nodes, bpos_[v] its index or -1
    std::vector<int> blist_, bpos_;
    // scratch
    std::vector<double> acc_;
    std::vector<uint32_t> acc_seen_;
    uint32_t acc_stamp_ = 0;
    std::vector<int> touched_;
    std::vector<uint32_t> seen_;
    uint32_t stamp_ = 0;
    std::vector<int> tgt_, owner_, uf_;
    std::vector<std::vector<int>> qs_;
    std::vector<size_t> heads_;
    int find(int i) {
        while (uf_[i] != i) i = uf_[i] = uf_[uf_[i]];
        return i;
    }
    std::vector<Candidate> cands_;
    std::vector<uint32_t> dirty_;
    uint32_t pass_stamp_ = 0;
    i64 balance_target_ = 0;

public:
    bool batch_balance_ = false;

private:

    void update_boundary(int v) {
        bool b = false;
        for (i64 e = xadj_[v]; e < xadj_[v + 1]; ++e)
            if (assign_[adjncy_[e]] != assign_[v]) { b = true; break; }
        if (b && bpos_[v] < 0) {
            bpos_[v] = static_cast<int>(blist_.size());
            blist_.push_back(v);
        } else if (!b && bpos_[v] >= 0) {
            int last = blist_.back();
            blist_[bpos_[v]] = last;
            bpos_[last] = bpos_[v];
            blist_.pop_back();
            bpos_[v] = -1;
        }
    }

    // Fill acc_ with border length from v to each district; touched_ lists them.
    void neighbor_lengths(int v) {
        ++acc_stamp_;
        touched_.clear();
        for (i64 e = xadj_[v]; e < xadj_[v + 1]; ++e) {
            int d = assign_[adjncy_[e]];
            if (acc_seen_[d] != acc_stamp_) {
                acc_seen_[d] = acc_stamp_;
                acc_[d] = 0;
                touched_.push_back(d);
            }
            acc_[d] += len_[e];
        }
    }

    // Population extremes over districts excluding a and b, via top/bottom-3.
    struct Extremes {
        int hi[3], lo[3];
    };
    Extremes extremes() const {
        Extremes x;
        std::vector<int> idx(k_);
        for (int i = 0; i < k_; ++i) idx[i] = i;
        std::sort(idx.begin(), idx.end(), [&](int a, int b) { return dpop_[a] > dpop_[b]; });
        for (int i = 0; i < 3; ++i) {
            x.hi[i] = idx[std::min(i, k_ - 1)];
            x.lo[i] = idx[std::max(k_ - 1 - i, 0)];
        }
        return x;
    }
    static i64 pick(const int* arr, int a, int b, const std::vector<i64>& dp, i64 fallback) {
        for (int i = 0; i < 3; ++i)
            if (arr[i] != a && arr[i] != b) return dp[arr[i]];
        return fallback;
    }

    int step(bool polish, i64 cap) {
        cands_.clear();
        Extremes ex{};
        if (polish) ex = extremes();
        for (int v : blist_) {
            const i64 p = pop_[v];
            if (!polish && p == 0) continue;
            const int a = assign_[v];
            neighbor_lengths(v);
            const double la = acc_seen_[a] == acc_stamp_ ? acc_[a] : 0.0;
            for (int b : touched_) {
                if (b == a) continue;
                const double dcut = la - acc_[b];
                double score;
                if (polish) {
                    if (dcut >= -1e-6) continue;
                    i64 na = dpop_[a] - p, nb = dpop_[b] + p;
                    i64 hi = std::max({na, nb, pick(ex.hi, a, b, dpop_, std::numeric_limits<i64>::min())});
                    i64 lo = std::min({na, nb, pick(ex.lo, a, b, dpop_, std::numeric_limits<i64>::max())});
                    if (hi - lo > cap) continue;
                    score = dcut;
                } else {
                    const double da = dpop_[a] - ideal_, db = dpop_[b] - ideal_;
                    const double gain = 2.0 * p * (da - db - p);
                    if (gain <= 0) continue;
                    score = dcut < 0 ? dcut - 1e12 : (dcut + 1e-6) / gain;
                }
                cands_.push_back({score, v, b});
            }
        }
        if (cands_.empty()) return 0;
        // Apply candidates best-first, many per scan. A candidate is skipped if it or a
        // neighbour already moved this pass (its border lengths changed); otherwise its
        // dcut is still exact and we re-check gain / spread against current populations.
        ++pass_stamp_;
        std::sort(cands_.begin(), cands_.end());
        int moved = 0;
        for (const Candidate& c : cands_) {
            if (!polish && spread() <= balance_target_) break;
            if (dirty_[c.v] == pass_stamp_) continue;
            const int a = assign_[c.v];
            const i64 p = pop_[c.v];
            if (polish) {
                i64 hi = std::numeric_limits<i64>::min(), lo = std::numeric_limits<i64>::max();
                for (int d = 0; d < k_; ++d) {
                    i64 x = dpop_[d] - (d == a ? p : 0) + (d == c.b ? p : 0);
                    hi = std::max(hi, x);
                    lo = std::min(lo, x);
                }
                if (hi - lo > cap) continue;
            } else {
                const double da = dpop_[a] - ideal_, db = dpop_[c.b] - ideal_;
                if (2.0 * p * (da - db - p) <= 0) continue;
            }
            if (!removable(c.v)) continue;
            move(c.v, c.b);
            ++moved;
            if (!polish && !batch_balance_) break;
            dirty_[c.v] = pass_stamp_;
            for (i64 e = xadj_[c.v]; e < xadj_[c.v + 1]; ++e) dirty_[adjncy_[e]] = pass_stamp_;
        }
        return moved;
    }
};

py::array_t<i64> refine(py::array_t<i64, py::array::c_style | py::array::forcecast> xadj,
                        py::array_t<i64, py::array::c_style | py::array::forcecast> adjncy,
                        py::array_t<double, py::array::c_style | py::array::forcecast> length,
                        py::array_t<i64, py::array::c_style | py::array::forcecast> pop,
                        py::array_t<i64, py::array::c_style | py::array::forcecast> assign, int k,
                        i64 target, int rounds, bool verbose, bool batch_balance) {
    Refiner r(xadj, adjncy, length, pop, assign, k);
    r.batch_balance_ = batch_balance;
    if (verbose) py::print("  start: spread =", r.spread(), "cut_km =", r.cut_length() / 1000);
    const int max_iter = 10'000'000;
    i64 cap = std::max(target, r.spread());
    r.polish(cap, max_iter, verbose);
    // Tighten the population cap gradually so polish can smooth each stage.
    while (cap > target) {
        cap = std::max(target, cap / 2);
        r.balance(cap, max_iter, false);
        r.polish(std::max(cap, r.spread()), max_iter, false);
        if (verbose) py::print("  cap", cap, "spread", r.spread(), "cut_km", r.cut_length() / 1000);
    }
    for (int i = 0; i < rounds; ++i) {
        double before = r.cut_length();
        r.balance(target, max_iter, verbose);
        r.polish(std::max(target, r.spread()), max_iter, verbose);
        if (r.spread() <= target && std::abs(before - r.cut_length()) < 1) break;
    }
    return r.assignment();
}

PYBIND11_MODULE(_refine, m) {
    m.doc() = "C++ local-search refinement for districting";
    py::class_<Refiner>(m, "Refiner")
        .def(py::init<py::array_t<i64, py::array::c_style | py::array::forcecast>,
                      py::array_t<i64, py::array::c_style | py::array::forcecast>,
                      py::array_t<double, py::array::c_style | py::array::forcecast>,
                      py::array_t<i64, py::array::c_style | py::array::forcecast>,
                      py::array_t<i64, py::array::c_style | py::array::forcecast>, int>(),
             py::arg("xadj"), py::arg("adjncy"), py::arg("length"), py::arg("pop"), py::arg("assign"),
             py::arg("k"))
        .def("spread", &Refiner::spread)
        .def("cut_length", &Refiner::cut_length)
        .def("assignment", &Refiner::assignment)
        .def("district_pop", &Refiner::district_pop)
        .def("balance", &Refiner::balance, py::arg("target") = 1, py::arg("max_iter") = 10'000'000,
             py::arg("verbose") = false)
        .def("polish", &Refiner::polish, py::arg("cap"), py::arg("max_iter") = 10'000'000,
             py::arg("verbose") = false)
        .def("removable", &Refiner::removable)
        .def("chains", &Refiner::chains)
        .def("swaps", &Refiner::swaps)
        .def("move", &Refiner::move);
    m.def("refine", &refine, py::arg("xadj"), py::arg("adjncy"), py::arg("length"), py::arg("pop"),
          py::arg("assign"), py::arg("k"), py::arg("target") = 1, py::arg("rounds") = 3,
          py::arg("verbose") = true, py::arg("batch_balance") = false);
}
