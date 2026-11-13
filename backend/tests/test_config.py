"""Config loading, inheritance and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from connectome_app.config import CircuitConfig, list_configs, load_config


def test_giant_fiber_config_loads() -> None:
    config = load_config("giant_fiber")
    assert config.name == "giant_fiber"
    assert config.selection.min_weight == 10
    assert "DNp01" in config.selection.hubs
    assert config.extra_edges.enabled is False


def test_lite_config_inherits_and_overrides() -> None:
    base = load_config("giant_fiber")
    lite = load_config("giant_fiber_lite")
    assert lite.name == "giant_fiber_lite"
    assert lite.selection.min_weight == 20
    assert lite.selection.edge_min_weight == 20
    assert lite.selection.outputs == base.selection.outputs
    assert lite.signs == base.signs
    assert lite.data_dir() != base.data_dir()


def test_all_configs_valid() -> None:
    names = list_configs()
    assert "giant_fiber" in names
    for name in names:
        load_config(name)


def test_unknown_key_rejected(synthetic_config: CircuitConfig) -> None:
    raw = synthetic_config.model_dump()
    raw["selection"]["min_wieght"] = 3
    with pytest.raises(ValidationError):
        CircuitConfig.model_validate(raw)


def test_circular_extends_rejected(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text("extends: b.yaml\n")
    (tmp_path / "b.yaml").write_text("extends: a.yaml\n")
    with pytest.raises(ValueError, match="Circular"):
        load_config(tmp_path / "a.yaml")
