"""Strongest signal paths between a source set and a target set.

Edge j -> i gets the weight share  s_ij = W[i, j] / D_i, where D_i is the postsynaptic
neuron's TOTAL input in the full dataset (not just inside the sub-circuit). The cost is
c_ij = -log(s_ij). A path's cost is then -log(product of shares), so the cheapest path
is the one that carries the largest product of "fraction of the target's input".
Costs are additive and non-negative, which allows exact shortest-path search.

Search: A* over the tree of simple paths. The heuristic h(v) is the exact cheapest cost
from v to any target (reverse Dijkstra, ignoring hop limits and simplicity); it is a lower
bound, so complete paths are popped in non-decreasing cost order and the first k are the
k cheapest simple paths within `max_hops`.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra

from connectome_app.data import Circuit

SignFilter = Literal["any", "excitatory", "inhibitory"]
Level = Literal["neuron", "type"]
Normalization = Literal["post", "input_weight"]

COST_EPSILON = 1e-9


@dataclass
class PathGraph:
    """Directed graph for path search. Rows of `synapses`/`shares` are PRE, columns POST."""

    level: Level
    labels: list[str]
    synapses: sp.csr_matrix
    shares: sp.csr_matrix
    signs: np.ndarray
    node_types: list[str]
    node_body_ids: list[int | None]


@dataclass
class FoundPath:
    nodes: list[int]
    synapses: list[int]
    shares: list[float]
    cost: float
    sign: int

    @property
    def score(self) -> float:
        """Product of the edge shares (between 0 and 1)."""
        return float(np.exp(-self.cost))

    @property
    def hops(self) -> int:
        return len(self.nodes) - 1


@dataclass
class PathSearchResult:
    paths: list[FoundPath]
    truncated: bool
    expansions: int


def _denominators(circuit: Circuit, normalization: Normalization) -> np.ndarray:
    """Full-dataset total input per neuron; falls back to in-circuit input if missing."""
    if normalization == "post":
        column = "total_post"
    else:
        column = "input_weight_total"
    totals = circuit.neurons[column].to_numpy(dtype=np.float64)
    in_circuit = np.asarray(circuit.weights.sum(axis=1)).ravel()
    bad = ~np.isfinite(totals) | (totals <= 0)
    totals = totals.copy()
    totals[bad] = in_circuit[bad]
    totals = np.maximum(totals, in_circuit)
    totals[totals <= 0] = 1.0
    return totals


def build_neuron_graph(circuit: Circuit, normalization: Normalization = "post") -> PathGraph:
    """Neuron-level graph."""
    denominators = _denominators(circuit, normalization)
    post_by_pre = sp.csr_matrix(circuit.weights.T)
    shares = post_by_pre.copy().astype(np.float64)
    # Column index of `post_by_pre` is the postsynaptic neuron.
    shares.data = shares.data / denominators[shares.indices]
    neurons = circuit.neurons
    labels: list[str] = []
    for cell_type, body_id in zip(neurons["type"], neurons["body_id"], strict=True):
        labels.append(f"{cell_type} ({int(body_id)})")
    body_ids: list[int | None] = []
    for body_id in neurons["body_id"]:
        body_ids.append(int(body_id))
    return PathGraph(
        level="neuron",
        labels=labels,
        synapses=post_by_pre,
        shares=shares,
        signs=circuit.signs.astype(np.int64),
        node_types=neurons["type"].tolist(),
        node_body_ids=body_ids,
    )


def _type_membership(circuit: Circuit) -> tuple[list[str], sp.csr_matrix]:
    types = sorted(circuit.neurons["type"].unique().tolist())
    type_index = {name: i for i, name in enumerate(types)}
    rows = np.arange(circuit.n_neurons)
    cols = np.array([type_index[t] for t in circuit.neurons["type"]], dtype=np.int64)
    data = np.ones(circuit.n_neurons)
    membership = sp.csr_matrix((data, (rows, cols)), shape=(circuit.n_neurons, len(types)))
    return types, membership


def build_type_graph(circuit: Circuit, normalization: Normalization = "post") -> PathGraph:
    """Cell-type-level graph: synapses summed over neurons, self-loops removed."""
    types, membership = _type_membership(circuit)
    denominators = _denominators(circuit, normalization)
    type_denominators = membership.T @ denominators
    type_weights = sp.csr_matrix(membership.T @ circuit.weights @ membership)  # post x pre
    type_weights.setdiag(0)
    type_weights.eliminate_zeros()
    post_by_pre = sp.csr_matrix(type_weights.T)
    shares = post_by_pre.copy()
    shares.data = shares.data / type_denominators[shares.indices]

    signs = np.zeros(len(types), dtype=np.int64)
    sign_frame = pd.DataFrame({"type": circuit.neurons["type"], "sign": circuit.signs})
    majority = sign_frame.groupby("type")["sign"].agg(lambda s: s.value_counts().idxmax())
    for i, name in enumerate(types):
        signs[i] = int(majority[name])
    body_ids: list[int | None] = [None] * len(types)
    return PathGraph(
        level="type",
        labels=list(types),
        synapses=post_by_pre,
        shares=shares,
        signs=signs,
        node_types=list(types),
        node_body_ids=body_ids,
    )


def _cost_matrix(graph: PathGraph, sign_filter: SignFilter, min_synapses: int) -> sp.csr_matrix:
    """-log(share) per edge, after removing edges that the search must not use."""
    costs = graph.shares.copy().tocsr()
    costs.data = -np.log(np.clip(costs.data, 1e-300, 1.0)) + COST_EPSILON
    keep = graph.synapses.data >= min_synapses
    if sign_filter != "any":
        row_of_entry = np.repeat(np.arange(costs.shape[0]), np.diff(costs.indptr))
        keep = keep & (graph.signs[row_of_entry] != 0)
    costs.data = np.where(keep, costs.data, 0.0)
    costs.eliminate_zeros()
    return costs


def k_shortest_paths(
    graph: PathGraph,
    sources: np.ndarray,
    targets: np.ndarray,
    k: int = 10,
    max_hops: int = 4,
    sign_filter: SignFilter = "any",
    min_synapses: int = 1,
    max_expansions: int = 500_000,
) -> PathSearchResult:
    """The k cheapest simple paths from any source to any target with at most max_hops edges."""
    costs = _cost_matrix(graph, sign_filter, min_synapses)
    target_set = set(int(t) for t in targets)
    if not target_set or len(sources) == 0:
        return PathSearchResult([], False, 0)
    target_list = sorted(target_set)
    reverse = sp.csr_matrix(costs.T)
    heuristic = dijkstra(reverse, directed=True, indices=target_list, min_only=True)
    min_hops = dijkstra(reverse, directed=True, indices=target_list, min_only=True, unweighted=True)

    counter = itertools.count()
    heap: list[tuple[float, int, float, int, tuple[int, ...], int]] = []
    for source in sorted(set(int(s) for s in sources)):
        if np.isfinite(heuristic[source]) and min_hops[source] <= max_hops:
            heapq.heappush(heap, (float(heuristic[source]), next(counter), 0.0, source, (source,), 1))

    found: list[FoundPath] = []
    expansions = 0
    truncated = False
    indptr = costs.indptr
    indices = costs.indices
    data = costs.data
    while heap and len(found) < k:
        _, _, cost_so_far, node, path, parity = heapq.heappop(heap)
        if node in target_set and len(path) > 1:
            if _parity_ok(parity, sign_filter):
                found.append(_make_path(graph, path, cost_so_far, parity))
            continue
        hops = len(path) - 1
        if hops >= max_hops:
            continue
        expansions += 1
        if expansions > max_expansions:
            truncated = True
            break
        next_parity = parity * int(graph.signs[node])
        for pos in range(indptr[node], indptr[node + 1]):
            neighbour = int(indices[pos])
            if neighbour in path:
                continue
            if not np.isfinite(heuristic[neighbour]):
                continue
            if hops + 1 + min_hops[neighbour] > max_hops:
                continue
            new_cost = cost_so_far + float(data[pos])
            priority = new_cost + float(heuristic[neighbour])
            heapq.heappush(
                heap, (priority, next(counter), new_cost, neighbour, path + (neighbour,), next_parity)
            )
    return PathSearchResult(found, truncated, expansions)


def _parity_ok(parity: int, sign_filter: SignFilter) -> bool:
    if sign_filter == "any":
        return True
    if sign_filter == "excitatory":
        return parity > 0
    return parity < 0


def _make_path(graph: PathGraph, nodes: tuple[int, ...], cost: float, parity: int) -> FoundPath:
    synapses: list[int] = []
    shares: list[float] = []
    for pre, post in zip(nodes[:-1], nodes[1:], strict=True):
        synapses.append(int(graph.synapses[pre, post]))
        shares.append(float(graph.shares[pre, post]))
    true_cost = float(-np.sum(np.log(np.clip(shares, 1e-300, 1.0))))
    return FoundPath(nodes=list(nodes), synapses=synapses, shares=shares, cost=true_cost, sign=parity)
