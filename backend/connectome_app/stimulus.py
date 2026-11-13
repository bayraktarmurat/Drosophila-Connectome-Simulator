"""External stimulus: time-varying Poisson spike trains onto chosen input neurons."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

ProfileName = Literal["constant", "step", "ramp"]
StimulusMode = Literal["spikes", "synaptic"]


@dataclass(frozen=True)
class Stimulus:
    """Poisson drive onto `targets` (matrix indices).

    profile:
      constant: `rate_hz` for the whole run.
      step:     `baseline_hz`, then `rate_hz` from `start_ms` to `end_ms`, then baseline.
      ramp:     linear rise from `baseline_hz` at `start_ms` to `rate_hz` at `end_ms`
                (a looming-like stimulus), then back to baseline.
    mode:
      spikes:   each Poisson event makes the target neuron spike directly (if not refractory).
      synaptic: each Poisson event adds `synaptic_weight_mv` to the target's synaptic variable g.
    """

    targets: np.ndarray
    profile: ProfileName = "ramp"
    rate_hz: float = 100.0
    baseline_hz: float = 0.0
    start_ms: float = 0.0
    end_ms: float | None = None
    mode: StimulusMode = "spikes"
    synaptic_weight_mv: float = 10.0


def rate_profile(stimulus: Stimulus, n_steps: int, dt_ms: float) -> np.ndarray:
    """Rate in Hz at every time step."""
    times = np.arange(n_steps, dtype=np.float64) * dt_ms
    end_ms = stimulus.end_ms
    if end_ms is None:
        end_ms = n_steps * dt_ms
    rates = np.full(n_steps, stimulus.baseline_hz, dtype=np.float64)
    active = (times >= stimulus.start_ms) & (times < end_ms)

    if stimulus.profile == "constant":
        rates[:] = stimulus.rate_hz
    elif stimulus.profile == "step":
        rates[active] = stimulus.rate_hz
    elif stimulus.profile == "ramp":
        span = max(end_ms - stimulus.start_ms, dt_ms)
        fraction = (times[active] - stimulus.start_ms) / span
        rates[active] = stimulus.baseline_hz + fraction * (stimulus.rate_hz - stimulus.baseline_hz)
    else:
        raise ValueError(f"Unknown stimulus profile: {stimulus.profile}")

    if np.any(rates < 0):
        raise ValueError("Stimulus rates must be non-negative")
    return rates


def poisson_events(rates_hz: np.ndarray, n_targets: int, dt_ms: float, seed: int) -> np.ndarray:
    """Boolean array (n_steps, n_targets): True where a Poisson event occurs."""
    probability = rates_hz * dt_ms / 1000.0
    if np.any(probability > 1.0):
        raise ValueError("rate * dt exceeds 1: lower the rate or the time step")
    rng = np.random.default_rng(seed)
    draws = rng.random((len(rates_hz), n_targets), dtype=np.float32)
    return draws < probability[:, None].astype(np.float32)
