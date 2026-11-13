"""Vectorized leaky integrate-and-fire network on a sparse connectome.

Model (per neuron i, per trial column b):
    dv/dt = (-(v - v_rest) + g + bias) / tau_m          (Euler, step dt)
    g decays exponentially with tau_syn
    a presynaptic spike of neuron j adds  w_syn * W[i, j] * sign[j]  to g_i after `delay`
    v >= v_threshold -> spike, v = v_reset, no integration for `refractory` ms

State arrays are (N, B): B columns run in lockstep. A column is one trial (one random
seed) under one condition (one lesion mask), so multi-trial runs and baseline-vs-lesion
comparisons share a single loop.

Spike delivery: the per-step spike pattern is stored in a ring buffer of spike events
(length = max delay in steps). When a step's spikes "arrive", only the columns of W that
belong to neurons that spiked are sliced (CSC format makes this cheap) and multiplied with
the small dense spike matrix.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp

from connectome_app.config import SimulationConfig
from connectome_app.data import Circuit
from connectome_app.stimulus import Stimulus, poisson_events, rate_profile

DTYPE = np.float32


@dataclass
class SimulationResult:
    """Spikes as three parallel arrays plus optional voltage traces."""

    spike_steps: np.ndarray
    spike_neurons: np.ndarray
    spike_columns: np.ndarray
    n_neurons: int
    n_columns: int
    n_steps: int
    dt_ms: float
    column_seeds: np.ndarray
    record_indices: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    voltage: np.ndarray | None = None

    @property
    def duration_ms(self) -> float:
        return self.n_steps * self.dt_ms

    @property
    def spike_times_ms(self) -> np.ndarray:
        return self.spike_steps.astype(np.float64) * self.dt_ms

    def spike_counts(self) -> np.ndarray:
        """Spike count per (neuron, column)."""
        flat = self.spike_neurons.astype(np.int64) * self.n_columns + self.spike_columns
        counts = np.bincount(flat, minlength=self.n_neurons * self.n_columns)
        return counts.reshape(self.n_neurons, self.n_columns)

    def first_spike_ms(self) -> np.ndarray:
        """Time of the first spike per (neuron, column); NaN if the neuron never spiked."""
        first = np.full((self.n_neurons, self.n_columns), np.inf)
        np.minimum.at(first, (self.spike_neurons, self.spike_columns), self.spike_times_ms)
        first[np.isinf(first)] = np.nan
        return first


@dataclass(frozen=True)
class LIFParams:
    """Numerical parameters, converted from the config into per-step quantities."""

    dt_ms: float
    tau_m_ms: float
    v_rest_mv: float
    v_reset_mv: float
    v_threshold_mv: float
    refractory_steps: int
    tau_syn_ms: float
    w_syn_mv: float
    delay_steps: int
    electrical_delay_steps: int

    @classmethod
    def from_config(cls, config: SimulationConfig) -> LIFParams:
        dt = config.dt_ms
        delay_steps = max(1, int(round(config.delay_ms / dt)))
        electrical_steps = max(1, int(round(config.electrical_delay_ms / dt)))
        return cls(
            dt_ms=dt,
            tau_m_ms=config.tau_m_ms,
            v_rest_mv=config.v_rest_mv,
            v_reset_mv=config.v_reset_mv,
            v_threshold_mv=config.v_threshold_mv,
            refractory_steps=int(round(config.refractory_ms / dt)),
            tau_syn_ms=config.tau_syn_ms,
            w_syn_mv=config.w_syn_mv,
            delay_steps=delay_steps,
            electrical_delay_steps=electrical_steps,
        )


class LIFNetwork:
    """A LIF network defined by a signed sparse weight matrix (post x pre)."""

    def __init__(
        self,
        signed_weights: sp.spmatrix,
        params: LIFParams,
        electrical_weights: sp.spmatrix | None = None,
    ) -> None:
        n_post, n_pre = signed_weights.shape
        if n_post != n_pre:
            raise ValueError("Weight matrix must be square (post x pre)")
        self.n_neurons = n_post
        self.params = params
        # Pre-scale by w_syn so a spike adds mV directly to g. CSC: fast column slicing.
        self.chemical = sp.csc_matrix(signed_weights * params.w_syn_mv, dtype=DTYPE)
        self.electrical: sp.csc_matrix | None = None
        if electrical_weights is not None and electrical_weights.nnz > 0:
            self.electrical = sp.csc_matrix(electrical_weights * params.w_syn_mv, dtype=DTYPE)

    @classmethod
    def from_circuit(
        cls,
        circuit: Circuit,
        params: LIFParams | None = None,
        use_extra_edges: bool = False,
    ) -> LIFNetwork:
        """Build the network from a loaded circuit (optionally with electrical extra edges)."""
        if params is None:
            params = LIFParams.from_config(circuit.config.simulation)
        electrical = None
        if use_extra_edges and len(circuit.extra_edges) > 0:
            extra = circuit.extra_edges
            electrical = sp.coo_matrix(
                (
                    extra["synapse_equivalent"].to_numpy(dtype=np.float64),
                    (
                        extra["post_index"].to_numpy(dtype=np.int64),
                        extra["pre_index"].to_numpy(dtype=np.int64),
                    ),
                ),
                shape=(circuit.n_neurons, circuit.n_neurons),
            )
        return cls(circuit.signed_weights(), params, electrical)

    def run(
        self,
        duration_ms: float,
        column_seeds: list[int] | np.ndarray,
        stimulus: Stimulus | None = None,
        alive: np.ndarray | None = None,
        bias_mv: np.ndarray | float = 0.0,
        record_indices: np.ndarray | list[int] | None = None,
    ) -> SimulationResult:
        """Simulate all columns in lockstep.

        column_seeds: one random seed per column; columns with equal seeds get identical
            stimulus spike trains (used for baseline-vs-lesion comparisons).
        alive: (N, B) or (N,) boolean; False = ablated neuron (never spikes).
        bias_mv: constant drive added to dv/dt, scalar or (N,) or (N, B).
        record_indices: neurons whose membrane voltage is stored every step.
        """
        p = self.params
        n = self.n_neurons
        seeds = np.asarray(column_seeds, dtype=np.int64)
        n_cols = len(seeds)
        n_steps = int(round(duration_ms / p.dt_ms))

        alive_mask = self._alive_mask(alive, n, n_cols)
        bias = self._bias_array(bias_mv, n, n_cols)
        events, seed_of_column, targets = self._stimulus_events(stimulus, seeds, n_steps)

        if record_indices is None:
            record = np.zeros(0, dtype=np.int64)
        else:
            record = np.asarray(record_indices, dtype=np.int64)
        voltage: np.ndarray | None = None
        if len(record) > 0:
            voltage = np.zeros((n_steps, len(record), n_cols), dtype=DTYPE)

        v = np.full((n, n_cols), p.v_rest_mv, dtype=DTYPE)
        g = np.zeros((n, n_cols), dtype=DTYPE)
        refractory = np.zeros((n, n_cols), dtype=np.int32)
        decay = DTYPE(np.exp(-p.dt_ms / p.tau_syn_ms))
        alpha = DTYPE(p.dt_ms / p.tau_m_ms)
        v_rest = DTYPE(p.v_rest_mv)
        v_reset = DTYPE(p.v_reset_mv)
        v_thr = DTYPE(p.v_threshold_mv)

        ring_length = max(p.delay_steps, p.electrical_delay_steps) + 1
        ring: list[tuple[np.ndarray, np.ndarray] | None] = [None] * ring_length

        steps_out: list[np.ndarray] = []
        neurons_out: list[np.ndarray] = []
        columns_out: list[np.ndarray] = []

        for step in range(n_steps):
            g *= decay
            self._deliver(ring, step - p.delay_steps, ring_length, self.chemical, g)
            if self.electrical is not None:
                self._deliver(ring, step - p.electrical_delay_steps, ring_length, self.electrical, g)

            stim_now: np.ndarray | None = None
            if events is not None:
                stim_now = events[seed_of_column, step, :].T
                if stimulus is not None and stimulus.mode == "synaptic":
                    g[targets, :] += DTYPE(stimulus.synaptic_weight_mv) * stim_now

            free = refractory == 0
            dv = alpha * (v_rest - v + g + bias)
            v += dv * free

            spikes = (v >= v_thr) & alive_mask
            if stim_now is not None and stimulus is not None and stimulus.mode == "spikes":
                forced = stim_now & free[targets, :] & alive_mask[targets, :]
                spikes[targets, :] |= forced

            np.subtract(refractory, 1, out=refractory, where=refractory > 0)
            if spikes.any():
                v[spikes] = v_reset
                refractory[spikes] = p.refractory_steps
                rows, cols = np.nonzero(spikes)
                steps_out.append(np.full(len(rows), step, dtype=np.int32))
                neurons_out.append(rows.astype(np.int32))
                columns_out.append(cols.astype(np.int32))
                active = np.unique(rows)
                ring[step % ring_length] = (active, spikes[active].astype(DTYPE))
            else:
                ring[step % ring_length] = None

            if voltage is not None:
                voltage[step] = v[record]

        return SimulationResult(
            spike_steps=self._concat(steps_out),
            spike_neurons=self._concat(neurons_out),
            spike_columns=self._concat(columns_out),
            n_neurons=n,
            n_columns=n_cols,
            n_steps=n_steps,
            dt_ms=p.dt_ms,
            column_seeds=seeds,
            record_indices=record,
            voltage=voltage,
        )

    @staticmethod
    def _deliver(
        ring: list[tuple[np.ndarray, np.ndarray] | None],
        source_step: int,
        ring_length: int,
        weights: sp.csc_matrix,
        g: np.ndarray,
    ) -> None:
        """Add the effect of the spikes emitted at `source_step` to g."""
        if source_step < 0:
            return
        entry = ring[source_step % ring_length]
        if entry is None:
            return
        active, pattern = entry
        g += weights[:, active] @ pattern

    @staticmethod
    def _alive_mask(alive: np.ndarray | None, n: int, n_cols: int) -> np.ndarray:
        if alive is None:
            return np.ones((n, n_cols), dtype=bool)
        mask = np.asarray(alive, dtype=bool)
        if mask.ndim == 1:
            mask = np.repeat(mask[:, None], n_cols, axis=1)
        if mask.shape != (n, n_cols):
            raise ValueError(f"alive mask must be ({n},) or ({n}, {n_cols})")
        return mask

    @staticmethod
    def _bias_array(bias_mv: np.ndarray | float, n: int, n_cols: int) -> np.ndarray:
        bias = np.asarray(bias_mv, dtype=DTYPE)
        if bias.ndim == 1:
            bias = bias[:, None]
        return np.ascontiguousarray(np.broadcast_to(bias, (n, n_cols)))

    def _stimulus_events(
        self, stimulus: Stimulus | None, seeds: np.ndarray, n_steps: int
    ) -> tuple[np.ndarray | None, np.ndarray, np.ndarray]:
        """Pre-draw Poisson events once per unique seed: (n_unique, n_steps, n_targets)."""
        unique_seeds, seed_of_column = np.unique(seeds, return_inverse=True)
        if stimulus is None or len(stimulus.targets) == 0:
            return None, seed_of_column, np.zeros(0, dtype=np.int64)
        targets = np.asarray(stimulus.targets, dtype=np.int64)
        rates = rate_profile(stimulus, n_steps, self.params.dt_ms)
        events = np.zeros((len(unique_seeds), n_steps, len(targets)), dtype=bool)
        for k, seed in enumerate(unique_seeds):
            events[k] = poisson_events(rates, len(targets), self.params.dt_ms, int(seed))
        return events, seed_of_column, targets

    @staticmethod
    def _concat(parts: list[np.ndarray]) -> np.ndarray:
        if not parts:
            return np.zeros(0, dtype=np.int32)
        return np.concatenate(parts)


def trial_seeds(base_seed: int, n_trials: int) -> np.ndarray:
    """Deterministic per-trial seeds derived from one base seed."""
    sequence = np.random.SeedSequence(base_seed)
    states = sequence.generate_state(n_trials, dtype=np.uint32)
    return states.astype(np.int64)
