"""LIF engine tests: analytic rate, silence, reproducibility, inhibition, delay, performance."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

from connectome_app.analysis import group_first_spike, group_rates, psth, type_rate_table
from connectome_app.config import CircuitConfig, SimulationConfig, load_config
from connectome_app.data import load_circuit
from connectome_app.lif import LIFNetwork, LIFParams, trial_seeds
from connectome_app.stimulus import Stimulus, poisson_events, rate_profile

PARAMS = LIFParams.from_config(SimulationConfig())


def analytic_rate_hz(drive_mv: float, params: LIFParams) -> float:
    """Firing rate of a LIF neuron with constant drive, reset = rest."""
    gap = params.v_threshold_mv - params.v_reset_mv
    if drive_mv <= gap:
        return 0.0
    time_to_threshold = params.tau_m_ms * np.log(drive_mv / (drive_mv - gap))
    period_ms = params.refractory_steps * params.dt_ms + time_to_threshold
    return 1000.0 / period_ms


def single_neuron() -> LIFNetwork:
    return LIFNetwork(sp.csr_matrix((1, 1)), PARAMS)


@pytest.mark.parametrize("drive_mv", [8.0, 10.0, 20.0, 50.0])
def test_a_constant_drive_matches_analytic_rate(drive_mv: float) -> None:
    result = single_neuron().run(5000.0, [1], bias_mv=drive_mv)
    times = result.spike_times_ms
    assert len(times) > 10
    measured = 1000.0 / np.mean(np.diff(times))
    expected = analytic_rate_hz(drive_mv, PARAMS)
    # Discrete threshold detection adds up to one dt per interval.
    assert measured == pytest.approx(expected, rel=0.02)


def test_a_subthreshold_drive_never_spikes() -> None:
    result = single_neuron().run(2000.0, [1], bias_mv=6.9)
    assert len(result.spike_steps) == 0


def random_network(n: int, density: float, seed: int) -> sp.csr_matrix:
    rng = np.random.default_rng(seed)
    matrix = sp.random(n, n, density=density, random_state=rng, format="csr")
    matrix.data = np.round(matrix.data * 20) + 1
    signs = rng.choice([-1.0, 1.0], size=n, p=[0.3, 0.7])
    return sp.csr_matrix(matrix @ sp.diags(signs))


def test_b_no_input_no_spikes() -> None:
    network = LIFNetwork(random_network(300, 0.05, 0), PARAMS)
    result = network.run(500.0, [1, 2, 3])
    assert len(result.spike_steps) == 0


def test_c_same_seed_identical_output() -> None:
    network = LIFNetwork(random_network(300, 0.05, 0), PARAMS)
    stimulus = Stimulus(targets=np.arange(30), profile="ramp", rate_hz=200.0, end_ms=300.0)
    first = network.run(300.0, [7, 8], stimulus=stimulus)
    second = network.run(300.0, [7, 8], stimulus=stimulus)
    assert len(first.spike_steps) > 0
    np.testing.assert_array_equal(first.spike_steps, second.spike_steps)
    np.testing.assert_array_equal(first.spike_neurons, second.spike_neurons)
    np.testing.assert_array_equal(first.spike_columns, second.spike_columns)
    other = network.run(300.0, [9, 10], stimulus=stimulus)
    assert not np.array_equal(first.spike_counts(), other.spike_counts())


def test_c_columns_with_same_seed_are_identical() -> None:
    network = LIFNetwork(random_network(200, 0.05, 1), PARAMS)
    stimulus = Stimulus(targets=np.arange(20), profile="constant", rate_hz=150.0)
    result = network.run(200.0, [5, 5], stimulus=stimulus)
    counts = result.spike_counts()
    np.testing.assert_array_equal(counts[:, 0], counts[:, 1])


def test_d_inhibitory_connection_suppresses_target() -> None:
    # neuron 0 = target (driven), neuron 1 = inhibitor (driven hard), W[0, 1] = -50 synapses
    weights = sp.csr_matrix(np.array([[0.0, -50.0], [0.0, 0.0]]))
    network = LIFNetwork(weights, PARAMS)
    bias = np.array([10.0, 30.0])
    alive = np.array([[True, True], [True, False]])  # column 1: inhibitor ablated
    result = network.run(2000.0, [1, 1], bias_mv=bias, alive=alive)
    counts = result.spike_counts()
    assert counts[1, 0] > 0
    assert counts[1, 1] == 0
    assert counts[0, 1] > 50
    assert counts[0, 0] < 0.1 * counts[0, 1]


def test_excitatory_connection_drives_silent_target_after_delay() -> None:
    weights = sp.csr_matrix(np.array([[0.0, 0.0], [200.0, 0.0]]))
    network = LIFNetwork(weights, PARAMS)
    result = network.run(100.0, [1], bias_mv=np.array([10.0, 0.0]))
    first = result.first_spike_ms()
    assert not np.isnan(first[1, 0])
    assert first[1, 0] >= first[0, 0] + PARAMS.delay_steps * PARAMS.dt_ms


def test_ablated_neuron_never_spikes_even_when_stimulated() -> None:
    network = LIFNetwork(sp.csr_matrix((3, 3)), PARAMS)
    stimulus = Stimulus(targets=np.array([0, 1, 2]), profile="constant", rate_hz=300.0)
    alive = np.array([True, False, True])
    result = network.run(200.0, [1], stimulus=stimulus, alive=alive)
    counts = result.spike_counts()
    assert counts[1, 0] == 0
    assert counts[0, 0] > 0


def test_refractory_limits_rate() -> None:
    result = single_neuron().run(1000.0, [1], bias_mv=1e6)
    max_rate = 1000.0 / ((PARAMS.refractory_steps + 1) * PARAMS.dt_ms)
    assert len(result.spike_steps) <= max_rate + 1


def test_rate_profiles() -> None:
    n_steps = 1000
    ramp = rate_profile(Stimulus(np.array([0]), "ramp", 100.0, 0.0, 20.0, 80.0), n_steps, 0.1)
    assert ramp[0] == 0.0
    assert ramp[int(50 / 0.1)] == pytest.approx(50.0, rel=0.01)
    assert ramp[-1] == 0.0
    step = rate_profile(Stimulus(np.array([0]), "step", 80.0, 5.0, 10.0, 20.0), n_steps, 0.1)
    assert step[50] == 5.0
    assert step[150] == 80.0
    assert step[300] == 5.0


def test_poisson_rate_is_correct() -> None:
    rates = np.full(100000, 50.0)
    events = poisson_events(rates, 20, 0.1, seed=3)
    measured = events.sum() / (20 * 100000 * 0.1 / 1000.0)
    assert measured == pytest.approx(50.0, rel=0.03)


def test_trial_seeds_are_deterministic_and_distinct() -> None:
    first = trial_seeds(12345, 10)
    np.testing.assert_array_equal(first, trial_seeds(12345, 10))
    assert len(set(first.tolist())) == 10


def test_from_circuit_with_extra_edges(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    without = LIFNetwork.from_circuit(circuit)
    with_extra = LIFNetwork.from_circuit(circuit, use_extra_edges=True)
    assert without.electrical is None
    assert with_extra.electrical is not None
    assert with_extra.electrical.nnz == 2


def test_analysis_helpers(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    network = LIFNetwork.from_circuit(circuit)
    stimulus = Stimulus(targets=circuit.indices_of_types(["LCa"]), profile="constant", rate_hz=200.0)
    result = network.run(300.0, [1, 2], stimulus=stimulus)
    groups = {"LCa": circuit.indices_of_types(["LCa"]), "MN": circuit.indices_of_types(["MN"])}
    rates = group_rates(result, groups)
    assert rates["LCa"].shape == (2,)
    assert np.all(rates["LCa"] > 100)
    latency = group_first_spike(result, groups)
    assert np.all(latency["LCa"] < 50)
    bins, curves = psth(result, groups, bin_ms=10.0)
    assert len(bins) == 30
    assert curves["LCa"].mean() == pytest.approx(rates["LCa"].mean(), rel=0.01)
    table = type_rate_table(result, circuit.neurons)
    assert set(table["type"]) == set(circuit.neurons["type"])


@pytest.mark.cached
def test_e_performance_giant_fiber() -> None:
    config = load_config("giant_fiber")
    if not (config.data_dir() / "neurons.parquet").exists():
        pytest.skip("giant_fiber not fetched yet")
    circuit = load_circuit(config)
    network = LIFNetwork.from_circuit(circuit)
    inputs = circuit.indices_of_role("input")
    stimulus = Stimulus(targets=inputs, profile="ramp", rate_hz=150.0, start_ms=100.0, end_ms=900.0)
    seeds = trial_seeds(config.simulation.base_seed, 10)
    started = time.perf_counter()
    result = network.run(1000.0, seeds, stimulus=stimulus)
    elapsed = time.perf_counter() - started
    print(
        f"\n[benchmark] N={circuit.n_neurons} nnz={circuit.weights.nnz} 1 s x 10 trials: "
        f"{elapsed:.2f}s, spikes={len(result.spike_steps)}"
    )
    assert elapsed < 120.0


@pytest.mark.parametrize(("strength", "expected_spikes"), [(120.0, 0), (300.0, 1), (360.0, 2)])
def test_electrical_calibration_isolated_pair(strength: float, expected_spikes: int) -> None:
    """Phase 5 calibration claim: 300 synapse-equivalents = strongest 1:1 GF -> TTMn coupling."""
    electrical = sp.csr_matrix(([strength], ([1], [0])), shape=(2, 2))
    network = LIFNetwork(sp.csr_matrix((2, 2)), PARAMS, electrical_weights=electrical)
    stimulus = Stimulus(targets=np.array([0]), profile="step", rate_hz=10000.0, start_ms=5.0, end_ms=5.1)
    result = network.run(60.0, [1], stimulus=stimulus)
    counts = result.spike_counts()
    assert counts[0, 0] == 1
    assert counts[1, 0] == expected_spikes


def test_giant_fiber_config_uses_calibrated_strength() -> None:
    config = load_config("giant_fiber")
    strengths = {edge.synapse_equivalent for edge in config.extra_edges.edges}
    assert strengths == {300.0}
