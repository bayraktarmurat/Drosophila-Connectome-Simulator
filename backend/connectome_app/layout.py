"""2-D graph layout: force-directed, with x pulled toward the neuron's signal-flow depth.

Signal-flow depth = hops from the inputs minus hops to the outputs, so inputs sit on the
left, motor neurons on the right, and activity in the animation visibly travels across.
Computed once (scripts/compute_layout.py) and cached as data/<name>/layout.parquet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp

from connectome_app.data import ROLE_HUB, ROLE_INPUT, ROLE_OUTPUT, Circuit

LAYOUT_FILE = "layout.parquet"


def flow_depth(circuit: Circuit) -> np.ndarray:
    """Target x per neuron in [-1, 1]: inputs -1, outputs +1, hubs from their hop distances."""
    neurons = circuit.neurons
    depth = np.zeros(circuit.n_neurons)
    if "dist_from_inputs" in neurons.columns and "dist_to_outputs" in neurons.columns:
        d_in = pd.to_numeric(neurons["dist_from_inputs"], errors="coerce").to_numpy(dtype=float)
        d_out = pd.to_numeric(neurons["dist_to_outputs"], errors="coerce").to_numpy(dtype=float)
        known = np.isfinite(d_in) & np.isfinite(d_out) & ((d_in + d_out) > 0)
        depth[known] = d_in[known] / (d_in[known] + d_out[known]) * 2.0 - 1.0
    roles = neurons["role"].to_numpy()
    depth[roles == ROLE_INPUT] = -1.0
    depth[roles == ROLE_OUTPUT] = 1.0
    hub = roles == ROLE_HUB
    depth[hub] = np.clip(depth[hub], -0.3, 0.3)
    return depth


def compute_layout(
    circuit: Circuit,
    iterations: int = 150,
    flow_strength: float = 0.15,
    seed: int = 0,
    chunk: int = 512,
) -> pd.DataFrame:
    """Return a DataFrame with body_id, x, y."""
    n = circuit.n_neurons
    rng = np.random.default_rng(seed)
    target_x = flow_depth(circuit) * np.sqrt(n) * 2.0
    positions = np.column_stack([target_x + rng.normal(0, 1, n), rng.normal(0, np.sqrt(n), n)])

    symmetric = sp.csr_matrix(circuit.weights + circuit.weights.T).tocoo()
    upper = symmetric.row < symmetric.col
    rows = symmetric.row[upper]
    cols = symmetric.col[upper]
    attraction = np.log1p(symmetric.data[upper])
    degree = np.bincount(np.concatenate([rows, cols]), minlength=n).astype(float) + 1.0

    repulsion_scale = 1.0
    gravity = 0.5
    step = 1.0
    for iteration in range(iterations):
        forces = np.zeros_like(positions)
        for start in range(0, n, chunk):
            block = positions[start : start + chunk]
            delta = block[:, None, :] - positions[None, :, :]
            dist2 = np.einsum("ijk,ijk->ij", delta, delta) + 1e-2
            mass = degree[start : start + chunk, None] * degree[None, :]
            strength = repulsion_scale * mass / dist2
            forces[start : start + chunk] += np.einsum("ij,ijk->ik", strength, delta)
        edge_delta = positions[cols] - positions[rows]
        pull = edge_delta * attraction[:, None]
        np.add.at(forces, rows, pull)
        np.add.at(forces, cols, -pull)
        forces -= gravity * positions * degree[:, None] / np.sqrt(n)
        forces[:, 0] += flow_strength * degree * (target_x - positions[:, 0])

        magnitude = np.linalg.norm(forces, axis=1, keepdims=True) + 1e-9
        max_move = step * (1.0 - iteration / iterations) * np.sqrt(n) * 0.05 + 0.05
        positions += forces / magnitude * np.minimum(magnitude / degree[:, None], max_move)

    positions -= positions.mean(axis=0)
    scale = np.abs(positions).max()
    if scale > 0:
        positions /= scale
    return pd.DataFrame({"body_id": circuit.body_ids, "x": positions[:, 0], "y": positions[:, 1]})


def load_or_flow_layout(circuit: Circuit) -> pd.DataFrame:
    """Cached layout if present (and matching), else a quick flow layout without forces."""
    path = circuit.config.data_dir() / LAYOUT_FILE
    if path.exists():
        layout = pd.read_parquet(path)
        if len(layout) == circuit.n_neurons and set(layout["body_id"]) == set(circuit.body_ids.tolist()):
            return layout.set_index("body_id").loc[circuit.body_ids].reset_index()
    rng = np.random.default_rng(0)
    x = flow_depth(circuit) + rng.normal(0, 0.05, circuit.n_neurons)
    y = rng.uniform(-1, 1, circuit.n_neurons)
    return pd.DataFrame({"body_id": circuit.body_ids, "x": x, "y": y})
