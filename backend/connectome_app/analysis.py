"""Summaries of simulation output: rates, first-spike latency, per-type PSTHs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from connectome_app.lif import SimulationResult


def _column_selection(result: SimulationResult, columns: np.ndarray | None) -> np.ndarray:
    if columns is None:
        return np.arange(result.n_columns)
    return np.asarray(columns, dtype=np.int64)


def rates_hz(result: SimulationResult) -> np.ndarray:
    """Mean firing rate per (neuron, column) over the whole run."""
    duration_s = result.duration_ms / 1000.0
    return result.spike_counts() / duration_s


def group_rates(
    result: SimulationResult, groups: dict[str, np.ndarray], columns: np.ndarray | None = None
) -> dict[str, np.ndarray]:
    """Mean rate of each neuron group, one value per selected column (trial)."""
    cols = _column_selection(result, columns)
    rates = rates_hz(result)[:, cols]
    out: dict[str, np.ndarray] = {}
    for name, indices in groups.items():
        if len(indices) == 0:
            out[name] = np.zeros(len(cols))
        else:
            out[name] = rates[indices].mean(axis=0)
    return out


def group_first_spike(
    result: SimulationResult, groups: dict[str, np.ndarray], columns: np.ndarray | None = None
) -> dict[str, np.ndarray]:
    """Earliest spike of any neuron in each group, per selected column (NaN if silent)."""
    cols = _column_selection(result, columns)
    first = result.first_spike_ms()[:, cols]
    out: dict[str, np.ndarray] = {}
    for name, indices in groups.items():
        values = np.full(len(cols), np.nan)
        if len(indices) > 0:
            subset = first[indices]
            has_spike = ~np.all(np.isnan(subset), axis=0)
            values[has_spike] = np.nanmin(subset[:, has_spike], axis=0)
        out[name] = values
    return out


def type_rate_table(
    result: SimulationResult, neurons: pd.DataFrame, columns: np.ndarray | None = None
) -> pd.DataFrame:
    """Per cell type: neuron count, mean rate (over neurons and trials), std over trials."""
    cols = _column_selection(result, columns)
    rates = rates_hz(result)[:, cols]
    frame = pd.DataFrame(
        {
            "type": neurons["type"].to_numpy(),
            "role": neurons["role"].to_numpy(),
            "mean_rate": rates.mean(axis=1),
            "active": (rates > 0).any(axis=1),
        }
    )
    per_trial = pd.DataFrame(rates, columns=[f"c{c}" for c in range(len(cols))])
    per_trial["type"] = frame["type"].to_numpy()
    trial_means = per_trial.groupby("type").mean()
    summary = frame.groupby("type").agg(
        role=("role", "first"),
        n_neurons=("mean_rate", "size"),
        mean_rate_hz=("mean_rate", "mean"),
        fraction_active=("active", "mean"),
    )
    summary["std_over_trials_hz"] = trial_means.std(axis=1, ddof=0)
    return summary.reset_index().sort_values("mean_rate_hz", ascending=False)


def psth(
    result: SimulationResult,
    groups: dict[str, np.ndarray],
    bin_ms: float = 10.0,
    columns: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Population rate (Hz per neuron) in time bins, averaged over the selected columns.

    Returns (bin_start_ms, {group: rate array of length n_bins}).
    """
    cols = _column_selection(result, columns)
    n_bins = int(np.ceil(result.duration_ms / bin_ms))
    edges_ms = np.arange(n_bins) * bin_ms
    in_cols = np.isin(result.spike_columns, cols)
    bins_of_spike = (result.spike_times_ms // bin_ms).astype(np.int64)
    out: dict[str, np.ndarray] = {}
    for name, indices in groups.items():
        if len(indices) == 0:
            out[name] = np.zeros(n_bins)
            continue
        member = np.isin(result.spike_neurons, indices) & in_cols
        counts = np.bincount(bins_of_spike[member], minlength=n_bins)[:n_bins]
        out[name] = counts / (len(indices) * len(cols) * bin_ms / 1000.0)
    return edges_ms, out
