"""Virtual lesions: ablate neurons, compare against a cached baseline with identical seeds.

An ablated neuron never spikes. That is equivalent to zeroing its column in W (no output)
and makes its row (input) irrelevant, without copying the matrix.

Columns of the batched simulation never interact, so a baseline run on its own is
bit-identical to the same columns run alongside lesion columns. That is why the baseline
can be computed once per (network, settings) and reused for every lesion condition.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from connectome_app.analysis import group_first_spike, psth
from connectome_app.lif import LIFNetwork, SimulationResult, trial_seeds
from connectome_app.stats import compare_paired
from connectome_app.stimulus import Stimulus

Metric = Literal["spike_count", "rate_hz", "first_spike_ms"]
METRICS: tuple[Metric, ...] = ("spike_count", "rate_hz", "first_spike_ms")
RankBy = Literal["percent_change", "cohens_d"]


@dataclass(frozen=True)
class RunSettings:
    """Everything that determines a simulation run apart from the lesion."""

    duration_ms: float
    n_trials: int
    base_seed: int
    stimulus: Stimulus | None

    def seeds(self) -> np.ndarray:
        return trial_seeds(self.base_seed, self.n_trials)

    def cache_key(self) -> tuple:
        stim_key: tuple = ()
        if self.stimulus is not None:
            s = self.stimulus
            stim_key = (
                tuple(int(t) for t in s.targets),
                s.profile,
                s.rate_hz,
                s.baseline_hz,
                s.start_ms,
                s.end_ms,
                s.mode,
                s.synaptic_weight_mv,
            )
        return (self.duration_ms, self.n_trials, self.base_seed, stim_key)


def group_metric(
    result: SimulationResult, indices: np.ndarray, metric: Metric, columns: np.ndarray
) -> np.ndarray:
    """One value per column for a neuron group."""
    if metric == "first_spike_ms":
        return group_first_spike(result, {"g": indices}, columns)["g"]
    counts = result.spike_counts()[indices][:, columns]
    if metric == "spike_count":
        return counts.sum(axis=0).astype(np.float64)
    duration_s = result.duration_ms / 1000.0
    if len(indices) == 0:
        return np.zeros(len(columns))
    return counts.mean(axis=0) / duration_s


def compare_metric(baseline: np.ndarray, lesion: np.ndarray, metric: Metric, seed: int = 0) -> dict:
    """Paired comparison; for latency only trials where both conditions responded are used."""
    responded_baseline = float(np.mean(np.isfinite(baseline)))
    responded_lesion = float(np.mean(np.isfinite(lesion)))
    if metric == "first_spike_ms":
        both = np.isfinite(baseline) & np.isfinite(lesion)
        baseline = baseline[both]
        lesion = lesion[both]
    row: dict = {
        "responded_baseline": responded_baseline,
        "responded_lesion": responded_lesion,
    }
    if len(baseline) < 2:
        row.update(
            {
                "n_trials": int(len(baseline)),
                "baseline_mean": _nanmean(baseline),
                "lesion_mean": _nanmean(lesion),
                "cohens_d": float("nan"),
                "comparison_valid": False,
            }
        )
        return row
    row.update(compare_paired(baseline, lesion, seed=seed).to_dict())
    row["comparison_valid"] = True
    return row


def _nanmean(values: np.ndarray) -> float:
    if len(values) == 0:
        return float("nan")
    return float(np.mean(values))


class BaselineCache:
    """Baseline results keyed by (network key, run settings)."""

    def __init__(self) -> None:
        self._store: dict[tuple, SimulationResult] = {}

    def get(self, network_key: tuple, network: LIFNetwork, settings: RunSettings) -> SimulationResult:
        key = (network_key, settings.cache_key())
        if key not in self._store:
            self._store[key] = network.run(settings.duration_ms, settings.seeds(), stimulus=settings.stimulus)
        return self._store[key]

    def __len__(self) -> int:
        return len(self._store)


@dataclass
class LesionOutcome:
    ablated: np.ndarray
    metrics: list[dict]
    bin_starts_ms: np.ndarray
    psth_baseline: dict[str, np.ndarray]
    psth_lesion: dict[str, np.ndarray]
    baseline: SimulationResult
    lesion: SimulationResult


def run_lesion(
    network: LIFNetwork,
    baseline: SimulationResult,
    settings: RunSettings,
    ablate: np.ndarray,
    groups: dict[str, np.ndarray],
    bin_ms: float = 10.0,
) -> LesionOutcome:
    """Run the lesion condition with the baseline's seeds and compare every metric per group."""
    alive = np.ones(network.n_neurons, dtype=bool)
    alive[np.asarray(ablate, dtype=np.int64)] = False
    lesion = network.run(settings.duration_ms, settings.seeds(), stimulus=settings.stimulus, alive=alive)
    columns = np.arange(settings.n_trials)
    rows: list[dict] = []
    for name, indices in groups.items():
        for metric in METRICS:
            base_values = group_metric(baseline, indices, metric, columns)
            lesion_values = group_metric(lesion, indices, metric, columns)
            row = compare_metric(base_values, lesion_values, metric)
            row["group"] = name
            row["metric"] = metric
            row["n_neurons"] = int(len(indices))
            row["n_ablated_in_group"] = int(np.isin(indices, ablate).sum())
            rows.append(row)
    bins, psth_base = psth(baseline, groups, bin_ms)
    _, psth_les = psth(lesion, groups, bin_ms)
    return LesionOutcome(
        ablated=np.asarray(ablate, dtype=np.int64),
        metrics=rows,
        bin_starts_ms=bins,
        psth_baseline=psth_base,
        psth_lesion=psth_les,
        baseline=baseline,
        lesion=lesion,
    )


@dataclass
class ScreenCandidate:
    label: str
    indices: np.ndarray


@dataclass
class ScreenOutcome:
    table: pd.DataFrame
    skipped: list[str] = field(default_factory=list)


def lesion_screen(
    network: LIFNetwork,
    baseline: SimulationResult,
    settings: RunSettings,
    candidates: list[ScreenCandidate],
    measure: np.ndarray,
    metric: Metric = "spike_count",
    rank_by: RankBy = "percent_change",
    max_columns: int = 200,
    progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ScreenOutcome:
    """Ablate each candidate on its own; rank by the effect on the measured group.

    Lesion conditions are batched as column groups (n_trials columns per condition) so
    one simulation loop handles many conditions. The baseline is computed once by the caller.
    """
    n_trials = settings.n_trials
    seeds = settings.seeds()
    columns = np.arange(n_trials)
    base_values = group_metric(baseline, measure, metric, columns)

    usable: list[ScreenCandidate] = []
    skipped: list[str] = []
    for candidate in candidates:
        if len(candidate.indices) == 0:
            skipped.append(candidate.label)
        elif np.isin(candidate.indices, measure).any():
            skipped.append(candidate.label)
        else:
            usable.append(candidate)

    per_batch = max(1, max_columns // n_trials)
    total = len(usable)
    rows: list[dict] = []
    if progress is not None:
        progress(0, total)
    for start in range(0, total, per_batch):
        if should_stop is not None and should_stop():
            break
        batch = usable[start : start + per_batch]
        n_cols = len(batch) * n_trials
        alive = np.ones((network.n_neurons, n_cols), dtype=bool)
        for slot, candidate in enumerate(batch):
            alive[candidate.indices, slot * n_trials : (slot + 1) * n_trials] = False
        batch_seeds = np.tile(seeds, len(batch))
        result = network.run(settings.duration_ms, batch_seeds, stimulus=settings.stimulus, alive=alive)
        for slot, candidate in enumerate(batch):
            cols = np.arange(slot * n_trials, (slot + 1) * n_trials)
            lesion_values = group_metric(result, measure, metric, cols)
            row = compare_metric(base_values, lesion_values, metric)
            row["label"] = candidate.label
            row["n_ablated"] = int(len(candidate.indices))
            rows.append(row)
        if progress is not None:
            progress(min(start + per_batch, total), total)

    table = pd.DataFrame(rows)
    if len(table) > 0:
        if rank_by == "cohens_d":
            key = table["cohens_d"].abs()
        else:
            key = table["percent_change"].abs()
        table = table.assign(_rank_key=key.fillna(-1.0))
        table = table.sort_values("_rank_key", ascending=False).drop(columns="_rank_key")
        table = table.reset_index(drop=True)
    return ScreenOutcome(table=table, skipped=skipped)
