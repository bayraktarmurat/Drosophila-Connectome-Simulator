"""Effect sizes and confidence intervals for baseline-vs-lesion comparisons.

Primary result: mean difference and Cohen's d, each with a percentile bootstrap 95% CI.
Trials are paired (same seed -> same stimulus in both conditions), so bootstrap resamples
trial indices jointly.

A p-value (Wilcoxon signed-rank) is reported only as a secondary number: with simulated
replicates it can be driven arbitrarily low just by running more trials, so it says little
about whether an effect is large or meaningful.
"""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats as scipy_stats

P_VALUE_NOTE = (
    "p-values from simulation replicates shrink with the number of trials alone; "
    "judge effects by Cohen's d and the confidence intervals."
)


@dataclass
class Comparison:
    baseline_mean: float
    baseline_std: float
    lesion_mean: float
    lesion_std: float
    mean_difference: float
    mean_difference_ci: tuple[float, float]
    percent_change: float
    cohens_d: float
    cohens_d_ci: tuple[float, float]
    p_value_wilcoxon: float
    n_trials: int

    def to_dict(self) -> dict:
        return asdict(self)


def cohens_d(baseline: np.ndarray, lesion: np.ndarray) -> float:
    """(lesion - baseline) / pooled SD, using the average of the two variances (d_av).

    If both groups have zero variance: 0 when the means are equal, +/-inf otherwise.
    """
    if len(baseline) < 2 or len(lesion) < 2:
        return float("nan")
    difference = float(np.mean(lesion) - np.mean(baseline))
    pooled = float(np.sqrt((np.var(baseline, ddof=1) + np.var(lesion, ddof=1)) / 2.0))
    if pooled > 0:
        return difference / pooled
    if difference == 0:
        return 0.0
    if difference > 0:
        return float("inf")
    return float("-inf")


def _vectorized_d(baseline_rows: np.ndarray, lesion_rows: np.ndarray, differences: np.ndarray) -> np.ndarray:
    """cohens_d applied row-wise (same zero-variance rules)."""
    n = baseline_rows.shape[1]
    if n < 2:
        return np.full(len(differences), np.nan)
    pooled = np.sqrt((baseline_rows.var(axis=1, ddof=1) + lesion_rows.var(axis=1, ddof=1)) / 2.0)
    result = np.zeros(len(differences))
    has_spread = pooled > 0
    result[has_spread] = differences[has_spread] / pooled[has_spread]
    no_spread = ~has_spread
    result[no_spread & (differences > 0)] = np.inf
    result[no_spread & (differences < 0)] = -np.inf
    return result


def percent_change(baseline_mean: float, lesion_mean: float) -> float:
    """Relative change in percent; NaN when the baseline is zero."""
    if baseline_mean == 0:
        if lesion_mean == 0:
            return 0.0
        return float("nan")
    return 100.0 * (lesion_mean - baseline_mean) / baseline_mean


def _percentile_ci(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return (float("nan"), float("nan"))
    return (float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5)))


def _wilcoxon(baseline: np.ndarray, lesion: np.ndarray) -> float:
    differences = lesion - baseline
    if np.allclose(differences, 0):
        return 1.0
    if len(differences) < 2:
        return float("nan")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = scipy_stats.wilcoxon(lesion, baseline, zero_method="zsplit")
    return float(result.pvalue)


def compare_paired(baseline: np.ndarray, lesion: np.ndarray, n_boot: int = 2000, seed: int = 0) -> Comparison:
    """Compare paired per-trial metric values from two conditions."""
    baseline = np.asarray(baseline, dtype=np.float64)
    lesion = np.asarray(lesion, dtype=np.float64)
    if baseline.shape != lesion.shape:
        raise ValueError("baseline and lesion must have the same number of paired trials")
    n_trials = len(baseline)
    rng = np.random.default_rng(seed)
    resample = rng.integers(0, n_trials, size=(n_boot, n_trials))
    boot_baseline = baseline[resample]
    boot_lesion = lesion[resample]
    boot_difference = boot_lesion.mean(axis=1) - boot_baseline.mean(axis=1)
    boot_d = _vectorized_d(boot_baseline, boot_lesion, boot_difference)

    baseline_mean = float(baseline.mean())
    lesion_mean = float(lesion.mean())
    return Comparison(
        baseline_mean=baseline_mean,
        baseline_std=float(baseline.std(ddof=1)),
        lesion_mean=lesion_mean,
        lesion_std=float(lesion.std(ddof=1)),
        mean_difference=lesion_mean - baseline_mean,
        mean_difference_ci=_percentile_ci(boot_difference),
        percent_change=percent_change(baseline_mean, lesion_mean),
        cohens_d=cohens_d(baseline, lesion),
        cohens_d_ci=_percentile_ci(boot_d),
        p_value_wilcoxon=_wilcoxon(baseline, lesion),
        n_trials=n_trials,
    )
