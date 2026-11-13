"""Effect-size statistics, cached baseline, lesion runs and the lesion screen."""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from connectome_app.config import SimulationConfig
from connectome_app.lesion import (
    BaselineCache,
    RunSettings,
    ScreenCandidate,
    group_metric,
    lesion_screen,
    run_lesion,
)
from connectome_app.lif import LIFNetwork, LIFParams
from connectome_app.stats import cohens_d, compare_paired, percent_change
from connectome_app.stimulus import Stimulus

PARAMS = LIFParams.from_config(SimulationConfig())


def test_cohens_d_known_value() -> None:
    baseline = np.array([1.0, 2.0, 3.0, 4.0])
    lesion = baseline + 2.0
    sd = np.std(baseline, ddof=1)
    assert cohens_d(baseline, lesion) == pytest.approx(2.0 / sd)


def test_cohens_d_zero_variance() -> None:
    same = np.array([3.0, 3.0, 3.0])
    assert cohens_d(same, same) == 0.0
    assert cohens_d(same, same + 1) == float("inf")
    assert cohens_d(same, same - 1) == float("-inf")


def test_percent_change() -> None:
    assert percent_change(10.0, 5.0) == -50.0
    assert percent_change(0.0, 0.0) == 0.0
    assert np.isnan(percent_change(0.0, 1.0))


def test_compare_paired_ci_contains_effect() -> None:
    rng = np.random.default_rng(0)
    baseline = rng.normal(10, 1, 40)
    lesion = baseline - 3 + rng.normal(0, 0.5, 40)
    result = compare_paired(baseline, lesion)
    low, high = result.mean_difference_ci
    assert low < -3 + 0.5 and high > -3 - 0.5
    assert low < result.mean_difference < high
    d_low, d_high = result.cohens_d_ci
    assert d_low < result.cohens_d < d_high
    assert result.cohens_d < -1.5


def test_identical_conditions_have_zero_effect() -> None:
    values = np.array([1.0, 4.0, 2.0, 8.0])
    result = compare_paired(values, values.copy())
    assert result.mean_difference == 0.0
    assert result.cohens_d == 0.0
    assert result.p_value_wilcoxon == 1.0


def chain_network() -> LIFNetwork:
    """input(0) -> relay(1) -> output(2), plus a weak side branch input(0) -> side(3)."""
    weights = np.zeros((4, 4))
    weights[1, 0] = 200.0
    weights[2, 1] = 200.0
    weights[3, 0] = 1.0
    return LIFNetwork(sp.csr_matrix(weights), PARAMS)


def chain_settings() -> RunSettings:
    stimulus = Stimulus(targets=np.array([0]), profile="constant", rate_hz=80.0)
    return RunSettings(duration_ms=400.0, n_trials=6, base_seed=11, stimulus=stimulus)


def test_cached_baseline_is_bit_identical_to_joint_run() -> None:
    network = chain_network()
    settings = chain_settings()
    cache = BaselineCache()
    baseline = cache.get(("chain", False), network, settings)
    again = cache.get(("chain", False), network, settings)
    assert again is baseline
    assert len(cache) == 1
    seeds = settings.seeds()
    alive = np.ones((4, 2 * len(seeds)), dtype=bool)
    alive[1, len(seeds) :] = False
    joint = network.run(
        settings.duration_ms, np.concatenate([seeds, seeds]), stimulus=settings.stimulus, alive=alive
    )
    np.testing.assert_array_equal(joint.spike_counts()[:, : len(seeds)], baseline.spike_counts())


def test_relay_lesion_silences_output() -> None:
    network = chain_network()
    settings = chain_settings()
    baseline = BaselineCache().get(("chain", False), network, settings)
    groups = {"out": np.array([2])}
    outcome = run_lesion(network, baseline, settings, np.array([1]), groups)
    by_metric = {row["metric"]: row for row in outcome.metrics}
    count = by_metric["spike_count"]
    assert count["baseline_mean"] > 5
    assert count["lesion_mean"] == 0
    assert count["percent_change"] == -100.0
    assert count["cohens_d"] < -2
    latency = by_metric["first_spike_ms"]
    assert latency["responded_baseline"] == 1.0
    assert latency["responded_lesion"] == 0.0
    assert latency["comparison_valid"] is False
    assert outcome.psth_lesion["out"].sum() == 0


def test_screen_ranks_relay_first_and_skips_measured_group() -> None:
    network = chain_network()
    settings = chain_settings()
    baseline = BaselineCache().get(("chain", False), network, settings)
    candidates = [
        ScreenCandidate("side", np.array([3])),
        ScreenCandidate("relay", np.array([1])),
        ScreenCandidate("output", np.array([2])),
        ScreenCandidate("input", np.array([0])),
    ]
    calls: list[tuple[int, int]] = []
    outcome = lesion_screen(
        network,
        baseline,
        settings,
        candidates,
        measure=np.array([2]),
        max_columns=12,
        progress=lambda done, total: calls.append((done, total)),
    )
    labels = outcome.table["label"].tolist()
    assert outcome.skipped == ["output"]
    assert set(labels[:2]) == {"relay", "input"}
    assert labels[-1] == "side"
    side = outcome.table.set_index("label").loc["side"]
    assert side["percent_change"] == 0.0
    assert calls[0] == (0, 3)
    assert calls[-1] == (3, 3)


def test_group_metric_rate_and_count() -> None:
    network = chain_network()
    settings = chain_settings()
    result = network.run(settings.duration_ms, settings.seeds(), stimulus=settings.stimulus)
    columns = np.arange(settings.n_trials)
    counts = group_metric(result, np.array([0]), "spike_count", columns)
    rates = group_metric(result, np.array([0]), "rate_hz", columns)
    np.testing.assert_allclose(rates, counts / 0.4)
