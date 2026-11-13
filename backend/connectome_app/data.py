"""Load a cached circuit: neuron table, sparse weight matrix W (post x pre), signs, extra edges.

The app never talks to neuPrint; it only reads files written by scripts/fetch_circuit.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

from connectome_app.config import CircuitConfig, ExtraEdgeSpec, SelectionConfig, load_config
from connectome_app.signs import resolve_signs

ROLE_INPUT = "input"
ROLE_HUB = "hub"
ROLE_OUTPUT = "output"
ROLE_INTERNEURON = "interneuron"

EXTRA_EDGE_COLUMNS = ["pre_index", "post_index", "synapse_equivalent", "kind", "source_key"]


@dataclass
class Circuit:
    """Everything the simulator, path finder and lesion code need about one circuit."""

    config: CircuitConfig
    neurons: pd.DataFrame
    weights: sp.csr_matrix
    weights_csc: sp.csc_matrix
    signs: np.ndarray
    extra_edges: pd.DataFrame
    manifest: dict
    warnings: list[str] = field(default_factory=list)
    body_to_index: dict[int, int] = field(default_factory=dict)

    @property
    def n_neurons(self) -> int:
        return len(self.neurons)

    @property
    def body_ids(self) -> np.ndarray:
        return self.neurons["body_id"].to_numpy()

    def index_of(self, body_id: int) -> int:
        """Matrix index for a neuPrint bodyId."""
        if body_id not in self.body_to_index:
            raise KeyError(f"bodyId {body_id} is not in circuit {self.config.name}")
        return self.body_to_index[body_id]

    def indices_of_types(self, types: list[str]) -> np.ndarray:
        """Matrix indices of all neurons whose type is in `types`."""
        mask = self.neurons["type"].isin(types).to_numpy()
        return np.flatnonzero(mask)

    def indices_of_role(self, role: str) -> np.ndarray:
        """Matrix indices of all neurons with the given role."""
        mask = (self.neurons["role"] == role).to_numpy()
        return np.flatnonzero(mask)

    def signed_weights(self) -> sp.csr_matrix:
        """W with each column (presynaptic neuron) multiplied by that neuron's sign."""
        scaled = self.weights @ sp.diags(self.signs.astype(np.float64))
        return sp.csr_matrix(scaled)


def assign_roles(neurons: pd.DataFrame, selection: SelectionConfig) -> pd.Series:
    """Role per neuron from the config's seed type lists (hub wins over input/output)."""
    roles: list[str] = []
    for cell_type in neurons["type"].tolist():
        if cell_type in selection.hubs:
            roles.append(ROLE_HUB)
        elif cell_type in selection.inputs:
            roles.append(ROLE_INPUT)
        elif cell_type in selection.outputs:
            roles.append(ROLE_OUTPUT)
        else:
            roles.append(ROLE_INTERNEURON)
    return pd.Series(roles, index=neurons.index, name="role")


def build_weight_matrix(
    edges: pd.DataFrame, body_to_index: dict[int, int], n_neurons: int
) -> sp.csr_matrix:
    """Sparse W with W[post, pre] = synapse count. Duplicate edges are summed."""
    pre_ids = edges["pre_id"].to_numpy()
    post_ids = edges["post_id"].to_numpy()
    unknown = set(pre_ids.tolist()) | set(post_ids.tolist())
    unknown = unknown - set(body_to_index)
    if unknown:
        raise ValueError(f"{len(unknown)} edge endpoints are missing from the neuron table")
    rows = np.fromiter((body_to_index[b] for b in post_ids), dtype=np.int64, count=len(post_ids))
    cols = np.fromiter((body_to_index[b] for b in pre_ids), dtype=np.int64, count=len(pre_ids))
    values = edges["weight"].to_numpy(dtype=np.float64)
    matrix = sp.coo_matrix((values, (rows, cols)), shape=(n_neurons, n_neurons))
    csr = matrix.tocsr()
    csr.sum_duplicates()
    return csr


def _pair_indices(
    spec: ExtraEdgeSpec,
    neurons: pd.DataFrame,
    weights: sp.csr_matrix,
    warnings: list[str],
) -> list[tuple[int, int]]:
    """Which (pre, post) neuron pairs an extra-edge spec connects."""
    pre_idx = np.flatnonzero((neurons["type"] == spec.pre_type).to_numpy())
    post_idx = np.flatnonzero((neurons["type"] == spec.post_type).to_numpy())
    if len(pre_idx) == 0 or len(post_idx) == 0:
        warnings.append(
            f"extra edge {spec.pre_type}->{spec.post_type}: type missing from circuit; skipped"
        )
        return []
    sides = neurons["soma_side"].to_numpy()
    pairs: list[tuple[int, int]] = []
    for pre in pre_idx:
        if spec.pairing == "all":
            for post in post_idx:
                pairs.append((int(pre), int(post)))
            continue
        if spec.pairing == "strongest_chemical":
            strengths = np.asarray(weights[post_idx, pre].todense()).ravel()
            if strengths.max() > 0:
                pairs.append((int(pre), int(post_idx[int(np.argmax(strengths))])))
                continue
            warnings.append(
                f"extra edge {spec.pre_type}->{spec.post_type}: no chemical partner for "
                f"index {int(pre)}; falling back to same-side pairing"
            )
        for post in post_idx:
            if sides[post] == sides[pre]:
                pairs.append((int(pre), int(post)))
    return pairs


def resolve_extra_edges(
    config: CircuitConfig, neurons: pd.DataFrame, weights: sp.csr_matrix, warnings: list[str]
) -> pd.DataFrame:
    """Expand the config's extra-edge specs into explicit neuron pairs (kept separate from W)."""
    records: list[dict] = []
    for spec in config.extra_edges.edges:
        for pre, post in _pair_indices(spec, neurons, weights, warnings):
            records.append(
                {
                    "pre_index": pre,
                    "post_index": post,
                    "synapse_equivalent": spec.synapse_equivalent,
                    "kind": spec.kind,
                    "source_key": spec.source_key,
                }
            )
    if not records:
        return pd.DataFrame(columns=EXTRA_EDGE_COLUMNS)
    return pd.DataFrame.from_records(records, columns=EXTRA_EDGE_COLUMNS)


def load_circuit(config: CircuitConfig | str, data_dir: Path | None = None) -> Circuit:
    """Load a cached circuit from parquet and build W, signs, roles and extra edges."""
    if isinstance(config, str):
        config = load_config(config)
    if data_dir is None:
        data_dir = config.data_dir()
    neurons_path = data_dir / "neurons.parquet"
    edges_path = data_dir / "edges.parquet"
    if not neurons_path.exists() or not edges_path.exists():
        raise FileNotFoundError(
            f"No cached data in {data_dir}. Run: python scripts/fetch_circuit.py --config {config.name}"
        )

    neurons = pd.read_parquet(neurons_path)
    edges = pd.read_parquet(edges_path)
    manifest: dict = {}
    manifest_path = data_dir / "manifest.json"
    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

    if neurons["body_id"].duplicated().any():
        raise ValueError("Duplicate body_id values in neurons.parquet")
    neurons = neurons.sort_values("body_id").reset_index(drop=True)
    neurons["type"] = neurons["type"].fillna("untyped")
    neurons["role"] = assign_roles(neurons, config.selection)

    body_ids = neurons["body_id"].astype(np.int64).tolist()
    body_to_index: dict[int, int] = {}
    for index, body_id in enumerate(body_ids):
        body_to_index[int(body_id)] = index

    weights = build_weight_matrix(edges, body_to_index, len(neurons))
    sign_result = resolve_signs(neurons, config.signs)
    neurons["sign"] = sign_result.signs
    neurons["sign_source"] = sign_result.sources

    warnings = list(sign_result.warnings)
    extra_edges = resolve_extra_edges(config, neurons, weights, warnings)

    return Circuit(
        config=config,
        neurons=neurons,
        weights=weights,
        weights_csc=weights.tocsc(),
        signs=sign_result.signs,
        extra_edges=extra_edges,
        manifest=manifest,
        warnings=warnings,
        body_to_index=body_to_index,
    )
