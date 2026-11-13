"""Shared fixtures: a tiny synthetic circuit written to a temp directory."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from connectome_app.config import CircuitConfig

SYNTHETIC_CONFIG: dict = {
    "name": "synthetic",
    "neuprint": {"server": "https://example.invalid", "dataset": "none"},
    "selection": {"inputs": ["LCa"], "hubs": ["GF"], "outputs": ["MN"]},
    "signs": {
        "nt_sign": {
            "acetylcholine": 1,
            "gaba": -1,
            "glutamate": -1,
            "dopamine": 0,
        },
        "use_celltype_fallback": True,
        "min_celltype_confidence": 0.5,
        "default_sign": 1,
        "type_overrides": {},
    },
    "extra_edges": {
        "enabled": False,
        "edges": [
            {
                "pre_type": "GF",
                "post_type": "MN",
                "pairing": "strongest_chemical",
                "synapse_equivalent": 50,
                "source_key": "test",
            }
        ],
    },
}

# body_id, type, side, consensus_nt, celltype_nt, celltype_conf
NEURON_ROWS = [
    (1, "LCa", "L", "acetylcholine", "acetylcholine", 0.9),
    (2, "LCa", "R", "acetylcholine", "acetylcholine", 0.9),
    (10, "GF", "L", "acetylcholine", "acetylcholine", 0.9),
    (11, "GF", "R", "acetylcholine", "acetylcholine", 0.9),
    (20, "MN", "L", "glutamate", "glutamate", 0.9),
    (21, "MN", "R", "glutamate", "glutamate", 0.9),
    (30, "INH", "L", "gaba", "gaba", 0.9),
    (40, "UNC1", "L", "unclear", "gaba", 0.9),
    (50, "UNC2", "R", "unclear", None, None),
    (60, "DA", "L", "dopamine", "dopamine", 0.9),
]

# pre, post, weight
EDGE_ROWS = [
    (1, 10, 5),
    (2, 11, 7),
    (10, 20, 3),
    (11, 21, 4),
    (30, 10, 2),
    (40, 20, 1),
    (50, 30, 6),
    (60, 11, 9),
]


def make_neurons() -> pd.DataFrame:
    records = []
    for body_id, cell_type, side, nt, ct_nt, ct_conf in NEURON_ROWS:
        records.append(
            {
                "body_id": body_id,
                "type": cell_type,
                "soma_side": side,
                "consensus_nt": nt,
                "celltype_predicted_nt": ct_nt,
                "celltype_predicted_nt_confidence": ct_conf,
                "total_post": 100,
                "total_pre": 100,
            }
        )
    return pd.DataFrame.from_records(records)


def make_edges() -> pd.DataFrame:
    records = []
    for pre, post, weight in EDGE_ROWS:
        records.append({"pre_id": pre, "post_id": post, "weight": weight, "weight_hp": weight})
    return pd.DataFrame.from_records(records)


@pytest.fixture()
def synthetic_config() -> CircuitConfig:
    return CircuitConfig.model_validate(SYNTHETIC_CONFIG)


@pytest.fixture()
def synthetic_dir(tmp_path: Path) -> Path:
    make_neurons().to_parquet(tmp_path / "neurons.parquet", index=False)
    make_edges().to_parquet(tmp_path / "edges.parquet", index=False)
    return tmp_path
