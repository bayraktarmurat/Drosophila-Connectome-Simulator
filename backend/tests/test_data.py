"""Data layer: W matrix, id mapping, roles, signs, extra edges."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from connectome_app.config import CircuitConfig, load_config
from connectome_app.data import (
    ROLE_HUB,
    ROLE_INPUT,
    ROLE_INTERNEURON,
    ROLE_OUTPUT,
    build_weight_matrix,
    load_circuit,
)
from connectome_app.signs import SOURCE_CELLTYPE, SOURCE_CONSENSUS, SOURCE_DEFAULT, SOURCE_OVERRIDE
from tests.conftest import EDGE_ROWS, NEURON_ROWS

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_matrix_shape_matches_metadata(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    n = len(NEURON_ROWS)
    assert circuit.weights.shape == (n, n)
    assert circuit.weights_csc.shape == (n, n)
    assert circuit.n_neurons == n
    assert circuit.weights.nnz == len(EDGE_ROWS)


def test_matrix_entries_are_post_by_pre(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    for pre, post, weight in EDGE_ROWS:
        row = circuit.index_of(post)
        col = circuit.index_of(pre)
        assert circuit.weights[row, col] == weight
    assert (circuit.weights != circuit.weights_csc).nnz == 0


def test_no_nans(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    assert not np.isnan(circuit.weights.data).any()
    assert not circuit.neurons[["body_id", "type", "role", "sign", "sign_source"]].isna().any().any()


def test_id_mapping_is_bijective(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    body_ids = circuit.body_ids
    assert len(set(body_ids.tolist())) == len(body_ids)
    for index, body_id in enumerate(body_ids):
        assert circuit.index_of(int(body_id)) == index
    assert sorted(circuit.body_to_index.values()) == list(range(circuit.n_neurons))
    with pytest.raises(KeyError):
        circuit.index_of(999999)


def test_roles(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    role_by_type = dict(zip(circuit.neurons["type"], circuit.neurons["role"]))
    assert role_by_type["LCa"] == ROLE_INPUT
    assert role_by_type["GF"] == ROLE_HUB
    assert role_by_type["MN"] == ROLE_OUTPUT
    assert role_by_type["INH"] == ROLE_INTERNEURON


def test_sign_resolution_order(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    table = circuit.neurons.set_index("type")
    assert table.loc["INH", "sign"] == -1
    assert table.loc["INH", "sign_source"] == SOURCE_CONSENSUS
    assert table.loc["UNC1", "sign"] == -1
    assert table.loc["UNC1", "sign_source"] == SOURCE_CELLTYPE
    assert table.loc["UNC2", "sign"] == 1
    assert table.loc["UNC2", "sign_source"] == SOURCE_DEFAULT
    assert table.loc["DA", "sign"] == 0
    assert set(np.unique(circuit.signs).tolist()) <= {-1, 0, 1}
    assert any("default_sign" in w for w in circuit.warnings)


def test_type_override_wins(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    raw = synthetic_config.model_dump()
    raw["signs"]["type_overrides"] = {"INH": 1}
    circuit = load_circuit(CircuitConfig.model_validate(raw), synthetic_dir)
    row = circuit.neurons.set_index("type").loc["INH"]
    assert row["sign"] == 1
    assert row["sign_source"] == SOURCE_OVERRIDE


def test_missing_nt_column_warns_loudly(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    neurons = pd.read_parquet(synthetic_dir / "neurons.parquet")
    neurons = neurons.drop(columns=["consensus_nt"])
    neurons.to_parquet(synthetic_dir / "neurons.parquet", index=False)
    circuit = load_circuit(synthetic_config, synthetic_dir)
    assert any("NO NEUROTRANSMITTER PREDICTIONS" in w for w in circuit.warnings)


def test_signed_weights_flip_inhibitory_columns(
    synthetic_config: CircuitConfig, synthetic_dir: Path
) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    signed = circuit.signed_weights()
    inh = circuit.index_of(30)
    gf = circuit.index_of(10)
    assert signed[gf, inh] == -2
    dopamine = circuit.index_of(60)
    assert signed[circuit.index_of(11), dopamine] == 0


def test_extra_edges_pair_by_strongest_chemical(
    synthetic_config: CircuitConfig, synthetic_dir: Path
) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    pairs = set(zip(circuit.extra_edges["pre_index"], circuit.extra_edges["post_index"]))
    expected = {
        (circuit.index_of(10), circuit.index_of(20)),
        (circuit.index_of(11), circuit.index_of(21)),
    }
    assert pairs == expected


def test_duplicate_edges_are_summed() -> None:
    edges = pd.DataFrame({"pre_id": [1, 1], "post_id": [2, 2], "weight": [3, 4]})
    matrix = build_weight_matrix(edges, {1: 0, 2: 1}, 2)
    assert matrix[1, 0] == 7
    assert matrix.nnz == 1


def test_unknown_edge_endpoint_raises() -> None:
    edges = pd.DataFrame({"pre_id": [1], "post_id": [99], "weight": [3]})
    with pytest.raises(ValueError):
        build_weight_matrix(edges, {1: 0}, 1)


def test_app_does_not_import_neuprint() -> None:
    code = (
        "import sys\n"
        "import connectome_app.data, connectome_app.config, connectome_app.signs\n"
        "if 'neuprint' in sys.modules:\n"
        "    sys.exit(1)\n"
    )
    env_path = str(PROJECT_ROOT / "backend")
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=env_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.cached
def test_cached_giant_fiber_circuit() -> None:
    config = load_config("giant_fiber")
    if not (config.data_dir() / "neurons.parquet").exists():
        pytest.skip("giant_fiber not fetched yet")
    circuit = load_circuit(config)
    assert circuit.n_neurons <= config.selection.max_neurons
    assert circuit.weights.shape == (circuit.n_neurons, circuit.n_neurons)
    assert not np.isnan(circuit.weights.data).any()
    assert len(circuit.indices_of_types(["DNp01"])) == 2
    assert len(circuit.indices_of_types(["TTMn"])) == 2
    assert len(circuit.indices_of_role(ROLE_INPUT)) > 0
    assert len(circuit.indices_of_role(ROLE_OUTPUT)) > 0
    assert circuit.neurons["total_post"].notna().all()
    assert len(circuit.extra_edges) == 4
