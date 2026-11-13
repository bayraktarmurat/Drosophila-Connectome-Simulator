"""Path finder: exactness vs brute force, normalization, hop and sign limits."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

from connectome_app.config import CircuitConfig, load_config
from connectome_app.data import load_circuit
from connectome_app.paths import PathGraph, build_neuron_graph, build_type_graph, k_shortest_paths


def random_graph(n: int, density: float, seed: int, with_signs: bool) -> PathGraph:
    rng = np.random.default_rng(seed)
    synapses = sp.random(n, n, density=density, random_state=rng, format="csr")
    synapses.data = np.round(synapses.data * 30) + 1
    synapses.setdiag(0)
    synapses.eliminate_zeros()
    totals = np.asarray(synapses.sum(axis=0)).ravel() * 2 + 1
    shares = synapses.copy()
    shares.data = shares.data / totals[shares.indices]
    if with_signs:
        signs = rng.choice([-1, 1], size=n)
    else:
        signs = np.ones(n, dtype=np.int64)
    return PathGraph("neuron", [str(i) for i in range(n)], synapses, shares, signs, [""] * n, [None] * n)


def brute_force(graph: PathGraph, sources, targets, max_hops: int, sign_filter: str) -> list[float]:
    """Costs of all simple paths (source -> first target reached), sorted."""
    targets = set(int(t) for t in targets)
    costs: list[float] = []
    dense = graph.shares.toarray()

    def walk(node: int, path: list[int], cost: float, parity: int) -> None:
        if node in targets and len(path) > 1:
            keep = sign_filter == "any"
            if sign_filter == "excitatory":
                keep = parity > 0
            if sign_filter == "inhibitory":
                keep = parity < 0
            if keep:
                costs.append(cost)
            return
        if len(path) - 1 >= max_hops:
            return
        if sign_filter != "any" and graph.signs[node] == 0:
            return
        for nxt in np.flatnonzero(dense[node]):
            if nxt in path:
                continue
            walk(int(nxt), path + [int(nxt)], cost - np.log(dense[node, nxt]), parity * int(graph.signs[node]))

    for source in sources:
        walk(int(source), [int(source)], 0.0, 1)
    return sorted(costs)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
@pytest.mark.parametrize("sign_filter", ["any", "excitatory", "inhibitory"])
def test_matches_brute_force(seed: int, sign_filter: str) -> None:
    graph = random_graph(25, 0.15, seed, with_signs=True)
    sources = np.array([0, 1, 2])
    targets = np.array([20, 21, 22])
    expected = brute_force(graph, sources, targets, max_hops=4, sign_filter=sign_filter)
    result = k_shortest_paths(graph, sources, targets, k=15, max_hops=4, sign_filter=sign_filter)
    got = [p.cost for p in result.paths]
    assert not result.truncated
    np.testing.assert_allclose(got, expected[:15], rtol=1e-9, atol=1e-9)
    for path in result.paths:
        assert len(set(path.nodes)) == len(path.nodes)
        assert path.hops <= 4
        assert path.nodes[0] in sources
        assert path.nodes[-1] in targets


def test_path_order_and_scores(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    graph = build_neuron_graph(circuit)
    sources = circuit.indices_of_types(["LCa"])
    targets = circuit.indices_of_types(["MN"])
    result = k_shortest_paths(graph, sources, targets, k=5, max_hops=3)
    assert len(result.paths) == 2
    best, second = result.paths
    # total_post = 100 for every neuron: shares are synapses / 100, NOT synapses / in-circuit input
    assert best.score == pytest.approx(0.07 * 0.04)
    assert second.score == pytest.approx(0.05 * 0.03)
    assert best.synapses == [7, 4]
    assert [circuit.body_ids[n] for n in best.nodes] == [2, 11, 21]


def test_max_hops_respected(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    graph = build_neuron_graph(circuit)
    sources = circuit.indices_of_types(["LCa"])
    targets = circuit.indices_of_types(["MN"])
    assert k_shortest_paths(graph, sources, targets, k=5, max_hops=1).paths == []


def test_sign_filter(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    graph = build_neuron_graph(circuit)
    sources = circuit.indices_of_types(["INH"])
    targets = circuit.indices_of_types(["MN"])
    any_sign = k_shortest_paths(graph, sources, targets, k=5, max_hops=3)
    assert len(any_sign.paths) == 1
    assert any_sign.paths[0].sign == -1
    assert k_shortest_paths(graph, sources, targets, k=5, max_hops=3, sign_filter="excitatory").paths == []
    assert len(k_shortest_paths(graph, sources, targets, k=5, max_hops=3, sign_filter="inhibitory").paths) == 1


def test_type_graph(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    graph = build_type_graph(circuit)
    position = {name: i for i, name in enumerate(graph.labels)}
    share = graph.shares[position["LCa"], position["GF"]]
    assert share == pytest.approx((5 + 7) / 200)
    result = k_shortest_paths(graph, np.array([position["LCa"]]), np.array([position["MN"]]), k=3, max_hops=3)
    assert [graph.labels[n] for n in result.paths[0].nodes] == ["LCa", "GF", "MN"]


@pytest.mark.cached
def test_giant_fiber_paths_lc4_to_ttmn() -> None:
    config = load_config("giant_fiber")
    if not (config.data_dir() / "neurons.parquet").exists():
        pytest.skip("giant_fiber not fetched yet")
    circuit = load_circuit(config)
    graph = build_type_graph(circuit)
    position = {name: i for i, name in enumerate(graph.labels)}
    result = k_shortest_paths(
        graph, np.array([position["LC4"]]), np.array([position["TTMn"]]), k=10, max_hops=4
    )
    assert len(result.paths) == 10
    costs = [p.cost for p in result.paths]
    assert costs == sorted(costs)
    labels = [[graph.labels[n] for n in p.nodes] for p in result.paths]
    print("\n".join(" -> ".join(path) + f"  score={p.score:.2e}" for path, p in zip(labels, result.paths)))
    assert any("DNp01" in path for path in labels)
